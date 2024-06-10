import datetime
import json as orjson
import re

from discord import Embed, Member, User, utils
from discord.ext.commands import (
    Author,
    Cog,
    bot_has_guild_permissions,
    command,
    group,
    has_guild_permissions,
)

from tools.bot import Pretend
from tools.converters import NoStaff
from tools.helpers import GreedContext
from tools.predicates import create_reskin, has_perks
from tools.validators import ValidReskinName


class Donor(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Premium commands"

    @Cog.listener()
    async def on_user_update(self, before: User, after: User):
        if before.discriminator == "0":
            if before.name != after.name:
                if not self.bot.cache.get("pomelo"):
                    await self.bot.cache.set(
                        "pomelo",
                        [
                            {
                                "username": before.name,
                                "time": utils.format_dt(
                                    datetime.datetime.now(), style="R"
                                ),
                            }
                        ],
                    )
                else:
                    lol = self.bot.cache.get("pomelo")
                    lol.append(
                        {
                            "username": before.name,P
                            "time": utils.format_dt(datetime.datetime.now(), style="R"),
                        }
                    )
                    await self.bot.cache.set("pomelo", lol)

    @Cog.listener()
    async def on_member_update(self, before: Member, after: Member):
        if str(before.nick) != str(after.nick):
            if nickname := await self.bot.db.fetchval(
                "SELECT nickname FROM force_nick WHERE guild_id = $1 AND user_id = $2",
                before.guild.id,
                before.id,
            ):
                if after.nick != nickname:
                    await after.edit(
                        nick=nickname, reason="Force nickname applied to this member"
                    )

    @command(aliases=["handles"], brief="donor")
    @has_perks()
    async def lookup(self, ctx: GreedContext):
        """get the most recent handles"""
        if not self.bot.cache.get("pomelo"):
            return await ctx.send_error("There is nothing to see here")
        pomelo = self.bot.cache.get("pomelo")
        return await ctx.paginate(
            [f"{m['username']} - {m['time']}" for m in pomelo[::-1]],
            f"Usernames ({len(pomelo)})",
        )

    @command(aliases=["sp"], brief="donor")
    @has_perks()
    async def selfpurge(self, ctx: GreedContext, amount: int = 100):
        """delete your own messages"""
        await ctx.channel.purge(
            limit=amount,
            check=lambda m: m.author.id == ctx.author.id and not m.pinned,
            bulk=True,
        )

    @command(
        brief="manage nicknames & donor",
        aliases=["forcenick", "fn"],
        usage="forcenick @sent bro\nnone passed as a nickname removes the force nickname",
    )
    @has_perks()
    @has_guild_permissions(manage_nicknames=True)
    @bot_has_guild_permissions(manage_nicknames=True)
    async def forcenickname(self, ctx: GreedContext, member: NoStaff, *, nickname: str):
        """lock a nickname to a member"""
        if nickname.lower() == "none":
            if await self.bot.db.fetchrow(
                "SELECT * FROM force_nick WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id,
                member.id,
            ):
                await self.bot.db.execute(
                    "DELETE FROM force_nick WHERE guild_id = $1 AND user_id = $2",
                    ctx.guild.id,
                    member.id,
                )
                await member.edit(
                    nick=None, reason="Removed the force nickname from this member"
                )
                return await ctx.send_success("Removed the nickname from this member")
            else:
                return await ctx.send_warning(
                    "There is no force nickname assigned for this member"
                )
        else:
            if await self.bot.db.fetchrow(
                "SELECT * FROM force_nick WHERE guild_id = $1 AND user_id = $2",
                ctx.guild.id,
                member.id,
            ):
                await self.bot.db.execute(
                    "UPDATE force_nick SET nickname = $1 WHERE guild_id = $2 AND user_id = $3",
                    nickname,
                    ctx.guild.id,
                    member.id,
                )
                await member.edit(
                    nick=nickname, reason="Force nickname applied to this member"
                )
            else:
                await member.edit(
                    nick=nickname, reason="Force nickname applied to this member"
                )
                await self.bot.db.execute(
                    "INSERT INTO force_nick VALUES ($1,$2,$3)",
                    ctx.guild.id,
                    member.id,
                    nickname,
                )
            await ctx.send_success(
                f"Force nicknamed {member.mention} to **{nickname}**"
            )

        # @group(invoke_without_command=True)
        # async def reskin(self, ctx: GreedContext):
        # await ctx.create_pages()

        # @reskin.command(name="enable", brief="manage server")
        # @has_guild_permissions(manage_guild=True)
        # async def reskin_enable(self, ctx: GreedContext):
        """enable reskin feature in your server"""
        if await self.bot.db.fetchrow(
            "SELECT * FROM reskin_enabled WHERE guild_id = $1", ctx.guild.id
        ):
            return await ctx.send_warning("Reskin is **already** enabled")

        await self.bot.db.execute(
            "INSERT INTO reskin_enabled VALUES ($1)", ctx.guild.id
        )
        return await ctx.send_success("Reskin is now enabled")

        # @reskin.command(name="disable", brief="manage server")
        # @has_guild_permissions(manage_guild=True)
        # async def reskin_disable(self, ctx: GreedContext):
        """disable the reskin feature in your server"""
        if not await self.bot.db.fetchrow(
            "SELECT * FROM reskin_enabled WHERE guild_id = $1", ctx.guild.id
        ):
            return await ctx.send_warning("Reskin is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM reskin_enabled WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.send_success("Reskin is now disabled")

        # @reskin.command(name="name", brief="donor")
        # @has_perks()
        # @create_reskin()
        # async def reskin_name(self, ctx: GreedContext, *, name: ValidReskinName):
        """edit your reskin name"""
        await self.bot.db.execute(
            "UPDATE reskin SET username = $1 WHERE user_id = $2", name, ctx.author.id
        )
        return await ctx.send_success(f"Updated your reskin name to **{name}**")

        # @reskin.command(name="avatar", brief="donor", aliases=["icon", "pfp"])
        # @has_perks()
        # @create_reskin()
        # async def reskin_avatar(self, ctx: GreedContext, url: str = None):
        """change your reskin's avatar"""
        if url is None:
            url = await ctx.get_attachment()
            if not url:
                return ctx.send_help(ctx.command)
            else:
                url = url.url

        regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
        if not re.findall(regex, url):
            return await ctx.send_error("The image provided is not an url")

        await self.bot.db.execute(
            "UPDATE reskin SET avatar_url = $1 WHERE user_id = $2", url, ctx.author.id
        )
        return await ctx.send_success(f"Updated your reskin [**avatar**]({url})")

        # @reskin.command(name="remove", brief="donor", aliases=["delete", "reset"])
        # async def reskin_delete(self, ctx: GreedContext):
        """delete your reskin"""
        await self.bot.db.execute(
            "DELETE FROM reskin WHERE user_id = $1", ctx.author.id
        )
        return await ctx.send_success("Deleted your reskin")


async def setup(bot: Pretend) -> None:
    await bot.add_cog(Donor(bot))
