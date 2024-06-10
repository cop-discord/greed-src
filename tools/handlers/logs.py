from asyncio import sleep
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import discord
from discord import (
    AuditLogAction,
    AuditLogEntry,
    Embed,
    Guild,
    Member,
    Message,
    User,
    VoiceState,
)
from pydantic import BaseModel


class LogGuild(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    icon_url: Optional[str] = None


class LogUser(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    mention: Optional[str] = None


class LogTarget(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    mention: Optional[str] = None


class LogEntry(BaseModel):
    id: Optional[int] = None
    guild: Optional[LogGuild] = None
    target: Optional[LogTarget] = None
    moderator: Optional[LogUser] = None
    message: Optional[str] = None
    timestamp: Optional[Union[int, float, str, datetime]] = None
    action: Optional[str] = None
    user: Optional[LogUser] = None


action_to_description = {
    "ban": "banned",
    "jail": "jailed",
    "unjail": "unjailed",
    "kick": "kicked",
    "mute": "muted",
    "unban": "unbanned",
    "unmute": "unmuted",
    "warn": "warned",
    "restore": "restored",
    "clear": "cleared",
    "voicemute": "muted the voice of",
    "voiceunmute": "unmuted the voice of",
    "voicedeafen": "deafened the sound for",
    "voiceundeafen": "undeafened the sound for",
    "clear": "cleared messages",
    "strip": "stripped the roles of",
    "lock": "locked",
    "unlock": "unlocked",
    "roleall": "gave all users the role",
    "nickname": "changed the nickname of",
    "unbanall": "unbanned all users",
    "nuke": "nuked",
}


async def ctx_to_log_data(
    ctx,
    member: Optional[
        Union[Member, User, discord.abc.GuildChannel, discord.Role]
    ] = None,
) -> LogEntry:
    message = action_to_description[ctx.command.qualified_name]
    guild = {
        "id": ctx.guild.id,
        "name": ctx.guild.name,
        "icon_url": ctx.guild.icon.url or None,
    }
    moderator = {
        "id": ctx.author.id,
        "name": ctx.author.name,
        "avatar_url": ctx.author.display_avatar.url,
        "mention": ctx.author.mention,
    }
    if isinstance(member, Member) or isinstance(member, User):
        target = {
            "id": member.id if member else None,
            "name": member.name if member else None,
            "avatar_url": member.display_avatar.url if member else None,
            "mention": member.mention if member else None,
        }
    if isinstance(member, discord.abc.GuildChannel) or isinstance(member, discord.Role):
        target = {
            "id": member.id,
            "name": member.name,
            "avatar_url": None,
            "mention": None,
        }
    log_entry = {
        "id": ctx.message.id,
        "guild": guild,
        "target": target,
        "moderator": moderator,
        "message": f"{ctx.author.name} **{message}** {target['name'] if target else ''}",
        "timestamp": ctx.message.created_at,
        "action": ctx.command.qualified_name,
    }
    return LogEntry(**log_entry)


def recursive_object_to_dict(obj, depth=0, max_depth=7):
    if depth > max_depth:
        return "max recursion depth exceeded"

    object_type = type(obj)
    if object_type.__module__.startswith("discord"):
        if object_type.__module__ == "discord.audit_logs":
            pass
        if "AuditLog" in object_type.__module__:
            pass
        else:
            try:
                return {
                    "type": object_type.__name__,
                    "id": obj.id,
                    "name": obj.name,
                }
            except:
                pass

    if isinstance(obj, datetime):
        return obj

    if isinstance(obj, discord.Guild):
        return obj.id

    if isinstance(obj, discord.Object):
        pass

    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj

    if isinstance(obj, (list, tuple)):
        return [recursive_object_to_dict(item, depth + 1) for item in obj]

    if isinstance(obj, dict):
        return {
            str(key): recursive_object_to_dict(value, depth + 1)
            for key, value in obj.items()
        }

    result = {}
    for attr in dir(obj):
        if attr == "TRANSFORMERS":
            continue

        if not callable(getattr(obj, attr)) and not attr.startswith("_"):
            try:
                value = getattr(obj, attr)
                if value is not obj:
                    result[str(attr)] = recursive_object_to_dict(value, depth + 1)
            except Exception:  # pylint: disable=broad-exception-caught
                try:
                    result[str(attr)] = str(getattr(obj, attr))
                except Exception:  # pylint: disable=broad-exception-caught
                    result[str(attr)] = "unencodable"

    return result


def get_username(u: Union[User, Member], escape_markdown: Optional[bool] = True):
    if isinstance(u, discord.Member):
        username = str(u._user)  # pylint: disable=protected-access
    else:
        username = str(u)

    if escape_markdown == True:
        try:
            username = discord.utils.escape_markdown(username)
        except:
            username = username
    return username


class AuditLogEntryLogMessage:
    def __init__(self, user: Union[Member, str], action: str, target: str):
        if not isinstance(user, Member) and user != "**AutoMod**":
            raise ValueError("user must be discord.Member or AutoMod")
        if not isinstance(action, str):
            raise ValueError("action must be a string")
        if not isinstance(target, str):
            raise ValueError("target must be a string")

        self.user = user
        self.action = action
        self.target = target


async def get_embed(
    bot,
    guild: Guild,
    entry: Union[discord.AuditLogEntry, LogEntry],
    user: discord.abc.User,
) -> Optional[Embed]:
    if isinstance(entry, discord.AuditLogEntry):
        if entry.user.id == bot.user.id:
            return
        log_entry_details = await audit_log_entry_handler(bot, guild, entry)
        if isinstance(log_entry_details.user, discord.Member):
            user = log_entry_details.user.mention
        else:
            user = log_entry_details.user
        description = f"`{entry.action.name}` {user} {log_entry_details.action} {log_entry_details.target}"
    else:
        if entry.moderator != None:
            description = f'{entry.moderator.name} {entry.message} {entry.target.name} {discord.utils.format_dt(datetime.now(), style="R")}'
        else:
            description = f'{entry.user.mention} {entry.message} {discord.utils.format_dt(datetime.now(), style="R")}'

    footer = entry.id
    embed = Embed(color=bot.color, title="Mod Logs", description=description)
    return embed


async def generic_object_converter(
    bot, guild: discord.Guild, entry: discord.AuditLogEntry
):
    if entry.before:
        if hasattr(entry.before, "name"):
            if entry.before.name:
                entry.before.id = entry.target.id
                entry.target = entry.before
                return entry, f"**{entry.target.name}** `{entry.target.id}`"

    if entry.after:
        if hasattr(entry.after, "name"):
            if entry.after.name:
                entry.after.id = entry.target.id
                entry.target = entry.after
                return entry, f"**{entry.target.name}** `{entry.target.id}`"

    if entry.target.type == discord.integrations.PartialIntegration:
        integrations = await entry.guild.integrations()
        for integration in integrations:
            if int(integration.account.id) == entry.target.id:
                entry.target = integration
                return entry, f"**{integration.name}**"

    elif entry.target.type == discord.app_commands.models.AppCommand:
        return entry, f"Command ID {entry.target.id}"

    elif entry.target.type == discord.Member:
        member = guild.get_member(entry.target.id)
        if not member:
            try:
                user = await bot.fetch_user(entry.target.id)
                username = get_username(user_object=user, escape_markdown=True)
            except discord.NotFound:
                username = "Deleted User"
        else:
            username = get_username(user_object=member, escape_markdown=True)
        return entry, f"**{username}** `{entry.target.id}`"

    else:
        print(f"else: {entry.target.type}")
        return entry, f"{entry.target.type.__name__}: ID `{entry.target.id}`"


async def audit_log_entry_handler(bot, guild: Guild, entry: AuditLogEntry):
    action_descriptions = {
        discord.AuditLogAction.app_command_permission_update: "updated permissions for",  # tested, needs better handler for application commands
        discord.AuditLogAction.automod_block_message: "blocked a message sent by",
        discord.AuditLogAction.automod_flag_message: "flagged a message sent by",
        discord.AuditLogAction.automod_timeout_member: "timed out",
        discord.AuditLogAction.automod_rule_create: "created AutoMod rule",
        discord.AuditLogAction.automod_rule_delete: "deleted AutoMod rule",
        discord.AuditLogAction.automod_rule_update: "updated AutoMod rule",
        discord.AuditLogAction.ban: "banned",
        discord.AuditLogAction.unban: "unbanned",
        discord.AuditLogAction.kick: "kicked",
        discord.AuditLogAction.member_prune: "pruned members: Members removed: {count}",  # needs testing
        discord.AuditLogAction.bot_add: "added the bot",  # needs testing
        discord.AuditLogAction.channel_create: "created the {channel_type} channel",
        discord.AuditLogAction.channel_delete: "deleted the {channel_type} channel",
        discord.AuditLogAction.channel_update: "updated the {channel_type} channel",
        discord.AuditLogAction.emoji_create: "created the emoji",
        discord.AuditLogAction.emoji_delete: "deleted the emoji",
        discord.AuditLogAction.emoji_update: "updated the emoji",
        discord.AuditLogAction.guild_update: "made changes to guild",
        discord.AuditLogAction.integration_create: "added the integration",  # needs testing
        discord.AuditLogAction.integration_delete: "removed the integration",  # needs testing
        discord.AuditLogAction.integration_update: "updated the integration",  # needs testing
        discord.AuditLogAction.invite_create: "created an invite",
        discord.AuditLogAction.invite_delete: "deleted an invite",
        discord.AuditLogAction.invite_update: "updated an invite",
        discord.AuditLogAction.member_update: "updated the member",
        discord.AuditLogAction.member_move: "moved to",  # needs testing
        discord.AuditLogAction.member_disconnect: "disconnected from",  # needs testing
        discord.AuditLogAction.member_role_update: "updated roles for",
        discord.AuditLogAction.message_bulk_delete: "bulk deleted message in",  # needs testing
        discord.AuditLogAction.message_delete: "deleted a message in {channel} sent by",
        discord.AuditLogAction.message_pin: "pinned a message in {channel} sent by",  # target seems to be guild
        discord.AuditLogAction.message_unpin: "unpinned a message in {channel} sent by",  # target seems to be guild
        discord.AuditLogAction.overwrite_create: "created channel overrides for",
        discord.AuditLogAction.overwrite_delete: "deleted channel overrides for",
        discord.AuditLogAction.overwrite_update: "updated channel overrides for",
        discord.AuditLogAction.role_create: "created a role",
        discord.AuditLogAction.role_delete: "deleted the role",
        discord.AuditLogAction.role_update: "updated the role",
        discord.AuditLogAction.scheduled_event_create: "created a scheduled event",
        discord.AuditLogAction.scheduled_event_delete: "deleted the scheduled event",
        discord.AuditLogAction.scheduled_event_update: "updated the scheduled event",
        discord.AuditLogAction.stage_instance_create: "created a stage instance",
        discord.AuditLogAction.stage_instance_delete: "deleted the stage instance",
        discord.AuditLogAction.stage_instance_update: "updated the stage instance",
        discord.AuditLogAction.sticker_create: "created a sticker",
        discord.AuditLogAction.sticker_delete: "deleted the sticker",
        discord.AuditLogAction.sticker_update: "updated the sticker",
        discord.AuditLogAction.thread_create: "created a {channel_type} thread",
        discord.AuditLogAction.thread_delete: "deleted the {channel_type} thread",
        discord.AuditLogAction.thread_update: "updated the {channel_type} thread",
        discord.AuditLogAction.webhook_create: "created a webhook",
        discord.AuditLogAction.webhook_delete: "deleted the webhook",
        discord.AuditLogAction.webhook_update: "updated the webhook",
    }
    channel_target_actions = [
        "channel_create",
        "channel_delete",
        "channel_update",
        "message_bulk_delete",
        "overwrite_create",
        "overwrite_delete",
        "overwrite_update",
        "thread_create",
        "thread_delete",
        "thread_update",
    ]

    if isinstance(entry.target, discord.object.Object):
        entry, target = await generic_object_converter(bot, guild, entry)
    elif hasattr(entry.target, "name"):
        target = f"**{discord.utils.escape_markdown(entry.target.name)}** `{entry.target.id}`"
    elif hasattr(entry.target, "id"):
        target = f"`{entry.target.id}`"
    elif entry.target is not None:
        target = str(entry.target)
    else:
        if hasattr(entry.after, "name"):
            target = f"**{discord.utils.escape_markdown(entry.after.name)}** `{entry.after.id}`"
        else:
            target = "Need handler"

    action = action_descriptions[entry.action]
    if entry.action.name in channel_target_actions:
        action = action.format(channel_type=entry.target.type)
        target = target[:2] + "#" + target[2:]
    if entry.action.name in ("message_pin", "message_unpin", "message_delete"):
        if isinstance(entry.extra.channel, discord.object.Object):
            entry.extra.channel = bot.get_channel(entry.extra.channel.id)
        action = action.format(
            channel=f"**#{discord.utils.escape_markdown(entry.extra.channel.name)}**"
        )
    elif entry.action.name in (
        "automod_block_message",
        "automod_flag_message",
        "automod_timeout_member",
    ):
        entry.user = "**AutoMod**"

    return AuditLogEntryLogMessage(user=entry.user, action=action, target=target)


class Logs:
    def __init__(self, bot):
        self.bot = bot

    async def send_message(self, guild: Guild, **kwargs):
        if channel_id := await self.bot.db.fetchval(
            """SELECT channel_id FROM modlogs WHERE guild_id = $1""", guild.id
        ):
            if channel := guild.get_channel(int(channel_id)):
                return await channel.send(**kwargs)

    async def parse_log(self, guild: Guild, log: Union[AuditLogEntry, LogEntry]) -> Any:
        entry = await get_embed(self.bot, guild, entry, user=entry.user)
        return entry

    async def send_moderator(
        self,
        ctx,
        member: Optional[
            Union[User, Member, discord.abc.GuildChannel, discord.Role]
        ] = None,
    ):
        data = await ctx_to_log_data(ctx, member)
        embed = await get_embed(self.bot, ctx.guild, data, user=member)
        return await self.send_message(ctx.guild, embed=embed)
