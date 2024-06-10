import asyncio
import datetime
import json as orjson
import typing
from typing import List, Union

import humanfriendly
import humanize
from discord import (
    AuditLogAction,
    Embed,
    Guild,
    Interaction,
    Member,
    Message,
    Role,
    TextChannel,
    User,
)
from discord.abc import GuildChannel
from discord.ext.commands import Cog, group

from tools.bot import Pretend
from tools.converters import Punishment
from tools.helpers import GreedContext
from tools.predicates import admin_antinuke, antinuke_configured, antinuke_owner
from tools.validators import ValidTime


class Antinuke(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Antinuke & antiraid commands"
        self.thresholds = {}
        self.modules = [
            "channel delete",
            "channel create",
            "role giving",
            "role delete",
            "role create",
            "kick",
            "ban",
            "edit role",
            "mass mention",
            "spammer",
            "new accounts",
            "bot add",
        ]

    async def joined_whitelist(self, member: Member) -> bool:
        """check if the added bot / young account is whitelisted"""
        check = await self.bot.db.fetchval(
            "SELECT whitelisted FROM antinuke WHERE guild_id = $1", member.guild.id
        )
        if check:
            if member.id in orjson.loads(check):
                return True

        return False

    def big_role_mention(self, roles: List[Role]) -> bool:
        for role in roles:
            if len(role.members) / role.guild.member_count * 100 > 70:
                return True

        return False

    @Cog.listener("on_guild_role_update")
    async def on_role_edit(self, before: Role, after: Role):
        if self.bot.an.get_bot_perms(before.guild):
            if await self.bot.an.is_module("edit role", before.guild):
                tasks = []
                if not before.mentionable and after.mentionable:
                    tasks.append(after.edit(mentionable=before.mentionable))

                elif not self.bot.is_dangerous(before) and self.bot.is_dangerous(after):
                    tasks.append(after.edit(permissions=before.permissions))

                else:
                    return

                async for entry in before.guild.audit_logs(
                    limit=1, action=AuditLogAction.role_update
                ):
                    if self.bot.an.check_hieracy(entry.user, before.guild.me):
                        if not await self.bot.an.is_whitelisted(entry.user):
                            tasks.append(
                                await self.bot.an.decide_punishment(
                                    "edit role", entry.user, "Maliciously editing roles"
                                )
                            )
                            action_time = datetime.datetime.now()
                            check = await self.bot.db.fetchrow(
                                "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                before.guild.id,
                            )
                            await self.bot.an.take_action(
                                "Maliciously editing roles",
                                entry.user,
                                tasks,
                                action_time,
                                check["owner_id"],
                                before.guild.get_channel(check["logs"]),
                            )

    @Cog.listener("on_guild_update")
    async def change_antinuke_owner(self, before: Guild, after: Guild):
        if before.owner_id != after.owner_id:
            if await self.bot.db.fetchrow(
                "SELECT * FROM antinuke WHERE guild_id = $1 and owner_id = $2",
                before.id,
                before.owner_id,
            ):
                await self.bot.db.execute(
                    "UPDATE antinuke SET owner_id = $1 WHERE guild_id = $2",
                    after.owner_id,
                    before.id,
                )

    @Cog.listener("on_member_join")
    async def on_new_acc_join(self, member: Member):
        if self.bot.an.get_bot_perms(member.guild):
            if await self.bot.an.is_module("new accounts", member.guild):
                if not await self.joined_whitelist(member):
                    res = await self.bot.db.fetchval(
                        "SELECT threshold FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
                        member.guild.id,
                        "new accounts",
                    )
                    if (
                        datetime.datetime.now()
                        - datetime.datetime.fromtimestamp(member.created_at.timestamp())
                    ).total_seconds() < res:
                        tasks = [
                            await self.bot.an.decide_punishment(
                                "new accounts",
                                member,
                                f"Account younger than {humanfriendly.format_timespan(res)}",
                            )
                        ]
                        action_time = datetime.datetime.now()
                        check = await self.bot.db.fetchrow(
                            "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                            member.guild.id,
                        )
                        await self.bot.an.take_action(
                            f"Account younger than {humanfriendly.format_timespan(res)}",
                            member,
                            tasks,
                            action_time,
                            check["owner_id"],
                            member.guild.get_channel(check["logs"]),
                        )

    @Cog.listener("on_member_join")
    async def on_flagged_join(self, member: Member):
        if self.bot.an.get_bot_perms(member.guild):
            if member.public_flags.spammer:
                if await self.bot.an.is_module("spammer", member.guild):
                    if not await self.joined_whitelist(member):
                        tasks = [
                            await self.bot.an.decide_punishment(
                                "spammer",
                                member,
                                f"Account flagged as spammer by discord",
                            )
                        ]
                        action_time = datetime.datetime.now()
                        check = await self.bot.db.fetchrow(
                            "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                            member.guild.id,
                        )
                        await self.bot.an.take_action(
                            f"Account flagged as spammer by discord",
                            member,
                            tasks,
                            action_time,
                            check["owner_id"],
                            member.guild.get_channel(check["logs"]),
                        )

    @Cog.listener("on_member_join")
    async def on_bot_join(self, member: Member):
        if self.bot.an.get_bot_perms(member.guild):
            if member.bot:
                if await self.bot.an.is_module("bot add", member.guild):
                    async for entry in member.guild.audit_logs(
                        limit=1, action=AuditLogAction.bot_add
                    ):
                        if not await self.joined_whitelist(member):
                            if self.bot.an.check_hieracy(entry.user, member.guild.me):
                                if not await self.bot.an.is_whitelisted(entry.user):
                                    tasks = [
                                        member.ban(reason="Unwhitelisted bot added"),
                                        await self.bot.an.decide_punishment(
                                            "bot add",
                                            entry.user,
                                            "Adding unwhitelisted bots",
                                        ),
                                    ]
                                    action_time = datetime.datetime.now()
                                    check = await self.bot.db.fetchrow(
                                        "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                        member.guild.id,
                                    )
                                    await self.bot.an.take_action(
                                        "Adding bots",
                                        entry.user,
                                        tasks,
                                        action_time,
                                        check["owner_id"],
                                        member.guild.get_channel(check["logs"]),
                                    )

    @Cog.listener("on_guild_channel_create")
    async def on_guild_channel_create(self, channel: GuildChannel):
        if self.bot.an.get_bot_perms(channel.guild):
            if await self.bot.an.is_module("channel create", channel.guild):
                async for entry in channel.guild.audit_logs(
                    limit=1, action=AuditLogAction.channel_create
                ):
                    if self.bot.an.check_hieracy(entry.user, channel.guild.me):
                        if not await self.bot.an.is_whitelisted(entry.user):
                            await channel.delete()
                            if await self.bot.an.check_threshold(
                                "channel create", entry.user
                            ):
                                cache = self.bot.cache.get(
                                    f"createchannel-{channel.guild.id}"
                                )
                                if not cache:
                                    await self.bot.cache.set(
                                        f"createchannel-{channel.guild.id}", True, 5
                                    )
                                    tasks = [
                                        await self.bot.an.decide_punishment(
                                            "channel create",
                                            entry.user,
                                            "Creating channels",
                                        )
                                    ]
                                    action_time = datetime.datetime.now()
                                    check = await self.bot.db.fetchrow(
                                        "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                        channel.guild.id,
                                    )
                                    await self.bot.an.take_action(
                                        "Creating channels",
                                        entry.user,
                                        tasks,
                                        action_time,
                                        check["owner_id"],
                                        channel.guild.get_channel(check["logs"]),
                                    )

    @Cog.listener("on_guild_channel_delete")
    async def on_guild_channel_delete(self, channel: GuildChannel):
        if self.bot.an.get_bot_perms(channel.guild):
            if await self.bot.an.is_module("channel delete", channel.guild):
                async for entry in channel.guild.audit_logs(
                    limit=1, action=AuditLogAction.channel_delete
                ):
                    if self.bot.an.check_hieracy(entry.user, channel.guild.me):
                        if not await self.bot.an.is_whitelisted(entry.user):
                            await channel.clone()
                            if await self.bot.an.check_threshold(
                                "channel delete", entry.user
                            ):
                                cache = self.bot.cache.get(
                                    f"deletechannel-{channel.guild.id}"
                                )
                                if not cache:
                                    await self.bot.cache.set(
                                        f"deletechannel-{channel.guild.id}", True, 5
                                    )
                                    tasks = [
                                        await self.bot.an.decide_punishment(
                                            "channel delete",
                                            entry.user,
                                            "Deleting channels",
                                        )
                                    ]
                                    action_time = datetime.datetime.now()
                                    check = await self.bot.db.fetchrow(
                                        "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                        channel.guild.id,
                                    )
                                    await self.bot.an.take_action(
                                        "Deleting channels",
                                        entry.user,
                                        tasks,
                                        action_time,
                                        check["owner_id"],
                                        channel.guild.get_channel(check["logs"]),
                                    )

    @Cog.listener("on_guild_role_delete")
    async def on_role_deletion(self, role: Role):
        if self.bot.an.get_bot_perms(role.guild):
            if await self.bot.an.is_module("role delete", role.guild):
                async for entry in role.guild.audit_logs(
                    limit=1, action=AuditLogAction.role_delete
                ):
                    if not await self.bot.an.is_whitelisted(
                        entry.user
                    ) and self.bot.an.check_hieracy(entry.user, role.guild.me):
                        await role.guild.create_role(
                            name=role.name,
                            permissions=role.permissions,
                            color=role.color,
                            hoist=role.hoist,
                            display_icon=role.display_icon,
                            mentionable=role.mentionable,
                        )
                        cache = self.bot.cache.get(f"roledelete-{role.guild.id}")
                        if not cache:
                            await self.bot.cache.set(
                                f"roledelete-{role.guild.id}", True, 5
                            )
                            tasks = [
                                await self.bot.an.decide_punishment(
                                    "role delete", entry.user, "Deleting roles"
                                )
                            ]
                            action_time = datetime.datetime.now()
                            check = await self.bot.db.fetchrow(
                                "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                role.guild.id,
                            )
                            await self.bot.an.take_action(
                                "Deleting roles",
                                entry.user,
                                tasks,
                                action_time,
                                check["owner_id"],
                                role.guild.get_channel(check["logs"]),
                            )

    @Cog.listener("on_guild_role_create")
    async def on_role_creation(self, role: Role):
        if self.bot.an.get_bot_perms(role.guild):
            if await self.bot.an.is_module("role create", role.guild):
                async for entry in role.guild.audit_logs(
                    limit=1, action=AuditLogAction.role_create
                ):
                    if not await self.bot.an.is_whitelisted(
                        entry.user
                    ) and self.bot.an.check_hieracy(entry.user, role.guild.me):
                        guild = role.guild
                        await role.delete()
                        cache = self.bot.cache.get(f"rolecreate-{guild.id}")
                        if not cache:
                            await self.bot.cache.set(f"rolecreate-{guild.id}", True, 5)
                            tasks = [
                                await self.bot.an.decide_punishment(
                                    "role create", entry.user, "Creating roles"
                                )
                            ]
                            action_time = datetime.datetime.now()
                            check = await self.bot.db.fetchrow(
                                "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                guild.id,
                            )
                            await self.bot.an.take_action(
                                "Creating roles",
                                entry.user,
                                tasks,
                                action_time,
                                check["owner_id"],
                                guild.get_channel(check["logs"]),
                            )

    @Cog.listener("on_member_update")
    async def on_member_role_give(self, before: Member, after: Member):
        if len(before.roles) < len(after.roles):
            roles = [
                r for r in after.roles if not r in before.roles and r.is_assignable()
            ]
            if len(roles) == 0:
                return

            if any(self.bot.is_dangerous(role) for role in roles):
                if self.bot.an.get_bot_perms(before.guild):
                    if await self.bot.an.is_module("role giving", before.guild):
                        async for entry in after.guild.audit_logs(
                            limit=1, action=AuditLogAction.member_role_update
                        ):
                            if not await self.bot.an.is_whitelisted(entry.user):
                                if self.bot.an.check_hieracy(
                                    entry.user, before.guild.me
                                ):
                                    if not self.bot.cache.get(
                                        f"role-give-{before.guild.id}"
                                    ):
                                        await self.bot.cache.set(
                                            f"role-give-{before.guild.id}", True, 5
                                        )
                                        tasks = [
                                            after.edit(
                                                roles=[
                                                    r
                                                    for r in before.roles
                                                    if r.is_assignable()
                                                    and r.is_bot_managed()
                                                ],
                                                reason="Roles being reverted",
                                            ),
                                            await self.bot.an.decide_punishment(
                                                "role giving",
                                                entry.user,
                                                "Giving roles with dangerous permissions",
                                            ),
                                        ]

                                        action_time = datetime.datetime.now()
                                        check = await self.bot.db.fetchrow(
                                            "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                            before.guild.id,
                                        )
                                        await self.bot.an.take_action(
                                            "Giving roles with dangerous permissions",
                                            entry.user,
                                            tasks,
                                            action_time,
                                            check["owner_id"],
                                            before.guild.get_channel(check["logs"]),
                                        )

    @Cog.listener("on_member_remove")
    async def on_kick_action(self, member: Member):
        if self.bot.an.get_bot_perms(member.guild):
            if await self.bot.an.is_module("kick", member.guild):
                async for entry in member.guild.audit_logs(
                    limit=1, action=AuditLogAction.kick
                ):
                    if not await self.bot.an.is_whitelisted(entry.user):
                        if await self.bot.an.check_threshold("kick", entry.user):
                            if self.bot.an.check_hieracy(entry.user, member.guild.me):
                                cache = self.bot.cache.get(f"kick-{member.guild.id}")
                                if not cache:
                                    await self.bot.cache.set(
                                        f"kick-{member.guild.id}", True, 5
                                    )
                                    tasks = [
                                        await self.bot.an.decide_punishment(
                                            "kick", entry.user, "Kicking members"
                                        )
                                    ]
                                    action_time = datetime.datetime.now()
                                    check = await self.bot.db.fetchrow(
                                        "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                        member.guild.id,
                                    )
                                    await self.bot.an.take_action(
                                        "Kicking members",
                                        entry.user,
                                        tasks,
                                        action_time,
                                        check["owner_id"],
                                        member.guild.get_channel(check["logs"]),
                                    )

    @Cog.listener("on_member_ban")
    async def on_ban_action(self, guild: Guild, user: Union[User, Member]):
        if self.bot.an.get_bot_perms(guild):
            if await self.bot.an.is_module("ban", guild):
                async for entry in guild.audit_logs(limit=1, action=AuditLogAction.ban):
                    if not await self.bot.an.is_whitelisted(entry.user):
                        if isinstance(user, Member):
                            if not self.bot.an.check_hieracy(entry.user, guild.me):
                                return
                        if await self.bot.an.check_threshold("ban", entry.user):
                            cache = self.bot.cache.get(f"ban-{guild.id}")
                            if not cache:
                                await self.bot.cache.set(f"ban-{guild.id}", True, 5)
                                tasks = [
                                    await self.bot.an.decide_punishment(
                                        "ban", entry.user, "Banning members"
                                    )
                                ]
                                action_time = datetime.datetime.now()
                                check = await self.bot.db.fetchrow(
                                    "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                    guild.id,
                                )
                                await self.bot.an.take_action(
                                    "Banning members",
                                    entry.user,
                                    tasks,
                                    action_time,
                                    check["owner_id"],
                                    guild.get_channel(check["logs"]),
                                )

    @Cog.listener("on_message")
    async def on_mass_mention(self, message: Message):
        if message.guild:
            if not message.is_system():
                if (
                    message.mention_everyone
                    or any([len(r.members) > 10 for r in message.role_mentions])
                    or self.big_role_mention(message.role_mentions)
                ):
                    if await self.bot.an.is_module("mass mention", message.guild):
                        tasks = []
                        if message.author.discriminator != "0000":
                            if await self.bot.an.is_whitelisted(message.author):
                                return

                            if not self.bot.an.check_hieracy(
                                message.author, message.guild.me
                            ):
                                return

                            tasks.append(
                                await self.bot.an.decide_punishment(
                                    "mass mention", message.author, "Mass mention"
                                )
                            )

                        if message.webhook_id:
                            webhook = [
                                w
                                for w in await message.channel.webhooks()
                                if w.id == message.webhook_id
                            ]
                            tasks.append(webhook[0].delete())

                        cache = self.bot.cache.get(f"massmention-{message.guild.id}")
                        if not cache:
                            await self.bot.cache.set(
                                f"massmention-{message.guild.id}", True, 5
                            )
                            action_time = datetime.datetime.now()
                            check = await self.bot.db.fetchrow(
                                "SELECT owner_id, logs FROM antinuke WHERE guild_id = $1",
                                message.guild.id,
                            )
                            await self.bot.an.take_action(
                                "Mass mention",
                                message.author,
                                tasks,
                                action_time,
                                check["owner_id"],
                                message.guild.get_channel(check["logs"]),
                            )

    @group(invoke_without_command=True, aliases=["an"])
    async def antinuke(self, ctx: GreedContext):
        await ctx.send_help(ctx.command)

    @antinuke.command(name="setup", brief="antinuke owner")
    async def antinuke_setup(self, ctx: GreedContext):
        """setup antinuke"""
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            if check["configured"] == "true":
                return await ctx.send_warning("Antinuke is **already** configured")

            if check["owner_id"]:
                owner_id = check["owner_id"]

            args = [
                "UPDATE antinuke SET configured = $1 WHERE guild_id = $2",
                "true",
                ctx.guild.id,
            ]
        else:
            owner_id = ctx.guild.owner_id
            args = [
                "INSERT INTO antinuke (guild_id, configured, owner_id) VALUES ($1,$2,$3)",
                ctx.guild.id,
                "true",
                ctx.guild.owner_id,
            ]

        if ctx.author.id != owner_id:
            return await ctx.send_warning(
                f"Only <@!{owner_id}> can use this command!\nIf the account cannot be used, please join the [**support server**](https://discord.gg/hill)"
            )

        await self.bot.db.execute(*args)
        await ctx.send_success("Antinuke is **enabled**")

    @antinuke.command(name="reset", aliases=["disable"], brief="antinuke owner")
    @antinuke_owner()
    async def antinuke_reset(self, ctx: GreedContext):
        """disable the antinuke system"""

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                "DELETE FROM antinuke WHERE guild_id = $1", interaction.guild.id
            )
            await interaction.client.db.execute(
                "DELETE FROM antinuke_modules WHERE guild_id = $1", interaction.guild.id
            )
            await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.yes_color,
                    description=f"{interaction.client.yes} {interaction.user.mention}: Disabled the antinuke",
                ),
                view=None,
            )

        async def no_callback(interaction: Interaction):
            await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color,
                    description="You changed your mind...",
                ),
                view=None,
            )

        await ctx.confirmation_send(
            "Are you sure you want to **disable** antinuke?",
            yes_func=yes_callback,
            no_func=no_callback,
        )

    async def enable_antinuke(
        self, ctx, threshold: int = None, punishment: str = "ban"
    ):
        return await asyncio.gather(
            *[self.do_enable(ctx, m, threshold, punishment) for m in self.modules]
        )

    async def do_enable(
        self, ctx, m: str, threshold: int = None, punishment: str = "ban"
    ):
        if not await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE guild_id = $1 AND module = $1",
            ctx.guild.id,
            m,
        ):
            await self.bot.db.execute(
                "INSERT INTO antinuke_modules VALUES($1,$2,$3,$4)",
                ctx.guild.id,
                m,
                punishment,
                threshold,
            )
            return True

    @antinuke.command(name="enable", aliases=["start"])
    @antinuke_configured()
    @admin_antinuke()
    async def an_enable(
        self, ctx, threshold: int = 1, punishment: typing.Optional[Punishment] = "ban"
    ):
        await self.enable_antinuke(ctx, threshold, punishment)
        return await ctx.send_success(
            "Enabled **antinuke** with a threshold of `{threshold}` and the **punishment** is `{punishment}`"
        )

    @antinuke.command(name="status", aliases=["settings", "config", "stats"])
    @antinuke_configured()
    @admin_antinuke()
    async def an_status(self, ctx: GreedContext):
        """check what is enabled in your antinuke system"""
        results = await self.bot.db.fetch(
            "SELECT module FROM antinuke_modules WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning("There is **no** module enabled")

        embed = Embed(
            color=self.bot.color,
            description="\n".join(
                f"{result['module'].capitalize()} protection {self.bot.yes}"
                for result in results
            ),
        )
        embed.set_author(
            name=f"{ctx.guild.name}'s antinuke configuration", icon_url=ctx.guild.icon
        )
        embed.set_thumbnail(url=ctx.guild.icon)
        await ctx.send(embed=embed)

    @antinuke.command(name="whitelisted")
    @antinuke_configured()
    @admin_antinuke()
    async def antinuke_whitelisted(self, ctx: GreedContext):
        """check who's antinuke whitelisted"""
        check = await self.bot.db.fetchrow(
            "SELECT owner_id, whitelisted FROM antinuke WHERE guild_id = $1",
            ctx.guild.id,
        )
        content = [f"<@!{check['owner_id']}> <a:crown:1205913233634889800>"]

        if check["whitelisted"]:
            whitelisted = [
                w for w in orjson.loads(check["whitelisted"]) if self.bot.get_user(w)
            ]
            content.extend(
                [
                    f"<@!{wl}> {'<:ClydeBot:1205913231911292958>' if self.bot.get_user(wl).bot else ''}"
                    for wl in whitelisted
                ]
            )

        await ctx.paginate(
            content,
            f"Antinuke whitelisted ({len(content)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @antinuke.command(name="admins")
    @antinuke_configured()
    @admin_antinuke()
    async def an_admins(self, ctx: GreedContext):
        """list antinuke admins"""
        check = await self.bot.db.fetchrow(
            "SELECT owner_id, admins FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        content = [f"<@!{check['owner_id']}> <a:crown:1205913233634889800>"]

        if check["admins"]:
            admins = [w for w in orjson.loads(check["admins"])]
            content.extend([f"<@!{wl}>" for wl in admins])

        await ctx.paginate(
            content,
            f"Antinuke admins ({len(content)})",
            {"name": ctx.guild.name, "icon_url": ctx.guild.icon},
        )

    @antinuke.command(name="logs")
    @antinuke_configured()
    @admin_antinuke()
    async def antinuke_logs(self, ctx: GreedContext, *, channel: TextChannel = None):
        """add an antinuke logs channel"""
        if not channel:
            await self.bot.db.execute(
                "UPDATE antinuke SET logs = $1 WHERE guild_id = $2", None, ctx.guild.id
            )
            return await ctx.send_success("Removed the logs channel")
        else:
            await self.bot.db.execute(
                "UPDATE antinuke SET logs = $1 WHERE guild_id = $2",
                channel.id,
                ctx.guild.id,
            )
            return await ctx.send_success(
                f"Set the antinuke logs channel to {channel.mention}"
            )

    @antinuke.group(
        name="channeldelete", brief="antinuke admin", invoke_without_command=True
    )
    async def an_channelremove(self, ctx):
        """prevent admins from deleting channels"""
        return await ctx.create_pages()

    @an_channelremove.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_channelremove_enable(
        self, ctx: GreedContext, threshold: int, punishment: Punishment
    ):
        """enable the protection deleting channels"""
        if threshold < 0:
            return await ctx.send_error("Threshold cannot be lower than **0**")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "channel delete",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "channel delete",
                punishment,
                threshold,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1, threshold = $2 WHERE module = $3 AND guild_id = $4",
                punishment,
                threshold,
                "channel delete",
                ctx.guild.id,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **channel delete** protection\nPunishment: **{punishment}**\nThreshold: **{threshold}/60s**"
        )

    @an_channelremove.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_channelremove_disable(self, ctx: GreedContext):
        """disable the protection against deleting channels"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "channel delete",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning(
                "Channel delete protection is **not** enabled"
            )

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "channel de;ete",
        )
        return await ctx.send_success("Disabled **channel delete** protection")

    @antinuke.group(
        name="channelcreate", brief="antinuke admin", invoke_without_command=True
    )
    async def an_channelcreate(self, ctx):
        """prevent admins from creating channels"""
        return await ctx.create_pages()

    @an_channelcreate.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_channelcreate_enable(
        self, ctx: GreedContext, threshold: int, punishment: Punishment
    ):
        """enable the protection against creating channels"""
        if threshold < 0:
            return await ctx.send_error("Threshold cannot be lower than **0**")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "channel create",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "channel create",
                punishment,
                threshold,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1, threshold = $2 WHERE module = $3 AND guild_id = $4",
                punishment,
                threshold,
                "channel create",
                ctx.guild.id,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **channel create** protection\nPunishment: **{punishment}**\nThreshold: **{threshold}/60s**"
        )

    @an_channelcreate.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_channelcreate_disable(self, ctx: GreedContext):
        """disable protection against creating discord channels"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "channel create",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning(
                "Channel create protection is **not** enabled"
            )

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "channel create",
        )
        return await ctx.send_success("Disabled **channel create** protection")

    @antinuke.group(
        name="giverole", brief="antinuke admin", invoke_without_command=True
    )
    async def an_giverole(self, ctx):
        """
        prevent the members giving dangerous permissions to other members
        """
        await ctx.create_pages()

    @an_giverole.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_giverole_enable(self, ctx: GreedContext, punishment: Punishment):
        """
        enable the protection against giving dangerous roles to other members
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "role giving",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "role giving",
                punishment,
                0,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1, threshold = $2 WHERE module = $3 AND guild_id = $4",
                punishment,
                0,
                "role giving",
                ctx.guild.id,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **role giving** protection\nPunishment: **{punishment}**"
        )

    @an_giverole.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_giverole_disable(self, ctx: GreedContext):
        """disable protection against giving dangerous roles"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "role giving",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning("Role giving protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "role giving",
        )
        return await ctx.send_success("Disabled **role giving** protection")

    @antinuke.group(
        name="roledelete", brief="antinuke admin", invoke_without_command=True
    )
    async def an_roledelete(self, ctx):
        """protect the server against role deletions"""
        await ctx.create_pages()

    @an_roledelete.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_roledelete_enable(
        self, ctx: GreedContext, threshold: int, punishment: Punishment
    ):
        """enable the protection against role deletions"""
        if threshold < 0:
            return await ctx.send_error("Threshold cannot be lower than **0**")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "role delete",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "role delete",
                punishment,
                threshold,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1, threshold = $2 WHERE module = $3 AND guild_id = $4",
                punishment,
                threshold,
                "role delete",
                ctx.guild.id,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **role delete** protection\nPunishment: **{punishment}**\nThreshold: **{threshold}/60s**"
        )

    @an_roledelete.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_roldelete_disable(self, ctx: GreedContext):
        """disable protection against deleting roles"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "role delete",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning("Role delete protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "role delete",
        )
        return await ctx.send_success("Disabled **role delete** protection")

    @antinuke.group(
        name="rolecreate", brief="antinuke admin", invoke_without_command=True
    )
    async def an_rolecreate(self, ctx):
        """protect the server against role creations"""
        await ctx.create_pages()

    @an_rolecreate.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_rolecreate_enable(
        self, ctx: GreedContext, threshold: int, punishment: Punishment
    ):
        """enable the protection against role creations"""
        if threshold < 0:
            return await ctx.send_error("Threshold cannot be lower than **0**")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "role create",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "role create",
                punishment,
                threshold,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1, threshold = $2 WHERE module = $3 AND guild_id = $4",
                punishment,
                threshold,
                "role create",
                ctx.guild.id,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **role create** protection\nPunishment: **{punishment}**\nThreshold: **{threshold}/60s**"
        )

    @an_rolecreate.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_rolecreate_disable(self, ctx: GreedContext):
        """disable protection against creating roles"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "role create",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning("Role create protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "role create",
        )
        return await ctx.send_success("Disabled **role create** protection")

    @antinuke.group(name="kick", brief="antinuke admin", invoke_without_command=True)
    async def an_kick(self, ctx):
        """prevent admins from kicking members"""
        return await ctx.create_pages()

    @an_kick.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_kick_enable(
        self, ctx: GreedContext, threshold: int, punishment: Punishment
    ):
        """enable the protection against kicking members"""
        if threshold < 0:
            return await ctx.send_error("Threshold cannot be lower than **0**")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "kick",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "kick",
                punishment,
                threshold,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1, threshold = $2 WHERE module = $3 AND guild_id = $4",
                punishment,
                threshold,
                "kick",
                ctx.guild.id,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **kick** protection\nPunishment: **{punishment}**\nThreshold: **{threshold}/60s**"
        )

    @an_kick.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_kick_disable(self, ctx: GreedContext):
        """disable protection against banning members"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "kick",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning("Kick protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "kick",
        )
        return await ctx.send_success("Disabled **kick** protection")

    @antinuke.group(name="ban", brief="antinuke admin", invoke_without_command=True)
    async def an_ban(self, ctx):
        """prevent admins from banning members"""
        return await ctx.create_pages()

    @an_ban.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_ban_enable(
        self, ctx: GreedContext, threshold: int, punishment: Punishment
    ):
        """enable the protection against banning members"""
        if threshold < 0:
            return await ctx.send_error("Threshold cannot be lower than **0**")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "ban",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "ban",
                punishment,
                threshold,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1, threshold = $2 WHERE module = $3 AND guild_id = $4",
                punishment,
                threshold,
                "ban",
                ctx.guild.id,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **ban** protection\nPunishment: **{punishment}**\nThreshold: **{threshold}/60s**"
        )

    @an_ban.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_ban_disable(self, ctx: GreedContext):
        """disable protection against banning members"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "ban",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning("Ban protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "ban",
        )
        return await ctx.send_success("Disabled **ban** protection")

    @antinuke.group(
        name="editrole", brief="antinuke admin", invoke_without_command=True
    )
    async def an_editrole(self, ctx):
        """prevent admins from giving dangerous permissions to roles"""
        await ctx.create_pages()

    @an_editrole.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_editrole_enable(self, ctx: GreedContext, punishment: Punishment):
        """enable protection against editing dangerous attributes of a role"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "edit role",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "edit role",
                punishment,
                None,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1 WHERE guild_id = $2 AND module = $3",
                punishment,
                ctx.guild.id,
                "edit role",
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **edit role** protection\nPunishment: **{punishment}**"
        )

    @an_editrole.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_editrole_disable(self, ctx: GreedContext):
        """disable protection against editing dangerous attributes of a role"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "edit role",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning("Edit role protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "edit role",
        )
        return await ctx.send_success("Disabled **edit role** protection")

    @antinuke.group(
        name="massmention", brief="antinuke admin", invoke_without_command=True
    )
    async def an_massmention(self, ctx):
        """protect your server against everyone or here mentions"""
        await ctx.create_pages()

    @an_massmention.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_massmention_enable(self, ctx: GreedContext, punishment: Punishment):
        """enable the mass mention protection"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "mass mention",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "mass mention",
                punishment,
                None,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1 WHERE guild_id = $2 AND module = $3",
                punishment,
                ctx.guild.id,
                "mass mention",
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **anti mass mention** protection\nPunishment: **{punishment}**"
        )

    @an_massmention.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_massmention_disable(self, ctx: GreedContext):
        """disable the mass mention protection"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "mass mention",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning("Mass mention protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "mass mention",
        )
        return await ctx.send_success("Disabled **mass mention** protection")

    @antinuke.group(name="spammer", brief="antinuke admin", invoke_without_command=True)
    async def an_spammer(self, ctx: GreedContext):
        """protect your server against flagged members"""
        await ctx.create_pages()

    @an_spammer.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_spammer_enable(self, ctx: GreedContext, punishment: Punishment):
        """enable the protection against flagged members"""
        if punishment == "strip":
            return await ctx.send_error("**Strip** cannot be a punishment in this case")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "spammer",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "spammer",
                punishment,
                None,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1 WHERE guild_id = $2 AND module = $3",
                punishment,
                ctx.guild.id,
                "spammer",
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **anti spammer** protection\nPunishment: **{punishment}**"
        )

    @an_spammer.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_spammer_disable(self, ctx: GreedContext):
        """disable the protection against flagged members"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "spammer",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning(
                "Spammer accounts protection is **not** enabled"
            )

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "spammer",
        )
        return await ctx.send_success("Disabled **spammer accounts** protection")

    @antinuke.group(
        name="newaccounts",
        aliases=["newaccs"],
        brief="antinuke admin",
        invoke_without_command=True,
    )
    async def an_newaccs(self, ctx):
        """protect your server against new accounts"""
        await ctx.create_pages()

    @an_newaccs.command(
        name="enable",
        brief="antinuke admin",
        usage="example: ;an newaccounts enable 3d kick (kicks accounts that were made less than 3 days ago)",
    )
    @antinuke_configured()
    @admin_antinuke()
    async def an_newaccs_enable(
        self, ctx: GreedContext, time: ValidTime, punishment: Punishment
    ):
        """enable the new account protection"""
        if punishment == "strip":
            return await ctx.send_error("**Strip** cannot be a punishment in this case")

        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "new accounts",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "new accounts",
                punishment,
                time,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1, threshold = $4 WHERE guild_id = $2 AND module = $3",
                punishment,
                ctx.guild.id,
                "new accounts",
                time,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **new accounts** protection\nPunishment: **{punishment}**\nApplying to: Accounts newer than **{humanfriendly.format_timespan(time)}**"
        )

    @an_newaccs.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_newaccs_disable(self, ctx: GreedContext):
        """disable new accounts protection"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "new accounts",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning("New accounts protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "new accounts",
        )
        return await ctx.send_success("Disabled **new accounts** protection")

    @antinuke.group(name="botadd", brief="antinuke admin", invoke_without_command=True)
    async def an_botadd(self, ctx):
        """keep the bots away"""
        await ctx.send_help(ctx.command)

    @an_botadd.command(name="enable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_botadd_enable(self, ctx: GreedContext, *, punishment: Punishment):
        """enable bot add protection"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "bot add",
            ctx.guild.id,
        )
        if not check:
            args = [
                "INSERT INTO antinuke_modules VALUES ($1,$2,$3,$4)",
                ctx.guild.id,
                "bot add",
                punishment,
                None,
            ]
        else:
            args = [
                "UPDATE antinuke_modules SET punishment = $1 WHERE guild_id = $2 AND module = $3",
                punishment,
                ctx.guild.id,
                "bot add",
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Enabled **bot add** protection\nPunishment: **{punishment}**"
        )

    @an_botadd.command(name="disable", brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def an_botadd_disable(self, ctx: GreedContext):
        """disable bot add protection"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM antinuke_modules WHERE module = $1 AND guild_id = $2",
            "bot add",
            ctx.guild.id,
        )
        if not check:
            return await ctx.send_warning("Bot add protection is **not** enabled")

        await self.bot.db.execute(
            "DELETE FROM antinuke_modules WHERE guild_id = $1 AND module = $2",
            ctx.guild.id,
            "bot add",
        )
        return await ctx.send_success("Disabled **bot add** protection")

    @antinuke.command(
        name="whitelist",
        aliases=["wl"],
        brief="antinuke admin",
        invoke_without_command=True,
    )
    @antinuke_configured()
    @admin_antinuke()
    async def antinuke_whitelist(
        self, ctx: GreedContext, *, member: Union[User, Member]
    ):
        """make an user antinuke whitelisted"""
        whitelisted = await self.bot.db.fetchval(
            "SELECT whitelisted FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        if whitelisted:
            whitelisted = orjson.loads(whitelisted)

            if member.id in whitelisted:
                return await ctx.send_warning(
                    "This member is **already** antinuke whitelisted"
                )

            whitelisted.append(member.id)
        else:
            whitelisted = [member.id]

        await self.bot.db.execute(
            "UPDATE antinuke SET whitelisted = $1 WHERE guild_id = $2",
            orjson.dumps(whitelisted),
            ctx.guild.id,
        )

        if isinstance(member, Member):
            return await ctx.send_success(f"Whitelisted {member.mention} from antinuke")

        return await ctx.send_success(
            f"Whitelisted {member.mention}. Now they can join the server"
        )

    @antinuke.command(name="unwhitelist", aliases=["uwl"], brief="antinuke admin")
    @antinuke_configured()
    @admin_antinuke()
    async def antinuke_wl_remove(
        self, ctx: GreedContext, *, member: Union[User, Member]
    ):
        """unwhitelist a member from antinuke"""
        whitelisted = await self.bot.db.fetchval(
            "SELECT whitelisted FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )

        if whitelisted:
            whitelisted = orjson.loads(whitelisted)

            if not member.id in whitelisted:
                return await ctx.send_warning(
                    "This member is **not** antinuke whitelisted"
                )

            whitelisted.remove(member.id)
            await self.bot.db.execute(
                "UPDATE antinuke SET whitelisted = $1 WHERE guild_id = $2",
                orjson.dumps(whitelisted),
                ctx.guild.id,
            )
            return await ctx.send_success(
                f"Unwhitelisted {member.mention} from antinuke"
            )

        return await ctx.send_warning("There is **no** antinuke whitelisted member")

    @antinuke.group(name="admin", brief="antinuke owner", invoke_without_command=True)
    async def antinuke_admin(self, ctx):
        """manage the members that can change the antinuke settings"""
        await ctx.create_pages()

    @antinuke_admin.command(name="add", brief="antinuke owner")
    @antinuke_configured()
    @antinuke_owner()
    async def an_admin_add(self, ctx: GreedContext, *, member: Member):
        """add a member as an antinuke admin. Please be aware of who you add here"""
        if member == ctx.author:
            return await ctx.send("You are the antinuke owner yourself lol")

        if member.bot:
            return await ctx.send(
                "Why would a bot be an antinuke admin? They cannot manage the settings anyways -_-"
            )

        admins = await self.bot.db.fetchval(
            "SELECT admins FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )

        if admins:
            admins = orjson.loads(admins)

            if member.id in admins:
                return await ctx.send_warning(
                    "This member is **already** an antinuke admin"
                )

            admins.append(member.id)
        else:
            admins = [member.id]

        await self.bot.db.execute(
            "UPDATE antinuke SET admins = $1 WHERE guild_id = $2",
            orjson.dumps(admins),
            ctx.guild.id,
        )
        return await ctx.send_success(f"Added {member.mention} as an antinuke admin")

    @antinuke_admin.command(name="remove", brief="antinuke owner")
    @antinuke_configured()
    @antinuke_owner()
    async def an_admin_remove(self, ctx: GreedContext, *, member: Member):
        """remove a member from the antinuke admin list"""
        admins = await self.bot.db.fetchval(
            "SELECT admins FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )

        if admins:
            admins = orjson.loads(admins)

            if not member.id in admins:
                return await ctx.send_warning("This member isn't an antinuke admin")

            admins.remove(member.id)
            await self.bot.db.execute(
                "UPDATE antinuke SET admins = $1 WHERE guild_id = $2",
                orjson.dumps(admins),
                ctx.guild.id,
            )
            return await ctx.send_success(
                f"Removed {member.mention} from the antinuke admins"
            )
        return await ctx.send_warning("There is **no** antinuke admin")


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Antinuke(bot))
