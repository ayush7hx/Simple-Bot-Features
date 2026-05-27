import discord
from discord.ext import commands
import aiosqlite
import asyncio
import os
from collections import defaultdict
import time

DB_PATH = "db/antinuke.db"

action_tracker = defaultdict(list)


class AntiNuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._create_table())

    async def _create_table(self):
        os.makedirs("db", exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS antinuke_config (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER DEFAULT 0,
                    action TEXT DEFAULT 'ban',
                    threshold INTEGER DEFAULT 3,
                    log_channel_id INTEGER,
                    whitelist TEXT DEFAULT '[]'
                )
            """)
            await db.commit()

    async def _get_config(self, guild_id):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT * FROM antinuke_config WHERE guild_id = ?", (guild_id,)) as cursor:
                return await cursor.fetchone()

    async def _ensure_config(self, guild_id):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO antinuke_config (guild_id) VALUES (?)", (guild_id,))
            await db.commit()

    def _track_action(self, guild_id, user_id, action_type, threshold):
        key = (guild_id, user_id, action_type)
        now = time.time()
        action_tracker[key] = [t for t in action_tracker[key] if now - t < 10]
        action_tracker[key].append(now)
        return len(action_tracker[key]) >= threshold

    async def _punish(self, guild, member, action, reason):
        try:
            if action == "ban":
                await guild.ban(member, reason=f"AntiNuke: {reason}", delete_message_days=0)
            elif action == "kick":
                await guild.kick(member, reason=f"AntiNuke: {reason}")
            elif action == "timeout":
                until = discord.utils.utcnow() + __import__("datetime").timedelta(hours=1)
                await member.timeout(until, reason=f"AntiNuke: {reason}")
            elif action == "strip":
                danger_perms = ["administrator", "manage_guild", "ban_members", "kick_members", "manage_channels", "manage_roles"]
                safe_roles = [r for r in member.roles if r.name != "@everyone" and not any(getattr(r.permissions, p) for p in danger_perms)]
                await member.edit(roles=safe_roles, reason=f"AntiNuke: {reason}")
        except Exception as e:
            print(f"[AntiNuke] Could not punish {member}: {e}")

    async def _log(self, guild, config, title, description):
        log_ch_id = config[4] if config else None
        if log_ch_id:
            ch = guild.get_channel(log_ch_id)
            if ch:
                embed = discord.Embed(title=f"🛡️ AntiNuke: {title}", description=description, color=0xFF0000, timestamp=discord.utils.utcnow())
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

    def _is_whitelisted(self, config, user_id, guild):
        import json
        if not config:
            return False
        if user_id == guild.owner_id:
            return True
        try:
            wl = json.loads(config[5] or "[]")
            return user_id in wl
        except Exception:
            return False

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        config = await self._get_config(guild.id)
        if not config or not config[1]:
            return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            executor = entry.user
            if executor.bot or self._is_whitelisted(config, executor.id, guild):
                return
            threshold = config[3] or 3
            if self._track_action(guild.id, executor.id, "ban", threshold):
                member = guild.get_member(executor.id)
                if member:
                    await self._punish(guild, member, config[2] or "ban", "Mass Ban Detected")
                    await self._log(guild, config, "Mass Ban", f"{executor.mention} was actioned for mass-banning.")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = member.guild
        config = await self._get_config(guild.id)
        if not config or not config[1]:
            return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if entry.target.id != member.id:
                return
            executor = entry.user
            if executor.bot or self._is_whitelisted(config, executor.id, guild):
                return
            threshold = config[3] or 3
            if self._track_action(guild.id, executor.id, "kick", threshold):
                m = guild.get_member(executor.id)
                if m:
                    await self._punish(guild, m, config[2] or "ban", "Mass Kick Detected")
                    await self._log(guild, config, "Mass Kick", f"{executor.mention} was actioned for mass-kicking.")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        guild = channel.guild
        config = await self._get_config(guild.id)
        if not config or not config[1]:
            return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            executor = entry.user
            if executor.bot or self._is_whitelisted(config, executor.id, guild):
                return
            threshold = config[3] or 3
            if self._track_action(guild.id, executor.id, "chdel", threshold):
                m = guild.get_member(executor.id)
                if m:
                    await self._punish(guild, m, config[2] or "ban", "Mass Channel Delete Detected")
                    await self._log(guild, config, "Mass Channel Delete", f"{executor.mention} was actioned for mass channel deletion.")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        guild = role.guild
        config = await self._get_config(guild.id)
        if not config or not config[1]:
            return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            executor = entry.user
            if executor.bot or self._is_whitelisted(config, executor.id, guild):
                return
            threshold = config[3] or 3
            if self._track_action(guild.id, executor.id, "rldel", threshold):
                m = guild.get_member(executor.id)
                if m:
                    await self._punish(guild, m, config[2] or "ban", "Mass Role Delete Detected")
                    await self._log(guild, config, "Mass Role Delete", f"{executor.mention} was actioned for mass role deletion.")

    @commands.group(name="antinuke", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def antinuke_cmd(self, ctx):
        await self._ensure_config(ctx.guild.id)
        config = await self._get_config(ctx.guild.id)
        log_ch = ctx.guild.get_channel(config[4]) if config[4] else None
        embed = discord.Embed(title="🛡️ AntiNuke Config", color=0xFF0000)
        embed.add_field(name="Status", value="✅ Enabled" if config[1] else "❌ Disabled", inline=True)
        embed.add_field(name="Action", value=str(config[2]).capitalize(), inline=True)
        embed.add_field(name="Threshold", value=f"{config[3]} actions/10s", inline=True)
        embed.add_field(name="Log Channel", value=log_ch.mention if log_ch else "Not set", inline=True)
        embed.set_footer(text=f"Use {ctx.prefix}antinuke enable/disable | {ctx.prefix}antinuke action <ban/kick/timeout/strip>")
        await ctx.send(embed=embed)

    @antinuke_cmd.command(name="enable")
    @commands.has_permissions(administrator=True)
    async def antinuke_enable(self, ctx):
        await self._ensure_config(ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE antinuke_config SET enabled = 1 WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(description="✅ AntiNuke **enabled**! Your server is now protected.", color=0xFF0000))

    @antinuke_cmd.command(name="disable")
    @commands.has_permissions(administrator=True)
    async def antinuke_disable(self, ctx):
        await self._ensure_config(ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE antinuke_config SET enabled = 0 WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(description="❌ AntiNuke **disabled**.", color=0xFF0000))

    @antinuke_cmd.command(name="action")
    @commands.has_permissions(administrator=True)
    async def antinuke_action(self, ctx, action: str):
        valid = ["ban", "kick", "timeout", "strip"]
        if action not in valid:
            return await ctx.send(embed=discord.Embed(description=f"❌ Valid actions: {', '.join(valid)}", color=0xFF0000))
        await self._ensure_config(ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE antinuke_config SET action = ? WHERE guild_id = ?", (action, ctx.guild.id))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"✅ AntiNuke action set to **{action}**.", color=0xFF0000))

    @antinuke_cmd.command(name="threshold")
    @commands.has_permissions(administrator=True)
    async def antinuke_threshold(self, ctx, count: int):
        if count < 1 or count > 20:
            return await ctx.send(embed=discord.Embed(description="❌ Threshold must be between 1 and 20.", color=0xFF0000))
        await self._ensure_config(ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE antinuke_config SET threshold = ? WHERE guild_id = ?", (count, ctx.guild.id))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"✅ Threshold set to **{count}** actions in 10 seconds.", color=0xFF0000))

    @antinuke_cmd.command(name="logchannel")
    @commands.has_permissions(administrator=True)
    async def antinuke_logchannel(self, ctx, channel: discord.TextChannel):
        await self._ensure_config(ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE antinuke_config SET log_channel_id = ? WHERE guild_id = ?", (channel.id, ctx.guild.id))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"✅ AntiNuke logs will be sent to {channel.mention}", color=0xFF0000))

    @antinuke_cmd.command(name="whitelist")
    @commands.has_permissions(administrator=True)
    async def antinuke_whitelist(self, ctx, member: discord.Member):
        import json
        await self._ensure_config(ctx.guild.id)
        config = await self._get_config(ctx.guild.id)
        wl = json.loads(config[5] or "[]")
        if member.id in wl:
            wl.remove(member.id)
            msg = f"✅ {member.mention} removed from AntiNuke whitelist."
        else:
            wl.append(member.id)
            msg = f"✅ {member.mention} added to AntiNuke whitelist."
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE antinuke_config SET whitelist = ? WHERE guild_id = ?", (json.dumps(wl), ctx.guild.id))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=msg, color=0xFF0000))


async def setup(bot):
    await bot.add_cog(AntiNuke(bot))
