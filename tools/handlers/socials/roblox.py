import datetime
from typing import Any, Optional

import aiohttp
from discord.ext import commands
from pydantic import BaseModel


class Roblox(BaseModel):
    """
    Model for roblox player
    """

    username: str
    id: str
    url: str
    display_name: str
    avatar_url: str
    banned: bool
    bio: Optional[str]
    created_at: Any
    friends: int
    followings: int
    followers: int
    icon: str = "https://play-lh.googleusercontent.com/WNWZaxi9RdJKe2GQM3vqXIAkk69mnIl4Cc8EyZcir2SKlVOxeUv9tZGfNTmNaLC717Ht=w240-h480-rw"


class RobloxUser(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Roblox:
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {ctx.bot.pretend_api}"}
        ) as session:
            async with session.get(
                "https://api.greed.best/roblox", params={"username": argument}
            ) as r:
                if r.status != 200:
                    raise commands.BadArgument(
                        "There was a problem getting details about this roblox user"
                    )

                else:
                    data = await r.json()
                    data["bio"] = data["bio"].replace("\\n", "\n")
                    data["created_at"] = datetime.datetime.fromtimestamp(
                        data["created_at"]
                    )
                    return Roblox(**data)
