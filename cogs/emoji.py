import asyncio
import datetime
import functools
import io
import unicodedata
import zipfile
from collections import defaultdict
from io import BytesIO
from typing import List, Tuple, Union

import aiohttp
import cairosvg
import discord
import emoji as emoji_lib
from discord import Embed, Emoji, File, PartialEmoji, utils
from discord.ext.commands import (
    BadArgument,
    Cog,
    bot_has_guild_permissions,
    command,
    group,
    has_guild_permissions,
)

from tools.bot import Pretend
from tools.helpers import GreedContext
from tools.misc.views import DownloadAsset


def generate(img):
    # Designed to be run in executor to avoid blocking
    kwargs = {"parent_width": 1024, "parent_height": 1024}
    return io.BytesIO(cairosvg.svg2png(bytestring=img, **kwargs))


class Emoji(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Emoji commands"
        self.locks = defaultdict(asyncio.Lock)

    async def emoji_bucket(self, ctx: GreedContext, emoj: PartialEmoji):
        """
        avoid emoji adding rate limit
        """

        if not self.bot.cache.get("emojis"):
            await self.bot.cache.set("emojis", {ctx.guild.id: []})

        emojis: dict = self.bot.cache.get("emojis")
        if not emojis.get(ctx.guild.id):
            emojis[ctx.guild.id] = []

        guild_emojis: List[Tuple[PartialEmoji, datetime.datetime]] = emojis[
            ctx.guild.id
        ]
        guild_emojis.append(tuple([emoj, datetime.datetime.now()]))

        for g in guild_emojis:
            if (datetime.datetime.now() - g[1]).total_seconds() > 3600:
                guild_emojis.remove(g)

        emojis.update({ctx.guild.id: guild_emojis})
        await self.bot.cache.set("emojis", emojis)

        if len(guild_emojis) > 29:
            raise BadArgument(
                f"Guild got rate limited for adding emojis. Try again **in the next hour**"
            )

        return False

    @group(name="emoji", invoke_without_command=True)
    async def emoji_group(self, ctx):
        """
        Manage the server's emojis
        """

        await ctx.create_pages()

    @emoji_group.command(name="add", aliases=["steal"], brief="manage expressions")
    @has_guild_permissions(manage_expressions=True)
    @bot_has_guild_permissions(manage_expressions=True)
    async def emoji_steal(
        self, ctx: GreedContext, emoji: PartialEmoji, *, name: str = None
    ):
        """
        Add an emoji to the server
        """

        await ctx.invoke(self.bot.get_command("addemoji"), emoji=emoji, name=name)

    @emoji_group.command(
        name="delete", aliases=["remove", "del"], brief="manage expressions"
    )
    @has_guild_permissions(manage_expressions=True)
    async def emoji_delete(self, ctx: GreedContext, *, emoji: Emoji):
        """
        Delete an emoji from the server
        """

        await ctx.invoke(self.bot.get_command("emojidelete"), emoji=emoji)

    @emoji_group.command(name="list")
    async def emoji_list(self, ctx: GreedContext):
        """
        Returns a list of emojis in this server
        """

        await ctx.invoke(self.bot.get_command("emojilist"))

    @emoji_group.command(name="info")
    async def emoji_info(self, ctx: GreedContext, *, emoji: Union[Emoji, PartialEmoji]):
        """
        Information about an emoji
        """

        await ctx.invoke(self.bot.get_command("emojiinfo"), emoji=emoji)

    @emoji_group.command(name="enlarge", aliases=["download", "e", "jumbo"])
    async def emoji_enlarge(
        self, ctx: GreedContext, *, emoji: Union[PartialEmoji, str]
    ):
        """
        Gets an image version of your emoji
        """

        return await ctx.invoke(self.bot.get_command("enlarge"), emoji=emoji)

    @emoji_group.command(name="search")
    async def emoji_search(self, ctx: GreedContext, *, query: str):
        """
        Search emojis based by query
        """

        emojis = [
            f"{e} `{e.id}` - {e.name}" for e in self.bot.emojis if query in e.name
        ]
        return await ctx.paginate(emojis, f"Emojis containing {query} ({len(emojis)})")

    @emoji_group.command(name="zip")
    async def emojis_zip(self, ctx: GreedContext):
        """
        Send a zip file of all emojis in the server
        """

        async with self.locks[ctx.guild.id]:
            async with ctx.typing():
                buff = BytesIO()
                with zipfile.ZipFile(buff, "w") as zip:
                    for emoji in ctx.guild.emojis:
                        zip.writestr(
                            f"{emoji.name}.{'gif' if emoji.animated else 'png'}",
                            data=await emoji.read(),
                        )

            buff.seek(0)
            await ctx.send(file=File(buff, filename=f"emojis-{ctx.guild.name}.zip"))

    @command(
        name="addemoji",
        aliases=["stealemoji", "emojiadd", "steal", "add"],
        brief="manage expressions",
    )
    @has_guild_permissions(manage_expressions=True)
    @bot_has_guild_permissions(manage_expressions=True)
    async def addemoji(
        self, ctx: GreedContext, emoji: PartialEmoji, *, name: str = None
    ):
        """
        Add an emoji to the server
        """

        if await self.emoji_bucket(ctx, emoji):
            return

        emoji_created = await ctx.guild.create_custom_emoji(
            name=name or emoji.name,
            image=await emoji.read(),
            reason=f"Emoji created by {ctx.author}",
        )
        return await ctx.send_success(
            f"Created {emoji_created} as [**{name or emoji_created.name}**]({emoji_created.url})"
        )

    @command(name="addmultiple", aliases=["am"], brief="manage expressions")
    @has_guild_permissions(manage_expressions=True)
    @bot_has_guild_permissions(manage_expressions=True)
    async def addmultiple(self, ctx: GreedContext, *emojis: PartialEmoji):
        """
        Add multiple emojis at the same time
        """

        if len(emojis) == 0:
            return await ctx.send_help(ctx.command)

        if len(emojis) > 30:
            raise BadArgument("Do not add more than 10 emojis at once")

        async with self.locks[ctx.channel.id]:
            mes = await ctx.reply(
                embed=Embed(
                    color=self.bot.color,
                    description=f"{ctx.author.mention}: Adding **{len(emojis)}** emojis...",
                )
            )
            emoji_list = []

            for emo in emojis:
                if await self.emoji_bucket(ctx, emo):
                    if len(emoji_list) > 0:
                        return await mes.edit(
                            embed=Embed(
                                color=self.bot.color,
                                title=f"Added {len(emojis)} emojis",
                                description="".join(emoji_list),
                            )
                        )

                emoj = await ctx.guild.create_custom_emoji(
                    name=emo.name,
                    image=await emo.read(),
                    reason=f"Emoji created by {ctx.author}",
                )
                emoji_list.append(f"{emoj}")

            return await mes.edit(
                embed=Embed(
                    color=self.bot.color,
                    title=f"Added {len(emojis)} emojis",
                    description="".join(emoji_list),
                )
            )

    @command(
        name="deleteemoji",
        aliases=["delemoji", "emojidelete", "removeemoji", "emojiremove"],
        brief="manage expressions",
    )
    @has_guild_permissions(manage_expressions=True)
    @bot_has_guild_permissions(manage_expressions=True)
    async def deleteemoji(self, ctx: GreedContext, *, emoji: Emoji):
        """
        Delete an emoji from the server
        """

        await emoji.delete(reason=f"Emoji deleted by {ctx.author}")
        return await ctx.send_success("Deleted the emoji")

    @command(aliases=["downloademoji", "e", "jumbo"])
    async def enlarge(self, ctx: GreedContext, emoji: Union[PartialEmoji, str]):
        """
        Get an image version of an emoji
        """

        if isinstance(emoji, PartialEmoji):
            return await ctx.reply(
                file=await emoji.to_file(
                    filename=f"{emoji.name}{'.gif' if emoji.animated else '.png'}"
                )
            )

        elif isinstance(emoji, str):
            convert = False
            if emoji[0] == "<":
                # custom Emoji
                try:
                    name = emoji.split(":")[1]
                except IndexError:
                    return await ctx.send_warning("This is **not** an emoji")
                emoji_name = emoji.split(":")[2][:-1]
                if emoji.split(":")[0] == "<a":
                    # animated custom emoji
                    url = f"https://cdn.discordapp.com/emojis/{emoji_name}.gif"
                    name += ".gif"
                else:
                    url = f"https://cdn.discordapp.com/emojis/{emoji_name}.png"
                    name += ".png"
            else:
                chars = []
                name = []
                for char in emoji:
                    chars.append(hex(ord(char))[2:])
                    try:
                        name.append(unicodedata.name(char))
                    except ValueError:
                        # Sometimes occurs when the unicodedata library cannot
                        # resolve the name, however the image still exists
                        name.append("none")
                name = "_".join(name) + ".png"
                if len(chars) == 2 and "fe0f" in chars:
                    # remove variation-selector-16 so that the appropriate url can be built without it
                    chars.remove("fe0f")
                if "20e3" in chars:
                    # COMBINING ENCLOSING KEYCAP doesn't want to play nice either
                    chars.remove("fe0f")
                url = "https://twemoji.maxcdn.com/2/svg/" + "-".join(chars) + ".svg"
                convert = True
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return await ctx.send_warning(
                            f"[This is **not** an emoji]({url})"
                        )
                    img = await resp.read()
            if convert:
                task = functools.partial(generate, img)
                task = self.bot.loop.run_in_executor(None, task)
                try:
                    img = await asyncio.wait_for(task, timeout=15)
                except asyncio.TimeoutError:
                    return await ctx.send_warning("Image Creation **Timed Out**")
            else:
                img = io.BytesIO(img)
            await ctx.send(file=discord.File(img, name))

    @command(aliases=["ei"])
    async def emojiinfo(self, ctx: GreedContext, *, emoji: Union[Emoji, PartialEmoji]):
        """
        Information about an emoji
        """

        embed = Embed(
            color=self.bot.color, title=emoji.name, timestamp=emoji.created_at
        )

        embed.set_thumbnail(url=emoji.url)

        embed.add_field(name="Animated", value=emoji.animated)
        embed.add_field(name="Link", value=f"[emoji]({emoji.url})")
        embed.set_footer(text=f"id: {emoji.id}")
        view = DownloadAsset(ctx, emoji)
        view.message = await ctx.reply(embed=embed, view=view)

    @command(aliases=["emojilist"])
    async def emojis(self, ctx: GreedContext):
        """
        Returns a list of emojis in the server
        """

        await ctx.paginate(
            [f"{emoji} - {emoji.name} (`{emoji.id}`)" for emoji in ctx.guild.emojis],
            f"Emojis ({len(ctx.guild.emojis)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @group(invoke_without_command=True)
    async def sticker(self, ctx: GreedContext):
        """
        Manage server's stickers
        """

        return await ctx.create_pages()

    @sticker.command(name="steal", aliases=["add"], brief="manage expressions")
    @has_guild_permissions(manage_expressions=True)
    @bot_has_guild_permissions(manage_expressions=True)
    async def sticker_steal(self, ctx: GreedContext, name: str = None):
        """
        Add a sticker
        """

        return await ctx.invoke(self.bot.get_command("stealsticker"), name=name)

    @sticker.command(name="enlarge", aliases=["e", "jumbo"])
    async def sticker_enlarge(self, ctx: GreedContext):
        """
        Returns a sticker as a file
        """

        stick = await ctx.get_sticker()
        view = DownloadAsset(ctx, stick)
        view.message = await ctx.reply(
            file=await stick.to_file(filename=f"{stick.name}.png"), view=view
        )

    @sticker.command(name="delete", brief="manage expressions")
    @has_guild_permissions(manage_expressions=True)
    @bot_has_guild_permissions(manage_expressions=True)
    async def sticker_delete(self, ctx: GreedContext):
        """
        Delete a sticker
        """

        sticker = await ctx.get_sticker()
        sticker = await sticker.fetch()

        if sticker.guild.id != ctx.guild.id:
            return await ctx.send_warning("This sticker is not from this server")

        await sticker.delete(reason=f"sticker deleted by {ctx.author}")
        return await ctx.send_success("Deleted the sticker")

    @sticker.command(name="zip")
    async def sticker_zip(self, ctx: GreedContext):
        """
        Send a zip file containing the server's stickers
        """

        async with self.locks[ctx.guild.id]:
            async with ctx.typing():
                buff = BytesIO()
                with zipfile.ZipFile(buff, "w") as zip:
                    for sticker in ctx.guild.stickers:
                        zip.writestr(f"{sticker.name}.png", data=await sticker.read())

            buff.seek(0)
            await ctx.send(file=File(buff, filename=f"stickers-{ctx.guild.name}.zip"))

    @command(name="stickerenlarge", aliases=["stickerjumbo"])
    async def stickerenlarge(self, ctx: GreedContext):
        """
        Return a sticker as a file
        """

        return await ctx.invoke(self.bot.get_command("sticker enlarge"))

    @command(
        brief="manage expressions", aliases=["stickersteal", "addsticker", "stickeradd"]
    )
    @has_guild_permissions(manage_expressions=True)
    @bot_has_guild_permissions(manage_expressions=True)
    async def stealsticker(self, ctx: GreedContext, *, name: str = None):
        """
        Add a sticker to the server
        """

        if len(ctx.guild.stickers) >= ctx.guild.sticker_limit:
            return await ctx.send_warning(
                "This server cannot have new stickers anymore"
            )

        sticker = await ctx.get_sticker()

        if name is None:
            name = sticker.name

        file = File(fp=BytesIO(await sticker.read()))
        stick = await ctx.guild.create_sticker(
            name=name,
            description=name,
            emoji="skull",
            file=file,
            reason=f"sticker created by {ctx.author}",
        )
        return await ctx.send_success(
            f"Added [**sticker**]({stick.url}) with the name **{name}**"
        )

    @sticker.command(name="tag", brief="manage expressions")
    @has_guild_permissions(manage_expressions=True)
    @bot_has_guild_permissions(manage_expressions=True)
    async def sticker_tag(self, ctx: GreedContext):
        """
        Add your server's vanity URL to the end of sticker names
        """

        if not ctx.guild.vanity_url:
            return await ctx.send_warning(f"There is no **vanity url** set")

        message = await ctx.pretend_send(
            f"Adding **gg/{ctx.guild.vanity_url_code}** to `{len(ctx.guild.stickers)}` stickers..."
        )

        for sticker in ctx.guild.stickers:
            if not sticker.name.endswith(f"gg/{ctx.guild.vanity_url_code}"):
                try:
                    await sticker.edit(
                        name=f"{sticker.name} gg/{ctx.guild.vanity_url_code}"
                    )
                    await asyncio.sleep(1.5)
                except:
                    pass

        await message.delete()
        await ctx.send_success(
            f"Added **gg/{ctx.guild.vanity_url_code}** to server stickers"
        )


async def setup(bot: Pretend):
    await bot.add_cog(Emoji(bot))
