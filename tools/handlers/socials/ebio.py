from typing import List

import aiohttp
from discord.ext import commands
from pydantic import BaseModel

from tools.helpers import GreedContext


class Ebio(BaseModel):
    """
    Model for ebio user
    """

    username: str
    display_name: str
    bio: str
    avatar: str
    background: str
    views: int
    socials: List[str]
    badges: List[str]
    url: str


class EbioUser(commands.Converter):
    async def convert(self, ctx: GreedContext, argument: str) -> Ebio:
        headers = {"Authorization": f"Bearer {ctx.bot.pretend_api}"}

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                "https://api.pretend.best/ebio", params={"username": argument}
            ) as r:
                if r.status != 200:
                    raise commands.BadArgument(
                        "Account not found or not able to be fetched"
                    )

                data = await r.json()
                data["socials"] = [
                    f"[**{social['displayname']}**]({social['profile'] if social['profile'] != '' else 'https://none.none'})"
                    for social in data.get("socials")
                    if not social["displayname"] in ["Discord", "Custom URL"]
                ]

                data["badges"] = list(
                    map(lambda badge: badge["displayname"], data["badges"])
                )

                return Ebio(**data)
