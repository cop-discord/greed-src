import asyncio
import datetime
import json as orjson
import re
from collections import defaultdict
from typing import Annotated, Optional

from discord import (
    Embed,
    Interaction,
    Member,
    Message,
    PermissionOverwrite,
    Role,
    TextChannel,
    Thread,
    User,
    utils,
    NotFound,
)
from discord.abc import GuildChannel
from discord.ext.commands import (
    Cog,
    CurrentChannel,
    bot_has_guild_permissions,
    command,
    group,
    has_guild_permissions,
    hybrid_command,
    hybrid_group,
)
from humanfriendly import format_timespan

from tools.bot import Pretend
from tools.converters import NewRoleConverter, TouchableMember
from tools.helpers import GreedContext, Invoking
from tools.predicates import admin_antinuke, is_jail
from tools.validators import ValidNickname, ValidTime


class Moderation(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Moderation commands"
        self.locks = defaultdict(asyncio.Lock)
        self.role_lock = defaultdict(asyncio.Lock)

    @Cog.listener()
    async def on_member_join(self, member: Member):
        if await self.bot.db.fetchrow(
            "SELECT * FROM jail_members WHERE guild_id = $1 AND user_id = $2",
            member.guild.id,
            member.id,
        ):
            if re := await self.bot.db.fetchrow(
                "SELECT role_id FROM jail WHERE guild_id = $1", member.guild.id
            ):
                if role := member.guild.get_role(re[0]):
                    await member.add_roles(role, reason="member jailed")

    @Cog.listener()
    async def on_member_remove(self, member: Member):
        await self.bot.redis.set(
            f"re-{member.id}-{member.guild.id}",
            orjson.dumps([r.id for r in member.roles]),
        )

    @Cog.listener()
    async def on_guild_channel_create(self, channel: GuildChannel):
        if check := await self.bot.db.fetchrow(
            "SELECT * FROM jail WHERE guild_id = $1", channel.guild.id
        ):
            if role := channel.guild.get_role(int(check["role_id"])):
                await channel.set_permissions(
                    role,
                    view_channel=False,
                    reason="overwriting permissions for jail role",
                )

    async def do_action(
        self, module: str, member: Member, reason: str, role: Optional[Role] = None
    ):
        guild = member.guild
        bot_perms = self.bot.an.get_bot_perms(guild)
        is_module_enabled = await self.bot.an.is_module(module, guild)
        is_whitelisted = await self.bot.an.is_whitelisted(member)
        check_threshold = await self.bot.an.check_threshold(module, member)
        hierarchy_check = self.bot.an.check_hieracy(member, guild.me)

        if not (bot_perms and is_module_enabled and not is_whitelisted):
            return

        if role or check_threshold:
            if not hierarchy_check:
                return

            cache_key = f"{module}-{guild.id}"
            cache = self.bot.cache.get(cache_key)

            if not cache:
                await self.bot.cache.set(cache_key, True, 5)
                action_time = datetime.datetime.now()
                check = await self.bot.db.fetchrow(
                    "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1", guild.id
                )

                if (
                    check
                    and check["owner_id"] is not None
                    and check["logs"] is not None
                ):
                    tasks = [
                        await self.bot.an.decide_punishment(module, member, reason)
                    ]
                    await self.bot.an.take_action(
                        reason,
                        member,
                        tasks,
                        action_time,
                        check["owner_id"],
                        guild.get_channel(check["logs"]),
                    )

    @hybrid_command(brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def restore(
        self, ctx: GreedContext, *, member: Annotated[Member, TouchableMember]
    ) -> Message:
        """
        give a member their roles back after rejoining
        """

        async with self.locks[ctx.guild.id]:
            check = await self.bot.redis.get(f"re-{member.id}-{ctx.guild.id}")

            if not check:
                return await ctx.send_error("This member doesn't have any roles saved")

            roles = [
                ctx.guild.get_role(r)
                for r in orjson.loads(check)
                if ctx.guild.get_role(r)
            ]
            await member.edit(
                roles=[r for r in roles if r.is_assignable()],
                reason=f"roles restored by {ctx.author}",
            )

            await self.bot.redis.delete(f"re-{member.id}-{ctx.guild.id}")
            await self.bot.logs.send_moderator(ctx, member)
            return await ctx.send_success(f"Restored {member.mention}'s roles")

    @command(brief="administrator")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    async def setme(self, ctx: GreedContext):
        """
        Set up jail module
        """

        async with self.locks[ctx.guild.id]:
            if await self.bot.db.fetchrow(
                "SELECT * FROM jail WHERE guild_id = $1", ctx.guild.id
            ):
                return await ctx.send_warning("Jail is **already** configured")

            mes = await ctx.pretend_send("Configuring jail..")
            async with ctx.typing():
                role = await ctx.guild.create_role(
                    name="jail", reason="creating jail channel"
                )

                await asyncio.gather(
                    *[
                        channel.set_permissions(role, view_channel=False)
                        for channel in ctx.guild.channels
                    ]
                )

                overwrite = {
                    role: PermissionOverwrite(view_channel=True),
                    ctx.guild.default_role: PermissionOverwrite(view_channel=False),
                }

                text = await ctx.guild.create_text_channel(
                    name="jail-greed",
                    overwrites=overwrite,
                    reason="creating jail channel",
                )
                await self.bot.db.execute(
                    """
      INSERT INTO jail
      VALUES ($1,$2,$3)
      """,
                    ctx.guild.id,
                    text.id,
                    role.id,
                )

                return await mes.edit(
                    embed=Embed(
                        color=self.bot.yes_color,
                        description=f"{self.bot.yes} {ctx.author.mention}: Jail succesfully configured",
                    )
                )

    @command(brief="administrator")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    @is_jail()
    async def unsetme(self, ctx: GreedContext):
        """
        disable the jail module
        """

        async def yes_func(interaction: Interaction):
            check = await self.bot.db.fetchrow(
                "SELECT * FROM jail WHERE guild_id = $1", interaction.guild.id
            )
            role = interaction.guild.get_role(check["role_id"])
            channel = interaction.guild.get_channel(check["channel_id"])

            if role:
                await role.delete(reason=f"jail disabled by {ctx.author}")

            if channel:
                await channel.delete(reason=f"jail disabled by {ctx.author}")

            for idk in [
                "DELETE FROM jail WHERE guild_id = $1",
                "DELETE FROM jail_members WHERE guild_id = $1",
            ]:
                await self.bot.db.execute(idk, interaction.guild.id)

            return await interaction.response.edit_message(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {interaction.user.mention}: Disabled the jail module",
                ),
                view=None,
            )

        async def no_func(interaction: Interaction) -> None:
            await interaction.response.edit_message(
                embed=Embed(color=self.bot.color, description="Cancelling action..."),
                view=None,
            )

        return await ctx.confirmation_send(
            f"{ctx.author.mention}: Are you sure you want to **disable** the jail module?\nThis action is **IRREVERSIBLE**",
            yes_func,
            no_func,
        )

    @hybrid_command(brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_roles=True)
    @is_jail()
    async def jail(
        self,
        ctx: GreedContext,
        member: Annotated[Member, TouchableMember],
        *,
        reason: str = "No reason provided",
    ):
        """
        Restrict someone from the server's channels
        """

        if member.id == ctx.author.id:
            return await ctx.send_warning(f"You cannot manage {ctx.author.mention}")

        if await self.bot.db.fetchrow(
            "SELECT * FROM jail_members WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member.id,
        ):
            return await ctx.send_warning(f"{member.mention} is **already** jailed")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM jail WHERE guild_id = $1", ctx.guild.id
        )
        role = ctx.guild.get_role(check["role_id"])

        if not role:
            return await ctx.send_error(
                "Jail role **not found**. Please unset jail and set it back"
            )

        old_roles = [r.id for r in member.roles if r.is_assignable()]
        roles = [r for r in member.roles if not r.is_assignable()]
        roles.append(role)
        await member.edit(roles=roles, reason=reason)

        try:
            await member.send(
                f"{member.mention}, you have been jailed in **{ctx.guild.name}** (`{ctx.guild.id}`) - {reason}! Wait for a staff member to unjail you"
            )
        except Exception:
            pass

        await self.bot.db.execute(
            """
    INSERT INTO jail_members VALUES ($1,$2,$3,$4)
    """,
            ctx.guild.id,
            member.id,
            orjson.dumps(old_roles),
            datetime.datetime.now(),
        )
        await self.bot.logs.send_moderator(ctx, member)
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Jailed {member.mention} - {reason}")

    @hybrid_command(brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_roles=True)
    @is_jail()
    async def unjail(
        self, ctx: GreedContext, member: Member, *, reason: str = "No reason provided"
    ):
        """
        lift the jail restriction from a member
        """

        re = await self.bot.db.fetchrow(
            """
    SELECT roles FROM jail_members
    WHERE guild_id = $1
    AND user_id = $2
    """,
            ctx.guild.id,
            member.id,
        )
        if not re:
            return await ctx.send_warning(f"{member.mention} is **not** jailed")

        roles = [
            ctx.guild.get_role(r) for r in orjson.loads(re[0]) if ctx.guild.get_role(r)
        ]

        if ctx.guild.premium_subscriber_role in member.roles:
            roles.append(ctx.guild.premium_subscriber_role)

        await member.edit(roles=[r for r in roles], reason=reason)
        await self.bot.db.execute(
            """
    DELETE FROM jail_members
    WHERE guild_id = $1
    AND user_id = $2
    """,
            ctx.guild.id,
            member.id,
        )
        await self.bot.logs.send_moderator(ctx, member)
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Unjailed {member.mention} - {reason}")

    @command()
    async def jailed(self, ctx: GreedContext):
        """
        returns the jailed members
        """

        results = await self.bot.db.fetch(
            "SELECT * FROM jail_members WHERE guild_id = $1", ctx.guild.id
        )
        jailed = [
            f"<@{result['user_id']}> - {utils.format_dt(result['jailed_at'], style='R')}"
            for result in results
            if ctx.guild.get_member(result["user_id"])
        ]

        if len(jailed) > 0:
            return await ctx.paginate(
                jailed,
                f"Jailed members ({len(results)})",
                {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
            )
        else:
            return await ctx.send_warning("There are no jailed members")

    @hybrid_command(brief="mute members")
    @has_guild_permissions(mute_members=True)
    @bot_has_guild_permissions(mute_members=True)
    async def voicemute(
        self, ctx: GreedContext, *, member: Annotated[Member, TouchableMember]
    ):
        """
        Voice mute a member
        """

        if not member.voice:
            return await ctx.send_error("This member is **not** in a voice channel")

        if member.voice.mute:
            return await ctx.send_warning("This member is **already** muted")

        await member.edit(mute=True, reason=f"Member voice muted by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        await ctx.send_success(f"Voice muted {member.mention}")

    @hybrid_command(brief="mute members")
    @has_guild_permissions(mute_members=True)
    @bot_has_guild_permissions(mute_members=True)
    async def voiceunmute(
        self, ctx: GreedContext, *, member: Annotated[Member, TouchableMember]
    ):
        """
        Voice unmute a member
        """

        if not member.voice.mute:
            return await ctx.send_warning("This member is **not** voice muted")

        await member.edit(mute=False, reason=f"Member voice unmuted by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        await ctx.send_success(f"Voice unmuted {member.mention}")

    @hybrid_command(brief="deafen members")
    @has_guild_permissions(deafen_members=True)
    @bot_has_guild_permissions(deafen_members=True)
    async def voicedeafen(
        self, ctx: GreedContext, *, member: Annotated[Member, TouchableMember]
    ):
        """
        Deafen a member in a voice channel
        """

        if not member.voice:
            return await ctx.send_error("This member is **not** in a voice channel")

        if member.voice.deaf:
            return await ctx.send_warning("This member is **already** voice deafened")

        await member.edit(deafen=True, reason=f"Member voice deafened by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        await ctx.send_success(f"Voice deafened {member.mention}")

    @hybrid_command(brief="deafen members")
    @has_guild_permissions(deafen_members=True)
    @bot_has_guild_permissions(deafen_members=True)
    async def voiceundeafen(
        self, ctx: GreedContext, *, member: Annotated[Member, TouchableMember]
    ):
        """
        Voice undeafen a member
        """

        if not member.voice.deaf:
            return await ctx.send_warning("This member is **not** deafened")

        await member.edit(deafen=False, reason=f"Voice undeafened by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        await ctx.send_success(f"Voice undeafened {member.mention}")

    @group(name="clear", invoke_without_command=True)
    async def idk_clear(self, ctx):
        return await ctx.create_pages()

    @idk_clear.command(name="invites", brief="Manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def clear_invites(self, ctx: GreedContext, limit: int):
        """
        Clear messages that contain Discord invite links.
        """
        if limit > 100:
            await ctx.send_warning("You can only delete up to 100 messages at a time.")
            return

        regex = r"discord(?:\.com|app\.com|\.gg)/(?:invite/)?([a-zA-Z0-9\-]{2,32})"
        await ctx.channel.purge(
            limit=limit,
            check=lambda m: re.search(regex, m.content),
            reason=f"Invite messages purged by {ctx.author}",
        )

    @idk_clear.command(name="contains", brief="Manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def contains(self, ctx: GreedContext, limit: int, *, word: str):
        """
        Clear messages that contain a certain word.
        """
        if limit > 100:
            await ctx.send("You can only delete up to 100 messages at a time.")
            return

        await ctx.channel.purge(
            limit=limit,
            check=lambda m: word in m.content,
            reason=f"Messages containing '{word}' purged by {ctx.author}",
        )

    @idk_clear.command(name="images", brief="Manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def clear_images(self, ctx: GreedContext, limit: int):
        """
        Clear messages that have attachments.
        """

        if limit > 100:
            await ctx.send_warning("You can only delete up to 100 messages at a time.")
            return

        await ctx.channel.purge(
            limit=limit,
            check=lambda m: m.attachments,
            reason=f"Image messages purged by {ctx.author}",
        )

    @command(brief="Manage messages", aliases=["c"])
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def purge(self, ctx: GreedContext, number: int, *, member: Member = None):
        """
        Delete multiple messages at once (up to 100).
        """
        if number > 100:
            await ctx.send_warning("You can only delete up to 100 messages at a time.")
            return

        async with self.locks[ctx.channel.id]:
            if not member:

                def check(m):
                    return not m.pinned
            else:

                def check(m):
                    return m.author.id == member.id and not m.pinned

            await ctx.message.delete()
            await ctx.channel.purge(
                limit=number, check=check, reason=f"Chat purged by {ctx.author}"
            )

    @command(name="botclear", brief="Manage messages", aliases=["bc", "bp", "botpurge"])
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_messages=True)
    async def botclear(self, ctx: GreedContext, limit: int):
        """
        Delete messages sent by bots.
        """
        if limit > 100:
            await ctx.send("You can only delete up to 100 messages at a time.")
            return

        async with self.locks[ctx.channel.id]:
            await ctx.channel.purge(
                limit=limit,
                check=lambda m: m.author.bot and not m.pinned,
                reason=f"Bot messages purged by {ctx.author}",
            )

    @hybrid_group(brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def lock(self, ctx: GreedContext, *, channel: TextChannel = CurrentChannel):
        """
        lock a channel
        """

        if channel.overwrites_for(ctx.guild.default_role).send_messages is False:
            return await ctx.send_error("Channel is **already** locked")

        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = False
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=f"channel locked by {ctx.author}",
        )
        return await ctx.send_success(f"Locked {channel.mention}")

    @lock.command(name="all", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def lock_all(self, ctx: GreedContext, *, reason: str = "No reason provided"):
        """
        Lock all channels
        """

        async with ctx.channel.typing():
            for channel in ctx.guild.text_channels:
                if (
                    channel.overwrites_for(ctx.guild.default_role).send_messages
                    is False
                ):
                    continue

                if check := await self.bot.db.fetchrow(
                    """
       SELECT role_id FROM lock_role
       WHERE guild_id = $1
       """,
                    ctx.guild.id,
                ):
                    if ctx.guild.get_role(check["role_id"]):
                        role = ctx.guild.get_role(check["role_id"])
                    else:
                        role = ctx.guild.default_role
                else:
                    role = ctx.guild.default_role

                overwrites = channel.overwrites_for(role)
                overwrites.send_messages = False

                await channel.set_permissions(
                    role,
                    overwrite=overwrites,
                    reason=f"{ctx.author} ({ctx.author.id}) locked all channels: {reason}",
                )
                await asyncio.sleep(1.5)

        return await ctx.send_success("Locked **all** channels")

    @lock.group(name="ignore", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def lock_ignore(self, ctx: GreedContext):
        """
        Ignore channels from being unlocked when using ;unlock all
        """

        await ctx.create_pages()

    @lock_ignore.command(name="add", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def lock_ignore_add(self, ctx: GreedContext, *, channel: TextChannel):
        """
        Add a channel to be ignored when using ;unlock all
        """

        if await self.bot.db.fetchrow(
            """
    SELECT * FROM lockdown_ignore
    WHERE guild_id = $1
    AND channel_id = $2
    """,
            ctx.guild.id,
            channel.id,
        ):
            return await ctx.send_warning(f"{channel.mention} is **already** ignored")

        await self.bot.db.execute(
            """
    INSERT INTO lockdown_ignore
    VALUES ($1, $2)
    """,
            ctx.guild.id,
            channel.id,
        )
        await ctx.send_success(
            f"Now **ignoring** {channel.mention} from `{ctx.clean_prefix}unlock all`"
        )

    @lock_ignore.command(name="remove", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def lock_ignore_remove(self, ctx: GreedContext, *, channel: TextChannel):
        """
        No longer ignore a channel from unlock all
        """

        if not await self.bot.db.fetchrow(
            """
    SELECT * FROM lockdown_ignore
    WHERE guild_id = $1
    AND channel_id = $2
    """,
            ctx.guild.id,
            channel.id,
        ):
            return await ctx.send_warning(f"{channel.mention} is **not** ignored")

        await self.bot.db.execute(
            """
    DELETE FROM lockdown_ignore
    WHERE guild_id = $1
    AND channel_id = $2
    """,
            ctx.guild.id,
            channel.id,
        )
        await ctx.send_success(f"No longer **ignoring** {channel.mention} from unlock")

    @lock_ignore.command(name="list", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    async def lock_ignore_list(self, ctx: GreedContext):
        """
        View all ignored unlock channels
        """

        results = await self.bot.db.fetch(
            """
    SELECT * FROM lockdown_ignore
    WHERE guild_id = $1
    """,
            ctx.guild.id,
        )

        if not results:
            return await ctx.send_warning("There are no ignored unlock channels")

        await ctx.paginate(
            [
                f"{ctx.guild.get_channel(result['channel_id']).mention}"
                for result in results
            ],
            title=f"Ignored Unlock Channels ({len(results)})",
            author={
                "name": ctx.guild.name,
                "icon_url": ctx.guild.icon.url if ctx.guild.icon else None,
            },
        )

    @lock.command(name="role", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def lock_role(self, ctx: GreedContext, role: Role):
        """
        Set the default role for lockdown
        """

        if await self.bot.db.execute(
            "SELECT * FROM lock_role WHERE guild_id = $1", ctx.guild.id
        ):
            args = [
                "UPDATE lock_role SET role_id = $1 WHERE guild_id = $2",
                role.id,
                ctx.guild.id,
            ]
            message = f"Updated the **lock role** to {role.mention}"
        else:
            args = ["INSERT INTO lock_role VALUES ($1, $2)", ctx.guild.id, role.id]
            message = f"Set the **lock role** to {role.mention}"

        await self.bot.db.execute(*args)
        await ctx.send_success(message)

    @hybrid_group(brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def unlock(self, ctx: GreedContext, *, channel: TextChannel = CurrentChannel):
        """
        unlock a channel
        """

        if (
            channel.overwrites_for(ctx.guild.default_role).send_messages is True
            or channel.overwrites_for(ctx.guild.default_role).send_messages is None
        ):
            return await ctx.send_error("Channel is **already** unlocked")

        overwrites = channel.overwrites_for(ctx.guild.default_role)
        overwrites.send_messages = None
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrites,
            reason=f"channel unlocked by {ctx.author}",
        )
        return await ctx.send_success(f"Unlocked {channel.mention}")

    @unlock.command(name="all", brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def unlock_all(
        self, ctx: GreedContext, *, reason: str = "No reason provided"
    ):
        """
        Unlock all locked channels
        """

        ignored_channels = await self.bot.db.fetch(
            """
    SELECT channel_id FROM lockdown_ignore
    WHERE guild_id = $1
    """,
            ctx.guild.id,
        )

        async with ctx.channel.typing():
            for channel in ctx.guild.text_channels:
                if (
                    channel.overwrites_for(ctx.guild.default_role).send_messages is True
                    or channel.id in ignored_channels
                ):
                    continue

                if check := await self.bot.db.fetchrow(
                    """
       SELECT role_id FROM lock_role
       WHERE guild_id = $1
       """,
                    ctx.guild.id,
                ):
                    if ctx.guild.get_role(check["role_id"]):
                        role = ctx.guild.get_role(check["role_id"])
                    else:
                        role = ctx.guild.default_role
                else:
                    role = ctx.guild.default_role

                overwrite = channel.overwrites_for(role)
                overwrite.send_messages = True
                await channel.set_permissions(
                    role,
                    overwrite=overwrite,
                    reason=f"{ctx.author} ({ctx.author.id}) unlocked all channels: {reason}",
                )

        await ctx.send_success("Unlocked all channels")

    @command(name="reactionmute", aliases=["rmute"], brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def reactionmute(
        self, ctx: GreedContext, member: Annotated[Member, TouchableMember]
    ):
        """
        Revoke a member's reaction permissions
        """

        if ctx.channel.overwrites_for(member).add_reactions is False:
            return await ctx.send_warning(
                f"{member.mention} is **already** reaction muted"
            )

        overwrites = ctx.channel.overwrites_for(member)
        overwrites.add_reactions = False

        await ctx.channel.set_permissions(
            member,
            overwrite=overwrites,
            reason=f"Reaction permissions removed by {ctx.author} ({ctx.author.id})",
        )
        await ctx.message.add_reaction("✅")

    @command(name="reactionunmute", aliases=["runmute"], brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def reactionunmute(
        self, ctx: GreedContext, member: Annotated[Member, TouchableMember]
    ):
        """
        Grant a reaction muted member reaction permissions
        """

        if (
            ctx.channel.overwrites_for(member).add_reactions is True
            or ctx.channel.overwrites_for(member).add_reactions is None
        ):
            return await ctx.send_warning(f"{member.mention} is **not** reaction muted")

        overwrites = ctx.channel.overwrites_for(member)
        overwrites.add_reactions = True

        await ctx.channel.set_permissions(
            member,
            overwrite=overwrites,
            reason=f"Reaction unmuted by {ctx.author} ({ctx.author.id})",
        )
        await ctx.message.add_reaction("✅")

    @command(name="hardban", brief="administrator & antinuke admin")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(ban_members=True)
    @admin_antinuke()
    async def hardban(
        self,
        ctx: GreedContext,
        user: Member | User,
        *,
        reason: str = "No reason provided",
    ):
        """
        Permanently ban a user from the server.
        """

        if isinstance(user, Member):
            await TouchableMember().check(ctx, user)

        await ctx.prompt(f"Are you sure you want to **hardban** {user.mention}?")
        await ctx.guild.ban(
            user, reason=f"Hardbanned by {ctx.author} ({ctx.author.id}): {reason}"
        )

        await self.bot.db.execute(
            """
            INSERT INTO hardban
            VALUES ($1, $2, $3, $4)
            """,
            ctx.guild.id,
            user.id,
            reason,
            ctx.author.id,
        )

        await ctx.send_success(f"Hardbanned {user.mention}")

    @command(name="unhardban", brief="administrator & antinuke admin")
    @has_guild_permissions(administrator=True)
    @bot_has_guild_permissions(ban_members=True)
    @admin_antinuke()
    async def unhardban(
        self, ctx: GreedContext, user: User, *, reason: str = "No reason provided"
    ):
        """
        Unhardban a hardbanned member
        """

        check = await self.bot.db.fetchrow(
            """
            SELECT * FROM hardban
            WHERE guild_id = $1
            AND user_id = $2
            """,
            ctx.guild.id,
            user.id,
        )

        if not check:
            return await ctx.send_warning(f"{user.mention} is **not** hardbanned")

        if (
            ctx.author.id != ctx.guild.owner.id
            and ctx.author.id != check["moderator_id"]
        ):
            moderator = self.bot.get_user(check["moderator_id"])
            return await ctx.send_warning(
                f"Only {moderator.mention}{f'/{ctx.guild.owner.mention}' if moderator.id != ctx.guild.owner.id else ''} can unhardban {user.mention}"
            )

        await self.bot.db.execute(
            """
            DELETE FROM hardban
            WHERE guild_id = $1
            AND user_id = $2
            """,
            ctx.guild.id,
            user.id,
        )

        try:
            await ctx.guild.unban(
                user, reason=f"Unhardbanned by {ctx.author} ({ctx.author.id}): {reason}"
            )
        except Exception:
            pass

        await ctx.send_success(f"Unhardbanned {user.mention}")

    @command(name="revokefiles", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    async def revokefiles(
        self,
        ctx: GreedContext,
        state: str,
        member: Annotated[Member, TouchableMember],
        *,
        reason: str = "No reason provided",
    ):
        """
        Remove file attachment permissions from a member
        """

        if state.lower() not in ("on", "off"):
            return await ctx.send_warning(
                "Invalid state- please provide **on** or **off**"
            )

        if state.lower().strip() == "on":
            overwrite = ctx.channel.overwrites_for(member)
            overwrite.attach_files = False

            await ctx.channel.set_permissions(
                member,
                overwrite=overwrite,
                reason=f"{ctx.author} ({ctx.author.id}) removed file attachment permissions: {reason}",
            )
        elif state.lower().strip() == "off":
            overwrite = ctx.channel.overwrites_for(member)
            overwrite.attach_files = True

            await ctx.channel.set_permissions(
                member,
                overwrite=overwrite,
                reason=f"{ctx.author} ({ctx.author.id}) removed file attachment permissions: {reason}",
            )

        await ctx.message.add_reaction("✅")

    @group(
        name="restrictcommand",
        aliases=["restrictcmd", "rc"],
        brief="manage sever",
        invoke_without_command=True,
    )
    @has_guild_permissions(manage_guild=True)
    async def restrictcommand(self, ctx: GreedContext):
        """
        Restrict people without roles from using commands
        """

        await ctx.create_pages()

    @restrictcommand.command(name="add", aliases=["make"], brief="manage sever")
    @has_guild_permissions(manage_guild=True)
    async def restrictcommand_add(self, ctx: GreedContext, command: str, *, role: Role):
        """
        Restrict a command to the given role
        """

        command = command.replace(".", "")
        _command = self.bot.get_command(command)
        if not _command:
            return await ctx.send_warning(f"Command `{command}` does not exist")

        if _command.name in ("help", "restrictcommand", "disablecmd", "enablecmd"):
            return await ctx.send("no lol")

        if not await self.bot.db.fetchrow(
            "SELECT * FROM restrictcommand WHERE guild_id = $1 AND command = $2 AND role_id = $3",
            ctx.guild.id,
            _command.qualified_name,
            role.id,
        ):
            await self.bot.db.execute(
                """
        INSERT INTO restrictcommand
        VALUES ($1, $2, $3)
        """,
                ctx.guild.id,
                _command.qualified_name,
                role.id,
            )
        else:
            return await ctx.send_warning(
                f"`{_command.qualified_name}` is **already** restricted to {role.mention}"
            )

        await ctx.send_success(
            f"Allowing members with {role.mention} to use `{_command.qualified_name}`"
        )

    @restrictcommand.command(
        name="remove", aliases=["delete", "del"], brief="manage sever"
    )
    @has_guild_permissions(manage_guild=True)
    async def restrictcommand_remove(
        self, ctx: GreedContext, command: str, *, role: Role
    ):
        """
        Stop allowing a role to use a command
        """

        command = command.replace(".", "")
        _command = self.bot.get_command(command)
        if not _command:
            return await ctx.send_warning(f"Command `{command}` does not exist")

        if await self.bot.db.fetchrow(
            "SELECT * FROM restrictcommand WHERE guild_id = $1 AND command = $2 AND role_id = $3",
            ctx.guild.id,
            _command.qualified_name,
            role.id,
        ):
            await self.bot.db.execute(
                """
        DELETE FROM restrictcommand
        WHERE guild_id = $1
        AND command = $2
        AND role_id = $3
        """,
                ctx.guild.id,
                _command.qualified_name,
                role.id,
            )
        else:
            return await ctx.send_warning(
                f"`{_command.qualified_name}` is **not** restricted to {role.mention}"
            )

        await ctx.send_success(
            f"No longer allowing members with {role.mention} to use `{_command.qualified_name}`"
        )

    @restrictcommand.command(name="list", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    async def restrictcommand_list(self, ctx: GreedContext):
        """
        Get a list of all restricted commands
        """

        results = await self.bot.db.fetch(
            """
      SELECT * FROM restrictcommand
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if not results:
            return await ctx.send_warning("There are **no** restricted commands")

        await ctx.paginate(
            [
                f"**{result['command']}**: {ctx.guild.get_role(result['role_id']).mention}"
                for result in results
            ],
            title=f"Restricted Commands ({len(results)})",
            author={
                "name": ctx.guild.name,
                "icon_url": ctx.guild.icon if ctx.guild.icon else None,
            },
        )

    @hybrid_command(brief="manage channels")
    @has_guild_permissions(manage_channels=True)
    @bot_has_guild_permissions(manage_channels=True)
    async def slowmode(
        self,
        ctx: GreedContext,
        time: ValidTime,
        *,
        channel: TextChannel = CurrentChannel,
    ):
        """
        enable slowmode option in a text channel
        """

        await channel.edit(
            slowmode_delay=time, reason=f"Slowmode invoked by {ctx.author}"
        )
        await ctx.send_success(
            f"Slowmode for {channel.mention} set to **{format_timespan(time)}**"
        )

    @hybrid_command(brief="moderate members", aliases=["timeout"])
    @has_guild_permissions(moderate_members=True)
    @bot_has_guild_permissions(moderate_members=True)
    async def mute(
        self,
        ctx: GreedContext,
        member: Annotated[Member, TouchableMember],
        time: ValidTime = 3600,
        *,
        reason: str = "No reason provided",
    ):
        """
        timeout a member
        """

        if member.is_timed_out():
            return await ctx.send_error(f"{member.mention} is **already** muted")

        if member.guild_permissions.administrator:
            return await ctx.send_warning("You **cannot** mute an administrator")

        await member.timeout(
            utils.utcnow() + datetime.timedelta(seconds=time), reason=reason
        )
        await self.bot.logs.send_moderator(ctx, member)
        if not await Invoking(ctx).send(member, reason):
            await ctx.send_success(
                f"Muted {member.mention} for {format_timespan(time)} - **{reason}**"
            )

    @hybrid_command(brief="moderate members", aliases=["untimeout"])
    @has_guild_permissions(moderate_members=True)
    @bot_has_guild_permissions(moderate_members=True)
    async def unmute(
        self,
        ctx: GreedContext,
        member: Annotated[Member, TouchableMember],
        *,
        reason: str = "No reason provided",
    ):
        """
        Remove the timeout from a member
        """
        if not member.is_timed_out():
            return await ctx.send_error(f"{member.mention} is **not** muted")

        await member.timeout(None, reason=reason)
        await self.bot.logs.send_moderator(ctx, member)
        if not await Invoking(ctx).send(member, reason):
            await ctx.send_success(f"Unmuted {member.mention} - **{reason}**")

    @hybrid_command(
        name="ban", help="Ban a member from the server", brief="ban members"
    )
    @has_guild_permissions(ban_members=True)
    @bot_has_guild_permissions(ban_members=True)
    async def ban(
        self,
        ctx: GreedContext,
        user: Member | User,
        *,
        reason: str = "No reason provided",
    ):
        if isinstance(user, Member):
            await TouchableMember().check(ctx, user)
            if user.premium_since:
                await ctx.prompt(
                    f"Are you sure you want to **ban** {user.mention}?",
                    "They are currently boosting the server!",
                )

        await ctx.guild.ban(user, reason=reason)
        await self.bot.logs.send_moderator(ctx, user)
        await self.do_action("ban", ctx.author, "Banning Members")
        if not await Invoking(ctx).send(user, reason):
            await ctx.send_success(f"Banned {user.mention} - **{reason}**")

    @command(aliases=["pardon"], brief="ban members")
    @has_guild_permissions(ban_members=True)
    @bot_has_guild_permissions(ban_members=True)
    async def unban(
        self,
        ctx: GreedContext,
        user: User,
        *,
        reason: str = "No reason provided",
    ):
        """
        Unban a member from the server
        """
        try:
            await ctx.guild.unban(user, reason=reason)
        except NotFound:
            return await ctx.send_warning(f"{user.mention} is **not** banned")

        await self.bot.logs.send_moderator(ctx, user)
        await self.do_action("ban", ctx.author, "Unbanning Members")
        await ctx.send_success(f"Unbanned {user.mention} - **{reason}**")

    @command(aliases=["boot", "k"])
    @has_guild_permissions(kick_members=True)
    @bot_has_guild_permissions(kick_members=True)
    async def kick(
        self,
        ctx: GreedContext,
        member: Annotated[
            Member,
            TouchableMember,
        ],
        *,
        reason: str = "No reason provided",
    ) -> Optional[Message]:
        """
        Kick a member from the server.
        """

        if member.premium_since:
            await ctx.prompt(
                f"Are you sure you want to **kick** {member.mention}?",
                "They are currently boosting the server!",
            )

        await member.kick(reason=reason)
        await self.bot.logs.send_moderator(ctx, member)
        await self.do_action("ban", ctx.author, "Kicking Members")
        if not await Invoking(ctx).send(member, reason):
            return await ctx.send_success(f"Kicked {member.mention} - **{reason}**")

    @hybrid_command(brief="manage roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def strip(
        self, ctx: GreedContext, member: Annotated[Member, TouchableMember]
    ) -> Message:
        """
        remove someone's dangerous roles
        """

        roles = [
            role
            for role in member.roles
            if role.is_assignable()
            and not self.bot.is_dangerous(role)
            or role == ctx.guild.premium_subscriber_role
        ]
        await self.bot.logs.send_moderator(ctx, member)
        await member.edit(roles=roles, reason=f"member stripped by {ctx.author}")
        return await ctx.send_success(f"Stripped {member.mention}'s roles")

    @command(aliases=["nick"], brief="manage nicknames")
    @has_guild_permissions(manage_nicknames=True)
    @bot_has_guild_permissions(manage_nicknames=True)
    async def nickname(
        self,
        ctx: GreedContext,
        member: Annotated[Member, TouchableMember],
        *,
        nick: ValidNickname,
    ):
        """
        change a member's nickname
        """

        await member.edit(nick=nick, reason=f"Nickname changed by {ctx.author}")
        await self.bot.logs.send_moderator(ctx, member)
        return await ctx.send_success(
            f"Changed {member.mention} nickname to **{nick}**"
            if nick
            else f"Removed {member.mention}'s nickname"
        )

    @group(invoke_without_command=True)
    @has_guild_permissions(manage_messages=True)
    async def warn(
        self,
        ctx: GreedContext,
        member: Annotated[Member, TouchableMember],
        *,
        reason: str = "No reason provided",
    ):
        if member is None:
            return await ctx.create_pages()
        await self.bot.logs.send_moderator(ctx, member)
        date = datetime.datetime.now()
        await self.bot.db.execute(
            """
            INSERT INTO warns
            VALUES ($1,$2,$3,$4,$5)
            """,
            ctx.guild.id,
            member.id,
            ctx.author.id,
            f"{date.day}/{f'0{date.month}' if date.month < 10 else date.month}/{str(date.year)[-2:]} at {datetime.datetime.strptime(f'{date.hour}:{date.minute}', '%H:%M').strftime('%I:%M %p')}",
            reason,
        )
        await ctx.send_success(f"Warned {member.mention} | {reason}")

    @warn.command(name="clear", brief="manage messages")
    @has_guild_permissions(manage_messages=True)
    async def warn_clear(
        self,
        ctx: GreedContext,
        *,
        member: Annotated[Member, TouchableMember],
    ):
        """
        clear all warns from an user
        """

        check = await self.bot.db.fetch(
            """
            SELECT * FROM warns
            WHERE guild_id = $1
            AND user_id = $2
            """,
            ctx.guild.id,
            member.id,
        )

        if len(check) == 0:
            return await ctx.send_warning("this user has no warnings".capitalize())

        await self.bot.db.execute(
            "DELETE FROM warns WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            member.id,
        )
        await ctx.send_success(f"Removed {member.mention}'s warns")

    @warn.command(name="list")
    async def warn_list(self, ctx: GreedContext, *, member: Member):
        """
        returns all warns that an user has
        """

        check = await self.bot.db.fetch(
            """
            SELECT * FROM warns 
            WHERE guild_id = $1
            AND user_id = $2
            """,
            ctx.guild.id,
            member.id,
        )

        if len(check) == 0:
            return await ctx.send_warning("this user has no warnings".capitalize())

        return await ctx.paginate(
            [
                f"{result['time']} by <@!{result['author_id']}> - {result['reason']}"
                for result in check
            ],
            f"Warnings ({len(check)})",
            {"name": member.name, "icon_url": member.display_avatar.url},
        )

    @command()
    async def warns(self, ctx: GreedContext, *, member: Member):
        """
        shows all warns of an user
        """

        return await ctx.invoke(self.bot.get_command("warn list"), member=member)

    @command(brief="server owner")
    @admin_antinuke()
    @bot_has_guild_permissions(manage_channels=True)
    async def nuke(self, ctx: GreedContext):
        """
        replace the current channel with a new one
        """

        async with self.locks[ctx.channel.id]:

            async def yes_callback(interaction: Interaction) -> None:
                new_channel = await interaction.channel.clone(
                    name=interaction.channel.name,
                    reason="Nuking channel invoked by the server owner",
                )
                await new_channel.edit(
                    topic=interaction.channel.topic,
                    position=interaction.channel.position,
                    nsfw=interaction.channel.nsfw,
                    slowmode_delay=interaction.channel.slowmode_delay,
                    type=interaction.channel.type,
                    reason="Nuking channel invoked by the server owner",
                )

                await interaction.channel.delete(
                    reason="Channel nuked by the server owner"
                )
                await self.bot.logs.send_moderator(ctx, ctx.channel)
                await new_channel.send("💣")

            async def no_callback(interaction: Interaction) -> None:
                await interaction.response.edit_message(
                    embed=Embed(
                        color=self.bot.color, description="Cancelling action..."
                    ),
                    view=None,
                )

            await ctx.confirmation_send(
                f"{ctx.author.mention}: Are you sure you want to **nuke** this channel?\nThis action is **IRREVERSIBLE**",
                yes_callback,
                no_callback,
            )

    @command(brief="manage_roles")
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def roleall(self, ctx: GreedContext, *, role: NewRoleConverter):
        """
        add a role to all members
        """

        async with self.role_lock[ctx.guild.id]:
            tasks = [
                m.add_roles(role, reason=f"Role all invoked by {ctx.author}")
                for m in ctx.guild.members
                if role not in m.roles
            ]

            if len(tasks) == 0:
                return await ctx.send_warning("Everyone has this role")

            mes = await ctx.pretend_send(
                f"Giving {role.mention} to **{len(tasks)}** members. This operation might take around **{format_timespan(0.3*len(tasks))}**"
            )
            await self.bot.logs.send_moderator(ctx, role)
            await asyncio.gather(*tasks)
            return await mes.edit(
                embed=Embed(
                    color=self.bot.yes_color,
                    description=f"{self.bot.yes} {ctx.author.mention}: Added {role.mention} to **{len(tasks)}** members",
                )
            )

    @command(brief="manage_roles", aliases=["r"])
    @has_guild_permissions(manage_roles=True)
    @bot_has_guild_permissions(manage_roles=True)
    async def role(self, ctx: GreedContext, member: Member, *, role_string: str):
        """
        Add roles to a member
        """

        roles = [
            await NewRoleConverter().convert(ctx, r) for r in role_string.split(", ")
        ]

        if len(roles) == 0:
            return await ctx.send_help(ctx.command)

        if len(roles) > 7:
            return await ctx.send_error("Too many roles parsed")

        if any(self.bot.is_dangerous(r) for r in roles):
            if await self.bot.an.is_module("role giving", ctx.guild):
                if not await self.bot.an.is_whitelisted(ctx.author):
                    roles = [r for r in roles if not self.bot.is_dangerous(r)]

        if len(roles) > 0:
            async with self.locks[ctx.guild.id]:
                role_mentions = []
                for role in roles:
                    if role not in member.roles:
                        await member.add_roles(
                            role, reason=f"{ctx.author} added the role"
                        )
                        role_mentions.append(f"**+**{role.mention}")
                    else:
                        await member.remove_roles(
                            role, reason=f"{ctx.author} removed the role"
                        )
                        role_mentions.append(f"**-**{role.mention}")

                return await ctx.send_success(
                    f"Edited {member.mention}'s roles: {', '.join(role_mentions)}"
                )
        else:
            return await ctx.send_error("There are no roles that you can give")

    @group(name="thread", brief="manage threads", invoke_without_command=True)
    @has_guild_permissions(manage_threads=True)
    async def thread(self, ctx: GreedContext):
        """
        Manage threads/forum posts
        """

        await ctx.create_pages()

    @thread.command(name="lock", brief="manage threads")
    @has_guild_permissions(manage_threads=True)
    async def thread_lock(self, ctx: GreedContext, thread: Thread = None):
        """
        Lock a thread/forum post
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a **thread**")

        if thread.locked:
            return await ctx.send_warning(f"{thread.mention} is already **locked**")

        await thread.edit(locked=True)
        await ctx.send_success(f"Successfully **locked** {thread.mention}")

    @thread.command(name="unlock", brief="manage threads")
    @has_guild_permissions(manage_threads=True)
    async def thread_unlock(self, ctx: GreedContext, thread: Thread = None):
        """
        Unock a thread/forum post
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a **thread**")

        if not thread.locked:
            return await ctx.send_warning(f"{thread.mention} is already **unlocked**")

        await thread.edit(locked=False)
        await ctx.send_success(f"Successfully **unlocked** {thread.mention}")

    @thread.command(name="rename", brief="manage threads")
    @has_guild_permissions(manage_threads=True)
    async def thread_rename(
        self, ctx: GreedContext, thread: Optional[Thread] = None, *, name: str
    ):
        """
        Rename a thread/forum post
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a **thread**")

        await thread.edit(name=name)
        await ctx.message.add_reaction("✅")

    @thread.command(name="delete", brief="manage threads")
    @has_guild_permissions(manage_threads=True)
    async def thread_delete(self, ctx: GreedContext, thread: Thread = None):
        """
        Delete a thread/forum post
        """

        thread = thread or ctx.channel

        if not isinstance(thread, Thread):
            return await ctx.send_warning(f"{thread.mention} is not a **thread**")

        await thread.delete()
        if thread != ctx.channel:
            await ctx.message.add_reaction("✅")


async def setup(bot: Pretend) -> None:
    await bot.add_cog(Moderation(bot))
