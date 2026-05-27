import discord
from discord.ext import commands
import aiosqlite
import os

DB_PATH = "db/autorole.db"


class AutoRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._create_table())

    async def _create_table(self):
        os.makedirs("db", exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS autorole (
                    guild_id INTEGER PRIMARY KEY,
                    role_id INTEGER
                )
            """)
            await db.commit()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT role_id FROM autorole WHERE guild_id = ?", (member.guild.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            return
        role = member.guild.get_role(row[0])
        if role:
            try:
                await member.add_roles(role, reason="AutoRole")
            except discord.Forbidden:
                pass

    @commands.group(name="autorole", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def autorole_cmd(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT role_id FROM autorole WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
        role = ctx.guild.get_role(row[0]) if row else None
        embed = discord.Embed(title="🎭 AutoRole Config", color=0xFF0000)
        embed.add_field(name="Auto Role", value=role.mention if role else "❌ Not set", inline=False)
        embed.set_footer(text=f"Use {ctx.prefix}autorole set @role to set | {ctx.prefix}autorole disable to remove")
        await ctx.send(embed=embed)

    @autorole_cmd.command(name="set")
    @commands.has_permissions(administrator=True)
    async def autorole_set(self, ctx, role: discord.Role):
        if role.managed or role >= ctx.guild.me.top_role:
            return await ctx.send(embed=discord.Embed(description="❌ I can't assign that role (it's too high or managed by integration).", color=0xFF0000))
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO autorole (guild_id, role_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET role_id = excluded.role_id",
                (ctx.guild.id, role.id),
            )
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"✅ AutoRole set to {role.mention}. New members will get this role automatically!", color=0xFF0000))

    @autorole_cmd.command(name="disable")
    @commands.has_permissions(administrator=True)
    async def autorole_disable(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM autorole WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(description="✅ AutoRole disabled.", color=0xFF0000))


async def setup(bot):
    await bot.add_cog(AutoRole(bot))
