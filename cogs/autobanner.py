from __future__ import annotations

from random import choices
from string import digits

from discord import TextChannel
from discord.ext import commands, tasks

from tools.helpers import GreedContext




class AutoBannerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.autobanner_loop.start()
        
    def cog_unload(self)
        self.autobanner_loop.cancel()

    @commands.command(
        name="autobanners", 
        brief="manage guild",
        description="sets a channel for sending banners",
        usage="autobanners <category> [channel]")

    @commands.has_permissions(manage_guild=True)
    async def autobanners(self, ctx: GreedContext, category: str = parameter(), 
async def setup(bot):
    cog = AutoBannerCog(bot)
    await bot.add_cog(cog)
