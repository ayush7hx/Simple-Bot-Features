import discord
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.help_command = None

    @commands.command(name="help", aliases=["h", "commands"])
    async def help_command(self, ctx: commands.Context):
        prefix = ctx.prefix

        embed = discord.Embed(
            title="📋 Bot Commands",
            color=0xFF0000
        )
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text="DARK INFINITE ERA • Made by AYUSH7HX")

        embed.add_field(
            name="🎉 Welcome",
            value=(
                f"`{prefix}greet setup` — Welcome message setup karo\n"
                f"`{prefix}greet channel` — Welcome channel set karo\n"
                f"`{prefix}greet test` — Test welcome message bhejo\n"
                f"`{prefix}greet config` — Current config dekho\n"
                f"`{prefix}greet reset` — Config delete karo"
            ),
            inline=False
        )

        embed.add_field(
            name="🏷️ AutoNick",
            value=(
                f"`{prefix}autonick` — Status dekho\n"
                f"`{prefix}autonick set <prefix>` — Prefix set karo\n"
                f"`{prefix}autonick disable` — Band karo\n"
                f"`{prefix}autonick show` — Current prefix dekho"
            ),
            inline=False
        )

        embed.add_field(
            name="📋 Embed Builder",
            value=(
                f"`{prefix}embed` — Interactive embed builder"
            ),
            inline=False
        )

        embed.add_field(
            name="🎫 Ticket",
            value=(
                f"`{prefix}ticket setup` — Ticket system setup karo\n"
                f"`{prefix}ticket panel <#channel>` — Panel bhejo\n"
                f"`{prefix}ticket close` — Ticket close karo *(Staff only)*\n"
                f"`{prefix}ticket reset` — Config delete karo"
            ),
            inline=False
        )

        embed.add_field(
            name="⚙️ Settings",
            value=(
                f"`{prefix}prefix` — Current prefix dekho\n"
                f"`{prefix}setprefix <new>` — Prefix change karo *(Admin)*"
            ),
            inline=False
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))
