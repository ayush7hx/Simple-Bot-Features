import discord
from discord.ext import commands
from discord.ui import View, Button, Select
import aiosqlite
import os

DB_PATH = "db/ticket.db"


class TicketCloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("You don't have permission to close tickets.", ephemeral=True)
            return

        await interaction.response.send_message("Closing ticket in 3 seconds...")
        import asyncio
        await asyncio.sleep(3)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            await interaction.channel.send("I don't have permission to delete this channel.")


class TicketOpenView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        member = interaction.user

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT category_id, support_role_id FROM ticket_config WHERE guild_id = ?",
                (guild.id,)
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            await interaction.response.send_message("Ticket system is not configured. Ask an admin to run `/ticket setup`.", ephemeral=True)
            return

        category_id, support_role_id = row
        category = guild.get_channel(category_id) if category_id else None
        support_role = guild.get_role(support_role_id) if support_role_id else None

        # Check if user already has an open ticket
        existing = discord.utils.get(guild.text_channels, name=f"ticket-{member.name.lower()}")
        if existing:
            await interaction.response.send_message(f"You already have an open ticket: {existing.mention}", ephemeral=True)
            return

        # Set up permissions
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

        embed = discord.Embed(
            title="🎫 Support Ticket",
            description=(
                f"Hello {member.mention}, welcome to your ticket!\n\n"
                "Please describe your issue and a staff member will assist you shortly.\n\n"
                "Click **Close Ticket** when your issue is resolved."
            ),
            color=0xFF0000,
        )
        embed.set_footer(text=f"Ticket by {member}", icon_url=member.display_avatar.url)

        await ticket_channel.send(
            content=f"{member.mention}" + (f" | {support_role.mention}" if support_role else ""),
            embed=embed,
            view=TicketCloseView(),
        )

        await interaction.response.send_message(f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True)


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
                    panel_message TEXT
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
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def ticket_setup(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Ticket System Setup",
            description="Let's configure the ticket system step by step.",
            color=0xFF0000,
        )
        await ctx.send(embed=embed)

        def chk(m):
            return m.author == ctx.author and m.channel == ctx.channel

        # Step 1: Category
        await ctx.send("**Step 1:** Mention or send the ID of the **category** where ticket channels should be created (or type `skip` to use no category):")
        try:
            msg = await self.bot.wait_for("message", timeout=60, check=chk)
            category = None
            if msg.content.lower() != "skip":
                try:
                    cid = int(msg.content.strip("<#>"))
                    category = ctx.guild.get_channel(cid)
                    if not isinstance(category, discord.CategoryChannel):
                        await ctx.send("That's not a valid category. Skipping...")
                        category = None
                except ValueError:
                    await ctx.send("Invalid input. Skipping category...")
        except Exception:
            await ctx.send("Timed out.")
            return

        # Step 2: Support Role
        await ctx.send("**Step 2:** Mention the **support role** who can see all tickets (or type `skip`):")
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
                        await ctx.send("Invalid role. Skipping...")
        except Exception:
            await ctx.send("Timed out.")
            return

        # Step 3: Panel channel
        await ctx.send("**Step 3:** Mention the **channel** where the ticket panel (open button) should be sent:")
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
                    await ctx.send("Invalid channel.")
                    return
        except Exception:
            await ctx.send("Timed out.")
            return

        # Save config
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO ticket_config (guild_id, category_id, support_role_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    category_id = excluded.category_id,
                    support_role_id = excluded.support_role_id
                """,
                (ctx.guild.id, category.id if category else None, support_role.id if support_role else None),
            )
            await db.commit()

        # Send panel
        panel_embed = discord.Embed(
            title="🎫 Support Tickets",
            description="Click the button below to open a support ticket.\nA private channel will be created just for you.",
            color=0xFF0000,
        )
        if ctx.guild.icon:
            panel_embed.set_thumbnail(url=ctx.guild.icon.url)
        panel_embed.set_footer(text=ctx.guild.name)

        await panel_channel.send(embed=panel_embed, view=TicketOpenView())

        confirm = discord.Embed(
            title="✅ Ticket System Ready!",
            color=0xFF0000,
        )
        confirm.add_field(name="Category", value=category.mention if category else "None (no category)", inline=True)
        confirm.add_field(name="Support Role", value=support_role.mention if support_role else "None", inline=True)
        confirm.add_field(name="Panel Channel", value=panel_channel.mention, inline=True)
        await ctx.send(embed=confirm)

    @ticket.command(name="panel", help="Resend the ticket panel to a channel.")
    @commands.has_permissions(administrator=True)
    async def ticket_panel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel

        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()

        if not row:
            return await ctx.send(embed=discord.Embed(description=f"Ticket system not configured. Run `{ctx.prefix}ticket setup` first.", color=0xFF0000))

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
            return await ctx.send(embed=discord.Embed(description="This command can only be used inside a ticket channel.", color=0xFF0000))

        await ctx.send("Closing ticket in 3 seconds...")
        import asyncio
        await asyncio.sleep(3)
        try:
            await ctx.channel.delete(reason=f"Ticket closed by {ctx.author}")
        except discord.Forbidden:
            await ctx.send("I don't have permission to delete this channel.")

    @ticket.command(name="reset", help="Remove the ticket system configuration.")
    @commands.has_permissions(administrator=True)
    async def ticket_reset(self, ctx: commands.Context):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM ticket_config WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(description="✅ Ticket configuration has been reset.", color=0xFF0000))


async def setup(bot):
    await bot.add_cog(Ticket(bot))
