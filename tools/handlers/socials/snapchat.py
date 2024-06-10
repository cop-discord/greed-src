from typing import Optional

import aiohttp
from discord.ext import commands
from pydantic import BaseModel

from tools.helpers import GreedContext


class Snapchat(BaseModel):
    """
    Model for snapchat profile
    """

    username: str
    display_name: str
    snapcode: str
    bio: Optional[str]
    avatar: str
    url: str


class SnapUser(commands.Converter):
    async def convert(self, ctx: GreedContext, argument: str) -> Snapchat:
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {ctx.bot.pretend_api}"}
        ) as cs:
            async with cs.get(
                "https://api.greed.best/snapchat", params={"username": argument}
            ) as r:
                if r.status != 200:
                    raise commands.BadArgument(
                        f"Couldn't get information about **{argument}**"
                    )

                return Snapchat(**(await r.json()))
