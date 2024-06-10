import asyncio
import datetime
import os
from typing import List, Optional

from aiofile import async_open
from aiohttp import ClientSession
from caio import linux_aio_asyncio, thread_aio_asyncio
from discord import Asset as DiscordAsset
from discord import User
from pydantic import BaseModel
from tuuid import tuuid

from tools.bot import Pretend


class Asset(BaseModel):
    name: str
    filepath: str


class Storage:
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.session = ClientSession()
        self.ctx = linux_aio_asyncio.AsyncioContext()
        self.base_dir = os.environ.get("ASSET_DIR", "/avatarhistory/")
        self.__lock = asyncio.Lock()

    async def store_asset(self, user: User, asset: DiscordAsset):
        assset = await asset.to_file()
        extension = assset.filename.split(".")[-1]
        filename = f"{self.base_dir}{user.id}/{asset.key}.{extension}"
        
        if not os.path.exists(f"{self.base_dir}{user.id}"):
            os.mkdir(f"/avatarhistory/{user.id}")
        
        async with self.__lock:
            async with async_open(filename, "wb", context=self.ctx) as f:
                await f.write(await asset.read())
        
        await self.bot.db.execute(
            """INSERT INTO avatars (user_id, name, avatar, key, timestamp) VALUES ($1, $2, $3, $4, $5) ON CONFLICT(user_id, key) DO NOTHING""",
            user.id,
            assset.filename,
            filename,
            asset.key,
            datetime.datetime.now(),
        )
        return filename

    async def get_user_assets(self, user: User):
        assets = []
        if os.path.exists(f"{self.base_dir}{user.id}"):
            for asset in os.listdir(f"{self.base_dir}{user.id}"):
                assets.append(f"{self.base_dir}{user.id}/{asset}")
        return assets

    async def load_asset(self, filepath: str):
        async with async_open(filepath, "rb") as f:
            return await f.read()

    async def load_user_assets(self, user: User) -> Optional[List[Asset]]:
        if os.path.exists(f"{self.base_dir}{user.id}"):
            assets = os.listdir(f"{self.base_dir}{user.id}")
            asset_list = [
                Asset(
                    name=await self.load_asset(f"{self.base_dir}{user.id}/{asset}"),
                    filepath=f"{self.base_dir}{user.id}/{asset}",
                )
                for asset in assets
            ]
            return asset_list
        else:
            return None
