import asyncio
import datetime
import json
import random
from functools import partial, wraps
from io import BytesIO
from math import sqrt
from typing import Any, List, Optional, Union

import aiohttp
import dateutil.parser
import discord
import humanfriendly
import humanize
import pytz
import requests
import uwuify
from deep_translator import GoogleTranslator
from deep_translator.exceptions import LanguageNotSupportedException
from discord import (
    Attachment,
    CategoryChannel,
    Embed,
    Emoji,
    Interaction,
    Member,
    Message,
    PartialEmoji,
    Role,
    TextChannel,
    app_commands,
)
from discord.ext import commands
from discord.ext.commands import (
    bot_has_guild_permissions,
    bot_has_permissions,
    command,
    group,
    has_guild_permissions,
    has_permissions,
    hybrid_command,
    hybrid_group,
)
from PIL import Image
from shazamio import Shazam

from tools.bot import Pretend
from tools.handlers.socials.cashapp import CashappUser
from tools.handlers.socials.ebio import EbioUser
from tools.handlers.socials.github import GithubUser
from tools.handlers.socials.instagram import InstagramUser
from tools.handlers.socials.roblox import RobloxUser
from tools.handlers.socials.snapchat import SnapUser
from tools.handlers.socials.tiktok import TikTokUser
from tools.handlers.socials.weather import WeatherLocation
from tools.helpers import GreedContext
from tools.misc.utils import (
    BdayDate,
    BdayMember,
    Timezone,
    TimezoneLocation,
    TimezoneMember,
)
from tools.misc.views import Donate
from tools.predicates import is_afk, is_there_a_reminder, reminder_exists
from tools.validators import ValidMessage, ValidTime
from ttapi import TikTokApi


def async_executor():
    def outer(func):
        @wraps(func)
        def inner(*args, **kwargs):
            task = partial(func, *args, **kwargs)
            return asyncio.get_event_loop().run_in_executor(None, task)

        return inner

    return outer


@async_executor()
def _collage_open(image: BytesIO):
    image = (
        Image.open(image)
        .convert("RGBA")
        .resize(
            (
                256,
                256,
            )
        )
    )
    return image


async def _collage_read(image: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(image) as response:
            try:
                return await _collage_open(BytesIO(await response.read()))
            except:
                return None


async def _collage_paste(image: Image, x: int, y: int, background: Image):
    background.paste(
        image,
        (
            x * 256,
            y * 256,
        ),
    )


async def collage(images: List[str]):
    tasks = list()
    for image in images:
        tasks.append(_collage_read(image))

    images = [image for image in await asyncio.gather(*tasks) if image]
    if not images:
        return None

    rows = int(sqrt(len(images)))
    columns = (len(images) + rows - 1) // rows

    background = Image.new(
        "RGBA",
        (
            columns * 256,
            rows * 256,
        ),
    )
    tasks = list()
    for i, image in enumerate(images):
        tasks.append(_collage_paste(image, i % columns, i // columns, background))
    await asyncio.gather(*tasks)

    buffer = BytesIO()
    background.save(
        buffer,
        format="png",
    )
    buffer.seek(0)

    background.close()
    for image in images:
        image.close()

    return discord.File(
        buffer,
        filename="collage.png",
    )


class Utility(commands.Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.tz = Timezone(bot)
        self.description = "Utility commands"
        self.tiktok = TikTokApi(debug=True)
        self.afk_cd = commands.CooldownMapping.from_cooldown(
            3, 3, commands.BucketType.channel
        )

    def human_format(self, number: int) -> str:
        """
        Humanize a number, if the case
        """

        if number > 999:
            return humanize.naturalsize(number, False, True)

        return number.__str__()

    def afk_ratelimit(self, message: discord.Message) -> Optional[int]:
        """
        Cooldown for the afk message event
        """

        bucket = self.afk_cd.get_bucket(message)
        return bucket.update_rate_limit()

    async def cache_profile(self, member: discord.User) -> Any:
        """
        Cache someone's banner
        """

        if member.banner:
            banner = member.banner.url
        else:
            banner = None

        return await self.bot.cache.set(
            f"profile-{member.id}", {"banner": banner}, 3600
        )

    def get_joined_date(self, date) -> str:
        if date.month < 10:
            month = (self.tz.months.get(date.month))[:3]
        else:
            month = (self.tz.months.get(date.month))[:3]

        return f"Joined {month} {date.day} {str(date.year)}"

    @commands.Cog.listener("on_message")
    async def afk_listener(self, message: discord.Message):
        if message.is_system():
            return

        if not message.guild:
            return

        if not message.author:
            return

        if message.author.bot:
            return

        if check := await self.bot.db.fetchrow(
            "SELECT * FROM afk WHERE guild_id = $1 AND user_id = $2",
            message.guild.id,
            message.author.id,
        ):
            ctx = await self.bot.get_context(message)
            time = check["time"]
            await self.bot.db.execute(
                "DELETE FROM afk WHERE guild_id = $1 AND user_id = $2",
                message.guild.id,
                message.author.id,
            )
            embed = discord.Embed(
                color=self.bot.color,
                description=f"👋 {ctx.author.mention}: Welcome back! You were gone for **{humanize.precisedelta(datetime.datetime.fromtimestamp(time.timestamp()), format='%0.0f')}**",
            )
            return await ctx.send(embed=embed)

        for mention in message.mentions:
            check = await self.bot.db.fetchrow(
                "SELECT * FROM afk WHERE guild_id = $1 AND user_id = $2",
                message.guild.id,
                mention.id,
            )
            if check:
                if self.afk_ratelimit(message):
                    continue

                ctx = await self.bot.get_context(message)
                time = check["time"]
                embed = discord.Embed(
                    color=self.bot.color,
                    description=f"👋 {ctx.author.mention}: **{mention.name}** is **AFK** for **{humanize.precisedelta(datetime.datetime.fromtimestamp(time.timestamp()), format='%0.0f')}** - {check['reason']}",
                )
                return await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if (before.avatar != after.avatar) or (before.banner != after.banner):
            cache = self.bot.cache.get(f"profile-{before.id}")
            if cache:
                await self.cache_profile(after)

    @commands.command(aliases=["uwu"])
    async def uwuify(self, ctx: GreedContext, *, message: str):
        """
        Convert a message to the uwu format
        """

        flags = uwuify.YU | uwuify.STUTTER
        embed = discord.Embed(
            color=self.bot.color, description=uwuify.uwu(message, flags=flags)
        )
        return await ctx.send(embed=embed)

    @commands.command(name="screenshot", aliases=["ss"])
    async def screenshot(
        self, ctx: GreedContext, url: str, wait: int = 0, full_page: bool = False
    ):
        """
        Take a screenshot of a url
        """
        embed = await self.bot.rival.screenshot(
            ctx, url, ctx.channel.is_nsfw(), full_page, wait
        )
        return await ctx.send(embed=embed) 

    @commands.command(name="transcribe", aliases=["voice2text", "v2t"])
    async def transcribe(self, ctx: GreedContext):
        """
        Transcribe a voice message
        """
        data = await self.bot.rival.transcribe(ctx)
        if not data:
            return await ctx.send_warning("Could not transcribe the voice message")
        return await ctx.send(
            embed=discord.Embed(color=self.bot.color, description=data.text).set_author(
                name=data.message.author.display_name,
                icon_url=data.message.author.avatar,
            )
        )

    @commands.command(aliases=["clearavs", "clearavh", "clearavatarhistory"])
    async def clearavatars(self, ctx: GreedContext):
        """
        Clear your avatar history
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM avatars WHERE user_id = $1", ctx.author.id
        )
        if not check:
            return await ctx.send_warning("There are no avatars saved for you")

        async def yes_func(interaction: discord.Interaction):
            await self.bot.db.execute(
                "DELETE FROM avatars WHERE user_id = $1", interaction.user.id
            )
            return await interaction.response.edit_message(
                embed=discord.Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {interaction.user.mention}: Cleared your avatar history",
                ),
                view=None,
            )

        async def no_func(interaction: discord.Interaction):
            return await interaction.response.edit_message(
                embed=discord.Embed(
                    color=self.bot.color,
                    description=f"{interaction.user.mention}: Aborting action",
                ),
                view=None,
            )

        await ctx.confirmation_send(
            "Are you sure you want to **clear** your avatar history?", yes_func, no_func
        )

    @commands.command(aliases=["firstmsg"])
    async def firstmessage(
        self,
        ctx: GreedContext,
        *,
        channel: discord.TextChannel = commands.CurrentChannel,
    ):
        """
        Get the first message in a channel
        """

        message = [mes async for mes in channel.history(limit=1, oldest_first=True)][0]
        await ctx.pretend_send(
            f"the first message sent in {channel.mention} - [**jump**]({message.jump_url})"
        )

    @commands.command(aliases=["guildvanity"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def gv(self, ctx: commands.Context):
        if ctx.guild.vanity_url_code is None:
            embed = discord.Embed(
                color=0x2F3136, description=f"> **This server does not have a vanity.**"
            )
            embed.set_footer(text="No Vanity")

        elif ctx.guild.vanity_url_code is not None:
            embed = discord.Embed(
                color=0x2F3136,
                description=f"> **Guild Vanity** /{ctx.guild.vanity_url_code}",
            )

        await ctx.send(embed=embed)

    @commands.command(name="avatarhistory", aliases=["avh", "avatars"], disabled=True)
    async def avatarhistory(
        self,
        ctx: GreedContext,
        *,
        user: Union[discord.Member, discord.User] = commands.Author,
    ):
        if (
            await self.bot.db.fetchval(
                """SELECT count(*) FROM avatars WHERE user_id = $1""", user.id
            )
            == 0
        ):
            return await ctx.send_warning(f"no **avatars** saved for you")
        avatars = [
            record.avatar
            for record in await self.bot.db.fetch(
                "SELECT avatar FROM avatars WHERE user_id = $1 ORDER BY ts DESC",
                user.id,
            )
        ]
        file = await collage(avatars)
        embed = discord.Embed(
            description=f"> {user.name}'s **avatar history**", color=self.bot.color
        )
        return await ctx.send(embed=embed, file=file)

    @commands.hybrid_command(aliases=["av"])
    async def avatar(
        self,
        ctx: GreedContext,
        *,
        member: Union[discord.Member, discord.User] = commands.Author,
    ):
        """
        Return someone's avatar
        """

        embed = discord.Embed(
            color=await self.bot.dominant_color(member.display_avatar.url),
            title=f"{member.name}'s avatar",
            url=member.display_avatar.url,
        )

        embed.set_image(url=member.display_avatar.url)
        return await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["sav"])
    async def serveravatar(
        self, ctx: GreedContext, *, member: Union[discord.Member, discord.User] = None
    ):
        """
        Return someone's avatar
        """
        if member is None:
            member = ctx.author

        embed = discord.Embed(
            color=await self.bot.dominant_color(member.guild_avatar.url),
            title=f"{member.name}'s server avatar",
            url=member.guild_avatar.url,
        )

        embed.set_image(url=member.guild_avatar.url)
        return await ctx.send(embed=embed)

    @commands.command(aliases=["pastusernanes", "usernames", "oldnames", "pastnames"])
    async def names(self, ctx: GreedContext, *, user: discord.User = commands.Author):
        """
        Check a member's past usernames
        """

        results = await self.bot.db.fetch(
            "SELECT * FROM usernames WHERE user_id = $1", user.id
        )
        if len(results) == 0:
            return await ctx.send_error("This user doesn't have past usernames")

        users = sorted(results, key=lambda m: m["time"], reverse=True)

        return await ctx.paginate(
            [
                f"**{result['user_name']}** - {discord.utils.format_dt(datetime.datetime.fromtimestamp(result['time']), style='R')}"
                for result in users
            ],
            f"Username changes ({len(users)})",
            {"name": user.name, "icon_url": user.display_avatar.url},
        )

    @commands.command(aliases=["clearusernames", "deletenames", "deleteusernames"])
    async def clearnames(self, ctx: GreedContext):
        """clear your username history"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM usernames WHERE user_id = $1", ctx.author.id
        )
        if not check:
            return await ctx.send_warning("There are no usernames saved for you")

        async def yes_func(interaction: discord.Interaction):
            await self.bot.db.execute(
                "DELETE FROM usernames WHERE user_id = $1", interaction.user.id
            )
            return await interaction.response.edit_message(
                embed=discord.Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {interaction.user.mention}: Cleared your username history",
                ),
                view=None,
            )

        async def no_func(interaction: discord.Interaction):
            return await interaction.response.edit_message(
                embed=discord.Embed(
                    color=self.bot.color,
                    description=f"{interaction.user.mention}: Aborting action",
                ),
                view=None,
            )

        await ctx.confirmation_send(
            "Are you sure you want to **clear** your username history?",
            yes_func,
            no_func,
        )

    @commands.command(name="banner", aliases=["userbanner"])
    async def user_banner(
        self, ctx: GreedContext, *, member: discord.User = commands.Author
    ):
        """
        Get someone's banner
        """

        cache = self.bot.cache.get(f"profile-{member.id}")

        if cache:
            banner = cache["banner"]

            if banner is None:
                return await ctx.send_error(f"{member.mention} doesn't have a banner")

        else:
            user = await self.bot.fetch_user(member.id)

            if not user.banner:
                await self.cache_profile(user)
                return await ctx.send_error(f"{member.mention} doesn't have a banner")

            banner = user.banner.url

        embed = discord.Embed(
            color=await self.bot.dominant_color(banner),
            title=f"{member.name}'s banner",
            url=banner,
        )
        embed.set_image(url=banner)
        return await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["ri"])
    async def roleinfo(self, ctx: GreedContext, *, role: Optional[discord.Role] = None):
        """
        Information about a role
        """

        if role is None:
            role = ctx.author.top_role

        embed = (
            discord.Embed(
                color=role.color if role.color.value != 0 else self.bot.color,
                title=role.name,
            )
            .set_author(
                name=ctx.author.name,
                icon_url=role.display_icon
                if isinstance(role.display_icon, discord.Asset)
                else None,
            )
            .add_field(name="Role ID", value=f"`{role.id}`")
            .add_field(
                name="Role color",
                value=f"`#{hex(role.color.value)[2:]}`"
                if role.color.value != 0
                else "No color",
            )
            .add_field(
                name="Created",
                value=f"{discord.utils.format_dt(role.created_at, style='f')} **{self.bot.humanize_date(role.created_at.replace(tzinfo=None))}**",
                inline=False,
            )
            .add_field(
                name=f"{len(role.members)} Member{'s' if len(role.members) != 1 else ''}",
                value=", ".join([str(m) for m in role.members])
                if len(role.members) < 7
                else f"{', '.join([str(m) for m in role.members][:7])} + {len(role.members)-7} others",
                inline=False,
            )
        )
        await ctx.send(embed=embed)

    @commands.command(name="image", aliases=["img", "googleimage", "images"])
    async def image(self, ctx: GreedContext, *, query: str):
        if ctx.channel.is_nsfw():
            nsfw = True
        else:
            nsfw = False
        try:
            results = await self.bot.rival.google_image(query, nsfw)
        except:
            return await ctx.send_warning("no results found")
        if len(results.results) == 0:
            return await ctx.send_warning("no results found")
        embeds = []
        for i, result in enumerate(results.results, start=1):
            embed = discord.Embed(
                color=discord.Color.from_str(f"{result.color}"),
                title=f"results for {query}",
                url=result.url,
            )
            embed.set_image(url=result.url)
            embed.set_author(
                name=str(ctx.author), icon_url=ctx.author.display_avatar.url
            )
            embed.set_footer(text=f"Page {i}/{len(results.results)} | greed")
            embeds.append(embed)
        return await ctx.paginator(embeds)

    # @commands.command()
    # async def purchase(self, ctx):
    #     embed = discord.Embed(title="greed payments",
    #         description="<:developer:1206296902631694336>  **[$10 payment](https://buy.stripe.com/dR6bMBa0ogh1dSUaEE), [$5 payment](https://buy.stripe.com/6oEeYN0pO4yjdSU7su)**\n"
    #         "<:paypal:1206296901398560798> - **[paypal](https://www.paypal.com/paypalme/lietomalice)**\n\n"
    #         "**$10 dollar payment comes with greed 2\n$5 dollar payment comes only with greed\n\n"
    #         "> open a ticket in [support](https://https://discord.gg/greedbot) and send proof of purchase with your user ID and server invite.**",
    #         color=self.bot.color)
    #     await ctx.send(embed=embed)

    @commands.command()
    async def donate(self, ctx):
        embed = discord.Embed(
            title="Donator",
            description="<:blvd_greenstar:1218906476639162419> **boosting the [support server](https://https://discord.gg/greedbot) will grant you donator perks**\n<:Cashapp:1218661725814132781> **buying either versions of greed will grant you donator**\n\n> <:twingklegreen:1218661731182837845> **if you dont want donator perks you can let one of the staff know in the ticket when buying greed.**",
            color=self.bot.color,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def invites(
        self, ctx: GreedContext, *, member: discord.Member = commands.Author
    ):
        """
        returns the number of invites you have in the server
        """

        invites = await ctx.guild.invites()
        await ctx.pretend_send(
            f"{f'{member.mention} has' if member.id != ctx.author.id else 'You have'} **{sum(invite.uses for invite in invites if invite.inviter == member)} invites**"
        )

    @commands.command(aliases=["cs"], brief="manage messages")
    @commands.has_guild_permissions(manage_messages=True)
    async def clearsnipes(self, ctx: GreedContext):
        """
        Clear the snipes from the channel
        """

        for i in ["snipe", "edit_snipe", "reaction_snipe"]:
            snipes = self.bot.cache.get(i)

            if snipes:
                for s in [m for m in snipes if m["channel"] == ctx.channel.id]:
                    snipes.remove(s)
                await self.bot.cache.set(i, snipes)

        await ctx.send_success("Cleared all snipes from this channel")

    @commands.command(aliases=["rs"])
    async def reactionsnipe(self, ctx: GreedContext, index: int = 1):
        """
        Get the most recent message with a reaction removed in this channel
        """

        if not self.bot.cache.get("reaction_snipe"):
            return await ctx.send_warning("No reaction snipes found in this channel")

        snipes = [
            s
            for s in self.bot.cache.get("reaction_snipe")
            if s["channel"] == ctx.channel.id
        ]

        if len(snipes) == 0:
            return await ctx.send_warning("No reaction snipes found in this channel")

        if index > len(snipes):
            return await ctx.send_warning(
                f"There are only **{len(snipes)}** reaction snipes in this channel"
            )

        result = snipes[::-1][index - 1]
        try:
            message = await ctx.channel.fetch_message(result["message"])
            return await ctx.pretend_send(
                f"**{result['user']}** reacted with {result['reaction']} **{self.bot.humanize_date(datetime.datetime.fromtimestamp(int(result['created_at'])))}** [**here**]({message.jump_url})"
            )
        except:
            return await ctx.pretend_send(
                f"**{result['user']}** reacted with {result['reaction']} **{self.bot.humanize_date(datetime.datetime.fromtimestamp(int(result['created_at'])))}**"
            )

    @commands.command(aliases=["es"])
    async def editsnipe(self, ctx: GreedContext, index: int = 1):
        """
        Get the most recent edited message in the channel
        """

        if not self.bot.cache.get("edit_snipe"):
            return await ctx.send_warning("No edit snipes found in this channel")

        snipes = [
            s
            for s in self.bot.cache.get("edit_snipe")
            if s["channel"] == ctx.channel.id
        ]

        if len(snipes) == 0:
            return await ctx.send_warning("No edit snipes found in this channel")

        if index > len(snipes):
            return await ctx.send_warning(
                f"There are only **{len(snipes)}** edit snipes in this channel"
            )

        result = snipes[::-1][index - 1]
        embed = (
            discord.Embed(color=self.bot.color)
            .set_author(name=result["name"], icon_url=result["avatar"])
            .set_footer(text=f"{index}/{len(snipes)}")
        )

        for m in ["before", "after"]:
            embed.add_field(name=m, value=result[m])

        return await ctx.send(embed=embed)

    @commands.command(aliases=["s"])
    async def snipe(self, ctx: GreedContext, index: int = 1):
        """
        Get the most recent deleted message in the channel
        """

        if not self.bot.cache.get("snipe"):
            return await ctx.send_warning("No snipes found in this channel")

        snipes = [
            s for s in self.bot.cache.get("snipe") if s["channel"] == ctx.channel.id
        ]

        if len(snipes) == 0:
            return await ctx.send_warning("No snipes found in this channel")

        if index > len(snipes):
            return await ctx.send_warning(
                f"There are only **{len(snipes)}** snipes in this channel"
            )

        result = snipes[::-1][index - 1]
        embed = (
            discord.Embed(
                color=self.bot.color,
                description=result["message"],
                timestamp=datetime.datetime.fromtimestamp(result["created_at"]).replace(
                    tzinfo=None
                ),
            )
            .set_author(name=result["name"], icon_url=result["avatar"])
            .set_footer(text=f"{index}/{len(snipes)}")
        )

        if len(result["stickers"]) > 0:
            sticker: discord.StickerItem = result["stickers"][0]
            embed.set_image(url=sticker.url)
        else:
            if len(result["attachments"]) > 0:
                attachment: discord.Attachment = result["attachments"][0]
                if ".mp4" in attachment.filename or ".mov" in attachment.filename:
                    file = discord.File(
                        BytesIO(await attachment.read()), filename=attachment.filename
                    )
                    return await ctx.send(embed=embed, file=file)
                else:
                    embed.set_image(url=attachment.url)

        return await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["mc"])
    async def membercount(self, ctx: GreedContext, invite: discord.Invite = None):
        """
        Returns the number of members in your server or the server given
        """

        if invite:
            embed = discord.Embed(
                color=self.bot.color,
                description=f"> **members:** {invite.approximate_member_count:,}",
            ).set_author(
                name=f"{invite.guild.name}'s statistics", icon_url=invite.guild.icon
            )
        else:
            embed = discord.Embed(
                color=self.bot.color,
                description=f">>> **humans** - {len(set(m for m in ctx.guild.members if not m.bot)):,}\n**bots** - {len(set(m for m in ctx.guild.members if m.bot)):,}\n**total** - {ctx.guild.member_count:,}",
            ).set_author(
                icon_url=ctx.guild.icon,
                name=f"{ctx.guild.name}'s statistics (+{len([m for m in ctx.guild.members if (datetime.datetime.now() - m.joined_at.replace(tzinfo=None)).total_seconds() < 3600*24])})",
            )

        return await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["si"])
    async def serverinfo(self, ctx: GreedContext, invite: discord.Invite = None):
        """
        Get the information about a server
        """

        if invite:
            embed = discord.Embed(
                color=self.bot.color, title=f"Invite code: {invite.code}"
            ).add_field(
                name="Invite",
                value=f"**channel:** {invite.channel.name} ({invite.channel.type})\n**id:** `{invite.channel.id}`\n**expires:** {f'yes ({self.bot.humanize_date(invite.expires_at.replace(tzinfo=None))})' if invite.expires_at else 'no'}\n**uses:** {invite.uses or 'unknown'}",
            )

            if invite.guild:
                embed.description = invite.guild.description or ""
                embed.set_thumbnail(url=invite.guild.icon).add_field(
                    name="Server",
                    value=f"**name:** {invite.guild.name}\n**id:** `{invite.guild.id}`\n**members:** {invite.approximate_member_count:,}\n**created**: {discord.utils.format_dt(invite.created_at, style='R') if invite.created_at else 'N/A'}",
                )

        else:
            servers = sorted(
                self.bot.guilds, key=lambda g: g.member_count, reverse=True
            )
            embed = (
                discord.Embed(
                    color=self.bot.color,
                    title=ctx.guild.name,
                    description=f"{ctx.guild.description or ''}\n\nCreated on {discord.utils.format_dt(ctx.guild.created_at, style='D')} {discord.utils.format_dt(ctx.guild.created_at, style='R')}\nJoined on {discord.utils.format_dt(ctx.guild.me.joined_at, style='D')} {discord.utils.format_dt(ctx.guild.me.joined_at, style='R')}",
                )
                .set_author(
                    name=f"{ctx.guild.owner} ({ctx.guild.owner_id})",
                    icon_url=ctx.guild.owner.display_avatar.url,
                )
                .set_thumbnail(url=ctx.guild.icon)
                .add_field(
                    name="Counts",
                    value=f">>> **Roles:** {len(ctx.guild.roles):,}\n**Emojis:** {len(ctx.guild.emojis):,}\n**Stickers:** {len(ctx.guild.stickers):,}",
                )
                .add_field(
                    name="Members",
                    value=f">>> **Users:** {len(set(i for i in ctx.guild.members if not i.bot)):,}\n**Bots:** {len(set(i for i in ctx.guild.members if i.bot)):,}\n**Total:** {ctx.guild.member_count:,}",
                )
                .add_field(
                    name="Channels",
                    value=f">>> **Text:** {len(ctx.guild.text_channels):,}\n**Voice:** {len(ctx.guild.voice_channels):,}\n**Categories:** {len(ctx.guild.categories):,}",
                )
                .add_field(
                    name="Info",
                    value=f">>> **Vanity:** {ctx.guild.vanity_url_code or 'N/A'}\n**Popularity:** {servers.index(ctx.guild)+1}/{len(self.bot.guilds)}",
                )
            )
            embed.add_field(
                name="Boost",
                value=f">>> **Boosts:** {ctx.guild.premium_subscription_count:,}\n**Level:** {ctx.guild.premium_tier}\n**Boosters:** {len(ctx.guild.premium_subscribers)}",
            ).add_field(
                name="Design",
                value=f">>> **Icon:** {f'[**here**]({ctx.guild.icon})' if ctx.guild.icon else 'N/A'}\n**Banner:**  {f'[**here**]({ctx.guild.banner})' if ctx.guild.banner else 'N/A'}\n**Splash:**  {f'[**here**]({ctx.guild.splash})' if ctx.guild.splash else 'N/A'}",
            ).set_footer(text=f"ID {ctx.guild.id}")

        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["user", "ui", "whois"])
    async def userinfo(
        self,
        ctx: GreedContext,
        *,
        member: Union[discord.Member, discord.User] = commands.Author,
    ):
        """
        Returns information about an user
        """

        def vc(mem: discord.Member):
            if mem.voice:
                channelname = mem.voice.channel.name
                deaf = (
                    "<:CureDeafen:1206966622489804800>"
                    if mem.voice.self_deaf or mem.voice.deaf
                    else "<:CureUndeafen:1206967875588333578>"
                )
                mute = (
                    "<:CureMuted:1206966623987171381>"
                    if mem.voice.self_mute or mem.voice.mute
                    else "<:CureUnmuted:1206966625140609084>"
                )
                stream = (
                    "<:status_streaming:1206966626784772159>"
                    if mem.voice.self_stream
                    else ""
                )
                video = "<:rename:1203422971646054461>" if mem.voice.self_video else ""
                channelmembers = (
                    f"with {len(mem.voice.channel.members)-1} other member{'s' if len(mem.voice.channel.members) > 2 else ''}"
                    if len(mem.voice.channel.members) > 1
                    else ""
                )
                return f"{deaf} {mute} {stream} {video} **in voice channel** {channelname} {channelmembers}\n"
            return ""

        embed = (
            discord.Embed(
                color=await self.bot.dominant_color(member.display_avatar),
                description=f"**{member}**",
            )
            .set_author(
                name=f"{member.name} ({member.id})", icon_url=member.display_avatar.url
            )
            .set_thumbnail(url=member.display_avatar.url)
            .add_field(
                name="Created",
                value=f"{discord.utils.format_dt(member.created_at, style='D')}\n{discord.utils.format_dt(member.created_at, style='R')}",
            )
        )

        if not isinstance(member, discord.ClientUser):
            embed.set_footer(text=f"{len(member.mutual_guilds):,} server(s)")

        if isinstance(member, discord.Member):
            members = sorted(ctx.guild.members, key=lambda m: m.joined_at)
            embed.description += vc(member)

            if not isinstance(member, discord.ClientUser):
                embed.set_footer(
                    text=f"Join position: {members.index(member)+1:,}, {len(member.mutual_guilds):,} server(s)"
                )

            embed.add_field(
                name="Joined",
                value=f"{discord.utils.format_dt(member.joined_at, style='D')}\n{discord.utils.format_dt(member.joined_at, style='R')}",
            )

            if member.premium_since:
                embed.add_field(
                    name="Boosted",
                    value=f"{discord.utils.format_dt(member.premium_since, style='D')}\n{discord.utils.format_dt(member.premium_since, style='R')}",
                )

            roles = member.roles[1:][::-1]

            if len(roles) > 0:
                embed.add_field(
                    name=f"Roles ({len(roles)})",
                    value=" ".join([r.mention for r in roles])
                    if len(roles) < 5
                    else " ".join([r.mention for r in roles[:4]])
                    + f" ... and {len(roles)-4} more",
                    inline=False,
                )

        await ctx.send(embed=embed)

    @commands.hybrid_command()
    async def weather(self, ctx: GreedContext, *, location: WeatherLocation):
        """
        Returns the weather of a location
        """

        embed = (
            discord.Embed(
                color=self.bot.color,
                title=f"{location.condition} in {location.place}, {location.country}",
                timestamp=location.time,
            )
            .set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            .set_thumbnail(url=location.condition_image)
            .add_field(
                name="Temperature",
                value=f"{location.temp_c} °C / {location.temp_f} °F",
                inline=False,
            )
            .add_field(name="Humidity", value=f"{location.humidity}%", inline=False)
            .add_field(
                name="Wind",
                value=f"{location.wind_mph} mph / {location.wind_kph} kph",
                inline=False,
            )
        )

        return await ctx.send(embed=embed)

    @commands.command(
        name="roblox",
        description="Shows information on a Roblox user",
        usage=";roblox <username>",
    )
    async def roblox(self, ctx, username):
        try:
            users_json = requests.get(
                f"https://www.roblox.com/search/users/results?keyword={username}&maxRows=1&startIndex=0"
            )
            users = json.loads(users_json.text)

            if "UserSearchResults" not in users or not users["UserSearchResults"]:
                await ctx.send("User not found.")
                return

            user_id = users["UserSearchResults"][0]["UserId"]

            profile_json = requests.get(f"https://users.roblox.com/v1/users/{user_id}")
            profile = json.loads(profile_json.text)

            if (
                "displayName" not in profile
                or "created" not in profile
                or "description" not in profile
            ):
                await ctx.send("An error occurred while fetching user data.")
                return

            display_name = profile["displayName"]
            created_date = profile["created"]
            description = profile["description"]

            avatar_json = requests.get(
                f"https://thumbnails.roblox.com/v1/users/avatar?userIds={user_id}&size=720x720&format=Png&isCircular=false"
            )
            avatar_data = json.loads(avatar_json.text)

            if "data" not in avatar_data or not avatar_data["data"]:
                await ctx.send("An error occurred while fetching user data.")
                return

            avatar_url = avatar_data["data"][0]["imageUrl"]

            followers_json = requests.get(
                f"https://friends.roblox.com/v1/users/{user_id}/followers/count"
            )
            followers_count = json.loads(followers_json.text)["count"]

            embed = discord.Embed(
                title=f"{username}",
                url=f"https://www.roblox.com/users/{user_id}/profile",
                description=f"> **name:** {display_name}\n"
                f"> **created:** ``{created_date[:10]}``\n"
                f"> **description:** {description}\n"
                f"> **followers:** {followers_count}",
                color=self.bot.color,
            )
            embed.set_image(url=avatar_url)
            button1 = discord.ui.Button(
                label="profile",
                style=discord.ButtonStyle.url,
                url=f"https://www.roblox.com/users/{user_id}/profile",
            )
            view = discord.ui.View()
            view.add_item(button1)

            await ctx.send(embed=embed, view=view)

        except Exception as e:
            await ctx.send(f"An error occurred while fetching user data: {e}")

    @commands.hybrid_command(aliases=["snap"], disabled=True)
    async def snapchat(self, ctx: GreedContext, user: SnapUser):
        """
        Get someone's snapchat profile
        """

        embed = (
            discord.Embed(
                color=self.bot.color,
                title=user.display_name,
                url=user.url,
                description=user.bio,
            )
            .set_author(name=user.username)
            .set_thumbnail(url=user.avatar)
        )

        button = discord.ui.Button(label="snapcode")

        async def button_callback(interaction: discord.Interaction):
            e = discord.Embed(color=0xFFFF00)
            e.set_image(url=user.snapcode)
            await interaction.response.send_message(embed=e, ephemeral=True)

        button.callback = button_callback
        view = discord.ui.View()
        view.add_item(button)

        await ctx.send(embed=embed, view=view)

    # @commands.hybrid_command(aliases=["ig"], disabled=True)
    async def instagram(self, ctx: GreedContext, user: InstagramUser):
        """
        Get someone's instagram profile
        """

        embed = (
            discord.Embed(
                color=user.color,
                title=f"{f'{user.username} aka {user.display_name}' if user.display_name else user.username} {''.join(user.badges)}",
                url=user.url,
                description=user.bio,
            )
            .set_thumbnail(url=user.avatar_url)
            .add_field(name="Followers", value=f"{user.followers:,}")
            .add_field(name="Following", value=f"{user.following:,}")
            .add_field(name="Posts", value=f"{user.posts:,}")
        )

        return await ctx.send(embed=embed)

    # @commands.hybrid_command(disabled=True)
    async def ebio(self, ctx: GreedContext, user: EbioUser):
        """
        get someone's ebio user profile
        """

        embed = (
            discord.Embed(
                color=self.bot.color,
                title=user.username,
                url=user.url,
                description=user.bio,
            )
            .set_thumbnail(url=user.avatar)
            .set_image(url=user.background)
            .add_field(name="Views", value=user.views, inline=False)
        )

        if len(user.socials) > 0:
            embed.add_field(name="Socials", value=", ".join(user.socials), inline=False)

        if len(user.badges) > 0:
            embed.add_field(name="Badges", value=", ".join(user.badges), inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["snapstory"], disabled=True)
    async def snapchatstory(self, ctx: GreedContext, *, username: str):
        """
        Get someone's snapchat stories
        """

        results = await self.bot.session.get_json(
            "https://api.greed.wtf/snapstory",
            headers={"Authorization": f"Bearer {self.bot.pretend_api}"},
            params={"username": username},
        )

        if results.get("detail"):
            return await ctx.send_error(results["detail"])

        await ctx.paginator(list(map(lambda s: s["url"], results["stories"])))

    # @commands.hybrid_command(aliases=["tt"], disabled=True)
    async def tiktok(self, ctx: GreedContext, *, user: TikTokUser):
        """
        Get someone's tiktok profile
        """

        embed = (
            discord.Embed(
                color=user.color,
                url=user.url,
                title=f"{user.display_name} ({user.username}) {''.join(user.badges)}"
                if user.display_name != "⠀⠀"
                else f"{user.username} {''.join(user.badges)}",
                description=user.bio,
            )
            .set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            .set_thumbnail(url=user.avatar)
            .add_field(name="Following", value=f"{user.following:,}")
            .add_field(name="Followers", value=f"{user.followers:,}")
            .add_field(name="Hearts", value=f"{user.hearts:,}")
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["git"])
    async def github(self, ctx: GreedContext, *, user: GithubUser):
        """
        Get someone's github profile
        """

        embed = (
            discord.Embed(
                color=self.bot.color,
                title=f"{user.username} {f'aka {user.display}' if user.display else ''}",
                description=user.bio,
                url=user.url,
                timestamp=user.created_at,
            )
            .set_author(name=ctx.author.name, icon_url=ctx.author.display_avatar.url)
            .set_thumbnail(url=user.avatar_url)
            .add_field(name="Followers", value=user.followers)
            .add_field(name="Following", value=user.following)
            .add_field(name="Repos", value=user.repos)
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["fnshop"])
    async def fortniteshop(self, ctx: GreedContext):
        """
        Get the fortnite item shop for today
        """

        now = datetime.datetime.now()
        file = discord.File(
            await self.bot.getbyte(
                f"https://bot.fnbr.co/shop-image/fnbr-shop-{now.day}-{now.month}-{now.year}.png"
            ),
            filename="fortnite.png",
        )

        await ctx.send(file=file)

    @commands.command(aliases=["splash"])
    async def serversplash(
        self, ctx: GreedContext, *, invite: Optional[discord.Invite] = None
    ):
        """
        Get a server's splash
        """

        if invite:
            guild = invite.guild
        else:
            guild = ctx.guild

        if not guild.splash:
            return await ctx.send_error("This server has no splash image")

        embed = discord.Embed(
            color=await self.bot.dominant_color(guild.splash.url),
            title=f"{guild.name}'s splash",
            url=guild.splash.url,
        ).set_image(url=guild.splash.url)

        await ctx.send(embed=embed)

    @commands.command(aliases=["sbanner"])
    async def serverbanner(
        self, ctx: GreedContext, *, invite: Optional[discord.Invite] = None
    ):
        """
        Get a server's banner
        """

        if invite:
            guild = invite.guild
        else:
            guild = ctx.guild

        if not guild.banner:
            return await ctx.send_error("This server has no banner")

        embed = discord.Embed(
            color=await self.bot.dominant_color(guild.banner.url),
            title=f"{guild.name}'s banner",
            url=guild.banner.url,
        ).set_image(url=guild.banner.url)

        await ctx.send(embed=embed)

    @commands.command(aliases=["sicon"])
    async def servericon(
        self, ctx: GreedContext, *, invite: Optional[discord.Invite] = None
    ):
        """
        Get a server's icon
        """

        if invite:
            guild = invite.guild
        else:
            guild = ctx.guild

        if not guild.icon:
            return await ctx.send_error("This server has no icon")

        embed = discord.Embed(
            color=await self.bot.dominant_color(guild.icon.url),
            title=f"{guild.name}'s icon",
            url=guild.icon.url,
        ).set_image(url=guild.icon.url)

        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["define"])
    async def urban(self, ctx: GreedContext, *, word: str):
        """
        find a definition of a word
        """

        embeds = []

        data = await self.bot.session.get_json(
            "http://api.urbandictionary.com/v0/define", params={"term": word}
        )

        defs = data["list"]
        if len(defs) == 0:
            return await ctx.send_error(f"No definition found for **{word}**")

        for defi in defs:
            e = (
                discord.Embed(
                    color=self.bot.color,
                    title=word,
                    description=defi["definition"],
                    url=defi["permalink"],
                    timestamp=dateutil.parser.parse(defi["written_on"]),
                )
                .set_author(
                    name=ctx.author.name, icon_url=ctx.author.display_avatar.url
                )
                .add_field(name="example", value=defi["example"], inline=False)
                .set_footer(text=f"{defs.index(defi)+1}/{len(defs)}")
            )
            embeds.append(e)

        return await ctx.paginator(embeds)

    @commands.command(aliases=["tr"])
    async def translate(self, ctx: GreedContext, language: str, *, message: str):
        """
        Translate a message to a specific language
        """

        try:
            translator = GoogleTranslator(source="auto", target=language)
            translated = await asyncio.to_thread(translator.translate, message)
            embed = discord.Embed(
                color=self.bot.color,
                title=f"translated to {language}",
                description=f"```{translated}```",
            )

            await ctx.send(embed=embed)
        except LanguageNotSupportedException:
            return await ctx.send_error("This language is **not** supported")

    @commands.hybrid_command()
    async def seen(
        self, ctx: GreedContext, *, member: discord.Member = commands.Author
    ):
        """
        Check when a member was last seen
        """

        time = await self.bot.db.fetchval(
            """
      SELECT time FROM seen
      WHERE user_id = $1
      AND guild_id = $2
      """,
            member.id,
            ctx.guild.id,
        )

        if not time:
            return await ctx.send_error("This member doesn't have any last seen record")

        await ctx.pretend_send(
            f"**{member}** was last seen **{self.bot.humanize_date(datetime.datetime.fromtimestamp(time.timestamp()))}**"
        )

    @commands.hybrid_command()
    @is_afk()
    async def afk(self, ctx: GreedContext, *, reason: str = "AFK"):
        """
        let the members know that you're away
        """

        await self.bot.db.execute(
            """
      INSERT INTO afk
      VALUES ($1,$2,$3,$4)
      """,
            ctx.guild.id,
            ctx.author.id,
            reason,
            datetime.datetime.now(),
        )

        embed = discord.Embed(
            color=self.bot.color,
            description=f"<:l_alert:1152440544342069338> {ctx.author.mention}: You are now AFK with the reason: **{reason}**",
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["hex"])
    async def dominant(self, ctx: GreedContext):
        """
        Get the color of an image
        """

        attachment = await ctx.get_attachment()

        if not attachment:
            return await ctx.send_help("dominant")

        color = hex(await self.bot.dominant_color(attachment.url))[2:]
        hex_info = await self.bot.session.get_json(
            "https://www.thecolorapi.com/id", params={"hex": color}
        )
        hex_image = f"https://singlecolorimage.com/get/{color}/200x200"
        embed = (
            discord.Embed(color=int(color, 16))
            .set_author(icon_url=hex_image, name=hex_info["name"]["value"])
            .set_thumbnail(url=hex_image)
            .add_field(name="RGB", value=hex_info["rgb"]["value"])
            .add_field(name="HEX", value=hex_info["hex"]["value"])
        )

        await ctx.send(embed=embed)

    @commands.command()
    async def perks(self, ctx: GreedContext):
        """
        Check the perks that you get for donating $5 to us / boost our server
        """

        commands = [
            f"**{c.qualified_name}** - {c.help}"
            for c in set(self.bot.walk_commands())
            if "has_perks" in [check.__qualname__.split(".")[0] for check in c.checks]
        ]

        embed = discord.Embed(
            color=self.bot.color, title="Perks", description="\n".join(commands)
        ).set_footer(text="use ;purchase to check payment methods")

        await ctx.send(embed=embed)

    @commands.command()
    async def youngest(self, ctx: GreedContext):
        """
        Get the youngest account in the server
        """

        member = (
            sorted(
                [m for m in ctx.guild.members if not m.bot],
                key=lambda m: m.created_at,
                reverse=True,
            )
        )[0]

        embed = (
            discord.Embed(
                color=self.bot.color,
                title=f"Youngest account in {ctx.guild.name}",
                url=f"https://discord.com/users/{member.id}",
            )
            .add_field(name="user", value=member.mention)
            .add_field(
                name="created",
                value=self.bot.humanize_date(member.created_at.replace(tzinfo=None)),
            )
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def oldest(self, ctx: GreedContext):
        """
        Get the oldest account in the server
        """

        member = (
            sorted(
                [m for m in ctx.guild.members if not m.bot], key=lambda m: m.created_at
            )
        )[0]
        embed = (
            discord.Embed(
                color=self.bot.color,
                title=f"Oldest account in {ctx.guild.name}",
                url=f"https://discord.com/users/{member.id}",
            )
            .add_field(name="user", value=member.mention)
            .add_field(
                name="created",
                value=self.bot.humanize_date(member.created_at.replace(tzinfo=None)),
            )
        )

        await ctx.send(embed=embed)

    @commands.hybrid_command(brief="manage messages", aliases=["pic"])
    @commands.has_guild_permissions(manage_messages=True)
    @commands.bot_has_guild_permissions(manage_channels=True)
    async def picperms(
        self,
        ctx: GreedContext,
        member: discord.Member,
        *,
        channel: discord.TextChannel = commands.CurrentChannel,
    ):
        """
        Give a member permissions to post attachments in a channel
        """

        overwrite = channel.overwrites_for(member)

        if (
            channel.permissions_for(member).attach_files
            and channel.permissions_for(member).embed_links
        ):
            overwrite.attach_files = False
            overwrite.embed_links = False
            await channel.set_permissions(
                member,
                overwrite=overwrite,
                reason=f"Picture permissions removed by {ctx.author}",
            )
            return await ctx.send_success(
                f"Removed pic perms from {member.mention} in {channel.mention}"
            )
        else:
            overwrite.attach_files = True
            overwrite.embed_links = True
            await channel.set_permissions(
                member,
                overwrite=overwrite,
                reason=f"Picture permissions granted by {ctx.author}",
            )
            return await ctx.send_success(
                f"Added pic perms to {member.mention} in {channel.mention}"
            )

    @commands.command()
    async def roles(self, ctx: GreedContext):
        """
        Returns a list of server's roles
        """

        role_list = [
            f"{role.mention} - {len(role.members)} member{'s' if len(role.members) != 1 else ''}"
            for role in ctx.guild.roles[1:][::-1]
        ]
        return await ctx.paginate(
            role_list,
            f"Roles in {ctx.guild.name} ({len(ctx.guild.roles[1:])})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @commands.command()
    async def muted(self, ctx: GreedContext):
        """
        Returns a list of muted members
        """

        members = [
            f"{member.mention} - {discord.utils.format_dt(member.timed_out_until, style='R')}"
            for member in ctx.guild.members
            if member.timed_out_until
        ]

        return await ctx.paginate(
            members,
            f"Muted in {ctx.guild.name} ({len(members)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @commands.command()
    async def joins(self, ctx: GreedContext):
        """
        Returns a list of members that joined in the last 24 hours
        """

        members = sorted(
            [
                m
                for m in ctx.guild.members
                if (
                    datetime.datetime.now() - m.joined_at.replace(tzinfo=None)
                ).total_seconds()
                < 3600 * 24
            ],
            key=lambda m: m.joined_at,
            reverse=True,
        )

        return await ctx.paginate(
            [
                f"{m} - {discord.utils.format_dt(m.joined_at, style='R')}"
                for m in members
            ],
            f"Joined today ({len(members)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @commands.command()
    @commands.has_guild_permissions(ban_members=True)
    @commands.bot_has_guild_permissions(ban_members=True)
    async def bans(self, ctx: GreedContext):
        """
        Returns a list of banned users
        """

        banned = [ban async for ban in ctx.guild.bans(limit=100)]
        if len(banned) == 0:
            return await ctx.send_error("No banned members found in this server")
        return await ctx.paginate(
            [f"{m.user} - {m.reason or 'no reason'}" for m in banned],
            f"Bans ({len(banned)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @commands.command()
    async def bots(self, ctx: GreedContext):
        """
        Returns a list of all bots in this server
        """

        return await ctx.paginate(
            [f"{m.mention} `{m.id}`" for m in ctx.guild.members if m.bot],
            f"Bots ({len([m for m in ctx.guild.members if m.bot])})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @commands.command()
    async def boosters(self, ctx: GreedContext):
        """
        Returns a list of members that boosted the server
        """

        members = sorted(
            ctx.guild.premium_subscribers, key=lambda m: m.premium_since, reverse=True
        )

        return await ctx.paginate(
            [
                f"{m} - {discord.utils.format_dt(m.premium_since, style='R')}"
                for m in members
            ],
            f"Boosters ({len(ctx.guild.premium_subscribers)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @commands.command()
    async def inrole(self, ctx: GreedContext, *, role: Union[discord.Role, str]):
        """
        Get the list of members that have a specific
        """

        if isinstance(role, str):
            role = ctx.find_role(role)
            if not role:
                return await ctx.send_error("Role not found")

        if len(role.members) > 200:
            return await ctx.send_warning(
                "Cannot view roles with more than **200** members"
            )

        return await ctx.paginate(
            [f"{m} (`{m.id}`)" for m in role.members],
            f"Members with {role.name} ({len(role.members)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @commands.command()
    async def shazam(self, ctx: GreedContext):
        """
        Get the name of a music in a file using shazam
        """

        attachment = await ctx.get_attachment()

        if not attachment:
            await ctx.send_help(ctx.command)

        embed = discord.Embed(
            color=0x09A1ED,
            description=f"<:shazam:1188946365678624879> {ctx.author.mention}: Searching for track...",
        )

        mes = await ctx.send(embed=embed)
        try:
            out = await Shazam().recognize_song(await attachment.read())
            track = out["track"]["share"]["text"]
            link = out["track"]["share"]["href"]

            embed = discord.Embed(
                color=0x09A1ED,
                description=f"<:shazam:1188946365678624879> {ctx.author.mention}: Found [**{track}**]({link})",
            )

            await mes.edit(embed=embed)
        except:
            embed = discord.Embed(
                color=self.bot.no_color,
                description=f"{self.bot.no} {ctx.author.mention}: Unable to find this attachment's track name",
            )

            await mes.edit(embed=embed)

    @commands.group(aliases=["tz"], invoke_without_command=True)
    async def timezone(
        self, ctx: GreedContext, *, member: Optional[TimezoneMember] = None
    ):
        """
        Get the member's current date
        """

        if member is None:
            member = await TimezoneMember().convert(ctx, str(ctx.author))

        embed = discord.Embed(
            color=self.bot.color,
            description=f"🕑 {ctx.author.mention}: **{member[0].name}'s** current date **{member[1]}**",
        )
        await ctx.send(embed=embed)

    @timezone.command(name="set")
    async def timezone_set(self, ctx: GreedContext, *, timezone: TimezoneLocation):
        """
        Set your timezone
        """

        embed = discord.Embed(
            color=self.bot.color,
            description=f"Saved your timezone as **{timezone.timezone}**\n🕑 Current date: **{timezone.date}**",
        )
        await ctx.send(embed=embed)

    @timezone.command(name="unset")
    async def timezone_unset(self, ctx: GreedContext):
        """
        Unset your timezone
        """

        await self.bot.db.execute(
            """
      DELETE FROM timezone
      WHERE user_id = $1
      """,
            ctx.author.id,
        )

        return await ctx.send_success(f"You succesfully deleted your timezone")

    @timezone.command(name="list")
    async def timezone_list(self, ctx: GreedContext):
        """
        Get the timezones of everyone in this server
        """

        ids = list(map(lambda m: str(m.id), ctx.guild.members))
        results = await self.bot.db.fetch(
            f"SELECT zone, user_id FROM timezone WHERE user_id IN ({', '.join(ids)})"
        )
        await ctx.paginate(
            [
                f"<@{result['user_id']}> - **{await self.tz.get_timezone(ctx.guild.get_member(result['user_id']))}"
                for result in results
            ],
            f"Timezones ({len(results)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @commands.group(aliases=["bday"], invoke_without_command=True)
    async def birthday(self, ctx: GreedContext, *, member: Optional[BdayMember] = None):
        """
        Get the birthday of an user
        """

        if member is None:
            member = await BdayMember().convert(ctx, str(ctx.author))

        embed = discord.Embed(
            color=0xDEA5A4,
            description=f"🎂 {ctx.author.mention}: **{member.name}'s** birthday is **{member.date}**. That's **{member.birthday}**",
        )

        await ctx.send(embed=embed)

    @birthday.command(name="set")
    async def bday_set(self, ctx: GreedContext, *, date: BdayDate):
        """
        Set your birthday
        """

        embed = discord.Embed(
            color=0xDEA5A4,
            description=f"🎂 Your birthday is **{date[0]}**. That's **{date[1]}**",
        )
        await ctx.send(embed=embed)

    @birthday.command(name="unset")
    async def bday_unset(self, ctx: GreedContext):
        """
        Unset your birthday
        """

        await self.bot.db.execute(
            """
      DELETE FROM bday
      WHERE user_id = $1
      """,
            ctx.author.id,
        )

        return await ctx.send_success(f"You succesfully deleted your birthday")

    @birthday.command(name="list")
    async def bday_list(self, ctx: GreedContext):
        """
        Get the birthdays of everyone in this server
        """

        ids = list(map(lambda m: str(m.id), ctx.guild.members))
        results = await self.bot.db.fetch(
            f"SELECT * FROM bday WHERE user_id IN ({', '.join(ids)})"
        )
        await ctx.paginate(
            [
                f"""<@{result['user_id']}> - **{self.tz.months.get(result['month'])} {result['day']}**"""
                for result in results
            ],
            f"Birthdays ({len(results)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @commands.group(invoke_without_command=True)
    async def reminder(self, ctx):
        return await ctx.create_pages()

    @reminder.command(name="add")
    @reminder_exists()
    async def reminder_add(self, ctx: GreedContext, time: ValidTime, *, task: str):
        """
        Make the bot remind you about a task
        """

        if time < 60:
            return await ctx.send_warning("Reminder time can't be less than a minute")

        else:
            try:
                await self.bot.db.execute(
                    """
        INSERT INTO reminder
        VALUES ($1,$2,$3,$4,$5)
        """,
                    ctx.author.id,
                    ctx.channel.id,
                    ctx.guild.id,
                    (datetime.datetime.now() + datetime.timedelta(seconds=time)),
                    task,
                )

                await ctx.send(
                    f"🕰️ {ctx.author.mention}: I'm going to remind you in {humanfriendly.format_timespan(time)} about **{task}**"
                )
            except:
                return await ctx.send_warning(
                    f"You already have a reminder set in this channel. Use `{ctx.clean_prefix}reminder stop` to cancel the reminder"
                )

    @reminder.command(name="stop", aliases=["cancel"])
    @is_there_a_reminder()
    async def reminder_stop(self, ctx: GreedContext):
        """
        Stop the bot from reminding you
        """

        await self.bot.db.execute(
            """
      DELETE FROM reminder
      WHERE guild_id = $1
      AND user_id = $2
      """,
            ctx.guild.id,
            ctx.author.id,
        )

        return await ctx.send_success("Deleted a reminder")

    @commands.command(aliases=["remindme"])
    @reminder_exists()
    async def remind(self, ctx: GreedContext, time: ValidTime, *, task: str):
        """
        Make the bot remind you about a task
        """

        if time < 60:
            return await ctx.send_warning("Reminder time can't be less than a minute")
        else:
            try:
                await self.bot.db.execute(
                    """
        INSERT INTO reminder
        VALUES ($1,$2,$3,$4,$5)
        """,
                    ctx.author.id,
                    ctx.channel.id,
                    ctx.guild.id,
                    (datetime.datetime.now() + datetime.timedelta(seconds=time)),
                    task,
                )
                await ctx.send(
                    f"🕰️ {ctx.author.mention}: I'm going to remind you in {humanfriendly.format_timespan(time)} about **{task}**"
                )
            except:
                return await ctx.send_warning(
                    f"You already have a reminder set in this channel. Use `{ctx.clean_prefix}reminder stop` to cancel the reminder"
                )

    @commands.hybrid_command(description="utility")
    async def vote(self, ctx):
        button = discord.ui.Button(
            label="vote for greed on top.gg",
            style=discord.ButtonStyle.url,
            url="https://top.gg/bot/1149535834756874250/vote",
        )
        view = discord.ui.View()
        view.add_item(button)
        await ctx.reply(view=view)

    @commands.group(invoke_without_command=True)
    async def guildedit(self, ctx):
        embed = discord.Embed(
            color=self.bot.color,
            title="guildedit",
            description="edit a part of the guild",
        )
        embed.set_author(name=self.bot.user.name, icon_url=self.bot.user.avatar.url)
        embed.add_field(name="category", value="config")
        embed.add_field(
            name="commands",
            value="guildedit icon - edits server's icon\nguildedit splash - edits server's invite background link\nguildedit banner - edits server's banner",
            inline=False,
        )
        embed.add_field(
            name="usage", value=f"```guildedit [guild part] [string]```", inline=False
        )
        embed.add_field(name="aliases", value="none")
        await ctx.reply(embed=embed)  # mention_author=False)

    @guildedit.command(
        name="name", description="edit the server's name", help="config", usage="[name]"
    )
    async def guildedit_name(self, ctx: commands.Context, *, name: str = None):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("you need `manage_guild` permission to use this command")
            return
        await ctx.guild.edit(name=name)
        return await ctx.send("Changed server's name to **{}**".format(name))

    @guildedit.command(
        name="description",
        description="edit the server's description",
        help="config",
        usage="[description]",
    )
    async def guildedit_description(self, ctx: commands.Context, *, desc: str = None):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("you need `manage_guild` permission to use this command")
            return
        await ctx.guild.edit(description=desc)
        return await ctx.send("Changed server's description to **{}**".format(desc))

    @guildedit.command(
        help="edit server's icon", description="config", usage="[icon url / attachment]"
    )
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def icon(self, ctx: commands.Context, icon=None):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("you need `manage_guild` permission to use this command")
            return
        if icon == None:
            icon = ctx.message.attachments[0].url

        link = icon
        async with aiohttp.ClientSession() as ses:
            async with ses.get(link) as r:
                try:
                    if r.status in range(200, 299):
                        img = BytesIO(await r.read())
                        bytes = img.getvalue()
                        await ctx.guild.edit(icon=bytes)
                        emb = discord.Embed(
                            color=self.bot.color,
                            description=f"{ctx.author.mention} changed server's icon to",
                        )
                        emb.set_image(url=link)
                        await ctx.reply(embed=emb, mention_author=False)
                        return
                except Exception as e:
                    e = discord.Embed(
                        color=self.bot.color,
                        description=f"{ctx.author.mention} unable to change server's icon {e}",
                    )
                    await ctx.reply(embed=e, mention_author=False)
                    return

    @guildedit.command(
        help="edit server's banner",
        description="config",
        usage="[banner url / attachment]",
    )
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def banner(self, ctx: commands.Context, icon=None):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("you need `manage_guild` permission to use this command")
            return
        if ctx.guild.premium_subscription_count < 7:
            e = discord.Embed(
                color=0xFFFF00,
                description=f"{ctx.author.mention} this server hasn't banners feature unlocked",
            )
            await ctx.reply(embed=e, mention_author=False)
            return
        if icon == None:
            icon = ctx.message.attachments[0].url

        link = icon
        async with aiohttp.ClientSession() as ses:
            async with ses.get(link) as r:
                try:
                    if r.status in range(200, 299):
                        img = BytesIO(await r.read())
                        bytes = img.getvalue()
                        await ctx.guild.edit(banner=bytes)
                        emb = discord.Embed(
                            color=self.bot.color,
                            description=f"{ctx.author.mention} changed server's banner to",
                        )
                        emb.set_image(url=link)
                        await ctx.reply(embed=emb, mention_author=False)
                        return
                except Exception as e:
                    e = discord.Embed(
                        color=self.bot.color,
                        description=f"{ctx.author.mention} unable to change server's banner {e}",
                    )
                    await ctx.reply(embed=e, mention_author=False)
                    return

    @guildedit.command(
        help="edit server's splash",
        description="config",
        usage="[splash url / attachment]",
    )
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def splash(self, ctx: commands.Context, icon=None):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("you need `manage_guild` permission to use this command")
            return
        if ctx.guild.premium_subscription_count < 2:
            e = discord.Embed(
                color=0xFFFF00,
                description=f"{ctx.author.mention} this server hasn't splash feature unlocked",
            )
            await ctx.reply(embed=e, mention_author=False)
            return
        if icon == None:
            icon = ctx.message.attachments[0].url

        link = icon
        async with aiohttp.ClientSession() as ses:
            async with ses.get(link) as r:
                try:
                    if r.status in range(200, 299):
                        img = BytesIO(await r.read())
                        bytes = img.getvalue()
                        await ctx.guild.edit(splash=bytes)
                        emb = discord.Embed(
                            color=self.bot.color,
                            description=f"{ctx.author.mention} changed server's banner to",
                        )
                        emb.set_image(url=link)
                        await ctx.reply(embed=emb, mention_author=False)
                        return
                except Exception as e:
                    e = discord.Embed(
                        color=self.bot.color,
                        description=f"{ctx.author.mention} unable to change server's banner {e}",
                    )
                    await ctx.reply(embed=e, mention_author=False)
                    return

    @commands.command(
        help="Creates a new role", description="config", usage="[role name]"
    )
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rolecreate(self, ctx, *, role_name: str):
        try:
            new_role = await ctx.guild.create_role(name=role_name)
            embed = discord.Embed(
                color=self.bot.color,
                description=f"Role **{new_role.name}** has been created.",
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                color=self.bot.color,
                description="I don't have the necessary permissions to create a role.",
            )
            await ctx.send(embed=embed)
        except discord.HTTPException:
            embed = discord.Embed(
                color=self.bot.color, description="Role creation failed."
            )
            await ctx.send(embed=embed)

    @commands.command(
        help="Changes color of a role", description="config", usage="[role] [hex_color]"
    )
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def rolecolor(self, ctx, role: discord.Role, hex_color: discord.Colour):
        try:
            await role.edit(colour=hex_color)
            embed = discord.Embed(
                color=hex_color,
                description=f"Changed color for role **{role.name}** to **{hex_color}**.",
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                color=self.bot.color,
                description="I don't have the necessary permissions to change the role's color.",
            )
            await ctx.send(embed=embed)
        except discord.HTTPException:
            embed = discord.Embed(
                color=self.bot.color, description="Failed to change the role's color."
            )
            await ctx.send(embed=embed)

    @commands.command(help="Deletes a role", description="config", usage="[role]")
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def roledelete(self, ctx, *, role: discord.Role):
        try:
            await role.delete()
            embed = discord.Embed(
                color=self.bot.color,
                description=f"Role **{role.name}** has been deleted.",
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(
                color=self.bot.color,
                description="I don't have the necessary permissions to delete the role.",
            )
            await ctx.send(embed=embed)
        except discord.HTTPException:
            embed = discord.Embed(
                color=self.bot.color, description="Role deletion failed."
            )
            await ctx.send(embed=embed)

    @commands.command(name="naught")
    @commands.has_permissions(manage_channels=True)
    async def naughty(self, ctx, channel: discord.TextChannel):
        try:
            await channel.edit(nsfw=True)

            # Introduce a delay of one second
            await asyncio.sleep(1)

            embed = discord.Embed(
                description=f"This channel is now NSFW.", color=self.bot.color
            )
            await ctx.send(embed=embed)  # Send the embed using ctx
        except discord.Forbidden:
            embed = discord.Embed(
                description="I don't have permission to set the channel as NSFW.",
                color=self.bot.color,
            )
            await ctx.send(embed=embed)
        except discord.HTTPException as e:
            embed = discord.Embed(
                description=f"An error occurred: {e}", color=self.bot.color
            )
            await ctx.send(embed=embed)

    @commands.command(
        help="Edits a role's color based on a user's profile picture",
        description="config",
        usage="[role] [user mention]",
    )
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.has_permissions(manage_roles=True)
    async def editcolor(self, ctx, role: discord.Role, user: discord.User):
        # Get the user's avatar URL
        avatar_url = user.avatar.url

        # Process the avatar image to extract the dominant color
        response = requests.get(avatar_url)
        if response.status_code != 200:
            return await ctx.send("Failed to fetch user's avatar.")

        # Read the image content
        img_content = response.content

        # Open the image using PIL
        with Image.open(BytesIO(img_content)) as img:
            # Resize the image to a smaller size to speed up processing
            img = img.resize((100, 100))

            # Get the average color of all pixels
            average_color = self.get_average_color(img)

            # Convert the average color to discord.Color
            discord_color = discord.Color.from_rgb(*average_color)

        try:
            # Edit the role's color
            await role.edit(colour=discord_color)
            embed = discord.Embed(
                description=f"<:check_white:1204583868435271731> Role **{role.name}** color edited based on **{user.mention}'s** profile picture",
                color=discord_color,
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(
                "I don't have the necessary permissions to edit the role's color."
            )
        except discord.HTTPException:
            await ctx.send("Failed to edit the role's color.")

    def get_average_color(self, image):
        # Get the size of the image
        width, height = image.size

        # Initialize variables to store total RGB values
        total_r = total_g = total_b = 0

        # Iterate over all pixels and accumulate RGB values
        for y in range(height):
            for x in range(width):
                r, g, b = image.getpixel((x, y))
                total_r += r
                total_g += g
                total_b += b

        # Calculate average RGB values
        num_pixels = width * height
        average_r = total_r // num_pixels
        average_g = total_g // num_pixels
        average_b = total_b // num_pixels

        return average_r, average_g, average_b

    @commands.group(name="tag", aliases=["tags", "t"], invoke_without_command=True)
    async def tag(self, ctx: GreedContext, *, tag: str):
        """
        view a tag
        """

        check = await self.bot.db.fetchrow(
            """
      SELECT * FROM tags
      WHERE guild_id = $1
      AND name = $2
      """,
            ctx.guild.id,
            tag,
        )

        if not check:
            return await ctx.send_warning(f"No tag found for **{tag}**")

        x = await self.bot.embed_build.convert(ctx, check["response"])
        await ctx.send(**x)

    @tag.command(name="create", aliases=["make"], brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def tag_create(self, ctx: GreedContext, *, args: str):
        """
        create a tag
        """

        args = args.split(",", maxsplit=1)

        if len(args) == 1:
            return await ctx.send_warning(
                "No response found. Make sure to use a `,` to split the trigger from the response"
            )

        name = args[0]
        response = args[1].strip()

        if await self.bot.db.fetchrow(
            """
      SELECT * FROM tags
      WHERE guild_id = $1
      AND name = $2
      """,
            ctx.guild.id,
            name,
        ):
            return await ctx.send_warning(f"A tag for **{name}** already exists!")

        await self.bot.db.execute(
            """
      INSERT INTO tags
      VALUES ($1, $2, $3, $4)
      """,
            ctx.guild.id,
            ctx.author.id,
            name,
            response,
        )
        await ctx.send_success(f"Added tag for **{name}**" + f"\n```{response}```")

    @tag.command(name="remove", aliases=["delete", "del"], brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def tag_remove(self, ctx: GreedContext, *, tag: str):
        """
        delete a tag
        """

        if not await self.bot.db.fetchrow(
            """
      SELECT * FROM tags
      WHERE guild_id = $1
      AND name = $2
      """,
            ctx.guild.id,
            tag,
        ):
            return await ctx.send_warning(f"That is **not** an existing tag")

        await self.bot.db.execute(
            """
      DELETE FROM tags
      WHERE guild_id = $1
      AND name = $2
      """,
            ctx.guild.id,
            tag,
        )
        await ctx.send_success(f"Deleted the tag **{tag}**")

    @tag.command(name="reset", brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def tag_reset(self, ctx: GreedContext):
        """
        delete all tags in the guild
        """

        if not await self.bot.db.fetchrow(
            """
      SELECT * FROM tags
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        ):
            return await ctx.send_warning(f"There are **no** tags set")

        async def yes_func(interaction: discord.Interaction):
            await self.bot.db.execute(
                """
        DELETE FROM tags
        WHERE guild_id = $1
        """,
                interaction.guild.id,
            )
            await interaction.response.edit_message(
                embed=discord.Embed(
                    description=f"{self.bot.yes} {interaction.user.mention}: Removed all **tags**",
                    color=self.bot.yes_color,
                ),
                view=None,
            )

        async def no_func(interaction: discord.Interaction):
            await interaction.response.edit_message(
                embed=discord.Embed(
                    description=f"{interaction.user.mention}: Cancelling action...",
                    color=self.bot.color,
                ),
                view=None,
            )

        await ctx.confirmation_send(
            f"Are you sure you want to **delete** all tags?", yes_func, no_func
        )

    @tag.command(name="list", brief="manage server")
    @commands.has_guild_permissions(manage_guild=True)
    async def tag_list(self, ctx: GreedContext):
        """
        returns a list of all tags
        """

        results = await self.bot.db.fetch(
            """
      SELECT * FROM tags
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if not results:
            return await ctx.send_warning(f"There are **no** tags set")

        await ctx.paginate(
            [f"{result['name']} - {result['response']}" for result in results],
            title=f"Tags ({len(results)})",
            author={"name": ctx.guild.name, "icon_url": ctx.guild.icon or None},
        )

    @tag.command(name="random")
    async def tag_random(self, ctx: GreedContext):
        """
        returns a random tag from the guild
        """

        result = await self.bot.db.fetchrow(
            """
      SELECT * FROM tags
      WHERE guild_id = $1
      ORDER BY RANDOM()
      LIMIT 1
      """,
            ctx.guild.id,
        )

        if not result:
            return await ctx.send_warning(f"There are **no** tags set")

        x = await self.bot.embed_build.convert(ctx, result["response"])
        x["content"] = f"({result['name']}) {x['content'] or ''}"
        await ctx.send(**x)

    @tag.command(name="edit", brief="tag owner")
    async def tag_edit(self, ctx: GreedContext, *, args: str):
        """
        edit a tag
        """

        args = args.split(",", maxsplit=1)

        if len(args) == 1:
            return await ctx.send_warning(
                "No response found. Make sure to use a `,` to split the trigger from the response"
            )

        name = args[0]
        response = args[1].strip()

        check = await self.bot.db.fetchrow(
            """
      SELECT * FROM tags
      WHERE guild_id = $1
      AND name = $2
      """,
            ctx.guild.id,
            name,
        )

        if not check:
            return await ctx.send_warning(f"No tag found for **{name}**")

        if check["author_id"] != ctx.author.id:
            return await ctx.send_warning(f"You are not the **author** of this tag")

        await self.bot.db.execute(
            """
      UPDATE tags
      SET response = $1
      WHERE guild_id = $2
      AND name = $3
      """,
            response,
            ctx.guild.id,
            name,
        )
        await ctx.send_success(f"Updated tag for **{name}**" + f"\n```{response}```")

    @tag.command(name="creator", aliases=["author"])
    async def tag_creator(self, ctx: GreedContext, *, tag: str):
        """
        view the creator of a tag
        """

        check = await self.bot.db.fetchrow(
            """
      SELECT * FROM tags
      WHERE guild_id = $1
      AND name = $2
      """,
            ctx.guild.id,
            tag,
        )

        if not check:
            return await ctx.send_warning(f"No tag found for **{tag}**")

        user = self.bot.get_user(check["author_id"])
        return await ctx.pretend_send(f"The author of this tag is **{user}**")

    @tag.command(name="search")
    async def tag_search(self, ctx: GreedContext, *, query: str):
        """
        search for a tag
        """

        results = await self.bot.db.fetch(
            f"""
      SELECT * FROM tags
      WHERE guild_id = $1
      AND name LIKE '%{query}%'
      """,
            ctx.guild.id,
        )

        if not results:
            return await ctx.send_warning(f"No **tags** found")

        await ctx.paginate(
            [f"**{result['name']}**" for result in results], title=f"Tags like {query}"
        )

    @group(name="set", brief="manage server", invoke_without_command=True)
    @has_guild_permissions(manage_guild=True)
    async def set(self, ctx: GreedContext):
        """
        Modify your server with pretend
        """

        await ctx.create_pages()

    @set.command(name="name", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def set_name(self, ctx: GreedContext, *, name: str):
        """
        Change your server's name
        """

        if len(name) > 200:
            return await ctx.send_warning(
                f"Server names can't be over **200 characters**"
            )

        _name = ctx.guild.name
        await ctx.guild.edit(name=name)
        await ctx.send_success(f"Changed **{_name}**'s name")

    @set.command(name="icon", aliases=["picture", "pic"], brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def set_icon(self, ctx: GreedContext, url: str = None):
        """
        Change your server's icon
        """

        if not url:
            url = await ctx.get_attachment()
            if not url:
                return await ctx.send_help(ctx.command)

            url = url.url

        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        if not re.findall(regex, url):
            return await ctx.send_error("The image provided is not an url")

        icon = await self.bot.getbyte(url)
        _icon = icon.read()

        try:
            await ctx.guild.edit(icon=_icon)
        except ValueError:
            return await ctx.send_warning(f"Invalid **media type**")
        await ctx.send_success(f"Set the server icon to [`Attachment`]({url})")

    @set.command(name="banner", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def set_banner(self, ctx: GreedContext, url: str = None):
        """
        Change your server's banner
        """

        if ctx.guild.premium_tier < 2:
            return await ctx.send_warning(f"You haven't **unlocked** banners")

        if not url:
            url = await ctx.get_attachment()
            if not url:
                return await ctx.send_help(ctx.command)

            url = url.url

        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        if not re.findall(regex, url):
            return await ctx.send_error("The attachment provided is not an url")

        banner = await self.bot.getbyte(url)
        _banner = banner.read()

        try:
            await ctx.guild.edit(banner=_banner)
        except ValueError:
            return await ctx.send_warning(f"Invalid **media type**")

    @set.command(name="splash", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def set_splash(self, ctx: GreedContext, url: str = None):
        """
        Change your server's splash
        """

        if ctx.guild.premium_tier < 1:
            return await ctx.send_warning(f"You haven't **unlocked** splash")

        if not url:
            url = await ctx.get_attachment()
            if not url:
                return await ctx.send_help(ctx.command)

            url = url.url

        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        if not re.findall(regex, url):
            return await ctx.send_error("The image provided is not an url")

        icon = await self.bot.getbyte(url)
        _icon = icon.read()

        try:
            await ctx.guild.edit(splash=_icon)
        except ValueError:
            return await ctx.send_warning(f"Invalid **media type**")
        await ctx.send_success(f"Set the server icon to [`Attachment`]({url})")

    @group(name="channel", brief="manage channels", invoke_without_command=True)
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel(self, ctx: GreedContext):
        """
        Manage channels in your sever
        """

        await ctx.create_pages()

    @channel.command(name="create", aliases=["make"], brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_create(self, ctx: GreedContext, *, name: str):
        """
        Create a channel in your server
        """

        channel = await ctx.guild.create_text_channel(name=name)
        return await ctx.send_success(f"Created {channel.mention}")

    @channel.command(name="remove", aliases=["delete", "del"], brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_remove(self, ctx: GreedContext, *, channel: TextChannel):
        """
        Delete a channel in your server
        """

        try:
            await channel.delete(reason=f"Deleted by {ctx.author} ({ctx.author.id})")
        except Forbidden:
            return await ctx.send_warning(f"Couldn't delete {channel.mention}")

        await ctx.send_success(f"Deleted channel `#{channel.name}`")

    @channel.command(name="rename", aliases=["name"], brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_rename(
        self, ctx: GreedContext, channel: TextChannel, *, name: str
    ):
        """
        Rename a channel
        """

        if len(name) > 150:
            return await ctx.send_error(
                f"Channel names can't be over **150 characters**"
            )

        name = name.replace(" ", "-")

        try:
            await channel.edit(name=name)
        except Forbidden:
            return await ctx.send_warning(f"Couldn't rename {channel.mention}")

        await ctx.send_success(f"Renamed `#{channel.name}` to **{name}**")

    @channel.command(name="category", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_category(
        self, ctx: GreedContext, channel: TextChannel, *, category: CategoryChannel
    ):
        """
        Move a channel to a new category
        """

        try:
            await channel.edit(category=category)
        except Forbidden:
            return await ctx.send_warning(
                f"Couldn't change {channel.mention}'s category"
            )

        await ctx.send_success(f"Moved {channel.mention} under {category.mention}")

    @channel.command(name="nsfw", aliases=["naughty"], brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_nsfw(self, ctx: GreedContext, *, channel: TextChannel):
        """
        Toggle NSFW for a channel
        """

        try:
            await channel.edit(nsfw=not channel.nsfw)
        except Forbidden:
            return await ctx.send_warning(
                f"Couldn't mark/unmark {channel.mention} as NSFW"
            )

        await ctx.message.add_reaction("✅")

    @channel.command(name="topic", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def channel_topic(
        self, ctx: GreedContext, channel: TextChannel, *, topic: str
    ):
        """
        Change a channel's topic
        """

        if len(topic) > 1024:
            return await ctx.send_warning(
                f"Channel topics can't be over **1024 characters**"
            )

        try:
            await channel.edit(topic=topic)
        except Forbidden:
            return await ctx.send_warning(f"Couldn't change {channel.mention}'s topic")

        await ctx.send_success(f"Changed {channel.mention}'s topic to `{topic}`")

    @group(name="category", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def category(self, ctx: GreedContext):
        """
        Manage categories in your server
        """

        await ctx.create_pages()

    @category.command(name="create", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def category_create(self, ctx: GreedContext, *, name: str):
        """
        Create a category in your server
        """

        category = await ctx.guild.create_category(name=name)

        await ctx.send_success(f"Created category {category.mention}")

    @category.command(name="delete", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def category_delete(self, ctx: GreedContext, *, category: CategoryChannel):
        """
        Delete a category in your server
        """

        async def yes_func(interaction: Interaction):
            await category.delete(reason=f"Deleted by {ctx.author} {ctx.author.id}")
            await interaction.response.edit_message(
                embed=Embed(
                    description=f"{self.bot.yes} {interaction.user.mention}: Deleted category `#{category.name}`",
                    color=self.bot.yes_color,
                )
            )

        async def no_func(interaction: Interaction):
            await interaction.response.edit_message(
                embed=Embed(
                    description=f"{interaction.user.mention}: Cancelling action...",
                    color=self.bot.color,
                )
            )

        await ctx.confirmation_send(
            f"Are you sure you want to **delete** the category `#{category.name}`?",
            yes_func,
            no_func,
        )

    @category.command(name="rename", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def category_rename(
        self, ctx: GreedContext, category: CategoryChannel, *, name: str
    ):
        """
        Rename a category in your server
        """

        _name = category.name
        await category.edit(
            name=name, reason=f"Edited by {ctx.author} ({ctx.author.id})"
        )
        await ctx.send_success(f"Renamed **{_name}** to `{name}`")

    @category.command(name="duplicate", aliases=["clone", "remake"])
    @has_guild_permissions(manage_channels=True)
    async def category_duplicate(self, ctx: GreedContext, *, category: CategoryChannel):
        """
        Clone an already existing category in your server
        """

        _category = await category.clone(
            name=category.name, reason=f"Cloned by {ctx.author} ({ctx.author.id})"
        )

        await ctx.send_success(f"Cloned {category.mention} to {_category.mention}")

    @command(name="pin", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def pin(self, ctx: GreedContext, message: ValidMessage = None):
        """
        Pin a message
        """

        if not message:
            if ctx.message.reference:
                message = await ctx.fetch_message(int(ctx.message.reference.message_id))
            else:
                async for message in ctx.channel.history(limit=2):
                    message = message

        message: Message = message

        if message.pinned:
            return await ctx.send_warning(f"That message is already **pinned**")

        try:
            await message.pin(reason=f"Pinned by {ctx.author} ({ctx.author.id})")
        except Exception as e:
            if " Cannot execute action on a system message" in str(e):
                return await ctx.send_warning(f"You can't **pin** system messages")

        await ctx.message.add_reaction("✅")

    @command(name="unpin", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def unpin(self, ctx: GreedContext, message: ValidMessage = None):
        """
        Unpin a message
        """

        if not message:
            if ctx.message.reference:
                message = await ctx.fetch_message(int(ctx.message.reference.message_id))
            else:
                async for message in ctx.channel.history(limit=2):
                    message = message

        message: Message = message

        if not message.pinned:
            return await ctx.send_warning(f"That message is **not** pinned")

        await message.unpin(reason=f"Unpinned by {ctx.author} ({ctx.author.id})")
        await ctx.message.add_reaction("✅")


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Utility(bot))
