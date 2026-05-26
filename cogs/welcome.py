import discord
from discord.ext import commands
from discord.ui import View, Select, Button
import aiosqlite
import asyncio
import re
import json
import os

DB_PATH = "db/welcome.db"

class VariableButton(Button):
    def __init__(self, author):
        super().__init__(label="Variables", style=discord.ButtonStyle.secondary)
        self.author = author

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message("Only the command author can use this button.", ephemeral=True)
            return

        variables = {
            "{user}": "Mentions the user (e.g., @UserName).",
            "{user_avatar}": "The user's avatar URL.",
            "{user_name}": "The user's username.",
            "{user_id}": "The user's ID number.",
            "{user_nick}": "The user's nickname in the server.",
            "{user_joindate}": "The user's join date in the server.",
            "{user_createdate}": "The user's account creation date.",
            "{server_name}": "The server's name.",
            "{server_id}": "The server's ID number.",
            "{server_membercount}": "The server's total member count.",
            "{server_icon}": "The server's icon URL.",
        }

        embed = discord.Embed(
            title="Available Placeholders",
            description="Use these placeholders in your welcome message:",
            color=discord.Color(0xFF0000),
        )
        for var, desc in variables.items():
            embed.add_field(name=var, value=desc, inline=False)
        embed.set_footer(text="Add placeholders directly in your welcome message or embed fields.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Welcomer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._create_table())

    async def _create_table(self):
        os.makedirs("db", exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS welcome (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_type TEXT,
                    welcome_message TEXT,
                    channel_id INTEGER,
                    embed_data TEXT,
                    auto_delete_duration INTEGER
                )
            """)
            await db.commit()

    def _build_placeholders(self, member: discord.Member):
        return {
            "user": member.mention,
            "user_avatar": str(member.display_avatar.url),
            "user_name": member.name,
            "user_id": str(member.id),
            "user_nick": member.display_name,
            "user_joindate": member.joined_at.strftime("%a, %b %d, %Y") if member.joined_at else "Unknown",
            "user_createdate": member.created_at.strftime("%a, %b %d, %Y"),
            "server_name": member.guild.name,
            "server_id": str(member.guild.id),
            "server_membercount": str(member.guild.member_count),
            "server_icon": str(member.guild.icon.url) if member.guild.icon else "",
        }

    def _safe_format(self, text: str, placeholders: dict) -> str:
        lower_ph = {k.lower(): v for k, v in placeholders.items()}
        def replace_var(match):
            return str(lower_ph.get(match.group(1).lower(), f"{{{match.group(1)}}}"))
        return re.sub(r"\{(\w+)\}", replace_var, text or "")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT welcome_type, welcome_message, channel_id, embed_data FROM welcome WHERE guild_id = ?",
                (member.guild.id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return

        welcome_type, welcome_message, channel_id, embed_data = row
        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        ph = self._build_placeholders(member)

        if welcome_type == "simple" and welcome_message:
            await channel.send(self._safe_format(welcome_message, ph))
        elif welcome_type == "embed" and embed_data:
            try:
                info = json.loads(embed_data)
                color_val = info.get("color", 0x2F3136)
                if isinstance(color_val, str):
                    color_val = int(color_val.lstrip("#"), 16)
                embed = discord.Embed(
                    title=self._safe_format(info.get("title", ""), ph),
                    description=self._safe_format(info.get("description", ""), ph),
                    color=discord.Color(color_val),
                )
                if info.get("footer_text"):
                    embed.set_footer(
                        text=self._safe_format(info["footer_text"], ph),
                        icon_url=self._safe_format(info.get("footer_icon", ""), ph) or None,
                    )
                if info.get("author_name"):
                    embed.set_author(
                        name=self._safe_format(info["author_name"], ph),
                        icon_url=self._safe_format(info.get("author_icon", ""), ph) or None,
                    )
                if info.get("thumbnail"):
                    embed.set_thumbnail(url=self._safe_format(info["thumbnail"], ph))
                if info.get("image"):
                    embed.set_image(url=self._safe_format(info["image"], ph))
                content = self._safe_format(info.get("message", ""), ph) or None
                await channel.send(content=content, embed=embed)
            except Exception:
                pass

    async def _save_welcome_data(self, guild_id, welcome_type, message, embed_data=None):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO welcome (guild_id, welcome_type, welcome_message, embed_data)
                VALUES (?, ?, ?, ?)
                """,
                (guild_id, welcome_type, message, json.dumps(embed_data) if embed_data else None),
            )
            await db.commit()

    @commands.hybrid_group(invoke_without_command=True, name="greet", help="Welcome message commands.")
    async def greet(self, ctx: commands.Context):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    @greet.command(name="setup", help="Set up a welcome message for new members.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_setup(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()

        if row:
            embed = discord.Embed(
                description=f"A welcome message is already set. Use `{ctx.prefix}greet reset` to reconfigure.",
                color=0xFF0000,
            )
            return await ctx.send(embed=embed)

        options_view = View(timeout=60)

        async def btn_callback(interaction: discord.Interaction, choice: str):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Only the command author can use this.", ephemeral=True)
                return
            await interaction.response.defer()
            await interaction.message.delete()
            if choice == "simple":
                await self.simple_setup(ctx)
            elif choice == "embed":
                await self.embed_setup(ctx)

        for label, cid in [("Simple", "simple"), ("Embed", "embed"), ("Cancel", "cancel")]:
            style = discord.ButtonStyle.success if cid != "cancel" else discord.ButtonStyle.danger
            btn = Button(label=label, style=style, custom_id=cid)
            if cid == "cancel":
                async def cancel_cb(interaction, _cid=cid):
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("Not yours.", ephemeral=True)
                        return
                    await interaction.response.defer()
                    await interaction.message.delete()
                btn.callback = cancel_cb
            else:
                async def make_cb(c):
                    async def cb(interaction):
                        await btn_callback(interaction, c)
                    return cb
                btn.callback = await make_cb(cid)
            options_view.add_item(btn)

        embed = discord.Embed(
            title="Welcome Message Setup",
            description="Choose the type of welcome message:",
            color=0xFF0000,
        )
        embed.add_field(name="Simple", value="Plain text message with placeholders.", inline=False)
        embed.add_field(name="Embed", value="Rich embed with custom title, description, image, etc.", inline=False)
        await ctx.send(embed=embed, view=options_view)

    async def simple_setup(self, ctx):
        first = View(timeout=60)
        first.add_item(VariableButton(ctx.author))
        preview_msg = await ctx.send("**Simple Welcome Setup**\nType your welcome message:", view=first)
        message_content = []

        try:
            msg = await self.bot.wait_for(
                "message", timeout=120,
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
            )
            message_content.append(msg.content)
        except asyncio.TimeoutError:
            await ctx.send("Setup timed out.")
            return

        ph = self._build_placeholders(ctx.author)
        preview = self._safe_format(message_content[0], ph)
        setup_view = View(timeout=60)
        setup_view.add_item(VariableButton(ctx.author))

        async def submit_cb(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Not yours.", ephemeral=True)
                return
            await self._save_welcome_data(ctx.guild.id, "simple", message_content[0])
            await interaction.response.send_message("✅ Welcome message saved!", ephemeral=True)
            for item in setup_view.children:
                item.disabled = True
            await preview_msg.edit(view=setup_view)

        submit_btn = Button(label="Save", style=discord.ButtonStyle.success)
        submit_btn.callback = submit_cb
        setup_view.add_item(submit_btn)

        await preview_msg.edit(content=f"**Preview:** {preview}", view=setup_view)

    async def embed_setup(self, ctx):
        setup_view = View(timeout=300)
        embed_data = {k: None for k in ["message", "title", "description", "color", "footer_text", "footer_icon", "author_name", "author_icon", "thumbnail", "image"]}
        ph = self._build_placeholders(ctx.author)

        def build_preview_embed():
            color_val = embed_data["color"] if embed_data["color"] else 0x2F3136
            e = discord.Embed(
                title=self._safe_format(embed_data["title"] or "", ph),
                description=self._safe_format(embed_data["description"] or "Customize your welcome embed using the menu below.", ph),
                color=discord.Color(color_val),
            )
            if embed_data["footer_text"]:
                e.set_footer(text=self._safe_format(embed_data["footer_text"], ph), icon_url=self._safe_format(embed_data.get("footer_icon") or "", ph) or None)
            if embed_data["author_name"]:
                e.set_author(name=self._safe_format(embed_data["author_name"], ph), icon_url=self._safe_format(embed_data.get("author_icon") or "", ph) or None)
            if embed_data["thumbnail"]:
                e.set_thumbnail(url=self._safe_format(embed_data["thumbnail"], ph))
            if embed_data["image"]:
                e.set_image(url=self._safe_format(embed_data["image"], ph))
            return e

        preview_msg = await ctx.send(content="**Embed Welcome Setup** — use the menu to edit:", embed=build_preview_embed(), view=setup_view)

        async def handle_select(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Not yours.", ephemeral=True)
                return
            selected = select_menu.values[0]
            await interaction.response.defer()
            await ctx.send(f"Enter value for **{selected.replace('_', ' ').title()}**:")
            try:
                reply = await self.bot.wait_for("message", timeout=60, check=lambda m: m.author == ctx.author and m.channel == ctx.channel)
                val = reply.content
                if selected == "color":
                    try:
                        embed_data["color"] = int(val.lstrip("#"), 16)
                    except ValueError:
                        await ctx.send("Invalid hex color.")
                        return
                elif selected in ("footer_icon", "author_icon", "thumbnail", "image"):
                    if not val.startswith("http") and val not in ("{user_avatar}", "{server_icon}"):
                        await ctx.send("Invalid URL.")
                        return
                    embed_data[selected] = val
                else:
                    embed_data[selected] = val
                await preview_msg.edit(embed=build_preview_embed())
                await interaction.followup.send(f"✅ {selected.replace('_', ' ').title()} updated.", ephemeral=True)
            except asyncio.TimeoutError:
                await ctx.send("Timed out.")

        select_menu = Select(
            placeholder="Choose what to edit",
            options=[
                discord.SelectOption(label="Message Content", value="message"),
                discord.SelectOption(label="Title", value="title"),
                discord.SelectOption(label="Description", value="description"),
                discord.SelectOption(label="Color (hex)", value="color"),
                discord.SelectOption(label="Footer Text", value="footer_text"),
                discord.SelectOption(label="Footer Icon URL", value="footer_icon"),
                discord.SelectOption(label="Author Name", value="author_name"),
                discord.SelectOption(label="Author Icon URL", value="author_icon"),
                discord.SelectOption(label="Thumbnail URL", value="thumbnail"),
                discord.SelectOption(label="Image URL", value="image"),
            ],
        )
        select_menu.callback = handle_select
        setup_view.add_item(select_menu)
        setup_view.add_item(VariableButton(ctx.author))

        async def submit_cb(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Not yours.", ephemeral=True)
                return
            if not embed_data.get("title") and not embed_data.get("description"):
                await interaction.response.send_message("Please set at least a title or description.", ephemeral=True)
                return
            await self._save_welcome_data(ctx.guild.id, "embed", embed_data.get("message") or "", embed_data)
            await interaction.response.send_message("✅ Embed welcome message saved!", ephemeral=True)
            for item in setup_view.children:
                item.disabled = True
            await preview_msg.edit(view=setup_view)

        submit_btn = Button(label="Save", style=discord.ButtonStyle.success)
        submit_btn.callback = submit_cb
        setup_view.add_item(submit_btn)

        async def cancel_cb(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Not yours.", ephemeral=True)
                return
            await preview_msg.delete()
            await interaction.response.send_message("Cancelled.", ephemeral=True)

        cancel_btn = Button(label="Cancel", style=discord.ButtonStyle.danger)
        cancel_btn.callback = cancel_cb
        setup_view.add_item(cancel_btn)

    @greet.command(name="reset", aliases=["disable"], help="Remove the welcome configuration.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_reset(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()

        if not row:
            return await ctx.send(embed=discord.Embed(description="No welcome message configured.", color=0xFF0000))

        view = View(timeout=30)
        embed = discord.Embed(title="Are you sure?", description="This will delete all welcome settings for this server.", color=0xFF0000)

        async def yes_cb(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Not yours.", ephemeral=True)
                return
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM welcome WHERE guild_id = ?", (ctx.guild.id,))
                await db.commit()
            embed.title = "✅ Done"
            embed.description = "Welcome configuration removed."
            await interaction.message.edit(embed=embed, view=None)

        async def no_cb(interaction):
            if interaction.user != ctx.author:
                await interaction.response.send_message("Not yours.", ephemeral=True)
                return
            embed.title = "Cancelled"
            embed.description = "No changes made."
            await interaction.message.edit(embed=embed, view=None)

        yes = Button(label="Confirm", style=discord.ButtonStyle.danger)
        no = Button(label="Cancel", style=discord.ButtonStyle.secondary)
        yes.callback = yes_cb
        no.callback = no_cb
        view.add_item(yes)
        view.add_item(no)
        await ctx.send(embed=embed, view=view)

    @greet.command(name="channel", help="Set the channel for welcome messages.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_channel(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channel_id FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()

        if not row:
            return await ctx.send(embed=discord.Embed(description=f"No welcome message set. Run `{ctx.prefix}greet setup` first.", color=0xFF0000))

        channels = ctx.guild.text_channels
        chunks = [channels[i:i+25] for i in range(0, len(channels), 25)]
        current = 0

        def make_view(page):
            v = View(timeout=60)
            menu = Select(
                placeholder="Select welcome channel",
                options=[discord.SelectOption(label=c.name, value=str(c.id)) for c in chunks[page]],
            )
            async def sel_cb(interaction):
                if interaction.user != ctx.author:
                    await interaction.response.send_message("Not yours.", ephemeral=True)
                    return
                cid = int(menu.values[0])
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE welcome SET channel_id = ? WHERE guild_id = ?", (cid, ctx.guild.id))
                    await db.commit()
                ch = ctx.guild.get_channel(cid)
                await interaction.response.edit_message(content=f"✅ Welcome channel set to {ch.mention}", view=None, embed=None)
            menu.callback = sel_cb
            v.add_item(menu)
            if page > 0:
                prev = Button(label="Previous", style=discord.ButtonStyle.secondary)
                async def prev_cb(interaction):
                    nonlocal current
                    current -= 1
                    await interaction.response.edit_message(view=make_view(current))
                prev.callback = prev_cb
                v.add_item(prev)
            if page < len(chunks) - 1:
                nxt = Button(label="Next", style=discord.ButtonStyle.secondary)
                async def nxt_cb(interaction):
                    nonlocal current
                    current += 1
                    await interaction.response.edit_message(view=make_view(current))
                nxt.callback = nxt_cb
                v.add_item(nxt)
            return v

        await ctx.send("Select the channel for welcome messages:", view=make_view(0))

    @greet.command(name="test", help="Send a test welcome message.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_test(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT welcome_type, welcome_message, channel_id, embed_data FROM welcome WHERE guild_id = ?",
                (ctx.guild.id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return await ctx.send(embed=discord.Embed(description=f"No welcome message set. Run `{ctx.prefix}greet setup` first.", color=0xFF0000))

        welcome_type, welcome_message, channel_id, embed_data = row
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return await ctx.send(embed=discord.Embed(description=f"Channel not found. Run `{ctx.prefix}greet channel` to set one.", color=0xFF0000))

        ph = self._build_placeholders(ctx.author)

        if welcome_type == "simple":
            await channel.send(self._safe_format(welcome_message, ph))
        elif welcome_type == "embed" and embed_data:
            info = json.loads(embed_data)
            color_val = info.get("color", 0x2F3136)
            if isinstance(color_val, str):
                color_val = int(color_val.lstrip("#"), 16)
            embed = discord.Embed(
                title=self._safe_format(info.get("title", ""), ph),
                description=self._safe_format(info.get("description", ""), ph),
                color=discord.Color(color_val),
            )
            if info.get("footer_text"):
                embed.set_footer(text=self._safe_format(info["footer_text"], ph), icon_url=self._safe_format(info.get("footer_icon", ""), ph) or None)
            if info.get("author_name"):
                embed.set_author(name=self._safe_format(info["author_name"], ph), icon_url=self._safe_format(info.get("author_icon", ""), ph) or None)
            if info.get("thumbnail"):
                embed.set_thumbnail(url=self._safe_format(info["thumbnail"], ph))
            if info.get("image"):
                embed.set_image(url=self._safe_format(info["image"], ph))
            await channel.send(content=self._safe_format(info.get("message", ""), ph) or None, embed=embed)

        await ctx.send(f"✅ Test welcome message sent to {channel.mention}!")

    @greet.command(name="config", help="Show the current welcome configuration.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_config(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT * FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()

        if not row:
            return await ctx.send(embed=discord.Embed(description="No welcome configuration found.", color=0xFF0000))

        _, welcome_type, welcome_message, channel_id, embed_data, auto_delete = row
        channel = self.bot.get_channel(channel_id) if channel_id else None

        embed = discord.Embed(title=f"Greet Config — {ctx.guild.name}", color=0xFF0000)
        embed.add_field(name="Type", value=welcome_type or "None", inline=True)
        embed.add_field(name="Channel", value=channel.mention if channel else "Not set", inline=True)
        if welcome_type == "simple":
            embed.add_field(name="Message", value=welcome_message or "None", inline=False)
        elif embed_data:
            info = json.loads(embed_data)
            summary = "\n".join(f"**{k.replace('_', ' ').title()}:** {v}" for k, v in info.items() if v)
            embed.add_field(name="Embed Data", value=summary[:1024] or "None", inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Welcomer(bot))
