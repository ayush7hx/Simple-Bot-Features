from __future__ import annotations
import os
import discord
import aiosqlite
from discord.ext import commands

DB_PATH = "db/autonick.db"


class AutoNick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._create_table())

    async def _create_table(self):
        os.makedirs("db", exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS autonick (
                    guild_id INTEGER PRIMARY KEY,
                    prefix TEXT NOT NULL
                )
            """)
            await db.commit()

    async def _get_prefix(self, guild_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT prefix FROM autonick WHERE guild_id = ?", (guild_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        prefix = await self._get_prefix(member.guild.id)
        if not prefix:
            return
        new_nick = f"{prefix} {member.display_name}"
        if len(new_nick) > 32:
            new_nick = new_nick[:32]
        try:
            await member.edit(nick=new_nick)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.group(name="autonick", aliases=["autonickname", "anick"], invoke_without_command=True, case_insensitive=True)
    @commands.has_permissions(manage_nicknames=True)
    async def autonick(self, ctx: commands.Context):
        prefix = await self._get_prefix(ctx.guild.id)
        embed = discord.Embed(color=0xFF0000)
        embed.set_author(name="Auto Nick", icon_url=self.bot.user.display_avatar.url)
        if prefix:
            embed.description = (
                f"✅ Auto Nick is **enabled** on this server.\n"
                f"**Current Prefix:** `{prefix}`\n\n"
                f"New members will get: `{prefix} <username>`\n\n"
                f"**Commands:**\n"
                f"`autonick set <prefix>` — set the prefix\n"
                f"`autonick disable` — disable autonick\n"
                f"`autonick show` — view current prefix"
            )
        else:
            embed.description = (
                "⚠️ Auto Nick is **disabled** on this server.\n\n"
                "**Commands:**\n"
                "`autonick set <prefix>` — set the prefix\n"
                "`autonick disable` — disable autonick\n"
                "`autonick show` — view current prefix"
            )
        await ctx.reply(embed=embed, mention_author=False)

    @autonick.command(name="set", aliases=["enable", "on", "add"])
    @commands.has_permissions(manage_nicknames=True)
    async def autonick_set(self, ctx: commands.Context, *, prefix: str):
        if len(prefix) > 20:
            return await ctx.reply(
                embed=discord.Embed(description="⚠️ Prefix cannot be more than 20 characters.", color=0xFF0000),
                mention_author=False,
            )
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO autonick (guild_id, prefix) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET prefix = ?",
                (ctx.guild.id, prefix, prefix),
            )
            await db.commit()

        embed = discord.Embed(color=0xFF0000)
        embed.set_author(name="Auto Nick Enabled", icon_url=self.bot.user.display_avatar.url)
        embed.description = (
            f"✅ Auto Nick has been set!\n\n"
            f"**Prefix:** `{prefix}`\n"
            f"**Example:** `{prefix} Username`\n\n"
            f"New members will automatically get the prefix added to their nickname."
        )
        await ctx.reply(embed=embed, mention_author=False)

    @autonick.command(name="disable", aliases=["remove", "off", "reset"])
    @commands.has_permissions(manage_nicknames=True)
    async def autonick_disable(self, ctx: commands.Context):
        prefix = await self._get_prefix(ctx.guild.id)
        if not prefix:
            return await ctx.reply(
                embed=discord.Embed(description="⚠️ Auto Nick is already **OFF** on this server.", color=0xFF0000),
                mention_author=False,
            )
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM autonick WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.reply(
            embed=discord.Embed(description="✅ Auto Nick has been **disabled**. New members will no longer get an automatic nickname.", color=0xFF0000),
            mention_author=False,
        )

    @autonick.command(name="show", aliases=["status", "check"])
    @commands.has_permissions(manage_nicknames=True)
    async def autonick_show(self, ctx: commands.Context):
        prefix = await self._get_prefix(ctx.guild.id)
        embed = discord.Embed(color=0xFF0000)
        embed.set_author(name="Auto Nick Status", icon_url=self.bot.user.display_avatar.url)
        if prefix:
            embed.description = (
                f"✅ Auto Nick is **ON**.\n"
                f"**Prefix:** `{prefix}`\n"
                f"**Format:** `{prefix} <member name>`"
            )
        else:
            embed.description = "⚠️ Auto Nick is currently **OFF**."
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot):
    await bot.add_cog(AutoNick(bot))
