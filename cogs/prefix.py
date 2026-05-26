import discord
import aiosqlite
import os
from discord.ext import commands

DB_PATH = "db/prefix.db"


class Prefix(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._create_table())

    async def _create_table(self):
        os.makedirs("db", exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS prefixes (
                    guild_id INTEGER PRIMARY KEY,
                    prefix TEXT NOT NULL
                )
            """)
            await db.commit()

    @commands.command(name="setprefix", aliases=["prefix", "changeprefix"])
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def setprefix(self, ctx: commands.Context, new_prefix: str):
        if len(new_prefix) > 5:
            return await ctx.send(embed=discord.Embed(
                description="❌ Prefix 5 characters se zyada nahi ho sakta.",
                color=0xFF0000
            ))

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO prefixes (guild_id, prefix) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET prefix = ?",
                (ctx.guild.id, new_prefix, new_prefix)
            )
            await db.commit()

        embed = discord.Embed(color=0xFF0000)
        embed.set_author(name="Prefix Updated", icon_url=self.bot.user.display_avatar.url)
        embed.description = (
            f"✅ Server prefix change ho gaya!\n\n"
            f"**New Prefix:** `{new_prefix}`\n"
            f"**Example:** `{new_prefix}help`"
        )
        await ctx.send(embed=embed)

    @commands.command(name="prefix", hidden=True)
    async def check_prefix(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
        prefix = row[0] if row else "!"
        await ctx.send(embed=discord.Embed(
            description=f"**Current Prefix:** `{prefix}`\n\nPrefix change karne ke liye: `{prefix}setprefix <new_prefix>`",
            color=0xFF0000
        ))


async def get_prefix(bot, message):
    if not message.guild:
        return "!"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (message.guild.id,)) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else "!"


async def setup(bot):
    await bot.add_cog(Prefix(bot))
