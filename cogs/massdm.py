import discord
from discord.ext import commands
from discord.ui import View, Button
import asyncio


class ConfirmView(View):
    def __init__(self, author):
        super().__init__(timeout=30)
        self.author = author
        self.confirmed = False

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Not yours.", ephemeral=True)
            return
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Not yours.", ephemeral=True)
            return
        self.confirmed = False
        self.stop()
        await interaction.response.defer()


class MassDM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="massdm", help="DM all non-bot members of the server.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 300, commands.BucketType.guild)
    async def massdm(self, ctx, *, message: str):
        members = [m for m in ctx.guild.members if not m.bot and m != ctx.author]

        confirm_embed = discord.Embed(
            title="⚠️ Mass DM Confirmation",
            description=(
                f"You are about to DM **{len(members)} members**.\n\n"
                f"**Message Preview:**\n{message[:500]}\n\n"
                "This action **cannot be undone**. Are you sure?"
            ),
            color=0xFF0000,
        )
        view = ConfirmView(ctx.author)
        confirm_msg = await ctx.send(embed=confirm_embed, view=view)
        await view.wait()

        if not view.confirmed:
            await confirm_msg.edit(embed=discord.Embed(description="❌ Mass DM cancelled.", color=0xFF0000), view=None)
            return

        await confirm_msg.edit(embed=discord.Embed(description=f"📨 Sending DMs to {len(members)} members... Please wait.", color=0xFF0000), view=None)

        sent = 0
        failed = 0
        dm_embed = discord.Embed(
            description=message,
            color=0xFF0000,
        )
        dm_embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        dm_embed.set_footer(text=f"Message from {ctx.guild.name} staff")

        for member in members:
            try:
                await member.send(embed=dm_embed)
                sent += 1
            except Exception:
                failed += 1
            await asyncio.sleep(1.2)

        result_embed = discord.Embed(
            title="📨 Mass DM Complete",
            color=0xFF0000,
        )
        result_embed.add_field(name="✅ Sent", value=str(sent), inline=True)
        result_embed.add_field(name="❌ Failed", value=str(failed), inline=True)
        result_embed.add_field(name="Total", value=str(len(members)), inline=True)
        result_embed.set_footer(text=f"By {ctx.author}")
        await confirm_msg.edit(embed=result_embed)


async def setup(bot):
    await bot.add_cog(MassDM(bot))
