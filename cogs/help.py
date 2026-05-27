import discord
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.help_command = None

    @commands.command(name="help", aliases=["h", "commands"])
    async def help_command(self, ctx: commands.Context):
        p = ctx.prefix

        embed = discord.Embed(title="📋 Bot Commands", color=0xFF0000)
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text="DARK INFINITE ERA • Made by AYUSH7HX")

        embed.add_field(
            name="🎉 Welcome",
            value=(
                f"`{p}greet setup` — Welcome setup karo\n"
                f"`{p}greet channel #ch` — Channel change karo\n"
                f"`{p}greet test` — Test bhejo\n"
                f"`{p}greet config` — Config dekho\n"
                f"`{p}greet reset` — Reset karo"
            ),
            inline=False,
        )

        embed.add_field(
            name="🏷️ AutoNick",
            value=(
                f"`{p}autonick set <prefix>` — Nick prefix set karo\n"
                f"`{p}autonick disable` — Band karo\n"
                f"`{p}autonick show` — Current prefix dekho"
            ),
            inline=False,
        )

        embed.add_field(
            name="📋 Embed Builder",
            value=f"`{p}embed` — Interactive embed builder",
            inline=False,
        )

        embed.add_field(
            name="🎫 Ticket",
            value=(
                f"`{p}ticket setup` — Ticket system setup\n"
                f"`{p}ticket embed` — Ticket open embed customize karo *(thumbnail/image)*\n"
                f"`{p}ticket panel [#ch]` — Panel bhejo\n"
                f"`{p}ticket close` — Ticket close karo *(Staff)*\n"
                f"`{p}ticket reset` — Reset karo"
            ),
            inline=False,
        )

        embed.add_field(
            name="🔨 Moderation",
            value=(
                f"`{p}ban @user [reason]` — Ban\n"
                f"`{p}unban <user_id>` — Unban\n"
                f"`{p}kick @user [reason]` — Kick\n"
                f"`{p}timeout @user [mins] [reason]` — Timeout/Mute\n"
                f"`{p}untimeout @user` — Unmute\n"
                f"`{p}warn @user [reason]` — Warn\n"
                f"`{p}purge <amount>` — Messages delete karo\n"
                f"`{p}lock [#ch]` — Channel lock\n"
                f"`{p}unlock [#ch]` — Channel unlock\n"
                f"`{p}snipe` — Last deleted message dekho\n"
                f"`{p}slowmode <seconds>` — Slowmode set karo"
            ),
            inline=False,
        )

        embed.add_field(
            name="🛡️ AutoMod",
            value=(
                f"`{p}automod` — Status dekho\n"
                f"`{p}automod antilink` — Link toggle\n"
                f"`{p}automod antiinvite` — Invite toggle\n"
                f"`{p}automod antispam` — Spam toggle\n"
                f"`{p}automod anticaps` — Caps toggle\n"
                f"`{p}automod antimention` — Mass mention toggle\n"
                f"`{p}automod logchannel #ch` — Log channel set"
            ),
            inline=False,
        )

        embed.add_field(
            name="📝 Logging",
            value=(
                f"`{p}logging` — Config dekho\n"
                f"`{p}logging setchannel #ch` — Log channel set karo\n"
                f"`{p}logging disable` — Band karo"
            ),
            inline=False,
        )

        embed.add_field(
            name="🎭 AutoRole",
            value=(
                f"`{p}autorole` — Status dekho\n"
                f"`{p}autorole set @role` — Role set karo\n"
                f"`{p}autorole disable` — Band karo"
            ),
            inline=False,
        )

        embed.add_field(
            name="🔰 AntiNuke",
            value=(
                f"`{p}antinuke` — Status dekho\n"
                f"`{p}antinuke enable` — Enable karo\n"
                f"`{p}antinuke disable` — Disable karo\n"
                f"`{p}antinuke action <ban/kick/timeout/strip>` — Punishment set\n"
                f"`{p}antinuke threshold <1-20>` — Trigger count set\n"
                f"`{p}antinuke logchannel #ch` — Log channel\n"
                f"`{p}antinuke whitelist @user` — Whitelist toggle"
            ),
            inline=False,
        )

        embed.add_field(
            name="📨 Mass DM",
            value=f"`{p}massdm <message>` — Sab members ko DM bhejo *(Admin only)*",
            inline=False,
        )

        embed.add_field(
            name="⚙️ Settings",
            value=(
                f"`{p}prefix` — Current prefix dekho\n"
                f"`{p}setprefix <new>` — Prefix change karo *(Admin)*"
            ),
            inline=False,
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))
