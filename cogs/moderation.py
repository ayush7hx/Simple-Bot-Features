import discord
from discord.ext import commands
from collections import defaultdict
import asyncio
import datetime

snipe_cache = {}


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        snipe_cache[message.channel.id] = message

    # --- BAN ---
    @commands.command(name="ban", help="Ban a member from the server.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role:
            return await ctx.send(embed=discord.Embed(description="❌ You can't ban someone with an equal or higher role.", color=0xFF0000))
        await member.ban(reason=f"{reason} | By {ctx.author}")
        embed = discord.Embed(description=f"🔨 **{member}** has been banned.\n**Reason:** {reason}", color=0xFF0000)
        embed.set_footer(text=f"By {ctx.author}")
        await ctx.send(embed=embed)

    # --- UNBAN ---
    @commands.command(name="unban", help="Unban a user by ID or username#discriminator.")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, *, user_id: int):
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user)
            await ctx.send(embed=discord.Embed(description=f"✅ **{user}** has been unbanned.", color=0xFF0000))
        except discord.NotFound:
            await ctx.send(embed=discord.Embed(description="❌ User not found or not banned.", color=0xFF0000))

    # --- KICK ---
    @commands.command(name="kick", help="Kick a member from the server.")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role:
            return await ctx.send(embed=discord.Embed(description="❌ You can't kick someone with an equal or higher role.", color=0xFF0000))
        await member.kick(reason=f"{reason} | By {ctx.author}")
        embed = discord.Embed(description=f"👢 **{member}** has been kicked.\n**Reason:** {reason}", color=0xFF0000)
        embed.set_footer(text=f"By {ctx.author}")
        await ctx.send(embed=embed)

    # --- TIMEOUT ---
    @commands.command(name="timeout", aliases=["mute"], help="Timeout a member for given minutes.")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, minutes: int = 10, *, reason: str = "No reason provided"):
        if member.top_role >= ctx.author.top_role:
            return await ctx.send(embed=discord.Embed(description="❌ Can't timeout someone with equal or higher role.", color=0xFF0000))
        until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.timeout(until, reason=f"{reason} | By {ctx.author}")
        embed = discord.Embed(
            description=f"⏱️ **{member}** has been timed out for **{minutes} minute(s)**.\n**Reason:** {reason}",
            color=0xFF0000,
        )
        embed.set_footer(text=f"By {ctx.author}")
        await ctx.send(embed=embed)

    # --- UNTIMEOUT ---
    @commands.command(name="untimeout", aliases=["unmute"], help="Remove timeout from a member.")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member):
        await member.timeout(None)
        await ctx.send(embed=discord.Embed(description=f"✅ Timeout removed from **{member}**.", color=0xFF0000))

    # --- WARN ---
    @commands.command(name="warn", help="Warn a member.")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        embed = discord.Embed(
            title="⚠️ Warning Issued",
            description=f"**{member.mention}** has been warned.\n**Reason:** {reason}",
            color=0xFF0000,
        )
        embed.set_footer(text=f"By {ctx.author}")
        await ctx.send(embed=embed)
        try:
            dm_embed = discord.Embed(
                title=f"⚠️ You were warned in {ctx.guild.name}",
                description=f"**Reason:** {reason}",
                color=0xFF0000,
            )
            await member.send(embed=dm_embed)
        except Exception:
            pass

    # --- PURGE ---
    @commands.command(name="purge", aliases=["clear"], help="Delete messages from a channel.")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int = 10):
        if amount < 1 or amount > 100:
            return await ctx.send(embed=discord.Embed(description="❌ Amount must be between 1 and 100.", color=0xFF0000))
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount)
        msg = await ctx.send(embed=discord.Embed(description=f"🗑️ Deleted **{len(deleted)}** messages.", color=0xFF0000))
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except Exception:
            pass

    # --- LOCK ---
    @commands.command(name="lock", help="Lock the current channel.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        await target.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send(embed=discord.Embed(description=f"🔒 {target.mention} has been **locked**.", color=0xFF0000))

    # --- UNLOCK ---
    @commands.command(name="unlock", help="Unlock the current channel.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        await target.set_permissions(ctx.guild.default_role, send_messages=None)
        await ctx.send(embed=discord.Embed(description=f"🔓 {target.mention} has been **unlocked**.", color=0xFF0000))

    # --- SNIPE ---
    @commands.command(name="snipe", help="Show the last deleted message in this channel.")
    @commands.has_permissions(manage_messages=True)
    async def snipe(self, ctx):
        msg = snipe_cache.get(ctx.channel.id)
        if not msg:
            return await ctx.send(embed=discord.Embed(description="❌ No deleted message found in this channel.", color=0xFF0000))
        embed = discord.Embed(
            description=msg.content or "*[No text content]*",
            color=0xFF0000,
            timestamp=msg.created_at,
        )
        embed.set_author(name=str(msg.author), icon_url=msg.author.display_avatar.url)
        embed.set_footer(text=f"Deleted in #{ctx.channel.name}")
        if msg.attachments:
            embed.set_image(url=msg.attachments[0].url)
        await ctx.send(embed=embed)

    # --- SLOWMODE ---
    @commands.command(name="slowmode", help="Set slowmode for a channel (seconds).")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int = 0):
        await ctx.channel.edit(slowmode_delay=seconds)
        if seconds == 0:
            await ctx.send(embed=discord.Embed(description="✅ Slowmode disabled.", color=0xFF0000))
        else:
            await ctx.send(embed=discord.Embed(description=f"✅ Slowmode set to **{seconds}s**.", color=0xFF0000))


async def setup(bot):
    await bot.add_cog(Moderation(bot))
