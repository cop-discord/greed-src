import discord
from discord.ext import commands
from discord.ext.commands import Cog, command, group, has_permissions

from tools.bot import Pretend
from tools.helpers import GreedContext


class Vanity(commands.Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot

    @Cog.listener("on_guild_update")
    async def vanity_listener(self, before, after):
        if before.vanity_url_code != after.vanity_url_code:
            for guild in self.bot.guilds:
                records = await self.bot.db.fetch(
                    """SELECT channel_id FROM vanity_channels WHERE guild_id = $1""",
                    guild.id,
                )
                vanity_channels = [record["channel_id"] for record in records]
                for channel_id in vanity_channels:
                    vanity_channel = guild.get_channel(channel_id)
                    if vanity_channel:
                        embed = discord.Embed(
                            description=f"Vanity /{before.vanity_url_code} has been dropped",
                            color=self.bot.color,
                        )
                        await vanity_channel.send(embed=embed)

    @group(name="vanity", brief="manage guild", invoke_without_command=True)
    async def vanity(self, ctx: GreedContext):
        return await ctx.create_pages()

    @vanity.command(
        name="set",
        help="sets the channel for vanity changes",
        brief="manage guild",
    )
    @has_permissions(manage_guild=True)
    async def vanityset(self, ctx: GreedContext, channel: discord.TextChannel):
        guild_id = ctx.guild.id
        if channel.guild.id != guild_id:
            await ctx.send_warning("Please mention a channel within this server.")
            return
        records = await self.bot.db.fetch(
            """SELECT channel_id FROM vanity_channels WHERE guild_id = $1""", guild_id
        )
        vanity_channels = [record["channel_id"] for record in records]
        if channel.id in vanity_channels:
            await ctx.send_warning(
                "Vanity logging is already enabled for this channel."
            )
        else:
            await self.bot.db.execute(
                """INSERT INTO vanity_channels (guild_id, channel_id) 
                                     VALUES ($1, $2) 
                                     ON CONFLICT DO NOTHING""",
                guild_id,
                channel.id,
            )
            await ctx.send_success(f"Vanity logging enabled for #{channel.name}.")

    @vanity.command(
        name="unset",
        help="removes the chsnnel from vanity logging",
        brief="manage guild",
    )
    @has_permissions(manage_guild=True)
    async def vanityunset(self, ctx: GreedContext, channel: discord.TextChannel):
        guild_id = ctx.guild.id
        if channel.guild.id != guild_id:
            await ctx.send_warning("Please mention a channel within this server.")
            return
        records = await self.bot.db.fetch(
            """SELECT channel_id FROM vanity_channels WHERE guild_id = $1""", guild_id
        )
        vanity_channels = [record["channel_id"] for record in records]
        if channel.id not in vanity_channels:
            await ctx.send_warning("Vanity logging is not enabled for this channel.")
        else:
            await self.bot.db.execute(
                """DELETE FROM vanity_channels 
                                     WHERE guild_id = $1 AND channel_id = $2""",
                guild_id,
                channel.id,
            )
            await ctx.send_success(f"Vanity logging disabled for #{channel.name}.")


async def setup(bot: Pretend):
    await bot.add_cog(Vanity(bot))
