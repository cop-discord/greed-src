# TODO: Yurrion, please check issue no. 3 on github (https://github.com/ErisServices/GreedBot/issues/3)

from asyncio import ensure_future, sleep
from datetime import datetime
from typing import Any, Optional, Union

import discord  # type: ignore
from discord import ExpiringDictionary  # type: ignore
from discord.ext import commands, tasks  # type: ignore
from discord.utils import escape_markdown  # type: ignore
from pydantic import BaseModel  # type: ignore
from pytz import timezone  # type: ignore

from tools.bot import Pretend
from tools.handlers.logs import Logs, get_embed, get_username
from tools.helpers import GreedContext


def human_readable_timedelta(delta):
    days = delta.days
    weeks, days = divmod(days, 7)
    total_seconds = round(delta.total_seconds())
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    def format_unit(value, unit):
        return f"{value} {unit}" if value == 1 else f"{value} {unit}S"

    if weeks > 0:
        weeks_str = format_unit(weeks, "WEEK")
        if days > 0:
            days_str = format_unit(days, "DAY")
            return f"{weeks_str}, {days_str}"
        return weeks_str
    elif days > 0:
        return format_unit(days, "DAY")
    elif hours > 0:
        hours_str = format_unit(hours, "HOUR")
        minutes_str = format_unit(minutes, "MIN")
        if minutes > 0:
            return f"{hours_str}, {minutes_str}"
        return hours_str
    elif total_seconds == 60:  # Exactly 1 minute
        return format_unit(total_seconds, "SEC")
    elif minutes > 0:
        return format_unit(minutes, "MIN")
    else:
        return format_unit(seconds, "SEC")


async def log_event(
    bot: Pretend,
    log_type: dict,
    user: discord.abc.User,
    message: str = None,
    footer: str = None,
    moderator: str = None,
):
    channel = bot.get_channel(int(log_type["channel_id"]))
    if channel is None:
        return

    embed = discord.Embed(
        title="Mod Logs",
        description=f"`{log_type['type']}` {user.name} **{message}**",
        color=bot.color,
    )
    if footer != None:
        embed.set_footer(text=footer)
    if await bot.ratelimiter.ratelimit(f"logs:{channel.guild.id}", 2, 5) != False:
        await sleep(5)
    await channel.send(channel, embed=embed)


class LogStatus(BaseModel):
    enabled: Optional[bool] = False
    channel_id: Optional[int] = None


class ModLogs(commands.Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.invites = {}

    @commands.Cog.listener("on_ready")
    async def cache_all(self):
        await self.set_all_invites()

    async def set_all_invites(self):
        for guild_id in await self.bot.db.fetch("""SELECT guild_id FROM modlogs"""):
            if guild := self.bot.get_guild(int(guild_id.guild_id)):
                await self.set_guild_invites(guild)

    async def check_logs(self, guild: Union[discord.Guild, int]) -> LogStatus:
        if isinstance(guild, discord.Guild):
            g = guild.id
        else:
            g = guild
        data = await self.bot.db.fetchrow(
            """SELECT channel_id FROM modlogs WHERE guild_id = $1""", g
        )
        if not data:
            data = {"enabled": False, "channel_id": None}
        else:
            data = {"enabled": True, "channel_id": int(data["channel_id"])}
        #     if g == 1203397622325583944:
        #          await (self.bot.get_channel(1203397624024137760)).send(data)
        return LogStatus(**data)

    async def send(self, channel: discord.TextChannel, **kwargs):
        if (
            await self.bot.ratelimiter.ratelimit(f"logs:{channel.guild.id}", 2, 5)
            != False
        ):
            await sleep(5)
        #       if channel.guild.id == 1203397622325583944:
        #            await (self.bot.get_channel(1203397624024137760)).send(f"sending mod log for {kwargs['embed'].description}")
        return await channel.send(**kwargs)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        log_type = "rejoin" if member.flags.did_rejoin else "join"
        log_status = await self.check_logs(member.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        try:
            message, footer = await self.guild_invite_compare(member.guild)
        except:
            return
        await self.log_join_part(
            channel_id=log_status.channel_id,
            log_type=log_type,
            member=member,
            message=message,
            footer=footer,
        )

    #    @commands.Cog.listener()
    #   async def on_raw_member_remove(self, payload: discord.RawMemberRemoveEvent):
    # log_type = 'part'
    #  log_status = await self.check_logs(payload.guild_id)
    ##    if log_status.enabled == False:
    #         return
    #      if log_status.channel_id == None:
    #           return

    #        await self.log_join_part(channel_id = log_status.channel_id, log_type=log_type, member=payload.user)

    async def set_guild_invites(self, guild: discord.Guild):
        self.invites[guild.id] = await guild.invites()
        return True

    async def add_invite(self, invite: discord.Invite):
        if invite.guild.id in self.invites:
            self.invites[invite.guild.id].append(invite)
            return True
        return False

    async def remove_invite(self, invite: discord.Invite) -> bool:
        if invite.guild.id in self.invites:
            self.invites[invite.guild.id].remove(invite)
            return True
        return False

    async def set_log_state(
        self,
        ctx: GreedContext,
        state: bool,
        channel: Optional[discord.abc.GuildChannel] = None,
    ):
        if channel == None:
            if state == True:
                return await ctx.send_warning(f"a channel is required")
            else:
                try:
                    self.invites.pop(ctx.guild.id)
                except:
                    pass
                await self.bot.db.execute(
                    """DELETE FROM modlogs WHERE guild_id = $1""", ctx.guild.id
                )
                return await ctx.send_success(f"mod logs are now **disabled**")
        else:
            if state == True:
                await self.bot.db.execute(
                    """INSERT INTO modlogs (guild_id, channel_id) VALUES ($1, $2) ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id""",
                    ctx.guild.id,
                    channel.id,
                )
                ensure_future(self.set_guild_invites(ctx.guild))
                return await ctx.send_success(f"mod logs are now **enabled**")
            else:
                try:
                    self.invites.pop(ctx.guild.id)
                except:
                    pass
                await self.bot.db.execute(
                    """DELETE FROM modlogs WHERE guild_id = $1 AND channel_id = $2""",
                    ctx.guild.id,
                    channel.id,
                )
                return await ctx.send_success(f"mod logs are now **disabled**")

    @commands.command(
        name="logs", aliases=["modlogs", "modlog", "log"], brief="manage_guild"
    )
    @commands.has_guild_permissions(manage_messages=True)
    async def logs(self, ctx: GreedContext, channel: discord.TextChannel = None):
        if channel == None:
            log_status = await self.check_logs(ctx.guild)
            if log_status.enabled == True:
                return await self.set_log_state(ctx, False)
            else:
                return await self.set_log_state(ctx, True)
        else:
            return await self.set_log_state(ctx, True, channel)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        return await self.add_invite(invite)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        await self.remove_invite(invite)

    async def log_join_part(
        self,
        channel_id: int,
        log_type: str,
        member: discord.User,
        message: str = None,
        footer: str = None,
    ):
        await log_event(
            bot=self.bot,
            log_type={"type": log_type, "channel_id": channel_id},
            user=member,
            message=message,
            footer=footer,
        )

    async def guild_invite_compare(self, guild: discord.Guild):
        # What if the invite is the last invite - is it deleted and cal on_invite_delete?
        message, footer = None, None
        before_invites = self.invites.get(guild.id, None)
        if before_invites == None:
            await self.set_guild_invites(guild=guild)
            return None
        before_dict = {invite.code: invite.uses for invite in before_invites}

        try:
            after_invites = await guild.invites()
        except discord.Forbidden:
            after_invites = []

        if after_invites:
            self.invites[guild.id] = after_invites

            for after in after_invites:
                before_uses = before_dict.get(after.code)
                if before_uses is not None and before_uses < after.uses:
                    message = f"Invited by: {after.inviter.mention} `{after.inviter}`"
                    footer = f"Invite: {after.code}"
                    break

        return message, footer

    @commands.Cog.listener("on_user_update")
    async def username_change(self, before: discord.User, after: discord.User):
        if before.id == self.bot.user.id:
            return
        log_type = "username"
        if hasattr(after, "mutual_guilds"):
            for guild in after.mutual_guilds:
                log_status = await self.check_logs(guild)
                if log_status.enabled == False:
                    return
                if log_status.channel_id == None:
                    return

                message = f"from **{escape_markdown(str(before))}** to **{escape_markdown(str(after))}**"
                if str(before) != str(after):
                    await self.log_member_update_event(
                        log_type=log_type, member=after, message=message, guild=guild
                    )

    @commands.Cog.listener("on_member_update")
    async def nick_name_change(self, before: discord.Member, after: discord.Member):
        update_checks = {
            (before.nick, after.nick): lambda: self.nick_handler(
                before=before, after=after
            ),
            (before.pending, after.pending): lambda: self.log_member_update_event(
                log_type="pending", member=after, message="verified", guild=after.guild
            ),
            (
                before.flags.started_onboarding,
                after.flags.started_onboarding,
            ): lambda: self.log_member_update_event(
                log_type="onboarding",
                member=after,
                message="started",
                guild=after.guild,
            ),
            (
                before.flags.completed_onboarding,
                after.flags.completed_onboarding,
            ): lambda: self.log_member_update_event(
                log_type="onboarding",
                member=after,
                message="completed",
                guild=after.guild,
            ),
        }

        for (before_attr, after_attr), handler in update_checks.items():
            if before_attr != after_attr:
                await handler()
                break

    async def nick_handler(self, before: discord.Member, after: discord.Member):
        log_type = "nick"
        log_status = await self.check_logs(before.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        nick_changes = {
            (False, True): lambda: self.log_member_update_event(
                log_type=log_type,
                member=after,
                message=f"set nick to **{escape_markdown(after.nick)}**",
                guild=after.guild,
            ),
            (True, False): lambda: self.log_member_update_event(
                log_type=log_type,
                member=before,
                message=f"removed nickname **{escape_markdown(before.nick)}**",
                guild=before.guild,
            ),
            (True, True): lambda: self.log_member_update_event(
                log_type=log_type,
                member=after,
                message=f"changed nickname from **{escape_markdown(before.nick)}** to **{escape_markdown(after.nick)}**",
                guild=after.guild,
            ),
        }

        handler = nick_changes[(bool(before.nick), bool(after.nick))]
        if handler:
            await handler()

    async def log_member_update_event(
        self, log_type: str, member: discord.Member, message: str, guild: discord.Guild
    ):
        if not hasattr(member, "guild"):
            return
        log_status = await self.check_logs(member.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        if guild is None:
            guild = member.guild

        embed = discord.Embed(
            title="Mod Logs",
            description=f"`{log_type}` {get_username(member)} **{message}**",
            color=self.bot.color,
        )
        if channel := guild.get_channel(log_status.channel_id):
            return await self.send(channel, embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        log_type = "voice"
        log_status = await self.check_logs(member.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        before_channel = before.channel.mention if before.channel else None
        after_channel = after.channel.mention if after.channel else None

        messages = {
            (False, True): f"joined {after_channel}",
            (True, False): f"disconnected from {before_channel}",
            (True, True): f"moved from {before_channel} to {after_channel}",
        }
        message = messages[(bool(before.channel), bool(after.channel))]
        await self.log_voice_event(
            channel_id=log_status.channel_id,
            log_type=log_type,
            member=member,
            message=message,
        )

    async def log_voice_event(
        self, channel_id: int, log_type: str, member: discord.Member, message: str
    ):
        return await log_event(
            self.bot,
            log_type={"type": log_type, "channel_id": channel_id},
            user=member,
            message=message,
        )

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        async def default_handler(entry):
            pass

        try:
            if entry.user.id == self.bot.user.id:
                return
        except:
            pass
        handler_name = f"{entry.action.name.lower()}_handler"
        handler = getattr(self, handler_name, default_handler)
        await handler(entry)

    async def kick_handler(self, entry: discord.AuditLogEntry):
        log_type = "kick"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        try:
            target = await self.bot.fetch_user(entry.target.id)
        except:
            pass
        message = f"kicked {target.mention} `{get_username(target)}`"
        if entry.reason:
            message += f"| Reason: {entry.reason}"
        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def ban_handler(self, entry: discord.AuditLogEntry):
        log_type = "ban"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        target = await self.bot.fetch_user(entry.target.id)
        message = f"banned {target.mention} `{get_username(target)}`"
        if entry.reason:
            message += f"| Reason: {entry.reason}"
        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def unban_handler(self, entry: discord.AuditLogEntry):
        log_type = "unban"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        target = await self.bot.fetch_user(entry.target.id)
        message = f"unbanned {target.mention} `{get_username(target)}`"
        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def member_update_handler(self, entry: discord.AuditLogEntry):
        attribute_to_handler = {
            "timed_out_until": self.member_time_out,
            "deaf": self.member_deafen,
            "mute": self.member_mute,
            "nick": self.member_nick,
        }

        for attr, handler in attribute_to_handler.items():
            if hasattr(entry.after, attr):
                await handler(entry)
                break

    async def member_time_out(self, entry: discord.AuditLogEntry):
        def timeout_length():
            return human_readable_timedelta(
                entry.after.timed_out_until - entry.created_at
            )

        log_type = "timedout"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        member_details = f"{entry.target.mention} `{get_username(entry.target)}`"
        if (
            not entry.before.timed_out_until
            or entry.before.timed_out_until < datetime.now(timezone.utc)
        ):
            message = f"timed out {member_details} for {timeout_length()}"
            if entry.reason:
                message += f"| Reason: {entry.reason}"
            if channel := entry.guild.get_channel(log_status.channel_id):
                await self.log_moderator_action_event(
                    channel=channel,
                    moderator=entry.user,
                    log_type=log_type,
                    message=message,
                )
        elif not entry.after.timed_out_until:
            message = f"removed timed out from {member_details}"
            if channel := entry.guild.get_channel(log_status.channel_id):
                await self.log_moderator_action_event(
                    channel=channel,
                    moderator=entry.user,
                    log_type=log_type,
                    message=message,
                )
        else:
            message = f"updated timeout for {member_details} to {timeout_length()}"
            if entry.reason:
                message += f"| Reason: {entry.reason}"
            if channel := entry.guild.get_channel(log_status.channel_id):
                await self.log_moderator_action_event(
                    channel=channel,
                    moderator=entry.user,
                    log_type=log_type,
                    message=message,
                )

    async def member_deafen(self, entry: discord.AuditLogEntry):
        log_type = "deafen"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        deafen_after = getattr(entry.after, "deaf", None)
        if deafen_after is True:
            message = f"deafened {entry.target.mention} `{get_username(entry.target)}`"
        else:
            message = (
                f"undeafened {entry.target.mention} `{get_username(entry.target)}`"
            )

        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def member_mute(self, entry: discord.AuditLogEntry):
        log_type = "mute"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        mute_after = getattr(entry.after, "mute", None)
        if mute_after is True:
            message = f"muted {entry.target.mention} `{get_username(entry.target)}`"
        else:
            message = f"unmuted {entry.target.mention} `{get_username(entry.target)}`"

        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def member_nick(self, entry: discord.AuditLogEntry):
        log_type = "nickname"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        old_nick = getattr(entry.before, "nick", None)
        new_nick = getattr(entry.after, "nick", None)
        target = f"{entry.target.mention} `{get_username(entry.target)}`"

        messages = {
            (
                False,
                True,
            ): f"set nickname for {target} to **{escape_markdown(str(new_nick))}**",
            (
                True,
                False,
            ): f"removed nickname **{escape_markdown(str(old_nick))}** from {target}",
            (
                True,
                True,
            ): f"changed nickname for {target} from **{escape_markdown(str(old_nick))}** to **{escape_markdown(str(new_nick))}**",
        }

        message = messages[(bool(old_nick), bool(new_nick))]
        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def message_delete_handler(self, entry: discord.AuditLogEntry):
        log_type = "deleted"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        if entry.user.bot:
            return

        if isinstance(entry.target, discord.object.Object):
            try:
                target = await self.bot.fetch_user(entry.target.id)
                username = get_username(target)
            except discord.errors.NotFound:
                username = "Deleted User"

        else:
            username = get_username(entry.target)

        message = f"deleted {entry.extra.count} message(s) in **#{entry.extra.channel.name}** `{entry.extra.channel.id}` sent by <@{entry.target.id}> `{username}`"
        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def member_move_handler(self, entry: discord.AuditLogEntry):
        log_type = "move"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        message = f"{entry.extra.count} member(s) were moved to **#{entry.extra.channel.name}** `{entry.extra.channel.id}`"
        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def member_disconnect_handler(self, entry: discord.AuditLogEntry):
        log_type = "disconnect"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        message = f"disconnected {entry.extra.count} member(s)"
        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def member_role_update_handler(self, entry: discord.AuditLogEntry):
        log_type = "roled"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        if (
            not entry.user
        ):  # Member assigned Premium role - this is probably integration roles
            return

        if entry.user.bot:
            return

        after_roles = [role.mention for role in entry.after.roles]
        before_roles = [role.mention for role in entry.before.roles]
        target = f"{entry.target.mention} `{get_username(entry.target)}`"

        if after_roles:
            message = (
                f'granted {target} {len(after_roles)} role(s): {", ".join(after_roles)}'
            )
        elif before_roles:
            message = f'removed {len(before_roles)} role(s) from {target}: {", ".join(before_roles)}'

        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def message_pin_handler(self, entry: discord.AuditLogEntry):
        log_type = "pinned msg"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        jump_url = f"https://discord.com/channels/{entry.guild.id}/{entry.extra.channel.id}/{entry.extra.message_id}"
        message = f"pinned message: {jump_url}"
        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def message_unpin_handler(self, entry: discord.AuditLogEntry):
        log_type = "unpinned msg"
        log_status = await self.check_logs(entry.guild)
        if log_status.enabled == False:
            return
        if log_status.channel_id == None:
            return

        jump_url = f"https://discord.com/channels/{entry.guild.id}/{entry.extra.channel.id}/{entry.extra.message_id}"
        message = f"unpinned message: {jump_url}"
        if channel := entry.guild.get_channel(log_status.channel_id):
            await self.log_moderator_action_event(
                channel=channel,
                moderator=entry.user,
                log_type=log_type,
                message=message,
            )

    async def log_moderator_action_event(
        self,
        channel: discord.TextChannel,
        moderator: discord.Member,
        log_type: str,
        message: str,
    ):
        guild = channel.guild  # Accessing the guild from the channel
        embed = discord.Embed(
            title="Mod Logs",
            description=f"`{log_type}`\n**{moderator.name}** {message}",
        )

        # Using guild.icon_url instead of guild.icon
        return await self.send(channel, embed=embed)


async def setup(bot: Pretend):
    await bot.add_cog(ModLogs(bot))
