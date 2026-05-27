import discord
from discord.ext import commands
from discord.ui import View, Button
import aiosqlite
import asyncio
import json
import os

DB_PATH = "db/ticket.db"


class TicketCloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        member = interaction.user
        if not (member.guild_permissions.manage_channels or member.guild_permissions.administrator):
            await interaction.response.send_message("❌ Only staff can close tickets.", ephemeral=True)
            return
        await interaction.response.send_message(f"🔒 Closing ticket by {member.mention} in 5 seconds...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {member}")
        except discord.Forbidden:
            await interaction.channel.send("❌ No permission to delete.")


class TicketOpenView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.success, emoji="🎫", custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        member = interaction.user

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT category_id, support_role_id, ticket_embed_data FROM ticket_config WHERE guild_id = ?",
                (guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            await interaction.response.send_message("Ticket system not configured. Ask admin to run `ticket setup`.", ephemeral=True)
            return

        category_id, support_role_id, ticket_embed_raw = row
        category = guild.get_channel(category_id) if category_id else None
        support_role = guild.get_role(support_role_id) if support_role_id else None

        existing = discord.utils.get(guild.text_channels, name=f"ticket-{member.name.lower()}")
        if existing:
            await interaction.response.send_message(f"You already have an open ticket: {existing.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{member.name}",
            category=category,
            overwrites=overwrites,
        )

        # Build ticket open embed
        if ticket_embed_raw:
            try:
                ed = json.loads(ticket_embed_raw)
                color_val = int(str(ed.get("color", "FF0000")).lstrip("#"), 16)
                te = discord.Embed(
                    title=ed.get("title", "🎫 Support Ticket"),
                    description=ed.get("description", f"Hello {member.mention}!\nDescribe your issue and staff will assist you.").replace("{user}", member.mention),
                    color=discord.Color(color_val),
                )
                th = ed.get("thumbnail", "")
                if th == "{user_avatar}":
                    te.set_thumbnail(url=member.display_avatar.url)
                elif th and th.startswith("http"):
                    te.set_thumbnail(url=th)
                img = ed.get("image", "")
                if img and img.startswith("http"):
                    te.set_image(url=img)
                ft = ed.get("footer", f"Ticket by {member.display_name}")
                te.set_footer(text=ft.replace("{user}", member.display_name), icon_url=member.display_avatar.url)
            except Exception:
                te = self._default_ticket_embed(member)
        else:
            te = self._default_ticket_embed(member)

        await ticket_channel.send(
            content=f"{member.mention}" + (f" | {support_role.mention}" if support_role else ""),
            embed=te,
            view=TicketCloseView(),
        )
        await interaction.response.send_message(f"✅ Ticket created: {ticket_channel.mention}", ephemeral=True)

    def _default_ticket_embed(self, member):
        e = discord.Embed(
            title="🎫 Support Ticket",
            description=f"Hello {member.mention}!\n\nPlease describe your issue clearly and a staff member will assist you shortly.\n\nClick **Close Ticket** when resolved.",
            color=0xFF0000,
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text=f"Ticket by {member.display_name}", icon_url=member.display_avatar.url)
        return e


class Ticket(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._create_table())

    async def _create_table(self):
        os.makedirs("db", exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_config (
                    guild_id INTEGER PRIMARY KEY,
                    category_id INTEGER,
                    support_role_id INTEGER,
                    panel_embed_data TEXT,
                    ticket_embed_data TEXT
                )
            """)
            await db.commit()

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketOpenView())
        self.bot.add_view(TicketCloseView())

    @commands.group(name="ticket", invoke_without_command=True, case_insensitive=True)
    @commands.has_permissions(administrator=True)
    async def ticket(self, ctx):
        await ctx.send_help(ctx.command)

    @ticket.command(name="setup", help="Set up the ticket system.")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx):
        def chk(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send(embed=discord.Embed(title="🎫 Ticket System Setup", description="Step by step setup.", color=0xFF0000))

        # Step 1: Category
        await ctx.send("**Step 1:** Category ID/mention for tickets (or type `skip`):")
        try:
            msg = await self.bot.wait_for("message", timeout=60, check=chk)
            category = None
            if msg.content.lower() != "skip":
                try:
                    category = ctx.guild.get_channel(int(msg.content.strip("<#>")))
                    if not isinstance(category, discord.CategoryChannel):
                        category = None
                except Exception:
                    pass
        except asyncio.TimeoutError:
            return await ctx.send("⏰ Timed out.")

        # Step 2: Support Role
        await ctx.send("**Step 2:** Mention the support role (or type `skip`):")
        try:
            msg = await self.bot.wait_for("message", timeout=60, check=chk)
            support_role = None
            if msg.content.lower() != "skip":
                if msg.role_mentions:
                    support_role = msg.role_mentions[0]
                else:
                    try:
                        support_role = ctx.guild.get_role(int(msg.content.strip("<@&>")))
                    except Exception:
                        pass
        except asyncio.TimeoutError:
            return await ctx.send("⏰ Timed out.")

        # Step 3: Panel channel
        await ctx.send("**Step 3:** Mention the channel for the ticket panel:")
        try:
            msg = await self.bot.wait_for("message", timeout=60, check=chk)
            panel_channel = None
            if msg.channel_mentions:
                panel_channel = msg.channel_mentions[0]
            else:
                try:
                    panel_channel = ctx.guild.get_channel(int(msg.content.strip("<#>")))
                except Exception:
                    return await ctx.send("Invalid channel.")
        except asyncio.TimeoutError:
            return await ctx.send("⏰ Timed out.")

        # Save
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO ticket_config (guild_id, category_id, support_role_id) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET category_id=excluded.category_id, support_role_id=excluded.support_role_id",
                (ctx.guild.id, category.id if category else None, support_role.id if support_role else None),
            )
            await db.commit()

        # Ask if they want to customize panel
        view = View(timeout=30)
        chosen = {"v": None}
        for label, val, style in [("Yes, Customize Panel", "yes", discord.ButtonStyle.success), ("Use Default", "no", discord.ButtonStyle.secondary)]:
            btn = Button(label=label, style=style)
            async def make_cb(v):
                async def cb(interaction: discord.Interaction):
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("Not yours.", ephemeral=True)
                        return
                    chosen["v"] = v
                    view.stop()
                    await interaction.response.defer()
                return cb
            btn.callback = await make_cb(val)
            view.add_item(btn)

        ask_msg = await ctx.send(embed=discord.Embed(description="Do you want to **customize the ticket panel embed** (title, image, etc.)?", color=0xFF0000), view=view)
        await view.wait()
        await ask_msg.delete()

        if chosen["v"] == "yes":
            panel_data = await self._panel_customizer(ctx, chk)
        else:
            panel_data = None

        # Send panel
        panel_embed = self._build_panel_embed(ctx.guild, panel_data)
        await panel_channel.send(embed=panel_embed, view=TicketOpenView())

        confirm = discord.Embed(title="✅ Ticket System Ready!", color=0xFF0000)
        confirm.add_field(name="Category", value=category.mention if category else "None", inline=True)
        confirm.add_field(name="Support Role", value=support_role.mention if support_role else "None", inline=True)
        confirm.add_field(name="Panel Channel", value=panel_channel.mention, inline=True)
        confirm.set_footer(text="Use infticket panelsetup to customize panel embed anytime")
        await ctx.send(embed=confirm)

    async def _panel_customizer(self, ctx, chk):
        """Interactive panel embed customizer with live preview."""
        panel_data = {
            "title": "🎫 — Support Tickets — 🎫",
            "description": "♡ Need help? Create a ticket\n♡ Tell us your issue clearly\n♡ Our team will respond soon",
            "color": "FF0000",
            "image": "",
            "footer": f"© {ctx.guild.name} Support",
        }

        def build_preview():
            try:
                color_val = int(panel_data["color"].lstrip("#"), 16)
            except Exception:
                color_val = 0xFF0000
            e = discord.Embed(
                title=panel_data.get("title", ""),
                description=panel_data.get("description", ""),
                color=discord.Color(color_val),
            )
            img = panel_data.get("image", "")
            if img and img.startswith("http"):
                e.set_image(url=img)
            if ctx.guild.icon:
                e.set_thumbnail(url=ctx.guild.icon.url)
            ft = panel_data.get("footer", "")
            if ft:
                e.set_footer(text=ft, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
            return e

        info = discord.Embed(
            title="🎨 Panel Customizer",
            description=(
                "I'll ask for each field. Type `skip` to keep default.\n\n"
                "**Tip:** For image, paste a direct image URL (e.g. from Imgur, Discord CDN)\n"
                "The image shows as a **big banner** on the panel!"
            ),
            color=0xFF0000,
        )
        await ctx.send(embed=info)
        preview_msg = await ctx.send(content="**Live Panel Preview:**", embed=build_preview())

        fields = [
            ("title", "Panel Title", "🎫 — Support Tickets — 🎫"),
            ("description", "Panel Description (use \\n for new line)", "♡ Need help? Create a ticket\n♡ Our team will assist you"),
            ("color", "Embed Color (hex, e.g. FF0000 or 9B59B6)", "FF0000"),
            ("image", "Banner Image URL (big image shown in panel)", ""),
            ("footer", "Footer Text", f"© {ctx.guild.name}"),
        ]

        for key, label, default in fields:
            prompt = await ctx.send(embed=discord.Embed(
                description=f"**{label}**\nDefault: `{default or 'none'}`\nType value or `skip`:",
                color=0x2F3136,
            ))
            try:
                msg = await self.bot.wait_for("message", timeout=90, check=chk)
                val = msg.content.strip()
                if val.lower() != "skip" and val:
                    panel_data[key] = val.replace("\\n", "\n")
                await preview_msg.edit(embed=build_preview())
                await prompt.delete()
                try:
                    await msg.delete()
                except Exception:
                    pass
            except asyncio.TimeoutError:
                await prompt.delete()

        # Save panel data
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE ticket_config SET panel_embed_data = ? WHERE guild_id = ?", (json.dumps(panel_data), ctx.guild.id))
            await db.commit()

        await ctx.send(embed=discord.Embed(description="✅ Panel customized!", color=0xFF0000), delete_after=5)
        return panel_data

    def _build_panel_embed(self, guild, panel_data=None):
        """Build the panel embed from stored data or defaults."""
        if panel_data:
            try:
                color_val = int(str(panel_data.get("color", "FF0000")).lstrip("#"), 16)
            except Exception:
                color_val = 0xFF0000
            e = discord.Embed(
                title=panel_data.get("title", "🎫 Support Tickets"),
                description=panel_data.get("description", "Click **Open Ticket** below to get help."),
                color=discord.Color(color_val),
            )
            img = panel_data.get("image", "")
            if img and img.startswith("http"):
                e.set_image(url=img)
            if guild.icon:
                e.set_thumbnail(url=guild.icon.url)
            ft = panel_data.get("footer", guild.name)
            e.set_footer(text=ft, icon_url=guild.icon.url if guild.icon else None)
        else:
            e = discord.Embed(
                title="🎫 Support Tickets",
                description="♡ Need help? Create a ticket\n♡ Tell us your issue clearly\n♡ Our team will respond soon",
                color=0xFF0000,
            )
            if guild.icon:
                e.set_thumbnail(url=guild.icon.url)
            e.set_footer(text=guild.name)
        return e

    @ticket.command(name="panelsetup", help="Customize the ticket panel embed (title, image, description, etc.)")
    @commands.has_permissions(administrator=True)
    async def ticket_panelsetup(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            return await ctx.send(embed=discord.Embed(description="Run `ticket setup` first.", color=0xFF0000))

        def chk(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await self._panel_customizer(ctx, chk)

    @ticket.command(name="ticketembed", help="Customize the embed shown inside a new ticket channel.")
    @commands.has_permissions(administrator=True)
    async def ticket_ticketembed(self, ctx):
        def chk(m):
            return m.author == ctx.author and m.channel == ctx.channel

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT ticket_embed_data FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            return await ctx.send(embed=discord.Embed(description="Run `ticket setup` first.", color=0xFF0000))

        embed_data = {}
        if row[0]:
            try:
                embed_data = json.loads(row[0])
            except Exception:
                pass

        def build_preview():
            try:
                color_val = int(str(embed_data.get("color", "FF0000")).lstrip("#"), 16)
            except Exception:
                color_val = 0xFF0000
            e = discord.Embed(
                title=embed_data.get("title", "🎫 Support Ticket"),
                description=embed_data.get("description", f"Hello {ctx.author.mention}!\nDescribe your issue.").replace("{user}", ctx.author.mention),
                color=discord.Color(color_val),
            )
            th = embed_data.get("thumbnail", "")
            if th == "{user_avatar}":
                e.set_thumbnail(url=ctx.author.display_avatar.url)
            elif th and th.startswith("http"):
                e.set_thumbnail(url=th)
            else:
                e.set_thumbnail(url=ctx.author.display_avatar.url)
            img = embed_data.get("image", "")
            if img and img.startswith("http"):
                e.set_image(url=img)
            e.set_footer(text=embed_data.get("footer", f"Ticket by {ctx.author.display_name}"), icon_url=ctx.author.display_avatar.url)
            return e

        info = discord.Embed(
            title="🎨 Ticket Channel Embed Customizer",
            description="This embed appears **inside the ticket channel** when it's opened.\nUse `{user}` for the member mention.",
            color=0xFF0000,
        )
        await ctx.send(embed=info)
        preview_msg = await ctx.send(content="**Live Preview:**", embed=build_preview())

        fields = [
            ("title", "Ticket Title", "🎫 Support Ticket"),
            ("description", "Description (use {user} for mention, \\n for new line)", "Hello {user}!\n\nDescribe your issue."),
            ("color", "Color (hex)", "FF0000"),
            ("thumbnail", "Thumbnail (URL or `{user_avatar}`)", "{user_avatar}"),
            ("image", "Banner Image URL (optional)", ""),
            ("footer", "Footer Text", "Support Ticket"),
        ]

        for key, label, default in fields:
            prompt = await ctx.send(embed=discord.Embed(
                description=f"**{label}**\nDefault: `{default or 'none'}`\nType value or `skip`:",
                color=0x2F3136,
            ))
            try:
                msg = await self.bot.wait_for("message", timeout=90, check=chk)
                val = msg.content.strip()
                if val.lower() != "skip" and val:
                    embed_data[key] = val.replace("\\n", "\n")
                await preview_msg.edit(embed=build_preview())
                await prompt.delete()
                try:
                    await msg.delete()
                except Exception:
                    pass
            except asyncio.TimeoutError:
                await prompt.delete()

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE ticket_config SET ticket_embed_data = ? WHERE guild_id = ?", (json.dumps(embed_data), ctx.guild.id))
            await db.commit()

        await ctx.send(embed=discord.Embed(description="✅ Ticket channel embed saved!", color=0xFF0000))

    @ticket.command(name="panel", help="Resend the ticket panel to a channel.")
    @commands.has_permissions(administrator=True)
    async def ticket_panel(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT panel_embed_data FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            return await ctx.send(embed=discord.Embed(description="Run `ticket setup` first.", color=0xFF0000))

        panel_data = None
        if row[0]:
            try:
                panel_data = json.loads(row[0])
            except Exception:
                pass

        panel_embed = self._build_panel_embed(ctx.guild, panel_data)
        await target.send(embed=panel_embed, view=TicketOpenView())
        await ctx.send(f"✅ Panel sent to {target.mention}!")

    @ticket.command(name="close", help="Close the current ticket channel.")
    @commands.has_permissions(manage_channels=True)
    async def ticket_close(self, ctx):
        if not ctx.channel.name.startswith("ticket-"):
            return await ctx.send(embed=discord.Embed(description="Use inside a ticket channel only.", color=0xFF0000))
        await ctx.send("Closing in 3 seconds...")
        await asyncio.sleep(3)
        try:
            await ctx.channel.delete(reason=f"Ticket closed by {ctx.author}")
        except discord.Forbidden:
            await ctx.send("❌ No permission to delete.")

    @ticket.command(name="reset", help="Remove the ticket system configuration.")
    @commands.has_permissions(administrator=True)
    async def ticket_reset(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(description="✅ Ticket config reset.", color=0xFF0000))


async def setup(bot):
    await bot.add_cog(Ticket(bot))
