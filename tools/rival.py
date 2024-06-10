import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Union

import aiohttp
from discord import Embed, File, Message
from discord.ext.commands import Context
from discord.ext.commands.errors import CommandError
from humanize import naturaldelta
from pydantic import BaseModel as Model


class BaseModel(Model):
    class Config:
        arbitrary_types_allowed = True


class GoogleImageResult(BaseModel):
    url: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    domain: Optional[str] = None
    color: Optional[str] = None


class GoogleImageRequest(BaseModel):
    query_time: Optional[float] = None
    status: Optional[str] = None
    results: Optional[List[GoogleImageResult]] = []


class DiscordAuthor(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    display_name: Optional[str] = None
    avatar: Optional[str] = None


class DiscordMessage(BaseModel):
    id: Optional[int] = None
    author: Optional[DiscordAuthor] = None
    channel: Optional[int] = None
    content: Optional[str] = ""
    timestamp: Optional[Union[int, float, str]] = None


class Transcribe(BaseModel):
    time_elapsed: Optional[Union[float, str]] = 0.0
    text: Optional[str] = None
    message: DiscordMessage


class ScreenshotAPIResponse(BaseModel):
    time_elapsed: Optional[Union[float, int, str]] = "0"
    screenshot: Optional[str] = None
    url: Optional[str] = None


class APIException(CommandError):
    def __init__(self, message: str, **kwargs):
        self.message = message
        super().__init__(self.message, **kwargs)


class RivalAPI:
    def __init__(self, token: str):
        self.token = token
        self.headers = {"api-key": self.token}
        self.base_url = "https://api.rival.rocks/"
        self.session = None

    async def request(self, method: str, endpoint: str, **kwargs):
        if self.session == None:
            self.session = aiohttp.ClientSession()
        async with self.session.request(
            method, self.base_url + endpoint, headers=self.headers, **kwargs
        ) as response:
            if response.status == 429:
                raise APIException(f"API Ratelimited please wait and try again")
            if response.status == 404:
                raise APIException(f"API endpoint not found")
            if response.status == 500:
                raise APIException("API Returned an error")
            try:
                return await response.json()
            except aiohttp.ContentTypeError:
                return await response.read()

    async def google_image(
        self, query: str, safe: bool = True
    ) -> Optional[GoogleImageRequest]:
        params = {"query": query}
        if safe == True:
            params["safe"] = "true"
        data = await self.request("POST", "google/image", params=params)
        return GoogleImageRequest(**data)

    def message_to_dict(self, m: Message) -> Dict:
        author = {
            "id": m.author.id,
            "name": m.author.name,
            "display_name": m.author.display_name,
            "avatar": m.author.display_avatar.url,
        }
        return {
            "id": m.id,
            "author": author,
            "channel": m.channel.id,
            "content": m.content,
            "timestamp": m.created_at.timestamp(),
        }

    async def transcribe(self, ctx: Context):
        attach = None
        msg = None
        if reference := ctx.message.reference:
            message = await ctx.channel.fetch_message(reference.message_id)
            for attachment in message.attachments:
                if attachment.is_voice_message() is True:
                    attach = attachment
                    msg = self.message_to_dict(message)
        else:
            async for message in ctx.channel.history(limit=100):
                for attachment in message.attachments:
                    if attachment.is_voice_message() is True:
                        attach = attachment
                        msg = self.message_to_dict(message)
                        break
        if attach:
            data = await self.request(
                "GET",
                "media/transcribe",
                params={"url": attach.url},
            )
            data["message"] = msg
            return Transcribe(**data)

    async def screenshot(
        self,
        ctx: Context,
        url: str,
        safe: bool = True,
        full_page: bool = False,
        wait: int = 0,
    ) -> Optional[Embed]:
        if not url.startswith("https://"):
            url = f"https://{url}"
        params = {"url": url, "response_type": "json"}
        if safe is True:
            params["safe"] = "true"
        if full_page is True:
            params["full_page"] = "true"
        if wait > 0:
            params["wait"] = str(wait)
        data = await self.request("GET", "screenshot", params=params)
        response = ScreenshotAPIResponse(**data)
        embed = Embed(
            color=ctx.bot.color if ctx is not None else 0x303135,
            description=f"[{response.url.strip('https://')}]({response.url})",
        )
        embed.set_footer(text=f"took {response.time_elapsed}")
        embed.set_image(url=response.screenshot)
        return embed
