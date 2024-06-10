import json as orjson
import re

from discord.ext.commands import Cog, group, has_guild_permissions

from tools.bot import Pretend
from tools.helpers import GreedContext


class Responders(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Message triggered response commands"

    @group(
        name="autoreact", aliases=["rt", "reactiontrigger"], invoke_without_command=True
    )
    async def autoreact(self, ctx: GreedContext):
        return await ctx.create_pages()

    @autoreact.command(
        name="add",
        brief="Manage server",
        usage=";autoreactadd skull, 💀",
        help="Create an autoreact using a trigger for this server",
    )
    @has_guild_permissions(manage_guild=True)
    async def autoreact_add(self, ctx, *, content: str):
        con = content.split(", ")
        if len(con) == 1:
            return await ctx.send_warning(
                "No reactions found. Make sure to use a `,` to split the trigger from the reactions"
            )

        trigger = con[0].strip()
        if not trigger:
            return await ctx.send_warning("No trigger found")

        custom_regex = re.compile(r"(<a?)?:\w+:(\d{18}>)?")
        unicode_regex = re.compile(
            "["
            "\U0001f1e0-\U0001f1ff"
            "\U0001f300-\U0001f5ff"
            "\U0001f600-\U0001f64f"
            "\U0001f680-\U0001f6ff"
            "\U0001f700-\U0001f77f"
            "\U0001f780-\U0001f7ff"
            "\U0001f800-\U0001f8ff"
            "\U0001f900-\U0001f9ff"
            "\U0001fa00-\U0001fa6f"
            "\U0001fa70-\U0001faff"
            "\U00002702-\U000027b0"
            "\U000024c2-\U0001f251"
            "]+"
        )
        reactions = [
            c.strip()
            for c in con[1].split(" ")
            if custom_regex.match(c) or unicode_regex.match(c)
        ]

        if not reactions:
            return await ctx.send_warning("No emojis found")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoreact WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )

        if not check:
            await self.bot.db.execute(
                "INSERT INTO autoreact (guild_id, trigger, reactions) VALUES ($1, $2, $3)",
                ctx.guild.id,
                trigger,
                reactions,
            )
        else:
            await self.bot.db.execute(
                "UPDATE autoreact SET reactions = $1 WHERE guild_id = $2 AND trigger = $3",
                reactions,
                ctx.guild.id,
                trigger,
            )

        return await ctx.send_success(
            f"Your autoreact for **{trigger}** has been created with the reactions {' '.join(reactions)}"
        )

    @autoreact.command(
        name="remove", brief="manage guild", help="remove an autoreaction"
    )
    @has_guild_permissions(manage_guild=True)
    async def autoreact_remove(self, ctx: GreedContext, *, trigger: str):
        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoreact WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )

        if not check:
            return await ctx.send_warning("There is no **autoreact** with this trigger")

        await self.bot.db.execute(
            "DELETE FROM autoreact WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )
        return await ctx.send_success(f"Removed **{trigger}** from autoreact")

    @autoreact.command(name="list", help="returns all the autoreactions in the server")
    async def autoreact_list(self, ctx: GreedContext):
        check = await self.bot.db.fetch(
            "SELECT * FROM autoreact WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            return await ctx.send_error(
                "There are no autoreactions available in this server"
            )

        return await ctx.paginate(
            [
                f"{r['trigger']} - {' '.join(orjson.loads(r['reactions']))}"
                for r in check
            ],
            f"Autoreactions ({len(check)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @group(name="autoresponder", aliases=["ar"], invoke_without_command=True)
    async def autoresponder(self, ctx: GreedContext):
        return await ctx.create_pages()

    @autoresponder.command(
        name="add",
        brief="manage server",
        usage=";autoresponder add hello, hello world",
        help="add an autoresponder to the server",
    )
    @has_guild_permissions(manage_guild=True)
    async def ar_add(self, ctx: GreedContext, *, response: str):
        responses = response.split(", ", maxsplit=1)
        if len(responses) == 1:
            return await ctx.send_warning(
                "Response not found! Please use `,` to split the trigger and the response"
            )

        trigger = responses[0].strip()

        if trigger == "":
            return await ctx.send_warning("No trigger found")

        resp = responses[1].strip()

        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoresponder WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )

        if check:
            await self.bot.db.execute(
                "UPDATE autoresponder SET response = $1 WHERE guild_id = $2 AND trigger = $3",
                resp,
                ctx.guild.id,
                trigger,
            )
        else:
            await self.bot.db.execute(
                "INSERT INTO autoresponder VALUES ($1,$2,$3)",
                ctx.guild.id,
                trigger,
                resp,
            )

        return await ctx.send_success(f"Added autoresponder for **{trigger}** - {resp}")

    @autoresponder.command(name="remove", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def ar_remove(self, ctx: GreedContext, *, trigger: str):
        """remove an autoresponder from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoresponder WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )

        if not check:
            return await ctx.send_error(
                "There is no autoresponder with the trigger you have provided"
            )

        await self.bot.db.execute(
            "DELETE FROM autoresponder WHERE guild_id = $1 AND trigger = $2",
            ctx.guild.id,
            trigger,
        )
        return await ctx.send_success(f"Deleted the autoresponder for **{trigger}**")

    @autoresponder.command(name="list")
    async def ar_list(self, ctx: GreedContext):
        """returns a list of all autoresponders in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM autoresponder WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.paginate(
            [f"{result['trigger']} - {result['response']}" for result in results],
            f"Autoresponders ({len(results)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Responders(bot))
