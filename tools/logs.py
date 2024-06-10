from asyncio import ensure_future, gather, sleep
from datetime import datetime as date
from datetime import timedelta
from io import BytesIO, StringIO
from typing import Dict as obj
from typing import List as array
from typing import Optional as pos
from typing import Union as one

import discord
from aiohttp import ClientSession as Session
from orjson import dumps as dump
from orjson import loads as load
from pydantic import BaseModel, Field


class EmbedAuthor(BaseModel):
    name: pos[str] = None
    url: pos[str] = None
    icon_url: pos[str] = None
    proxy_icon_url: pos[str] = None


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


class Attachment(BaseModel):
    url: str
    filename: str


class Embeds(BaseModel):
    title: pos[str] = None
    description: pos[str] = None
    url: pos[str] = None
    type: pos[str] = "rich"
    author: pos[EmbedAuthor] = None
    timestamp: pos[str] = None
    color: pos[int] = 0
    image: pos[EmbedImage] = None
    thumbnail: pos[EmbedThumbnail] = None
    fields: pos[array[EmbedField]] = []
    footer: pos[EmbedFooter] = None


class Author(BaseModel):
    id: int
    username: str
    discriminator: pos[str] = "0"
    bot: pos[bool] = False
    color: pos[int] = 0
    avatar: str


class Message(BaseModel):
    id: int
    channel_id: int
    guild_id: int
    author: Author
    content: pos[str] = ""
    timestamp: str
    edited_timestamp: pos[str] = None
    raw_content: pos[str] = None
    attachments: pos[array[Attachment]] = []
    embeds: pos[array[dict]] = []


class TicketLogs:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://logs.discord.website/api/v2"

    async def get_session(self) -> Session:
        if not hasattr(self, "session"):
            self.session = Session()
        return self.session

    async def message_to_dict(self, message: discord.Message) -> Message:
        data = {
            "id": message.id,
            "channel_id": message.channel.id,
            "guild_id": message.guild.id,
            "author": {
                "id": message.author.id,
                "username": message.author.name,
                "discriminator": message.author.discriminator,
                "bot": message.author.bot,
                "color": int(message.author.color.value),
                "avatar": str(message.author.display_avatar.url),
            },
            "content": message.content,
            "timestamp": str(message.created_at),
            "edited_timestamp": str(message.edited_at) if message.edited_at else None,
            "raw_content": message.clean_content,
            "attachments": [
                {"url": str(i.url), "filename": str(i.filename)}
                for i in message.attachments
            ],
            "embeds": [i.to_dict() for i in message.embeds],
        }
        return Message(**data)

    async def dump_channel(self, channel: discord.TextChannel) -> array[Message]:
        messages = [
            (await self.message_to_dict(i)).dict()
            async for i in channel.history(limit=None)
        ]
        return messages

    async def get_expiration(self):
        now = date.now()
        then = now + timedelta(days=7)
        return then.isoformat()

    async def create_log(self, origin: one[discord.TextChannel, list]) -> str:
        session = await self.get_session()
        if isinstance(origin, discord.TextChannel):
            origin = [origin]
            data = await gather(*[dump(await self.dump_channel(i)) for i in origin])
        else:
            data = origin
        async with session.request(
            "POST",
            f"{self.base_url}/logs",
            json={
                "type": "pretend",
                "messages": data,
                "expires": await self.get_expiration(),
            },
            headers={"Authorization": f"Token {self.token}"},
        ) as response:
            return (await response.json())["url"]
