import discord
from discord.ext import commands
from discord.ui import View, Select, Button
import asyncio


class EmbedBuilder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="embed", help="Build and send a custom embed message.")
    @commands.has_permissions(manage_messages=True)
    @commands.cooldown(1, 7, commands.BucketType.user)
    async def _embed(self, ctx: commands.Context):
        author = ctx.author
        embed = discord.Embed(
            title="Edit Your Embed!",
            description="Select an option from the menu below to customize your embed.\nEdit the title & description to remove these instructions.",
            color=0xFF0000,
        )

        def chk(m):
            return m.channel.id == ctx.channel.id and m.author.id == author.id and not m.author.bot

        view = View(timeout=180)

        async def select_cb(interaction: discord.Interaction):
            if interaction.user.id != author.id:
                await interaction.response.send_message("This embed builder doesn't belong to you.", ephemeral=True)
                return
            await interaction.response.defer()
            value = select.values[0]

            prompts = {
                "Title": "Enter the **title** of the embed:",
                "Description": "Enter the **description** of the embed:",
                "Color": "Enter the embed color as hex (e.g. `#FF0000`):",
                "Thumbnail": "Enter the **thumbnail URL**:",
                "Image": "Enter the **image URL**:",
                "Footer Text": "Enter the **footer text**:",
                "Footer Icon": "Enter the **footer icon URL**:",
                "Author Text": "Enter the **author name**:",
                "Author Icon": "Enter the **author icon URL**:",
                "Add Field": "Enter the **field title**:",
            }

            await ctx.send(prompts[value])
            try:
                if value == "Title":
                    msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    embed.title = msg.content
                elif value == "Description":
                    msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    embed.description = msg.content
                elif value == "Color":
                    msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    try:
                        embed.color = discord.Colour(int(msg.content.strip("#"), 16))
                    except ValueError:
                        await ctx.send("Invalid color. Use a hex value like `#FF0000`.")
                        return
                elif value == "Thumbnail":
                    msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    if not msg.content.startswith("http"):
                        await ctx.send("Invalid URL.")
                        return
                    embed.set_thumbnail(url=msg.content)
                elif value == "Image":
                    msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    if not msg.content.startswith("http"):
                        await ctx.send("Invalid URL.")
                        return
                    embed.set_image(url=msg.content)
                elif value == "Footer Text":
                    msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    embed.set_footer(text=msg.content, icon_url=embed.footer.icon_url if embed.footer else None)
                elif value == "Footer Icon":
                    msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    if not msg.content.startswith("http"):
                        await ctx.send("Invalid URL.")
                        return
                    embed.set_footer(text=embed.footer.text or "Footer", icon_url=msg.content)
                elif value == "Author Text":
                    msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    embed.set_author(name=msg.content, icon_url=embed.author.icon_url if embed.author else None)
                elif value == "Author Icon":
                    msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    if not msg.content.startswith("http"):
                        await ctx.send("Invalid URL.")
                        return
                    embed.set_author(name=embed.author.name or "Author", icon_url=msg.content)
                elif value == "Add Field":
                    title_msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    await ctx.send("Enter the **field value**:")
                    val_msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                    embed.add_field(name=title_msg.content, value=val_msg.content, inline=False)

                await main_msg.edit(embed=embed)
            except asyncio.TimeoutError:
                await ctx.send("Timed out.")

        select = Select(
            placeholder="Choose what to edit",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Title", description="Edit the embed title"),
                discord.SelectOption(label="Description", description="Edit the description"),
                discord.SelectOption(label="Add Field", description="Add a field"),
                discord.SelectOption(label="Color", description="Change the embed color"),
                discord.SelectOption(label="Thumbnail", description="Set a thumbnail image"),
                discord.SelectOption(label="Image", description="Set a large image"),
                discord.SelectOption(label="Footer Text", description="Edit footer text"),
                discord.SelectOption(label="Footer Icon", description="Edit footer icon URL"),
                discord.SelectOption(label="Author Text", description="Edit author name"),
                discord.SelectOption(label="Author Icon", description="Edit author icon URL"),
            ],
        )
        select.callback = select_cb
        view.add_item(select)

        async def send_cb(interaction: discord.Interaction):
            if interaction.user.id != author.id:
                await interaction.response.send_message("This doesn't belong to you.", ephemeral=True)
                return
            await interaction.response.defer()
            await ctx.send("Mention the **channel** to send the embed to:")
            try:
                msg = await ctx.bot.wait_for("message", timeout=30, check=chk)
                if not msg.channel_mentions:
                    await ctx.send("No channel mentioned.")
                    return
                target = msg.channel_mentions[0]
                await target.send(embed=embed)
                await ctx.send(embed=discord.Embed(title="✅ Success", description=f"Embed sent to {target.mention}", color=0xFF0000))
            except asyncio.TimeoutError:
                await ctx.send("Timed out.")

        async def cancel_cb(interaction: discord.Interaction):
            if interaction.user.id != author.id:
                await interaction.response.send_message("This doesn't belong to you.", ephemeral=True)
                return
            await interaction.response.defer()
            await main_msg.delete()

        btn_send = Button(label="Send Embed", style=discord.ButtonStyle.success, emoji="✅")
        btn_send.callback = send_cb
        btn_cancel = Button(label="Cancel", style=discord.ButtonStyle.danger, emoji="❌")
        btn_cancel.callback = cancel_cb

        view.add_item(btn_send)
        view.add_item(btn_cancel)

        main_msg = await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(EmbedBuilder(bot))
