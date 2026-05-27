import discord
from discord.ext import commands
import aiosqlite
import os

DB_PATH = "db/logging.db"


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._create_table())

    async def _create_table(self):
        os.makedirs("db", exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS log_config (
                    guild_id INTEGER PRIMARY KEY,
                    log_channel_id INTEGER,
                    log_message_delete INTEGER DEFAULT 1,
                    log_message_edit INTEGER DEFAULT 1,
                    log_member_join INTEGER DEFAULT 1,
                    log_member_leave INTEGER DEFAULT 1,
                    log_member_ban INTEGER DEFAULT 1,
                    log_member_unban INTEGER DEFAULT 1
                )
            """)
            await db.commit()

    async def _get_log_channel(self, guild_id):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT log_channel_id FROM log_config WHERE guild_id = ?", (guild_id,)) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else None

    async def _get_config(self, guild_id):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT * FROM log_config WHERE guild_id = ?", (guild_id,)) as cursor:
                return await cursor.fetchone()

    async def _send_log(self, guild, embed):
        channel_id = await self._get_log_channel(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        config = await self._get_config(message.guild.id)
        if not config or not config[2]:
            return
        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=0xFF4444,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Author", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=False)
        embed.add_field(name="Content", value=message.content[:1000] or "*No text*", inline=False)
        if message.attachments:
            embed.add_field(name="Attachments", value="\n".join(a.filename for a in message.attachments), inline=False)
        embed.set_thumbnail(url=message.author.display_avatar.url)
        await self._send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        config = await self._get_config(before.guild.id)
        if not config or not config[3]:
            return
        embed = discord.Embed(
            title="✏️ Message Edited",
            color=0xFFAA00,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Author", value=f"{before.author.mention} (`{before.author.id}`)", inline=False)
        embed.add_field(name="Channel", value=before.channel.mention, inline=False)
        embed.add_field(name="Before", value=before.content[:500] or "*empty*", inline=False)
        embed.add_field(name="After", value=after.content[:500] or "*empty*", inline=False)
        embed.set_thumbnail(url=before.author.display_avatar.url)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Jump to Message", url=after.jump_url))
        await self._send_log(before.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await self._get_config(member.guild.id)
        if not config or not config[4]:
            return
        embed = discord.Embed(
            title="✅ Member Joined",
            description=f"{member.mention} (`{member.id}`)",
            color=0x00CC44,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%d %b %Y"), inline=True)
        embed.add_field(name="Member Count", value=str(member.guild.member_count), inline=True)
        embed.set_footer(text=member.guild.name)
        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        config = await self._get_config(member.guild.id)
        if not config or not config[5]:
            return
        embed = discord.Embed(
            title="❌ Member Left",
            description=f"{member.mention} (`{member.id}`)",
            color=0xFF4444,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed.add_field(name="Roles", value=", ".join(roles) or "None", inline=False)
        embed.set_footer(text=member.guild.name)
        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        config = await self._get_config(guild.id)
        if not config or not config[6]:
            return
        embed = discord.Embed(
            title="🔨 Member Banned",
            description=f"{user.mention} (`{user.id}`)",
            color=0xFF0000,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=guild.name)
        await self._send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        config = await self._get_config(guild.id)
        if not config or not config[7]:
            return
        embed = discord.Embed(
            title="✅ Member Unbanned",
            description=f"{user.mention} (`{user.id}`)",
            color=0x00CC44,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=guild.name)
        await self._send_log(guild, embed)

    @commands.group(name="logging", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def logging_cmd(self, ctx):
        config = await self._get_config(ctx.guild.id)
        channel_id = config[1] if config else None
        log_ch = ctx.guild.get_channel(channel_id) if channel_id else None

        embed = discord.Embed(title="📋 Logging Config", color=0xFF0000)
        embed.add_field(name="Log Channel", value=log_ch.mention if log_ch else "❌ Not set", inline=False)
        if config:
            embed.add_field(name="Msg Delete", value="✅" if config[2] else "❌", inline=True)
            embed.add_field(name="Msg Edit", value="✅" if config[3] else "❌", inline=True)
            embed.add_field(name="Member Join", value="✅" if config[4] else "❌", inline=True)
            embed.add_field(name="Member Leave", value="✅" if config[5] else "❌", inline=True)
            embed.add_field(name="Member Ban", value="✅" if config[6] else "❌", inline=True)
            embed.add_field(name="Member Unban", value="✅" if config[7] else "❌", inline=True)
        embed.set_footer(text=f"Use {ctx.prefix}logging setchannel #channel to set log channel")
        await ctx.send(embed=embed)

    @logging_cmd.command(name="setchannel")
    @commands.has_permissions(administrator=True)
    async def logging_setchannel(self, ctx, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO log_config (guild_id, log_channel_id) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET log_channel_id = excluded.log_channel_id",
                (ctx.guild.id, channel.id),
            )
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"✅ Log channel set to {channel.mention}", color=0xFF0000))

    @logging_cmd.command(name="disable")
    @commands.has_permissions(administrator=True)
    async def logging_disable(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM log_config WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(description="✅ Logging disabled.", color=0xFF0000))


async def setup(bot):
    await bot.add_cog(Logging(bot))
