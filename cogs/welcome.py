import discord
from discord.ext import commands
from discord.ui import View, Select, Button
import aiosqlite
import asyncio
import re
import json
import os

DB_PATH = "db/welcome.db"


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
                    embed_data TEXT
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
        if not text:
            return ""
        lower_ph = {k.lower(): v for k, v in placeholders.items()}
        def replace_var(match):
            return str(lower_ph.get(match.group(1).lower(), f"{{{match.group(1)}}}"))
        return re.sub(r"\{(\w+)\}", replace_var, text)

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

        if not channel_id:
            return

        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return

        ph = self._build_placeholders(member)

        if welcome_type == "simple" and welcome_message:
            await channel.send(self._safe_format(welcome_message, ph))

        elif welcome_type == "embed" and embed_data:
            try:
                info = json.loads(embed_data)
                color_val = info.get("color", 0xFF0000)
                if isinstance(color_val, str):
                    try:
                        color_val = int(color_val.lstrip("#"), 16)
                    except Exception:
                        color_val = 0xFF0000

                embed = discord.Embed(
                    title=self._safe_format(info.get("title", ""), ph) or None,
                    description=self._safe_format(info.get("description", ""), ph) or None,
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
                thumbnail = self._safe_format(info.get("thumbnail", ""), ph)
                if thumbnail and thumbnail.startswith("http"):
                    embed.set_thumbnail(url=thumbnail)
                image = self._safe_format(info.get("image", ""), ph)
                if image and image.startswith("http"):
                    embed.set_image(url=image)

                content = self._safe_format(info.get("message", ""), ph) or None
                await channel.send(content=content, embed=embed)
            except Exception as e:
                print(f"[Welcome] Embed send error: {e}")

    @commands.hybrid_group(invoke_without_command=True, name="greet", help="Welcome message commands.")
    async def greet(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @greet.command(name="setup", help="Set up a welcome message for new members.")
    @commands.has_permissions(administrator=True)
    async def greet_setup(self, ctx):
        def chk(m):
            return m.author == ctx.author and m.channel == ctx.channel

        # Step 1: Choose type
        view = View(timeout=60)
        chosen = {"type": None}

        for label, cid, style in [
            ("Simple Text", "simple", discord.ButtonStyle.success),
            ("Embed", "embed", discord.ButtonStyle.primary),
            ("Cancel", "cancel", discord.ButtonStyle.danger),
        ]:
            btn = Button(label=label, style=style, custom_id=cid)
            async def make_cb(c):
                async def cb(interaction: discord.Interaction):
                    if interaction.user != ctx.author:
                        await interaction.response.send_message("Not yours.", ephemeral=True)
                        return
                    chosen["type"] = c
                    view.stop()
                    await interaction.response.defer()
                return cb
            btn.callback = await make_cb(cid)
            view.add_item(btn)

        type_msg = await ctx.send(embed=discord.Embed(
            title="Welcome Setup — Step 1",
            description="Choose welcome message type:",
            color=0xFF0000,
        ), view=view)

        await view.wait()
        await type_msg.delete()

        if chosen["type"] in (None, "cancel"):
            return await ctx.send("Setup cancelled.", delete_after=5)

        # Step 2: Welcome channel
        ch_msg = await ctx.send(embed=discord.Embed(
            description="**Step 2:** Mention the channel where welcome messages should be sent (e.g. `#welcome`):",
            color=0xFF0000,
        ))
        try:
            msg = await self.bot.wait_for("message", timeout=60, check=chk)
            if msg.channel_mentions:
                welcome_channel = msg.channel_mentions[0]
            else:
                try:
                    welcome_channel = ctx.guild.get_channel(int(msg.content.strip()))
                except Exception:
                    welcome_channel = None
            if not welcome_channel:
                return await ctx.send("❌ Invalid channel. Setup cancelled.")
        except asyncio.TimeoutError:
            return await ctx.send("⏰ Timed out.")
        await ch_msg.delete()

        if chosen["type"] == "simple":
            await self._simple_setup(ctx, chk, welcome_channel)
        else:
            await self._embed_setup(ctx, chk, welcome_channel)

    async def _simple_setup(self, ctx, chk, welcome_channel):
        vars_embed = discord.Embed(
            title="Available Placeholders",
            description=(
                "`{user}` — Mention\n`{user_name}` — Username\n`{user_id}` — User ID\n"
                "`{user_avatar}` — Avatar URL\n`{user_joindate}` — Join date\n"
                "`{server_name}` — Server name\n`{server_membercount}` — Member count"
            ),
            color=0xFF0000,
        )
        await ctx.send(embed=vars_embed)
        await ctx.send("**Type your welcome message:**")
        try:
            msg = await self.bot.wait_for("message", timeout=120, check=chk)
            message_content = msg.content
        except asyncio.TimeoutError:
            return await ctx.send("⏰ Timed out.")

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO welcome (guild_id, welcome_type, welcome_message, channel_id, embed_data) VALUES (?, ?, ?, ?, ?)",
                (ctx.guild.id, "simple", message_content, welcome_channel.id, None),
            )
            await db.commit()

        await ctx.send(embed=discord.Embed(
            description=f"✅ Simple welcome message saved! Channel: {welcome_channel.mention}",
            color=0xFF0000,
        ))

    async def _embed_setup(self, ctx, chk, welcome_channel):
        embed_data = {
            "title": "Welcome to {server_name}!",
            "description": "Hey {user}, welcome! You are member #{server_membercount}.",
            "color": 0xFF0000,
            "footer_text": "{server_name}",
            "footer_icon": "{server_icon}",
            "author_name": "",
            "author_icon": "",
            "thumbnail": "{user_avatar}",
            "image": "",
            "message": "",
        }

        def build_preview():
            ph = {
                "user": ctx.author.mention,
                "user_avatar": str(ctx.author.display_avatar.url),
                "user_name": ctx.author.name,
                "server_name": ctx.guild.name,
                "server_membercount": str(ctx.guild.member_count),
                "server_icon": str(ctx.guild.icon.url) if ctx.guild.icon else "",
            }
            color_val = embed_data["color"] if isinstance(embed_data["color"], int) else 0xFF0000
            e = discord.Embed(
                title=self._safe_format(embed_data.get("title", ""), ph) or None,
                description=self._safe_format(embed_data.get("description", ""), ph) or None,
                color=discord.Color(color_val),
            )
            ft = self._safe_format(embed_data.get("footer_text", ""), ph)
            if ft:
                fi = self._safe_format(embed_data.get("footer_icon", ""), ph)
                e.set_footer(text=ft, icon_url=fi if fi.startswith("http") else None)
            an = self._safe_format(embed_data.get("author_name", ""), ph)
            if an:
                ai = self._safe_format(embed_data.get("author_icon", ""), ph)
                e.set_author(name=an, icon_url=ai if ai.startswith("http") else None)
            th = self._safe_format(embed_data.get("thumbnail", ""), ph)
            if th and th.startswith("http"):
                e.set_thumbnail(url=th)
            img = self._safe_format(embed_data.get("image", ""), ph)
            if img and img.startswith("http"):
                e.set_image(url=img)
            return e

        fields = [
            ("title", "Title"),
            ("description", "Description"),
            ("color", "Color (hex, e.g. FF0000)"),
            ("footer_text", "Footer Text"),
            ("footer_icon", "Footer Icon URL or {server_icon}/{user_avatar}"),
            ("author_name", "Author Name"),
            ("thumbnail", "Thumbnail URL or {user_avatar}"),
            ("image", "Banner/Image URL (full width)"),
            ("message", "Message Content (outside embed)"),
        ]

        info_embed = discord.Embed(
            title="Embed Welcome Setup",
            description=(
                "I'll ask you for each field one by one.\n"
                "Type `skip` to keep the default value.\n\n"
                "**Placeholders:** `{user}` `{user_name}` `{user_avatar}` `{server_name}` `{server_membercount}` `{server_icon}`"
            ),
            color=0xFF0000,
        )
        await ctx.send(embed=info_embed)

        preview_msg = await ctx.send(content="**Live Preview:**", embed=build_preview())

        for key, label in fields:
            prompt = await ctx.send(embed=discord.Embed(
                description=f"**{label}:** Type value or `skip`:",
                color=0x2F3136,
            ))
            try:
                msg = await self.bot.wait_for("message", timeout=60, check=chk)
                if msg.content.lower() != "skip":
                    if key == "color":
                        try:
                            embed_data["color"] = int(msg.content.strip().lstrip("#"), 16)
                        except Exception:
                            await ctx.send("❌ Invalid hex. Using default red.", delete_after=3)
                    else:
                        embed_data[key] = msg.content.strip()
                await preview_msg.edit(embed=build_preview())
                await prompt.delete()
                try:
                    await msg.delete()
                except Exception:
                    pass
            except asyncio.TimeoutError:
                await prompt.delete()
                break

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO welcome (guild_id, welcome_type, welcome_message, channel_id, embed_data) VALUES (?, ?, ?, ?, ?)",
                (ctx.guild.id, "embed", None, welcome_channel.id, json.dumps(embed_data)),
            )
            await db.commit()

        await ctx.send(embed=discord.Embed(
            description=f"✅ Embed welcome saved! Channel: {welcome_channel.mention}",
            color=0xFF0000,
        ))

    @greet.command(name="channel", help="Change the welcome channel.")
    @commands.has_permissions(administrator=True)
    async def greet_channel(self, ctx, channel: discord.TextChannel):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
            if not row:
                return await ctx.send(embed=discord.Embed(description="No welcome config found. Run `greet setup` first.", color=0xFF0000))
            await db.execute("UPDATE welcome SET channel_id = ? WHERE guild_id = ?", (channel.id, ctx.guild.id))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"✅ Welcome channel updated to {channel.mention}!", color=0xFF0000))

    @greet.command(name="test", help="Send a test welcome message.")
    @commands.has_permissions(administrator=True)
    async def greet_test(self, ctx):
        await self.on_member_join(ctx.author)
        await ctx.send(embed=discord.Embed(description="✅ Test welcome sent!", color=0xFF0000), delete_after=5)

    @greet.command(name="config", help="View current welcome config.")
    @commands.has_permissions(administrator=True)
    async def greet_config(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT welcome_type, channel_id FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            return await ctx.send(embed=discord.Embed(description="No welcome config set.", color=0xFF0000))
        wtype, cid = row
        channel = ctx.guild.get_channel(cid) if cid else None
        embed = discord.Embed(title="Welcome Config", color=0xFF0000)
        embed.add_field(name="Type", value=wtype or "Not set")
        embed.add_field(name="Channel", value=channel.mention if channel else "Not set")
        await ctx.send(embed=embed)

    @greet.command(name="reset", help="Reset welcome configuration.")
    @commands.has_permissions(administrator=True)
    async def greet_reset(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM welcome WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(description="✅ Welcome config reset.", color=0xFF0000))


async def setup(bot):
    await bot.add_cog(Welcomer(bot))
