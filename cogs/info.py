import asyncio
import json
import os
import platform
from datetime import datetime, timedelta
from platform import python_version
from typing import Optional

import discord  # type: ignore
import humanize  # type: ignore
import psutil  # type: ignore
import pytz  # type: ignore
from discord import (
    Color,
    Embed,
    Permissions,
    TextChannel,  # type: ignore
    User,
    __version__,
    utils,
)
from discord.ext import commands
from discord.ext.commands import Cog, command, hybrid_command  # type: ignore
from discord.ui import Button, View  # type: ignore

from tools.bot import Pretend
from tools.conversion import Conversion
from tools.helpers import GreedContext
from tools.socials import get_instagram_user, get_tiktok_user
from tools.validators import ValidCommand

my_system = platform.uname()


class Info(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Information commands"
        self.conversion = Conversion()

    def create_bot_invite(self, user: User) -> View:
        """
        Create a view containing a button with the bot invite url
        """

        view = View()
        view.add_item(
            Button(
                label=f"invite {user.name}",
                url=utils.oauth_url(client_id=user.id, permissions=Permissions(8)),
            )
        )
        return view

    @command(name="tiktok")
    async def tiktok(self, ctx: GreedContext, *, username: str):
        try:
            data = await get_tiktok_user(username)
            embed = data.to_embed(ctx)
            return await ctx.send(embed=embed)
        except:
            return await ctx.send_warning(f"tiktok user {username} not found")

    @command(name="instagram")
    async def instagram(self, ctx: GreedContext, *, username: str):
        try:
            data = await get_instagram_user(username)
            embed = data.to_embed(ctx)
            return await ctx.send(embed=embed)
        except:
            return await ctx.send_warning(f"instagram user {username} not found")

    @command(name="creategif")
    async def creategif(self, ctx: GreedContext, *, url: str = None):
        return await self.conversion.do_conversion(ctx, url)

    @hybrid_command(name="commands", aliases=["h"])
    async def _help(self, ctx: GreedContext, *, command: ValidCommand = None):
        """
        The help command menu
        """

        if not command:
            return await ctx.send_help()
        else:
            return await ctx.send_help(command)

    @command()
    async def getbotinvite(self, ctx: GreedContext, *, member: User):
        """
        Get the bot invite based on it's id
        """

        if not member.bot:
            return await ctx.send_error("This is **not** a bot")

        await ctx.reply(ctx.author.mention, view=self.create_bot_invite(member))

    @hybrid_command(aliases=["up"])
    async def uptime(self, ctx: GreedContext):
        """
        Displays how long has the bot been online for
        """

        return await ctx.reply(
            embed=Embed(
                color=self.bot.color,
                description=f"<:greedOnlineTime:1246099284433178654> {ctx.author.mention}: **{self.bot.uptime}**",
            )
        )

    @command(aliases=["pi"])
    async def profileicon(self, ctx: GreedContext, *, member: discord.User = None):
        if member == None:
            member = ctx.author
        user = await self.bot.fetch_user(member.id)
        if user.banner == None:
            em = discord.Embed(
                color=0x8D7F64,
                description=f"{member.mention}: doesn't have a profile I can display.",
            )
            await ctx.reply(embed=em, mention_author=False)
        else:
            banner_url = user.banner.url
            avatar_url = user.avatar.url
            button1 = Button(label="Icon", url=avatar_url)
            button2 = Button(label="Banner", url=banner_url)
            e = discord.Embed(
                color=0x8D7F64,
                description=f"*Here is the icon and banner for [**{member.display_name}**](https://discord.com/users/{member.id})*",
            )
            e.set_author(
                name=f"{member.display_name}",
                icon_url=f"{member.avatar}",
                url=f"https://discord.com/users/{member.id}",
            )
            e.set_image(url=f"{banner_url}")
            e.set_thumbnail(url=f"{avatar_url}")
            view = View()
            view.add_item(button1)
            view.add_item(button2)
            await ctx.reply(embed=e, view=view, mention_author=False)

    @Cog.listener()
    async def on_command_completion(self, ctx: GreedContext):
        await self.bot.db.execute("""
            INSERT INTO metrics (command_usage)
            VALUES (1)
            ON CONFLICT (command_usage)
            DO UPDATE SET command_usage = metrics.command_usage + 1
        """)

    @command(name="status")
    async def status(self, ctx: GreedContext):
        """Displays bot statistics."""
        # Calculate uptime

        # Calculate bot ping
        latency = round(self.bot.latency * 1000)

        # Get bot process memory usage
        process = psutil.Process()
        memory_usage = process.memory_full_info().rss / 1024**2
        final_memory = round(memory_usage / 1024, 2)

        # Get shard information
        shard_id = ctx.guild.shard_id if ctx.guild else 0
        shard_count = self.bot.shard_count

        result = await self.bot.db.fetchrow("SELECT command_usage FROM metrics")
        commands_executed = result["command_usage"] if result else 0
        # Send statistics embed
        embed = discord.Embed(color=self.bot.color)
        embed.add_field(name="Uptime", value=self.bot.uptime, inline=True)
        embed.add_field(name="Ping", value=f"{latency}ms", inline=True)
        embed.add_field(name="Memory Usage", value=f"{final_memory} GB", inline=False)
        embed.add_field(name="Shard ID", value=str(shard_id), inline=True)
        embed.add_field(name="Shard Count", value=str(shard_count), inline=True)
        embed.add_field(name="Commands Executed", value=commands_executed, inline=True)
        await ctx.send(embed=embed)

    @hybrid_command()
    async def ping(self, ctx: GreedContext):
        """
        Check status of each bot shard
        """

        shard_id = ctx.guild.shard_id if ctx.guild else 0

        embed = Embed(
            color=self.bot.color,
            description=f"current client ping: `{round(self.bot.latency * 1000)}`ms with a total of ({self.bot.shard_count}) shards. Check other [shards status's](https://greed.best/status)",
        )

        await ctx.send(embed=embed)

    @hybrid_command(aliases=["inv", "link"])
    async def invite(self, ctx: GreedContext):
        """
        Send an invite link of the bot
        """

        await ctx.reply("greed is free btw", view=self.create_bot_invite(ctx.guild.me))

    @command()
    async def ready(self, ctx):
        online = "<:greedOnlineTime:1246099284433178654>"
        logss_channel_id = 1225240930466926652
        logss_channel = self.bot.get_channel(logss_channel_id)
        total_members = sum(guild.member_count for guild in self.bot.guilds)

        if logss_channel:
            embed = discord.Embed(
                color=self.bot.color,
                description=f"{online} {self.bot.user.name} serving **{len(self.bot.guilds)}** servers & **{total_members}** users at **{round(self.bot.latency * 1000)}ms**",
            )
            await logss_channel.send(embed=embed)
            await ctx.send("Notification sent!")
        else:
            await ctx.send("Log channel not found. Unable to send the message.")

    @hybrid_command(aliases=["bi", "bot", "info", "about"])
    async def botinfo(self, ctx: GreedContext):
        embed = discord.Embed(
            title=str(f"{self.bot.user.name} greed.best"),
            color=self.bot.color,
            timestamp=datetime.now(),
            description=f"multipurpose discord bot with aesthetics in mind serving over **{len(self.bot.guilds)}** with **{sum(g.member_count for g in self.bot.guilds):,}** members. For support [join our discord server](https://discord.gg/greedbot)",
        ).set_thumbnail(url=(self.bot.user.avatar or self.bot.user.default_avatar))

        embed.add_field(
            name="System",
            value=f"**commands:** {len(set(self.bot.walk_commands()))}\n**discord.py:** {__version__}\n**Python:** {python_version()}\n**Lines:** {self.bot.lines:,}",
        )

        view = discord.ui.View()
        support_button = discord.ui.Button(
            label="Support",
            url="https://discord.gg/greedbot",
            style=discord.ButtonStyle.url,
        )
        invite_button = discord.ui.Button(
            label="Invite",
            url="https://greed.best/invite",
            style=discord.ButtonStyle.url,
        )

        view.add_item(support_button)
        view.add_item(invite_button)

        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="channelinfo", aliases=["ci"])
    async def channelinfo(
        self, ctx: GreedContext, *, channel: Optional[TextChannel] = None
    ):
        """
        view information about a channel
        """

        channel = channel or ctx.channel

        embed = (
            discord.Embed(color=self.bot.color, title=channel.name)
            .set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar)
            .add_field(name="Channel ID", value=f"`{channel.id}`", inline=True)
            .add_field(name="Type", value=str(channel.type), inline=True)
            .add_field(
                name="Guild",
                value=f"{channel.guild.name} (`{channel.guild.id}`)",
                inline=True,
            )
            .add_field(
                name="Category",
                value=f"{channel.category.name} (`{channel.category.id}`)",
                inline=False,
            )
            .add_field(name="Topic", value=channel.topic or "N/A", inline=True)
            .add_field(
                name="Created At",
                value=f"{discord.utils.format_dt(channel.created_at, style='F')} ({discord.utils.format_dt(channel.created_at, style='R')})",
                inline=False,
            )
        )

        await ctx.send(embed=embed)

    @hybrid_command(name="song", aliases=["music", "beat", "songinfo"])
    async def song(self, ctx: GreedContext, *, title: str):
        """
        get information about a song
        """

        headers = {
            "X-RapidAPI-Key": str(self.songkey),
            "X-RapidAPI-Host": "genius-song-lyrics1.p.rapidapi.com",
        }
        query = {"q": title, "per_page": 1, "page": 1}

        response = await self.bot.session.get_json(
            "https://genius-song-lyrics1.p.rapidapi.com/search,
            headers=headers,
            params=query,
        )

        if not response:
            return await ctx.send_warning(f"No results found for **{title}**")

        info = response["hits"][0]["result"]

        try:
            thumbnail = info["song_art_image_url"]
        except KeyError:
            thumbnail = None

        if thumbnail:
            color = await self.bot.dominant_color(str(thumbnail))
        else:
            color = self.bot.color

        embed = (
            discord.Embed(
                title=info["title"],
                url=info["url"],
                color=color,
                timestamp=datetime.datetime.now(),
            )
            .set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            .add_field(
                name="Artists",
                value=self.shorten(info["artist_names"], 33),
                inline=False,
            )
            .add_field(
                name="Release Date", value=info["release_date_for_display"], inline=True
            )
            .add_field(name="Hot", value=info["stats"]["hot"], inline=True)
            .add_field(name="Instrumental", value=info["instrumental"], inline=True)
            .set_footer(text=f"{int(info['stats']['pageviews']):,} views")
            .set_thumbnail(url=thumbnail or None)
        )

        if rows := info["featured_artists"]:
            artists = []

            for row in rows:
                artists.append(row["name"])

            embed.add_field(name="More Artists", value=", ".join(artists))

        await ctx.send(embed=embed)

    @commands.command(name="color", aliases=["colour"])
    async def color(self, ctx: GreedContext, *, color: Color):
        """
        view info about a color
        """

        embed = discord.Embed(color=color)
        embed.set_author(name=f"Showing hex code: {color}")

        embed.add_field(
            name="RGB Value",
            value=", ".join([str(x) for x in color.to_rgb()]),
            inline=True,
        )
        embed.add_field(name="INT", value=color.value, inline=True)

        embed.set_thumbnail(
            url=(
                "https://place-hold.it/250x219/"
                + str(color).replace("#", "")
                + "?text=%20"
            )
        )

        return await ctx.send(embed=embed)


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Info(bot))
