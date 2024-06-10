import asyncio
import datetime
import logging
import os
import urllib
from copy import copy
from io import BytesIO
from typing import Any, List, Optional, Set, Union

import aiohttp
import asyncpg
import colorgram
import discord
import dotenv
from discord.ext import commands  # type: ignore
from discord.gateway import DiscordWebSocket
from humanize import precisedelta
from num2words import num2words
from PIL import Image
from PretendAPI import API

# from cogs.music import Music
from cogs.fun import BlackTea

from .database import PostgreSQL
from .exceptions import LastFmException, RenameRateLimit, WrongMessageLink
from .expiringdictionary import ExpiringDictionary
from .handlers.embedbuilder import EmbedScript
from .handlers.logs import Logs
from .handlers.socials.profile import ServerProfile
from .helpers import (
    AntinukeMeasures,
    Cache,
    CustomInteraction,
    GreedContext,
    PretendHelp,
    guild_perms,
    identify,
)
from .misc.session import Session
from .misc.tasks import (
    bump_remind,
    check_monthly_guilds,
    counter_update,
    gw_loop,
    pomelo_task,
    reminder_task,
    shit_loop,
    snipe_delete,
)
from .persistent.giveaway import GiveawayView
from .persistent.tickets import TicketView
from .persistent.vm import VoiceMasterView
from .rival import RivalAPI
from .tickets import TicketLogs

dotenv.load_dotenv(verbose=True)

# handler = logging.FileHandler(
#    filename="discord.log",
#    encoding="utf-8",
#    mode="w",
# )

# console = logging.StreamHandler()
# console.setLevel(logging.INFO)

formatter = logging.Formatter(
    "%(asctime)s | %(name)-12s: %(levelname)-8s %(message)s", "%Y-%m-%d %H:%M:%S"
)

# console.setFormatter(formatter)

log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.guilds = True
intents.message_content = True

commands.has_guild_permissions = guild_perms
DiscordWebSocket.identify = identify
discord.Interaction.warn = CustomInteraction.warn
discord.Interaction.approve = CustomInteraction.approve
discord.Interaction.error = CustomInteraction.error


class Pretend(commands.AutoShardedBot):
    """
    The discord bot
    """

    def __init__(self, db: asyncpg.Pool = None):
        super().__init__(
            command_prefix=getprefix,
            intents=intents,
            help_command=PretendHelp(),
            chunk_guilds_at_startup=False,
            owner_ids=[
                930383131863842816,
                227955834972405760,
                153643814605553665,
                1246541711308619959,
            ],
            case_insensitive=True,
            shard_count=1,
            strip_after_prefix=True,
            enable_debug_events=True,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, replied_user=False
            ),
            member_cache=discord.MemberCacheFlags(joined=True, voice=True),
        )

        self.db = db
        self.login_data = {
            x: os.environ[x] for x in ["host", "password", "database", "user", "port"]
        }
        self.color = 0x7291DF
        self.warning = "<:warn:1225126477880623175>"
        self.warning_color = 0xEFBC1B
        self.no = "<:deny:1225126443638325361>"
        self.no_color = 0xFF3735
        self.yes = "<:check:1225126153098891304>"
        self.yes_color = 0x48DB01
        self.time = datetime.datetime.now()
        self.mcd = commands.CooldownMapping.from_cooldown(
            3, 5, commands.BucketType.user
        )
        self.ccd = commands.CooldownMapping.from_cooldown(
            4, 5, commands.BucketType.channel
        )
        self.session = Session()
        self.cache = Cache()
        self.tickets = TicketLogs(self)
        self.rival = RivalAPI("1c6ad8e0-6dbc-4e61-9600-275bddf0997d")
        self.proxy_url = os.environ.get("proxy_url")
        self.other_bots = {}
        self.logs = Logs(self)
        self.ratelimiter = ExpiringDictionary()
        self.pretend_api = os.environ.get("pretend_key")
        self.pretend = API(self.pretend_api)
        self.tea = BlackTea(self)
        self.an = AntinukeMeasures(self)
        self.embed_build = EmbedScript()
        self.before_invoke = self.clear

    def run(self):
        """
        Run the bot
        """

        return super().run(os.environ["token"])

    def ordinal(self, number: int) -> str:
        """
        convert a number to an ordinal number (ex: 1 -> 1st)
        """

        return num2words(number, to="ordinal_num")

    @property
    def public_cogs(self) -> List[commands.Cog]:
        """
        the cogs that are shown in the help command
        """

        return [
            c
            for c in self.cogs
            if not c in ["Jishaku", "Owner", "Members", "Auth", "Reactions", "Messages"]
        ]

    @property
    def uptime(self) -> str:
        """
        The amount of time the bot is running for
        """

        return precisedelta(self.time, format="%0.0f")

    @property
    def chunked_guilds(self) -> int:
        """
        Returns the amount of chunked servers
        """

        return len([g for g in self.guilds if g.chunked])

    @property
    def lines(self) -> int:
        """
        Return the code's amount of lines
        """

        lines = 0
        for d in [x[0] for x in os.walk("./") if not ".git" in x[0]]:
            for file in os.listdir(d):
                if file.endswith(".py"):
                    lines += len(open(f"{d}/{file}", "r").read().splitlines())

        return lines

    def humanize_date(self, date: datetime.datetime) -> str:
        """
        Humanize a datetime (ex: 2 days ago)
        """

        if date.timestamp() < datetime.datetime.now().timestamp():
            return f"{(precisedelta(date, format='%0.0f').replace('and', ',')).split(', ')[0]} ago"
        else:
            return f"in {(precisedelta(date, format='%0.0f').replace('and', ',')).split(', ')[0]}"

    async def dominant_color(self, url: Union[discord.Asset, str]) -> int:
        """
        Get the dominant color of a discord asset or image link
        """

        if isinstance(url, discord.Asset):
            url = url.url

        img = Image.open(BytesIO(await self.session.get_bytes(url)))
        img.thumbnail((32, 32))

        colors = await asyncio.to_thread(lambda: colorgram.extract(img, 1))
        return discord.Color.from_rgb(*list(colors[0].rgb)).value

    async def getbyte(self, url: str) -> BytesIO:
        """
        Get the BytesIO object of an url
        """

        return BytesIO(await self.session.get_bytes(url))

    async def create_db(self) -> asyncpg.Pool:
        """
        Create a connection to the postgresql database
        """

        log.info("Creating db connection")
        return await PostgreSQL().__aenter__(**self.login_data)

    async def get_context(
        self, message: discord.Message, cls=GreedContext
    ) -> GreedContext:
        """
        Get the bot's custom context
        """

        return await super().get_context(message, cls=cls)

    async def start_loops(self) -> None:
        """
        Start all the loops
        """

        shit_loop.start(self)
        snipe_delete.start(self)
        pomelo_task.start(self)
        gw_loop.start(self)
        bump_remind.start(self)
        check_monthly_guilds.start(self)
        reminder_task.start(self)
        counter_update.start(self)

    def url_encode(self, url: str):
        """
        Encode an url
        """

        return urllib.parse.unquote(urllib.parse.quote_plus(url))

    async def setup_hook(self) -> None:
        self.session2 = aiohttp.ClientSession()
        from .redis import PretendRedis

        self.redis = await PretendRedis.from_url()

        log.info("Starting bot")
        if not self.db:
            self.db = await self.create_db()

        self.bot_invite = discord.utils.oauth_url(
            client_id=self.user.id, permissions=discord.Permissions(8)
        )
        asyncio.ensure_future(self.load())

    async def load(self) -> None:
        """
        load all cogs
        """

        await self.load_extension("jishaku")
        log.info("Loaded jishaku")

        for file in [f[:-3] for f in os.listdir("./cogs") if f.endswith(".py")]:
            try:
                await self.load_extension(f"cogs.{file}")
                log.info(f"Loaded {file.replace('.py','')}")
            except Exception as e:
                log.warning(f"Unable to load {file}: {e}")

        for file in [f[:-3] for f in os.listdir("./events") if f.endswith(".py")]:
            await self.load_extension(f"events.{file}")

        log.info("Loaded all cogs")
        await self.load_views()
        log.info("Loaded views")

    async def load_views(self) -> None:
        """
        Add the persistent views
        """

        vm_results = await self.db.fetch("SELECT * FROM vm_buttons")
        self.add_view(VoiceMasterView(self, vm_results))
        self.add_view(GiveawayView())
        self.add_view(TicketView(self, True))

    async def on_ready(self) -> None:
        asyncio.ensure_future(self.__chunk_guilds())
        log.info(f"Connected as {self.user}")
        #  await Music(self).start_nodes()
        await self.load()
        await self.start_loops()

    async def __chunk_guilds(self):
        for guild in self.guilds:
            await asyncio.sleep(0.1)
            await guild.chunk(cache=True)

    async def do_aliases(self, ctx: GreedContext):
        aliases = await self.db.fetch(
            "SELECT alias, command_name FROM aliases WHERE guild_id = $1", ctx.guild.id
        )
        if not aliases:
            return
        ctx.message = copy(ctx.message)
        m = ctx.message.content.strip(ctx.prefix).lower().split(" ")
        for alias, command_name in aliases:
            if alias.lower() in m:
                i = m.index(alias.lower())
                m[i] = m[i].replace(alias.lower(), command_name.lower())
        ctx.message.content = ctx.prefix + " ".join(d for d in m)
        #        log.info(f'{ctx.message.content}')
        return await self.process_commands(ctx.message)

    async def on_command_error(
        self, ctx: GreedContext, error: commands.CommandError
    ) -> Any:
        """
        The place where the command errors raise
        """

        channel_perms = ctx.channel.permissions_for(ctx.guild.me)

        if not channel_perms.send_messages or not channel_perms.embed_links:
            return
        #       log.info(str(error))
        #      log.info(type(error))
        #     if ctx.author.name == 'aiohttp':
        #        await ctx.send(str(error))
        #       await ctx.send(type(error))
        if isinstance(error, discord.ext.commands.errors.CommandNotFound):
            log.info("command not found lol")
            return await self.do_aliases(ctx)
            for alias, command_name in await ctx.bot.db.fetch(
                "SELECT alias, command_name FROM aliases WHERE guild_id = $1",
                ctx.guild.id,
            ):
                if alias.lower() in ctx.message.content.lower():
                    m = copy(ctx.message)
                    m.content = m.content.lower().replace(
                        alias.lower(), command_name.lower()
                    )
                    return await self.get_context(m).invoke()

            return await ctx.send_warning(
                f"command `{ctx.message.content.split(ctx.prefix)[1]}` not found"
            )

        if isinstance(
            error,
            (commands.CommandOnCooldown, commands.CommandNotFound, commands.NotOwner),
        ):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send_help(ctx.command)
        if isinstance(error, (RenameRateLimit, LastFmException, WrongMessageLink)):
            return await ctx.send_warning(error.message)
        if isinstance(error, commands.CheckFailure):
            if isinstance(error, commands.MissingPermissions):
                return await ctx.send_warning(
                    f"You are **missing** the following permission: `{error.missing_permissions[0]}`"
                )
            else:
                return
        log.info(f"{error}")
        if hasattr(error, "messags"):
            return await ctx.send_warning(error.message)
        return await ctx.send_warning(error.args[0])

    def dt_convert(self, datetime: datetime.datetime) -> str:
        """
        Get a detailed version of a datetime value
        """

        hour = datetime.hour

        if hour > 12:
            meridian = "PM"
            hour -= 12
        else:
            meridian = "AM"

        return f"{datetime.month}/{datetime.day}/{str(datetime.year)[-2:]} at {hour}:{datetime.minute} {meridian}"

    async def get_prefixes(self, message: discord.Message) -> Set[str]:
        """
        Returns a list of the bot's prefixes
        """

        prefixes = set()
        r = await self.db.fetchrow(
            "SELECT prefix FROM selfprefix WHERE user_id = $1", message.author.id
        )
        if r:
            prefixes.add(r[0])
        re = await self.db.fetchrow(
            "SELECT prefix FROM prefixes WHERE guild_id = $1", message.guild.id
        )
        if re:
            prefixes.add(re[0])
        else:
            prefixes.add(",")
        return set(prefixes)

    def member_cooldown(self, message: discord.Message) -> Optional[int]:
        bucket = self.mcd.get_bucket(message)
        return bucket.update_rate_limit()

    def channel_cooldown(self, message: discord.Message) -> Optional[int]:
        bucket = self.ccd.get_bucket(message)
        return bucket.update_rate_limit()

    def is_dangerous(self, role: discord.Role) -> bool:
        """
        Check if the role has dangerous permissions
        """

        return any(
            [
                role.permissions.ban_members,
                role.permissions.kick_members,
                role.permissions.mention_everyone,
                role.permissions.manage_channels,
                role.permissions.manage_events,
                role.permissions.manage_expressions,
                role.permissions.manage_guild,
                role.permissions.manage_roles,
                role.permissions.manage_messages,
                role.permissions.manage_webhooks,
                role.permissions.manage_permissions,
                role.permissions.manage_threads,
                role.permissions.moderate_members,
                role.permissions.mute_members,
                role.permissions.deafen_members,
                role.permissions.move_members,
                role.permissions.administrator,
            ]
        )

    async def process_commands(self, message: discord.Message) -> Any:
        """
        Process a command from the given message
        """
        if not self.is_ready():
            return

        if message.content.startswith(
            tuple(await self.get_prefixes(message))
        ) or message.content.startswith(f"<@{self.user.id}>"):
            channel_rl = self.channel_cooldown(message)
            member_rl = self.member_cooldown(message)

            if channel_rl or member_rl:
                return

            return await super().process_commands(message)

    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> Any:
        if not after.guild:
            return

        if before.content != after.content:
            if after.content.startswith(
                tuple(await self.get_prefixes(after))
            ) or after.content.startswith(f"<@{self.user.id}>"):
                return await self.process_commands(after)

    async def on_message(self, message: discord.Message) -> Any:
        if not message.author.bot and message.guild:
            perms = message.channel.permissions_for(message.guild.me)
            if perms.send_messages and perms.embed_links:
                if not await self.db.fetchrow(
                    "SELECT * FROM blacklist WHERE id = $1 AND type = $2",
                    message.author.id,
                    "user",
                ):
                    if message.content == f"<@{self.user.id}>":
                        channel_rl = self.channel_cooldown(message)
                        member_rl = self.member_cooldown(message)

                        if not channel_rl and not member_rl:
                            prefixes = ", ".join(
                                f"`{p}`" for p in await self.get_prefixes(message)
                            )
                            ctx = await self.get_context(message)
                            return await ctx.send(
                                embed=discord.Embed(
                                    color=self.color,
                                    description=f"your {'prefix is' if len(await self.get_prefixes(message)) == 1 else 'prefixes are'}: {prefixes}",
                                )
                            )

                    await self.process_commands(message)


async def getprefix(bot: Pretend, message: discord.Message) -> List[str]:
    """
    Return the actual prefixes for the bot
    """

    if message.guild:
        prefixes = list(map(lambda x: x, await bot.get_prefixes(message)))
        return commands.when_mentioned_or(*prefixes)(bot, message)


async def lean(self, ctx):
    """
    simply just preventing spam in both channel and user and proceeds w/o invocation , meaning silent u cooldown u jiggaboo -keron

    """
    command_is_on_cooldown = self.ccd(ctx.message) or self.mcd(ctx.message)
    if not command_is_on_cooldown:
        await super().before_invoke(ctx)


# THIS CODE SUCKS,
# LIM IS A CRAZY SKID 😭
