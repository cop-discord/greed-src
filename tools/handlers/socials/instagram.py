from typing import List, Optional

import aiohttp
from discord.ext import commands
from pydantic import BaseModel


class Instagram(BaseModel):
    """
    Model for instagram user
    """

    username: str
    display_name: Optional[str]
    avatar_url: Optional[str]
    color: int
    bio: str
    url: str
    following: int
    followers: int
    posts: int
    badges: List[str]


class InstagramUser(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> Instagram:
        async with ctx.typing():
            async with aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {ctx.bot.pretend_api}"}
            ) as session:
                async with session.get(
                    "https://api.greed.best/instagram", params={"username": argument}
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        badges = []

                        if data.get("is_private"):
                            badges.append("🔒")

                        if data.get("is_verified"):
                            badges.append("<:verified:1111747172677988373>")

                        data["badges"] = badges

                        try:
                            color = int(data.get("color"), 16)
                        except:
                            color = 2829617

                        data["color"] = color
                        data["avatar_url"] = data["avatar"]
                        return Instagram(**data)
                    else:
                        raise commands.BadArgument("I am unable to get this profile")
