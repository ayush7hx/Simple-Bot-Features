import discord
from discord.ext import commands
from collections import defaultdict
import asyncio
import aiosqlite
import os
import re
import time

DB_PATH = "db/automod.db"

INVITE_PATTERN = re.compile(r"(discord\.gg|discord\.com/invite|discordapp\.com/invite)/[\w-]+", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam_tracker = defaultdict(list)
        self.bot.loop.create_task(self._create_table())

    async def _create_table(self):
        os.makedirs("db", exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS automod_config (
                    guild_id INTEGER PRIMARY KEY,
                    anti_link INTEGER DEFAULT 0,
                    anti_invite INTEGER DEFAULT 0,
                    anti_spam INTEGER DEFAULT 0,
                    anti_caps INTEGER DEFAULT 0,
                    anti_mass_mention INTEGER DEFAULT 0,
                    log_channel_id INTEGER
                )
            """)
            await db.commit()

    async def _get_config(self, guild_id):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,)) as cursor:
                return await cursor.fetchone()

    async def _ensure_config(self, guild_id):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO automod_config (guild_id) VALUES (?)", (guild_id,))
            await db.commit()

    def _has_bypass(self, member: discord.Member) -> bool:
        return (
            member.guild_permissions.manage_messages or
            member.guild_permissions.administrator or
            member.bot
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.author or self._has_bypass(message.author):
            return

        config = await self._get_config(message.guild.id)
        if not config:
            return

        _, anti_link, anti_invite, anti_spam, anti_caps, anti_mass_mention, log_channel_id = config

        # Anti-Invite
        if anti_invite and INVITE_PATTERN.search(message.content):
            await self._delete_and_warn(message, "❌ Discord invite links are not allowed here!", log_channel_id, "Anti-Invite")
            return

        # Anti-Link
        if anti_link and URL_PATTERN.search(message.content):
            if not INVITE_PATTERN.search(message.content):
                await self._delete_and_warn(message, "❌ Links are not allowed here!", log_channel_id, "Anti-Link")
                return

        # Anti-Spam (5 messages in 5 seconds)
        if anti_spam:
            now = time.time()
            uid = message.author.id
            cid = message.channel.id
            key = (uid, cid)
            self.spam_tracker[key] = [t for t in self.spam_tracker[key] if now - t < 5]
            self.spam_tracker[key].append(now)
            if len(self.spam_tracker[key]) >= 5:
                self.spam_tracker[key] = []
                await self._delete_and_warn(message, "⚠️ Please don't spam!", log_channel_id, "Anti-Spam")
                try:
                    until = discord.utils.utcnow() + __import__("datetime").timedelta(seconds=30)
                    await message.author.timeout(until, reason="AutoMod: Spamming")
                except Exception:
                    pass
                return

        # Anti-Caps (>70% caps and >10 chars)
        if anti_caps and len(message.content) > 10:
            caps_count = sum(1 for c in message.content if c.isupper())
            if caps_count / len(message.content) > 0.7:
                await self._delete_and_warn(message, "⚠️ Please don't use excessive caps!", log_channel_id, "Anti-Caps")
                return

        # Anti-Mass-Mention (>5 mentions)
        if anti_mass_mention and len(message.mentions) > 5:
            await self._delete_and_warn(message, "❌ Mass mentioning is not allowed!", log_channel_id, "Anti-MassMention")
            try:
                until = discord.utils.utcnow() + __import__("datetime").timedelta(minutes=5)
                await message.author.timeout(until, reason="AutoMod: Mass mention")
            except Exception:
                pass
            return

    async def _delete_and_warn(self, message, warn_text, log_channel_id, rule):
        try:
            await message.delete()
        except Exception:
            pass

        try:
            warn_msg = await message.channel.send(
                embed=discord.Embed(description=f"{message.author.mention} {warn_text}", color=0xFF0000),
            )
            await asyncio.sleep(5)
            await warn_msg.delete()
        except Exception:
            pass

        if log_channel_id:
            log_ch = message.guild.get_channel(log_channel_id)
            if log_ch:
                embed = discord.Embed(
                    title=f"🛡️ AutoMod: {rule}",
                    description=f"**User:** {message.author.mention} (`{message.author.id}`)\n**Channel:** {message.channel.mention}\n**Content:** {message.content[:200] or '*empty*'}",
                    color=0xFF0000,
                    timestamp=discord.utils.utcnow(),
                )
                await log_ch.send(embed=embed)

    @commands.group(name="automod", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def automod(self, ctx):
        await self._ensure_config(ctx.guild.id)
        config = await self._get_config(ctx.guild.id)
        if not config:
            return await ctx.send("No config found.")

        _, anti_link, anti_invite, anti_spam, anti_caps, anti_mass_mention, log_channel_id = config
        log_ch = ctx.guild.get_channel(log_channel_id) if log_channel_id else None

        embed = discord.Embed(title="🛡️ AutoMod Config", color=0xFF0000)
        embed.add_field(name="Anti-Link", value="✅ ON" if anti_link else "❌ OFF", inline=True)
        embed.add_field(name="Anti-Invite", value="✅ ON" if anti_invite else "❌ OFF", inline=True)
        embed.add_field(name="Anti-Spam", value="✅ ON" if anti_spam else "❌ OFF", inline=True)
        embed.add_field(name="Anti-Caps", value="✅ ON" if anti_caps else "❌ OFF", inline=True)
        embed.add_field(name="Anti-Mass-Mention", value="✅ ON" if anti_mass_mention else "❌ OFF", inline=True)
        embed.add_field(name="Log Channel", value=log_ch.mention if log_ch else "Not set", inline=True)
        embed.set_footer(text=f"Use {ctx.prefix}automod <rule> to toggle | {ctx.prefix}automod logchannel #channel")
        await ctx.send(embed=embed)

    async def _toggle(self, ctx, column):
        await self._ensure_config(ctx.guild.id)
        config = await self._get_config(ctx.guild.id)
        cols = ["guild_id", "anti_link", "anti_invite", "anti_spam", "anti_caps", "anti_mass_mention", "log_channel_id"]
        idx = cols.index(column)
        current = config[idx]
        new_val = 0 if current else 1
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"UPDATE automod_config SET {column} = ? WHERE guild_id = ?", (new_val, ctx.guild.id))
            await db.commit()
        status = "✅ Enabled" if new_val else "❌ Disabled"
        await ctx.send(embed=discord.Embed(description=f"{status} **{column.replace('_', '-').title()}**", color=0xFF0000))

    @automod.command(name="antilink")
    @commands.has_permissions(administrator=True)
    async def automod_antilink(self, ctx):
        await self._toggle(ctx, "anti_link")

    @automod.command(name="antiinvite")
    @commands.has_permissions(administrator=True)
    async def automod_antiinvite(self, ctx):
        await self._toggle(ctx, "anti_invite")

    @automod.command(name="antispam")
    @commands.has_permissions(administrator=True)
    async def automod_antispam(self, ctx):
        await self._toggle(ctx, "anti_spam")

    @automod.command(name="anticaps")
    @commands.has_permissions(administrator=True)
    async def automod_anticaps(self, ctx):
        await self._toggle(ctx, "anti_caps")

    @automod.command(name="antimention")
    @commands.has_permissions(administrator=True)
    async def automod_antimention(self, ctx):
        await self._toggle(ctx, "anti_mass_mention")

    @automod.command(name="logchannel")
    @commands.has_permissions(administrator=True)
    async def automod_logchannel(self, ctx, channel: discord.TextChannel):
        await self._ensure_config(ctx.guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE automod_config SET log_channel_id = ? WHERE guild_id = ?", (channel.id, ctx.guild.id))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"✅ AutoMod logs will be sent to {channel.mention}", color=0xFF0000))


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
