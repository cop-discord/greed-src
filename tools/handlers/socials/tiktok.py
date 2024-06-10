from typing import List

import aiohttp
from discord.ext import commands
from pydantic import BaseModel

from tools.helpers import GreedContext


class TikTok(BaseModel):
    """
    Model for tiktok user
    """

    username: str
    display_name: str
    avatar: str
    color: int
    bio: str
    badges: List[str]
    url: str
    followers: int
    following: int
    hearts: int


class TikTokUser(commands.Converter):
    async def convert(self, ctx: GreedContext, argument: str) -> TikTok:
        async with ctx.typing():
            async with aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {ctx.bot.pretend_api}"}
            ) as cs:
                async with cs.get(
                    "https://api.greed.best/tiktok", params={"username": argument}
                ) as r:
                    if r.status != 200:
                        raise commands.BadArgument("Couldn't get this tiktok page")

                    data = await r.json()
                    badges = []

                    if data.get("private"):
                        badges.append("🔒")

                    if data.get("verified"):
                        badges.append("<:verified:1111747172677988373>")

                    data["badges"] = badges
                    data["display_name"] = data["display"]
                    data["color"] = int(data["color"][1], 16)
                    return TikTok(**data)
