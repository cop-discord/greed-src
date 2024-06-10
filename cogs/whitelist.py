from typing import Union

from discord import Forbidden, Member, User
from discord.ext.commands import Cog, group, has_permissions

from tools.bot import Pretend
from tools.helpers import GreedContext
from tools.predicates import whitelist_enabled


class Whitelist(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot

    @group(
        name="whitelist",
        aliases=["wl"],
        invoke_without_command=True,
        brief="administrator",
    )
    @has_permissions(administrator=True)
    async def whitelist(self, ctx: GreedContext) -> None:
        await ctx.create_pages()

    @whitelist.command(name="enable", brief="administrator")
    @has_permissions(administrator=True)
    async def whitelist_enable(self, ctx: GreedContext) -> None:
        await self.bot.db.execute(
            """
            INSERT INTO whitelist_state VALUES ($1, $2) ON CONFLICT (guild_id) DO NOTHING
            """,
            ctx.guild.id,
            "default",
        )
        await ctx.send_success("Enabled the **whitelist**")

    @whitelist.command(name="disable", brief="administrator")
    @has_permissions(administrator=True)
    async def whitelist_disable(self, ctx: GreedContext) -> None:
        await self.bot.db.execute(
            """
            DELETE FROM whitelist_state WHERE guild_id = $1
            """,
            ctx.guild.id,
        )
        await ctx.send_success("Disabled the **whitelist**")

    @whitelist.command(name="message", aliases=["msg", "dm"], brief="administrator")
    @has_permissions(administrator=True)
    @whitelist_enabled()
    async def whitelist_message(self, ctx: GreedContext, *, code: str) -> None:
        await self.bot.db.execute(
            """
            UPDATE whitelist_state SET embed = $1 WHERE guild_id = $2
            """,
            code,
            ctx.guild.id,
        )
        await ctx.send_success(f"Set your **whitelist** message to: {code}")

    @whitelist.command(name="add", brief="administrator")
    @has_permissions(administrator=True)
    @whitelist_enabled()
    async def whitelist_add(self, ctx: GreedContext, user: User) -> None:
        await self.bot.db.execute(
            """
            INSERT INTO whitelist (guild_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING
            """,
            ctx.guild.id,
            user.id,
        )
        await ctx.send_success(f"Added {user.mention} to the **whitelist**")

    @whitelist.command(name="remove", brief="administrator")
    @has_permissions(administrator=True)
    @whitelist_enabled()
    async def whitelist_remove(
        self, ctx: GreedContext, user: Union[Member, User]
    ) -> None:
        await self.bot.db.execute(
            """
            DELETE FROM whitelist WHERE guild_id = $1 AND user_id = $2
            """,
            ctx.guild.id,
            user.id,
        )
        await ctx.send_success(f"Removed {user.mention} from the **whitelist**")

    @whitelist.command(name="list", brief="administrator")
    @has_permissions(administrator=True)
    @whitelist_enabled()
    async def whitelist_list(self, ctx: GreedContext):
        """
        View all whitelisted members
        """

        results = await self.bot.db.fetch(
            """
            SELECT * FROM whitelist
            WHERE guild_id = $1
            """,
            ctx.guild.id,
        )

        if not results:
            return await ctx.send_error(f"No users are **whitelisted**")

        await ctx.paginate(
            [f"{self.bot.get_user(result['user_id']).mention}" for result in results],
            title=f"Whitelist Users ({len(results)})",
            author={"name": ctx.guild.name, "icon_url": ctx.guild.icon.url or None},
        )


async def setup(bot: Pretend):
    await bot.add_cog(Whitelist(bot))
