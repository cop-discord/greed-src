import os
from asyncio import create_subprocess_shell as shell
from asyncio import gather, sleep
from asyncio import to_thread as thread
from asyncio.subprocess import PIPE
from io import BytesIO
from typing import Optional

from aiofiles import open as async_open
from aiohttp import ClientSession as Session
from discord import Embed, File
from discord.ext.commands import CommandError, Context
from tuuid import tuuid


class Conversion:
    def __init__(self):
        self.command = "ffmpeg"

    async def download(self, url: str) -> str:
        async with Session() as session:
            async with session.get(url) as resp:
                data = await resp.read()
        fp = f"{tuuid()}.mp4"
        async with async_open(fp, "wb") as file:
            await file.write(data)
        return fp

    async def convert(self, fp: str) -> str:
        _fp = f"{tuuid()}.gif"
        process = await shell(f"{self.command} -i {fp} {_fp}", stdout=PIPE)
        await process.communicate()
        os.remove(fp)
        if not os.path.exists(_fp):
            raise CommandError(f"Could not convert the file")
        return _fp

    async def do_conversion(self, ctx: Context, url: Optional[str] = None):
        if not url:
            if len(ctx.message.attachments) > 0:
                url = ctx.message.attachments[0].url
            else:
                raise CommandError(f"please provide an attachment")
        filepath = await self.download(url)
        converted = await self.convert(filepath)
        await ctx.send(
            embed=Embed(color=ctx.bot.color, description=f"heres your gif.."),
            file=File(converted),
        )
        os.remove(converted)
