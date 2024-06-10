import discord
from discord.ext import commands
from discord.ext.commands import Cog, command, group

from tools.bot import Pretend
from tools.helpers import GreedContext


class Sob(commands.Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot

    async def log_server(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self.bot.db.execute(
                """
                INSERT INTO sob_data (guild_id, sob_users)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) DO NOTHING
            """,
                guild.id,
                [],
            )

    @Cog.listener("on_guild_join")
    async def on_sob_join(self, guild: discord.Guild):
        await self.bot.db.execute(
            """
            INSERT INTO sob_data (guild_id, sob_users)
            VALUES ($1, $2)
            ON CONFLICT (guild_id) DO NOTHING
        """,
            guild.id,
            [],
        )

    @group(name="sob", invoke_without_command=True)
    async def sob(self, ctx: GreedContext):
        await ctx.send_pages()

    @sob.command(
        name="add",
        aliases=["set"],
        help="Add automatic sob reactions to a user messages",
        brief="manage messages",
    )
    @commands.has_permissions(manage_messages=True)
    async def add(self, ctx: GreedContext, user: discord.User):
        if ctx.guild is None:
            return await ctx.send("This command can only be used in a server.")

        guild_id = ctx.guild.id
        user_id = user.id

        sob_users = await self.bot.db.fetchval(
            """
            SELECT sob_users FROM sob_data WHERE guild_id = $1
        """,
            guild_id,
        )

        if sob_users is None:
            sob_users = []

        if user_id not in sob_users:
            sob_users.append(user_id)
            await self.bot.db.execute(
                """
                UPDATE sob_data SET sob_users = $1 WHERE guild_id = $2
            """,
                sob_users,
                guild_id,
            )
            await ctx.send_success(
                f"sob reactions have been added to {user.mention}'s messages."
            )
        else:
            await ctx.send(f"{user.name} is already in the sob list.")

    @sob.command(
        name="remove",
        aliases=["unset", "delete"],
        brief="manage messages",
        help="Removes a user from the sob reaction list",
    )
    @commands.has_permissions(manage_messages=True)
    async def remove(self, ctx: GreedContext, user: discord.User):
        guild_id = ctx.guild.id
        user_id = user.id

        sob_users = await self.bot.db.fetchval(
            """
            SELECT sob_users FROM sob_data WHERE guild_id = $1
        """,
            guild_id,
        )

        if sob_users is None:
            sob_users = []

        if user_id in sob_users:
            sob_users.remove(user_id)
            await self.bot.db.execute(
                """
                UPDATE sob_data SET sob_users = $1 WHERE guild_id = $2
            """,
                sob_users,
                guild_id,
            )
            await ctx.send_success(
                f"sob reactions have been removed from {user.mention}'s messages."
            )
        else:
            await ctx.send(f"{user.name} is not in the sob list for this server.")

    @Cog.listener("on_message")
    async def sob_message(self, message: discord.Message):
        if not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        sob_users = await self.bot.db.fetchval(
            """
            SELECT sob_users FROM sob_data WHERE guild_id = $1
        """,
            guild_id,
        )

        if sob_users is None:
            sob_users = []

        if user_id in sob_users:
            await message.add_reaction("😭")


async def setup(bot: Pretend):
    await bot.add_cog(Sob(bot))
