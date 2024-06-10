import datetime

import orjson
from discord.ext.commands import BadArgument, check

from .helpers import GreedContext
from .persistent.vm import rename_vc_bucket

"""

LEVELING PREDICATES

"""


def leveling_enabled():
    async def predicate(ctx: GreedContext):
        if await ctx.bot.db.fetchrow(
            "SELECT * FROM leveling WHERE guild_id = $1", ctx.guild.id
        ):
            return True

        await ctx.send_warning("Leveling is **not** enabled")
        return False

    return check(predicate)


"""

ANTINUKE PREDICATES

"""


def antinuke_owner():
    async def predicate(ctx: GreedContext):
        if owner_id := await ctx.bot.db.fetchval(
            "SELECT owner_id FROM antinuke WHERE guild_id = $1", ctx.guild.id
        ):
            if ctx.author.id != owner_id:
                await ctx.send_warning(f"Only <@!{owner_id}> can use this command!")
                return False
            return True
        await ctx.send_warning("Antinuke is **not** configured")
        return False

    return check(predicate)


def antinuke_configured():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchval(
            "SELECT configured FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        if not check or check == "false":
            await ctx.send_warning("Antinuke is **not** configured")
        return str(check) == "true"

    return check(predicate)


def admin_antinuke():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT owner_id, admins FROM antinuke WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            allowed = [check["owner_id"]]
            if check["admins"]:
                allowed.extend([id for id in orjson.loads(check["admins"])])

            if not ctx.author.id in allowed:
                await ctx.send_warning("You **cannot** use this command")
                return False
            return True
        else:
            await ctx.send_warning("Antinuke is **not** configured")
            return False

    return check(predicate)


"""

BOOSTER ROLES PREDICATES  

"""


def has_br_or_shared_role():
    async def predicate(ctx):
        if ctx.guild.premium_subscriber_role in ctx.author.roles:
            return True
        shared_role_id = await ctx.bot.db.fetchval(
            "SELECT role_id FROM shared_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            ctx.author.id,
        )
        if shared_role_id:
            return True
        await ctx.send_warning(
            "You must be boosting the guild or have a shared role to use this command"
        )

    return check(predicate)


def sharing_enabled():
    async def predicate(ctx):
        sharing_enabled = await ctx.bot.db.fetchval(
            "SELECT sharing_enabled FROM booster_module WHERE guild_id = $1",
            ctx.guild.id,
        )
        if not sharing_enabled:
            await ctx.send_warning("sharing a booster role is disabled mf")
            return False
        return True

    return check(predicate)


def has_shared_role():
    async def predicate(ctx):
        shared_roles = await ctx.bot.db.fetch(
            "SELECT role_id FROM shared_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            ctx.author.id,
        )
        shared_role_ids = [result["role_id"] for result in shared_roles]
        user_role_ids = [role.id for role in ctx.author.roles]
        if not any(role_id in shared_role_ids for role_id in user_role_ids):
            await ctx.send_warning("You don't have a shared booster role")
            return False
        return True

    return check(predicate)


def br_is_configured():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM booster_module WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            await ctx.send_warning("Booster roles are **not** configured")
        return check is not None

    return check(predicate)


def has_br_role():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM booster_roles WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            ctx.author.id,
        )
        if not check:
            await ctx.send_warning(
                f"You do not have a booster role set\nPlease use `{ctx.clean_prefix}br create` to create a booster role"
            )
        return check is not None

    return check(predicate)


"""

LIMIT PREDICATES

"""


def query_limit(table: str, limit: int = 5):
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchval(
            f"SELECT COUNT(*) FROM {table} WHERE guild_id = $1", ctx.guild.id
        )
        if check == limit:
            await ctx.send_warning(
                f"You cannot create more than **{limit}** {table} messages"
            )
            return False
        return True

    return check(predicate)


def boosted_to(level: int):
    async def predicate(ctx: GreedContext):
        if ctx.guild.premium_tier < level:
            await ctx.send_warning(
                f"The server has to be boosted to level **{level}** to be able to use this command"
            )
        return ctx.guild.premium_tier >= level

    return check(predicate)


def max_gws():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchval(
            "SELECT COUNT(*) FROM giveaway WHERE guild_id = $1", ctx.guild.id
        )
        if check == 5:
            await ctx.send_warning(
                "You cannot host more than **5** giveaways in the same time"
            )
            return False
        return True

    return check(predicate)


"""

OWNER PREDICATES

"""


def guild_owner():
    async def predicate(ctx: GreedContext):
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send_warning(
                f"This command can be only used by **{ctx.guild.owner}**"
            )
        return ctx.author.id == ctx.guild.owner_id

    return check(predicate)


"""

MODERATION PREDICATES

"""


def is_jail():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM jail WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            raise BadArgument("Jail is **not** configured")
        return True

    return check(predicate)


def antispam_enabled():
    async def predicate(ctx: GreedContext):
        if not await ctx.bot.db.fetchrow(
            "SELECT * FROM antispam WHERE guild_id = $1", ctx.guild.id
        ):
            await ctx.send_warning("Antispam is **not** enabled in this server")
            return False
        return True

    return check(predicate)


"""

DONATOR PREDICATES

"""


def create_reskin():
    async def predicate(ctx: GreedContext):
        if not await ctx.reskin_enabled():
            await ctx.send_warning("Reskin is **not** enabled in this server")
            return False

        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM reskin WHERE user_id = $1", ctx.author.id
        )

        if not check:
            await ctx.bot.db.execute(
                "INSERT INTO reskin VALUES ($1,$2,$3)",
                ctx.author.id,
                ctx.bot.user.name,
                ctx.bot.user.display_avatar.url,
            )

        return True

    return check(predicate)


def has_perks():
    async def predicate(ctx: GreedContext):
        if cache := ctx.bot.cache.get(f"donor-{ctx.author.id}"):
            return cache

        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM donor WHERE user_id = $1", ctx.author.id
        )
        if not check:
            data = await ctx.bot.session.get_json(
                f"https://top.gg/api/bots/{ctx.bot.user.id}/check",
                params={"userId": ctx.author.id},
                headers={
                    "Authorization": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjExNDk1MzU4MzQ3NTY4NzQyNTAiLCJib3QiOnRydWUsImlhdCI6MTcwODYyMDQ4Nn0.htIQgitv90wWGmK8qXf0zMTiDIF0xO7coZfBwUe9k0c"
                },
            )

            if data["voted"] == 0:
                await ctx.send_warning(
                    f"Please [**vote**](https://top.gg/bot/{ctx.bot.user.id}/vote) me to use donor commands for **12** hours"
                )
                return False
            else:
                await ctx.bot.cache.set(f"donor-{ctx.author.id}", True, 3600 * 12)
        return True

    return check(predicate)


"""

MUSIC PREDICATES

"""


def is_voice():
    async def predicate(ctx: GreedContext):
        if not ctx.author.voice:
            await ctx.send_warning("You are not in a voice channel")
            return False
        if ctx.guild.me.voice:
            if ctx.guild.me.voice.channel.id != ctx.author.voice.channel.id:
                await ctx.send_warning(
                    "You are not in the same voice channel as the bot"
                )
                return False
        return True

    return check(predicate)


def bot_is_voice():
    async def predicate(ctx):
        if not ctx.guild.me.voice:
            await ctx.send_warning("The bot is not in a voice channel")
            return False

        if ctx.voice_client:
            if hasattr(ctx.voice_client, "context"):
                if ctx.voice_client.context != ctx:
                    ctx.voice_client.context = ctx
            else:
                ctx.voice_client.context = ctx

        return True

    return check(predicate)


def lastfm_user_exists():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM lastfm WHERE user_id = $1", ctx.author.id
        )
        if not check:
            await ctx.lastfm_send("You don't have a **Last.Fm** account set")
            return False
        return True

    return check(predicate)


"""

ECONOMY PREDICATES

"""


def create_account():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM economy WHERE user_id = $1", ctx.author.id
        )
        if not check:
            await ctx.bot.db.execute(
                "INSERT INTO economy (user_id, cash, card) VALUES ($1,$2,$3)",
                ctx.author.id,
                100.00,
                0.00,
            )
        return True

    return check(predicate)


def dice_cooldown():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT dice FROM economy WHERE user_id = $1", ctx.author.id
        )
        if check:
            if check["dice"]:
                if datetime.datetime.now().timestamp() < check["dice"]:
                    await ctx.economy_send(
                        f"You can **dice** again **{ctx.bot.humanize_date(datetime.datetime.fromtimestamp(check['dice']))}**"
                    )
                    return False
        return True

    return check(predicate)


def daily_taken():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT daily FROM economy WHERE user_id = $1", ctx.author.id
        )
        if check:
            if check["daily"]:
                if datetime.datetime.now().timestamp() < check["daily"]:
                    await ctx.economy_send(
                        f"You **already** claimed your daily credits\nTry again **{ctx.bot.humanize_date(datetime.datetime.fromtimestamp(check['daily']))}**"
                    )
                    return False
        return True

    return check(predicate)


"""

VOICEMASTER PREDICATES

"""


def rename_cooldown():
    async def predicate(ctx: GreedContext):
        return await rename_vc_bucket(ctx.bot, ctx.author.voice.channel)

    return check(predicate)


async def check_owner(ctx: GreedContext):
    check = await ctx.bot.db.fetchrow(
        "SELECT * FROM vcs WHERE voice = $1 AND user_id = $2",
        ctx.author.voice.channel.id,
        ctx.author.id,
    )
    if check is None:
        await ctx.send_warning("You are not the owner of this voice channel")
        return True


async def check_voice(ctx: GreedContext):
    check = await ctx.bot.db.fetchrow(
        "SELECT * FROM voicemaster WHERE guild_id = $1", ctx.guild.id
    )
    if check is not None:
        channeid = check[1]
        voicechannel = ctx.guild.get_channel(channeid)
        category = voicechannel.category
        if ctx.author.voice is None:
            await ctx.send_warning("You are not in a voice channel")
            return True
        elif ctx.author.voice is not None:
            if ctx.author.voice.channel.category != category:
                await ctx.send_warning(
                    "You are not in a voice channel created by the bot"
                )
                return True


def is_vm():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM voicemaster WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            raise BadArgument("VoiceMaster is **already** configured")
        return True

    return check(predicate)


def check_vc_owner():
    async def predicate(ctx: GreedContext):
        voice = await check_voice(ctx)
        owner = await check_owner(ctx)
        if voice is True or owner is True:
            return False
        return True

    return check(predicate)


"""

TICKET PREDICATES

"""


def get_ticket():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM opened_tickets WHERE guild_id = $1 AND channel_id = $2",
            ctx.guild.id,
            ctx.channel.id,
        )
        if check is None:
            await ctx.send_warning("This message has to be used in an opened ticket")
            return False
        return True

    return check(predicate)


def manage_ticket():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT support_id FROM tickets WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            role = ctx.guild.get_role(check[0])
            if role:
                if (
                    not role in ctx.author.roles
                    and not ctx.author.guild_permissions.manage_channels
                ):
                    await ctx.send_warning(
                        f"Only members with {role.mention} role and members with the `manage_channels` permission can **add** or **remove** new members from the ticket"
                    )
                    return False
            else:
                if not ctx.author.guild_permissions.manage_channels:
                    await ctx.send_warning(
                        f"Only members with the `manage_channels` permission can **add** or **remove** new members from the ticket"
                    )
                    return False
        else:
            if not ctx.author.guild_permissions.manage_channels:
                await ctx.send_warning(
                    f"Only members with the `manage_channels` permission can **add** or **remove** new members from the ticket"
                )
                return False
        return True

    return check(predicate)


def ticket_exists():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM tickets WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            await ctx.bot.db.execute(
                "INSERT INTO tickets (guild_id) VALUES ($1)", ctx.guild.id
            )
        return True

    return check(predicate)


"""

MISC

"""


def bump_enabled():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT guild_id FROM bumpreminder WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            return await ctx.send_error("Bump reminder feature is **not** enabled")
        return check is not None

    return check(predicate)


def is_afk():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM afk WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            ctx.author.id,
        )
        return check is None

    return check(predicate)


def is_there_a_reminder():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM reminder WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            ctx.author.id,
        )
        if not check:
            await ctx.send_warning("You don't have a reminder set in this server")
        return check is not None

    return check(predicate)


def reminder_exists():
    async def predicate(ctx: GreedContext):
        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM reminder WHERE guild_id = $1 AND user_id = $2",
            ctx.guild.id,
            ctx.author.id,
        )
        if check:
            await ctx.send_warning("You already have a reminder in this channel")
            return False
        return True

    return check(predicate)


def whitelist_enabled():
    async def predicate(ctx: GreedContext):
        if not await ctx.bot.db.fetchrow(
            """
            SELECT * FROM whitelist_state
            WHERE guild_id = $1
            """,
            ctx.guild.id,
        ):
            await ctx.send_warning(f"Whitelist is **not** enabled")
            return False
        return True

    return check(predicate)
