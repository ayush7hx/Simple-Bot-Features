import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from keep_alive import keep_alive

load_dotenv()
keep_alive()

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


async def get_prefix(bot, message):
    if not message.guild:
        return "!"
    try:
        import aiosqlite
        async with aiosqlite.connect("db/prefix.db") as db:
            async with db.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (message.guild.id,)) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else "!"
    except Exception:
        return "!"


bot = commands.Bot(command_prefix=get_prefix, intents=intents)

COGS = ["cogs.welcome", "cogs.autonick", "cogs.embed", "cogs.ticket", "cogs.prefix"]


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


async def main():
    async with bot:
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                print(f"Loaded {cog}")
            except Exception as e:
                print(f"Failed to load {cog}: {e}")
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
