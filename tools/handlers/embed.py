import asyncio
import datetime
import re
from datetime import datetime as date
from datetime import timedelta
from typing import Dict as obj
from typing import List as array
from typing import Optional as pos
from typing import Union as one

import discord
import TagScriptEngine as tse
from aiohttp import ClientSession as Session
from discord import Color, Embed, File, Guild, Member, TextChannel, User
from discord.ext.commands import Context
from pydantic import BaseModel, Field
from TagScriptEngine import Verb as String


async def to_embedcode(data: str) -> str:
    data = data.replace("```", "`` `")
    return f"``` {data} ```"


async def to_embedcode_escaped(data: str) -> str:
    return discord.utils.escape_markdown(data)


class FormatError(Exception):
    def __init__(self, message: str):
        self.message = message
        return super().__init__(message)


class InvalidEmbed(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def link_validation(string: str):
    regex = r"((http(s)?(\:\/\/))+(www\.)?([\w\-\.\/])*(\.[a-zA-Z]{2,3}\/?))[^\s\b\n|]*[^.,;:\?\!\@\^\$ -]"
    results = re.findall(regex, string)
    if len(results) == 0:
        return False
    else:
        return True


def get_amount(amount: one[int, str], limit: int):
    if isinstance(amount, int):
        return limit - amount
    else:
        return limit - len(amount)


async def validate_images(url: str, type: str):
    try:
        if (
            "cdn" not in url
            and not "discord.com" in url.lower()
            and "discordapp.com" not in url
        ):
            async with Session() as session:
                async with session.get(f"https://proxy.rival.rocks?url={url}") as req:
                    if (
                        "image" in req.headers["Content-Type"].lower()
                        and int(req.headers.get("Content-Length", 50000)) < 50000000
                    ):
                        return True
                    else:
                        raise InvalidEmbed(
                            f"{type.lower().title()} URL {url} is invalid"
                        )
        else:
            return True
    except Exception as e:
        raise InvalidEmbed(f"{type.lower().title()} URL {url} is invalid")


async def validator(data: dict):
    for k, v in data.items():
        k = k.lower()
        if k in ("image", "thumbnail"):
            if v in ["", "", None, "None", "None", "none"]:
                data.pop(k)
            else:
                await validate_images(v, k)
                if link_validation(v["url"]) == False:
                    raise InvalidEmbed(f'Embed {k} URL is not a valid URL `{v["url"]}`')
        if k == "url":
            c = link_validation(v)
            if c == False:
                raise InvalidEmbed("Embed URL isnt a valid URL")
        if k == "title":
            if len(v) >= 256:
                raise InvalidEmbed(f"title is too long (`{get_amount(v,256)}`)")
        if k == "description":
            if len(v) >= 4096:
                raise InvalidEmbed(f"description is too long (`{get_amount(v,4096)}`)")
        if k == "author":
            if len(v.get("name", "")) >= 256:
                raise InvalidEmbed(
                    f"author name is too long (`{get_amount(v['name'],256)}`)"
                )
            if v.get("icon_url"):
                if v["icon_url"] in ["", "", None, "None", "None", "none"]:
                    v.pop("icon_url")
                else:
                    c = link_validation(v["icon_url"])
                    if c == False:
                        raise InvalidEmbed("Author Icon Isnt a valid URL")
                    await validate_images(v, "icon_url")
        if k == "fields":
            for f in v:
                i = v.index(f)
                if len(f["name"]) >= 256:
                    raise InvalidEmbed(
                        f"field {i+1}'s name is too long (`{get_amount(f['name'],256)}`)"
                    )
                if len(f["value"]) >= 1024:
                    raise InvalidEmbed(
                        f"field {i+1}'s value is too long (`{get_amount(f['value'],1024)}`)"
                    )
        if k == "footer":
            if len(v.get("text", "")) >= 2048:
                raise InvalidEmbed(
                    f"footer text is too long (`{get_amount(v['text'],2048)}`)"
                )
            if v.get("icon_url"):
                if v["icon_url"] in ["", "", None, "None", "None", "none"]:
                    v.pop("icon_url")
                else:
                    if link_validation(v.get("icon_url")) == False:
                        raise InvalidEmbed("Footer Icon URL is not a valid URL")
                    await validate_images(v["icon_url"], "icon_url")
    if len(discord.Embed.from_dict(data)) >= 6000:
        raise InvalidEmbed(
            f"Embed is too long (`{get_amount(len(discord.Embed.from_dict(data)),6000)}`)"
        )
    return True


class EmbedAuthor(BaseModel):
    name: pos[str] = None
    url: pos[str] = None


class EmbedFooter(BaseModel):
    text: pos[str] = None
    icon_url: pos[str] = None


class EmbedImage(BaseModel):
    url: pos[str] = None


class EmbedThumbnail(BaseModel):
    url: pos[str] = None


class EmbedField(BaseModel):
    name: pos[str] = None
    value: pos[str] = None
    inline: pos[bool] = False


class DiscordEmbed(BaseModel):
    title: pos[str] = None
    description: pos[str] = None
    url: pos[str] = None
    color: pos[one[int, str, Color]] = 0
    timestamp: pos[str] = None
    author: pos[EmbedAuthor] = None
    image: pos[EmbedImage] = None
    thumbnail: pos[EmbedThumbnail] = None
    fields: pos[array[EmbedField]] = []
    footer: pos[EmbedFooter] = None


class DiscordMessage(BaseModel):
    error: pos[str] = None
    content: pos[str] = None
    embed: pos[DiscordEmbed] = None
    view: pos[discord.ui.View] = None
    delete_after: pos[int] = None


class EmbedBuilder:
    def __init__(self, bot):
        self.bot = bot

    def make_replacements(self, code: str, **kwargs) -> Embed:
        if user := kwargs.get("user", kwargs.get("member")):
            if "{user}" in code:
                code = code.replace("{user}", str(user))
            if "{user.mention}" in code:
                code = code.replace("{user.mention}", user.mention)
            if "{user.name}" in code:
                code = code.replace("{user.name}", user.name)
            if "{user.avatar}" in code:
                code = code.replace("{user.avatar}", str(user.display_avatar.url))
            if "{user.joined_at}" in code:
                code = code.replace(
                    "{user.joined_at}",
                    discord.utils.format_dt(user.joined_at, style="R"),
                )
            if "{user.created_at}" in code:
                code = code.replace(
                    "{user.created_at}",
                    discord.utils.format_dt(user.created_at, style="R"),
                )
            if "{user.discriminator}" in code:
                code = code.replace("{user.discriminator}", user.discriminator)
        if guild := kwargs.get("guild", kwargs.get("server")):
            if "{guild.name}" in code:
                code = code.replace("{guild.name}", user.guild.name)
            if "{guild.count}" in code:
                code = code.replace("{guild.count}", str(user.guild.member_count))
            if "{guild.count.format}" in code:
                code = code.replace(
                    "{guild.count.format}", self.ordinal(len(user.guild.members))
                )
            if "{guild.id}" in code:
                code = code.replace("{guild.id}", user.guild.id)
            if "{guild.created_at}" in code:
                code = code.replace(
                    "{guild.created_at}",
                    discord.utils.format_dt(user.guild.created_at, style="R"),
                )
            if "{guild.boost_count}" in code:
                code = code.replace(
                    "{guild.boost_count}", str(user.guild.premium_subscription_count)
                )
            if "{guild.booster_count}" in code:
                code = code.replace(
                    "{guild.booster_count}", str(len(user.guild.premium_subscribers))
                )
            if "{guild.boost_count.format}" in code:
                code = code.replace(
                    "{guild.boost_count.format}",
                    self.ordinal(user.guild.premium_subscription_count),
                )
            if "{guild.booster_count.format}" in code:
                code = code.replace(
                    "{guild.booster_count.format}",
                    self.ordinal(len(user.guild.premium_subscribers)),
                )
            if "{guild.boost_tier}" in code:
                code = code.replace("{guild.boost_tier}", str(user.guild.premium_tier))
            if "{guild.vanity}" in code:
                code = code.replace(
                    "{guild.vanity}", "/" + user.guild.vanity_url_code or "none"
                )
            if "{guild.icon}" in code:
                if user.guild.icon:
                    code = code.replace("{guild.icon}", user.guild.icon.url)
                else:
                    code = code.replace("{guild.icon}", "https://none.none")
        if "{invisible}" in code:
            code = code.replace("{invisible}", "2b2d31")
        if "{botcolor}" in code:
            code = code.replace("{botcolor}", "7b90d5")
        return code

    async def build_embed(self, code: str, sendable: bool = False):
        d = code
        d = d.replace("{embed}", "")
        o = {}
        final = {}
        author = None
        e = discord.Embed()
        view = discord.ui.View()
        final["view"] = view
        if d.startswith("$v"):
            d = d[2:]
        if d.endswith("$v"):
            d = d[: len(d) - 2]
        data = d.split("$v")
        for string_check in data:
            if "}{" in string_check:
                raise FormatError(f"Missing `$v` between `}}{{`")
            if not str(string_check).startswith("{"):
                raise FormatError(f"Missing `{{` in portion of embed `{string_check}`")
            if not str(string_check).endswith("}"):
                raise FormatError(f"Missing `}}` in portion of embed `{string_check}`")
        o["fields"] = []
        for s in data:
            pr = String(s)
            k = pr.declaration
            pay = pr.payload.lstrip().rstrip()
            if pay and " && " in pay:
                meow = {}
                py = pay.split(" && ")
                if k.lower() in ("field", "footer", "label", "author"):
                    if k.lower() == "footer":
                        meow["text"] = py[0]
                        meow["icon"] = py[1].replace("icon: ", "")
                    if k.lower() == "label":
                        view.add_item(
                            discord.ui.Button(
                                label=py[0], url=py[1].strip("link:").lstrip().rstrip()
                            )
                        )
                    if k.lower() == "field":
                        meo = {}
                        meo["name"] = py[0]
                        meo["value"] = py[1].replace("value:", "")
                        if len(py) == 3:
                            meo["inline"] = bool(py[2].replace("inline:", "").strip())
                        o["fields"].append(meo)
                    if k.lower() == "author" or k.lower() == "uthor":
                        meo = {"name": py[0]}
                        py.remove(py[0])
                        for t in py:
                            t = t.lstrip().rstrip()
                            if ":" in t:
                                if "icon:" in t:
                                    icon = t.replace("icon:", "")
                                    if link_validation(icon) != False:
                                        meo["icon_url"] = icon
                                    else:
                                        raise InvalidEmbed(
                                            message="Author Icon URL is an Invalid URL"
                                        )
                                else:
                                    url = t.replace("url:", "")
                                    if link_validation(url) != False:
                                        meo["url"] = url
                                    else:
                                        raise InvalidEmbed(
                                            message="Author URL is an Invalid URL"
                                        )
                        o["author"] = meo
                        author = meo
                else:
                    for t in py:
                        if ":" in t:
                            parts = t.split(":", 1)
                            meow[parts[0].strip()] = parts[1]
                        else:
                            o[k] = t
                o[k] = meow
            else:
                if k.lower() == "content" or k.lower() == "autodelete":
                    final[k] = pay
                elif k.lower() == "author" or k.lower() == "url":
                    if k.lower() == "url":
                        if link_validation(pay) == False:
                            raise InvalidEmbed(message=f"Embed URL is an Invalid URL")
                    else:
                        o["author"] = {"name": pay}
                else:
                    if k.lower() == "timestamp":
                        o["timestamp"] = datetime.datetime.now().isoformat()
                    else:
                        o[k] = pay
        if o.get("author") == {} and author != None:
            o["author"] = author
        final["embed"] = o
        if final["embed"].get("thumbnail"):
            if link_validation(final["embed"].get("thumbnail")) == False:
                raise InvalidEmbed(
                    message=f"Thumbnail URL is an Invalid URL {final['embed']['thumbnail']}"
                )
            else:
                th = {"url": final["embed"]["thumbnail"]}
                final["embed"]["thumbnail"] = th
        if final["embed"].get("image"):
            if link_validation(final["embed"].get("image")) == False:
                raise InvalidEmbed(message="Image URL is an Invalid URL")
            else:
                th = {"url": final["embed"]["image"]}
                final["embed"]["image"] = th
        if final["embed"].get("footer"):
            if isinstance(final["embed"]["footer"], str):
                final["embed"]["footer"] = {"text": final["embed"]["footer"]}
            if final["embed"]["footer"].get("icon"):
                if final["embed"]["footer"]["icon"].startswith("icon: "):
                    final["embed"]["footer"]["icon_url"] = final["embed"]["footer"][
                        "icon"
                    ].strip("icon: ")
                else:
                    final["embed"]["footer"]["icon_url"] = final["embed"]["footer"][
                        "icon"
                    ]
                try:
                    final["embed"]["footer"].pop("icon")
                except:
                    pass
        if final["embed"].get("author"):
            if final["embed"]["author"].get("icon"):
                final["embed"]["author"]["icon_url"] = (
                    final["embed"]["author"].get("icon").strip(" icon: ")
                )
                try:
                    final["embed"]["author"].pop("icon")
                except:
                    pass
        if final["embed"].get("uthor"):
            final["embed"]["author"] = final["embed"]["uthor"]
            final["embed"]["author"]["icon_url"] = final["embed"]["author"].get(
                "icon", None
            )
            try:
                final["embed"]["author"].pop("icon")
            except:
                pass
            final["embed"].pop("uthor")
        if final.get("autodelete"):
            final["delete_after"] = int(final["autodelete"])
            final.pop("autodelete")
        if final["embed"].get("color"):
            color = final["embed"]["color"]
            if color.endswith("}") and "{" not in color:
                color = color[: len(color) - 2]
            if not color.startswith("#"):
                try:
                    final["embed"]["color"] = discord.Color(value=int(color))
                except:
                    color = f"#{color}"
            try:
                final["embed"]["color"] = int(discord.Color.from_str(color))
            except Exception as e:
                final["error"] = f"{str(e)} ({final['embed']['color']})"
                final["embed"]["color"] = 0x000001
        try:
            final["embed"].pop("field")
        except:
            pass
        try:
            final["embed"].pop("label")
        except:
            pass
        if len(final["embed"]) == 0:
            final.pop("embed")
        if final.get("embed"):
            if len(final["embed"].get("fields", [])) == 0:
                final["embed"].pop("fields")
            await validator(final["embed"])
        if len(final.get("embed", {})) == 0:
            try:
                final.pop("embed")
            except:
                pass
        if sendable == True:
            if final.get("embed"):
                final["embed"] = discord.Embed.from_dict(final["embed"])
        return final

    async def make_embed(
        self, destination: one[Context, discord.TextChannel], code: str, **kwargs
    ):
        if isinstance(destination, Context):
            destination = destination.channel
        code = self.make_replacements(code, **kwargs)
        embed = DiscordMessage(**await self.build_embed(code))
        if error := embed.error:
            return await destination.send(
                embed=discord.Embed(description=f"```{error}```", color=0xFF0000)
            )
        return await destination.send(**embed.dict())
