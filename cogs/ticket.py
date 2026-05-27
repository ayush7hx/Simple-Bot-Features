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
        has_permission = (
            member.guild_permissions.manage_channels or
            member.guild_permissions.administrator
        )
        if not has_permission:
            await interaction.response.send_message("❌ Only staff members can close tickets.", ephemeral=True)
            return
        await interaction.response.send_message(f"🔒 Ticket being closed by {member.mention}. Channel deletes in 5 seconds...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {member}")
        except discord.Forbidden:
            await interaction.channel.send("❌ I don't have permission to delete this channel.")


class TicketOpenView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        member = interaction.user

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT category_id, support_role_id, embed_data FROM ticket_config WHERE guild_id = ?",
                (guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            await interaction.response.send_message("Ticket system is not configured. Ask an admin to run `ticket setup`.", ephemeral=True)
            return

        category_id, support_role_id, embed_data_raw = row
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
            reason=f"Ticket opened by {member}",
        )

        # Build ticket open embed (customizable or default)
        if embed_data_raw:
            try:
                ed = json.loads(embed_data_raw)
                color_val = ed.get("ticket_color", 0xFF0000)
                if isinstance(color_val, str):
                    try:
                        color_val = int(color_val.lstrip("#"), 16)
                    except Exception:
                        color_val = 0xFF0000

                ticket_embed = discord.Embed(
                    title=ed.get("ticket_title", "🎫 Support Ticket"),
                    description=ed.get("ticket_description",
                        f"Hello {member.mention}, welcome to your ticket!\n\n"
                        "Please describe your issue and a staff member will assist you shortly.\n\n"
                        "Click **Close Ticket** when your issue is resolved."
                    ).replace("{user}", member.mention).replace("{server}", guild.name),
                    color=discord.Color(color_val),
                )
                th = ed.get("ticket_thumbnail", "")
                if th == "{user_avatar}":
                    ticket_embed.set_thumbnail(url=member.display_avatar.url)
                elif th and th.startswith("http"):
                    ticket_embed.set_thumbnail(url=th)
                img = ed.get("ticket_image", "")
                if img and img.startswith("http"):
                    ticket_embed.set_image(url=img)
                ticket_embed.set_footer(text=f"Ticket by {member.display_name}", icon_url=member.display_avatar.url)
            except Exception:
                ticket_embed = self._default_ticket_embed(member, guild)
        else:
            ticket_embed = self._default_ticket_embed(member, guild)

        await ticket_channel.send(
            content=f"{member.mention}" + (f" | {support_role.mention}" if support_role else ""),
            embed=ticket_embed,
            view=TicketCloseView(),
        )
        await interaction.response.send_message(f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

    def _default_ticket_embed(self, member, guild):
        embed = discord.Embed(
            title="🎫 Support Ticket",
            description=(
                f"Hello {member.mention}, welcome to your ticket!\n\n"
                "Please describe your issue and a staff member will assist you shortly.\n\n"
                "Click **Close Ticket** when your issue is resolved."
            ),
            color=0xFF0000,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Ticket by {member.display_name}", icon_url=member.display_avatar.url)
        return embed


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
                    panel_message TEXT,
                    embed_data TEXT
                )
            """)
            await db.commit()

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(TicketOpenView())
        self.bot.add_view(TicketCloseView())

    @commands.group(name="ticket", invoke_without_command=True, case_insensitive=True)
    @commands.has_permissions(administrator=True)
    async def ticket(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @ticket.command(name="setup", help="Set up the ticket system.")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx: commands.Context):
        def chk(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send(embed=discord.Embed(title="Ticket System Setup", description="Setting up step by step.", color=0xFF0000))

        # Step 1: Category
        await ctx.send("**Step 1:** Send the **category** ID or mention where tickets go (type `skip` for none):")
        try:
            msg = await self.bot.wait_for("message", timeout=60, check=chk)
            category = None
            if msg.content.lower() != "skip":
                try:
                    cid = int(msg.content.strip("<#>"))
                    category = ctx.guild.get_channel(cid)
                    if not isinstance(category, discord.CategoryChannel):
                        await ctx.send("Not a valid category, skipping...")
                        category = None
                except ValueError:
                    await ctx.send("Invalid input, skipping category...")
        except asyncio.TimeoutError:
            return await ctx.send("⏰ Timed out.")

        # Step 2: Support Role
        await ctx.send("**Step 2:** Mention the **support role** (type `skip` for none):")
        try:
            msg = await self.bot.wait_for("message", timeout=60, check=chk)
            support_role = None
            if msg.content.lower() != "skip":
                if msg.role_mentions:
                    support_role = msg.role_mentions[0]
                else:
                    try:
                        rid = int(msg.content.strip("<@&>"))
                        support_role = ctx.guild.get_role(rid)
                    except ValueError:
                        await ctx.send("Invalid role, skipping...")
        except asyncio.TimeoutError:
            return await ctx.send("⏰ Timed out.")

        # Step 3: Panel channel
        await ctx.send("**Step 3:** Mention the **channel** for the ticket panel:")
        try:
            msg = await self.bot.wait_for("message", timeout=60, check=chk)
            panel_channel = None
            if msg.channel_mentions:
                panel_channel = msg.channel_mentions[0]
            else:
                try:
                    cid = int(msg.content.strip("<#>"))
                    panel_channel = ctx.guild.get_channel(cid)
                except ValueError:
                    return await ctx.send("Invalid channel.")
        except asyncio.TimeoutError:
            return await ctx.send("⏰ Timed out.")

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO ticket_config (guild_id, category_id, support_role_id) VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET category_id=excluded.category_id, support_role_id=excluded.support_role_id",
                (ctx.guild.id, category.id if category else None, support_role.id if support_role else None),
            )
            await db.commit()

        panel_embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Click the button below to open a support ticket.\nA private channel will be created just for you.",
            color=0xFF0000,
        )
        if ctx.guild.icon:
            panel_embed.set_thumbnail(url=ctx.guild.icon.url)
        panel_embed.set_footer(text=ctx.guild.name)

        await panel_channel.send(embed=panel_embed, view=TicketOpenView())

        confirm = discord.Embed(title="✅ Ticket System Ready!", color=0xFF0000)
        confirm.add_field(name="Category", value=category.mention if category else "None", inline=True)
        confirm.add_field(name="Support Role", value=support_role.mention if support_role else "None", inline=True)
        confirm.add_field(name="Panel Channel", value=panel_channel.mention, inline=True)
        await ctx.send(embed=confirm)

    @ticket.command(name="embed", help="Customize the ticket open embed (thumbnail, image, text).")
    @commands.has_permissions(administrator=True)
    async def ticket_embed(self, ctx: commands.Context):
        def chk(m):
            return m.author == ctx.author and m.channel == ctx.channel

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT embed_data FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()

        if not row:
            return await ctx.send(embed=discord.Embed(description="Run `ticket setup` first.", color=0xFF0000))

        embed_data = {}
        if row[0]:
            try:
                embed_data = json.loads(row[0])
            except Exception:
                embed_data = {}

        fields = [
            ("ticket_title", "Ticket Embed Title", "🎫 Support Ticket"),
            ("ticket_description", "Ticket Description (use {user} for mention)", "Hello {user}! Describe your issue."),
            ("ticket_color", "Embed Color (hex, e.g. FF0000)", "FF0000"),
            ("ticket_thumbnail", "Thumbnail URL or `{user_avatar}` for user's avatar", "{user_avatar}"),
            ("ticket_image", "Banner Image URL (full width, or `skip`)", ""),
        ]

        preview_embed = discord.Embed(
            title=embed_data.get("ticket_title", "🎫 Support Ticket"),
            description=embed_data.get("ticket_description", "Hello {user}! Describe your issue.").replace("{user}", ctx.author.mention),
            color=discord.Color(int(embed_data.get("ticket_color", "FF0000").lstrip("#"), 16) if embed_data.get("ticket_color") else 0xFF0000),
        )
        preview_embed.set_thumbnail(url=ctx.author.display_avatar.url)
        preview_embed.set_footer(text="Live Preview")
        preview_msg = await ctx.send(content="**Ticket Embed Customizer — Live Preview:**", embed=preview_embed)

        for key, label, default in fields:
            prompt = await ctx.send(embed=discord.Embed(
                description=f"**{label}**\nDefault: `{default}`\nType value or `skip`:",
                color=0x2F3136,
            ))
            try:
                msg = await self.bot.wait_for("message", timeout=60, check=chk)
                val = msg.content.strip()
                if val.lower() != "skip" and val:
                    embed_data[key] = val
                elif key not in embed_data:
                    embed_data[key] = default

                # Update preview
                try:
                    color_val = int(embed_data.get("ticket_color", "FF0000").lstrip("#"), 16)
                except Exception:
                    color_val = 0xFF0000

                new_preview = discord.Embed(
                    title=embed_data.get("ticket_title", "🎫 Support Ticket"),
                    description=embed_data.get("ticket_description", "Hello {user}!").replace("{user}", ctx.author.mention),
                    color=discord.Color(color_val),
                )
                th = embed_data.get("ticket_thumbnail", "")
                if th == "{user_avatar}":
                    new_preview.set_thumbnail(url=ctx.author.display_avatar.url)
                elif th and th.startswith("http"):
                    new_preview.set_thumbnail(url=th)
                img = embed_data.get("ticket_image", "")
                if img and img.startswith("http"):
                    new_preview.set_image(url=img)
                new_preview.set_footer(text="Live Preview")
                await preview_msg.edit(embed=new_preview)
                await prompt.delete()
                try:
                    await msg.delete()
                except Exception:
                    pass
            except asyncio.TimeoutError:
                await prompt.delete()

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE ticket_config SET embed_data = ? WHERE guild_id = ?", (json.dumps(embed_data), ctx.guild.id))
            await db.commit()

        await ctx.send(embed=discord.Embed(description="✅ Ticket embed customized! New tickets will use this embed.", color=0xFF0000))

    @ticket.command(name="panel", help="Resend the ticket panel to a channel.")
    @commands.has_permissions(administrator=True)
    async def ticket_panel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            return await ctx.send(embed=discord.Embed(description="Run `ticket setup` first.", color=0xFF0000))

        panel_embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Click the button below to open a support ticket.\nA private channel will be created just for you.",
            color=0xFF0000,
        )
        if ctx.guild.icon:
            panel_embed.set_thumbnail(url=ctx.guild.icon.url)
        panel_embed.set_footer(text=ctx.guild.name)

        await target.send(embed=panel_embed, view=TicketOpenView())
        await ctx.send(f"✅ Ticket panel sent to {target.mention}!")

    @ticket.command(name="close", help="Close the current ticket channel.")
    @commands.has_permissions(manage_channels=True)
    async def ticket_close(self, ctx: commands.Context):
        if not ctx.channel.name.startswith("ticket-"):
            return await ctx.send(embed=discord.Embed(description="This can only be used inside a ticket channel.", color=0xFF0000))
        await ctx.send("Closing in 3 seconds...")
        await asyncio.sleep(3)
        try:
            await ctx.channel.delete(reason=f"Ticket closed by {ctx.author}")
        except discord.Forbidden:
            await ctx.send("❌ No permission to delete.")

    @ticket.command(name="reset", help="Remove the ticket system configuration.")
    @commands.has_permissions(administrator=True)
    async def ticket_reset(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(description="✅ Ticket configuration reset.", color=0xFF0000))


async def setup(bot):
    await bot.add_cog(Ticket(bot))
