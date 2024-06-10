import asyncio
import datetime
from typing import Optional, Tuple

import arrow
from discord import Member, User
from discord.ext.commands import BadArgument, Converter, MemberConverter
from pydantic import BaseModel
from timezonefinder import TimezoneFinder

from ..bot import Pretend
from ..helpers import GreedContext


class BirthdaySchema(BaseModel):
    name: str
    date: str
    birthday: str


class TimezoneSchema(BaseModel):
    timezone: str
    date: str


class Timezone:
    def __init__(self, bot: Pretend):
        self.bot = bot

        self.week_days = {
            0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday",
            5: "Saturday",
            6: "Sunday",
        }

        self.months = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }

    async def get_lat_long(self, location: str) -> Optional[dict]:
        params = {"q": location, "format": "json"}

        results = await self.bot.session.get_json(
            "https://nominatim.openstreetmap.org/search", params=params
        )
        if len(results) == 0:
            return None

        return {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"])}

    async def get_timezone(self, member: Member) -> Optional[str]:
        timezone = await self.bot.db.fetchval(
            "SELECT zone FROM timezone WHERE user_id = $1", member.id
        )

        if not timezone:
            return None

        local = arrow.utcnow().to(timezone).naive
        hour = local.strftime("%I:%M %p")
        week_day = self.week_days.get(local.weekday())
        month = self.months.get(local.month)
        day = self.bot.ordinal(local.day)
        return f"{week_day} {month} {day} {hour}"

    async def set_timezone(self, member: Member, location: str) -> str:
        obj = TimezoneFinder()
        kwargs = await self.get_lat_long(location)

        if not kwargs:
            raise BadArgument("Wrong location given")

        timezone = await asyncio.to_thread(obj.timezone_at, **kwargs)
        local = arrow.utcnow().to(timezone).naive
        check = await self.bot.db.fetchrow(
            "SELECT * FROM timezone WHERE user_id = $1", member.id
        )

        if not check:
            await self.bot.db.execute(
                "INSERT INTO timezone VALUES ($1,$2)", member.id, timezone
            )
        else:
            await self.bot.db.execute(
                "UPDATE timezone SET zone = $1 WHERE user_id = $2", timezone, member.id
            )

        hour = local.strftime("%I:%M %p")
        week_day = self.week_days.get(local.weekday())
        month = self.months.get(local.month)
        day = self.bot.ordinal(local.day)

        payload = {"timezone": timezone, "date": f"{week_day} {month} {day} {hour}"}

        return TimezoneSchema(**payload)


class TimezoneMember(MemberConverter):
    async def convert(self, ctx: GreedContext, argument: str):
        if not argument:
            return None

        try:
            member = await super().convert(ctx, argument)
        except:
            raise BadArgument("Member not found")

        tz = Timezone(ctx.bot)
        result = await tz.get_timezone(member)

        if not result:
            raise BadArgument("Timezone **not** found for this member")

        return [member, result]


class TimezoneLocation(Converter):
    async def convert(self, ctx: GreedContext, argument: str):
        tz = Timezone(ctx.bot)
        return await tz.set_timezone(ctx.author, argument)


class BdayDate(Converter):
    async def convert(self, ctx: GreedContext, argument: str):
        bdays = argument.split()

        if len(bdays) < 2:
            raise BadArgument(
                "This is not a correct birthday format!\nPlease make sure you are following the example: `January 19`"
            )

        return await Birthday(ctx.bot).set_bday(ctx.author, bdays[0], bdays[1])


class BdayMember(MemberConverter):
    async def convert(self, ctx: GreedContext, argument: str):
        if argument is None:
            return None

        try:
            member = await super().convert(ctx, argument)
        except:
            raise BadArgument("Member **not** found")

        check = await ctx.bot.db.fetchrow(
            "SELECT * FROM bday WHERE user_id = $1", member.id
        )
        if not check:
            raise BadArgument(
                f"{f'**You** don' if member == ctx.author else f'**{member.name}** doesn'}'t have a **birthday** configured"
            )

        payload = {
            "name": member.name,
            "date": f"""on {Timezone(ctx.bot).months.get(check['month'])} {ctx.bot.ordinal(check['day'])}""",
            "birthday": await Birthday(ctx.bot).get_bday(member),
        }

        return BirthdaySchema(**payload)


class Birthday:
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.months = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }

    async def set_bday(self, member: Member, month: str, day: str) -> Tuple[str, str]:
        check = await self.bot.db.fetchrow(
            "SELECT * FROM bday WHERE user_id = $1", member.id
        )
        mon = self.months.get(month.lower())

        try:
            d = int(day)
        except ValueError:
            raise BadArgument(f"**{day}** is not a valid day number")

        if not mon:
            raise BadArgument(f"**{month}** is not a valid month")

        try:
            now = datetime.datetime.now()
            bday = datetime.datetime(now.year, self.months.get(month.lower()), int(day))
            print(str(bday.timestamp()))
        except ValueError:
            raise BadArgument("This is **not** a valid birthday date")

        args = [member.id, mon, d]

        if not check:
            await self.bot.db.execute("INSERT INTO bday VALUES ($1,$2,$3)", *args)
        else:
            await self.bot.db.execute(
                "UPDATE bday SET month = $2, day = $3 WHERE user_id = $1", *args
            )

        return (f"on {month} {self.bot.ordinal(day)}", await self.get_bday(member))

    async def get_bday(self, member: User) -> Optional[str]:
        """get a user's birthday"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM bday WHERE user_id = $1", member.id
        )

        if not check:
            return None

        now = datetime.datetime.now()
        bday = datetime.datetime(now.year, check["month"], check["day"])

        if bday.day == now.day and bday.month == now.month:
            return "today"

        if bday.timestamp() < now.timestamp():
            bday = datetime.datetime(now.year + 1, check["month"], check["day"])

        if (bday - now).total_seconds() < 3600 * 48:
            return "tomorrow"

        return self.bot.humanize_date(bday)
