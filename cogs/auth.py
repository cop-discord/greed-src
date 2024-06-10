import contextlib
import datetime
from typing import Union

import discord
from discord.ext import commands

from tools.helpers import GreedContext


class Auth(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.channel_id = 1225419595431805040

    async def add_subscriber(self, user: discord.User):
        """
        add the subscriber role to the subscriber
        """

        if member := self.bot.get_guild(1215100684978880512).get_member(user.id):
            if role := member.guild.get_role(1215866425898696734):
                await member.add_roles(role, reason="A new subscriber")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        if self.bot.is_ready():
            embed = (
                discord.Embed(
                    color=self.bot.color,
                    description=f"joined **{guild.name}** (`{guild.id}`)",
                )
                .add_field(name="owner", value=guild.owner)
                .add_field(name="member count", value=f"{guild.member_count} members")
            )
            await self.bot.get_channel(self.channel_id).send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        if self.bot.is_ready():
            embed = (
                discord.Embed(
                    color=self.bot.color,
                    description=f"left **{guild.name}** (`{guild.id}`)",
                )
                .add_field(name="owner", value=guild.owner)
                .add_field(name="member count", value=f"{guild.member_count} members")
            )
            await self.bot.get_channel(self.channel_id).send(embed=embed)

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def auth(self, ctx):
        """
        Auth group command
        """

        await ctx.create_pages()

    @auth.group(invoke_without_command=True, name="add")
    @commands.is_owner()
    async def auth_add(self, ctx: GreedContext):
        """
        Authorize a server
        """

        await ctx.create_pages()

    @auth_add.command(name="onetime")
    @commands.is_owner()
    async def auth_add_onetime(
        self,
        ctx: GreedContext,
        user: discord.User,
        invite: Union[discord.Invite, int],
    ):
        """
        Authorize a server (onetime subscription)
        """

        if isinstance(invite, discord.Invite):
            invite = invite.guild.id

        if await self.bot.db.fetchrow(
            "SELECT * FROM authorize WHERE guild_id = $1", invite
        ):
            return await ctx.reply("This guild is **already** authorized")

        await self.bot.db.execute(
            """
      INSERT INTO authorize
      VALUES ($1,$2,$3,$4)
      """,
            invite,
            user.id,
            None,
            2,
        )

        await self.add_subscriber(user)
        channel = self.bot.get_channel(1215101028492509234)

        embed = (
            discord.Embed(color=self.bot.color, title="onetime subscription added")
            .set_author(
                name=str(ctx.author),
                icon_url=ctx.author.display_avatar.url,
            )
            .add_field(name="type", value="onetime")
            .add_field(name="price", value="$6")
            .add_field(name="buyer", value=str(user))
            .set_footer(text=f"guild id: {invite}")
        )

        await channel.send(embed=embed)
        return await ctx.pretend_send(
            f"Authorized **{invite}**, requested by **{user}** (onetime)"
        )

    @auth_add.command(name="monthly")
    @commands.is_owner()
    async def auth_add_monthly(
        self,
        ctx: GreedContext,
        user: discord.User,
        invite: Union[discord.Invite, int],
    ):
        """
        Authorize a server (monthly subscription)
        """

        if isinstance(invite, discord.Invite):
            invite = invite.guild.id

        if await self.bot.db.fetchrow(
            "SELECT * FROM authorize WHERE guild_id = $1", invite
        ):
            return await ctx.reply("This guild is **already** authorized")

        next = datetime.datetime.now() + datetime.timedelta(days=30)
        await self.add_subscriber(user)
        await self.bot.db.execute(
            "INSERT INTO authorize VALUES ($1,$2,$3,$4)", invite, user.id, next, 2
        )
        channel = self.bot.get_channel(1215101028492509234)

        embed = (
            discord.Embed(color=self.bot.color, title="monthly subscription added")
            .set_author(
                name=str(ctx.author),
                icon_url=ctx.author.display_avatar.url,
            )
            .add_field(name="type", value="monthly")
            .add_field(name="price", value="$10")
            .add_field(name="buyer", value=str(user))
            .add_field(
                name="billing date", value=f"On {next.day}/{next.month}/{next.year}"
            )
            .set_footer(text=f"guild id: {invite}")
        )

        await channel.send(embed=embed)
        return await ctx.pretend_send(
            f"Authorized **{invite}**, requested by **{user}** (monthly)"
        )

    @auth.command(name="update")
    @commands.is_owner()
    async def auth_update(self, ctx: GreedContext, invite: Union[discord.Invite, int]):
        """
        Update the monthly authorization for a server
        """

        if isinstance(invite, discord.Invite):
            invite = invite.guild.id

        check = await self.bot.db.fetchrow(
            "SELECT * FROM authorize WHERE guild_id = $1 AND till IS NOT NULL", invite
        )

        if not check:
            return await ctx.reply(
                "THis guild is **not** authorized with a monthly offer"
            )

        old_datetime = check["till"]

        await self.bot.db.execute(
            """
    UPDATE authorize
    SET till = $1
    WHERE guild_id = $2
    """,
            (old_datetime + datetime.timedelta(days=30)),
            invite,
        )

        return await ctx.send_success(f"Updated monthly payment for **{invite}**")

    @auth.command(name="inspect")
    @commands.is_owner()
    async def auth_inspect(self, ctx: GreedContext, invite: Union[discord.Invite, int]):
        """
        check a guild authorization status
        """

        if isinstance(invite, discord.Invite):
            invite = invite.guild.id

        check = await self.bot.db.fetchrow(
            "SELECT * FROM authorize WHERE guild_id = $1", invite
        )

        if not check:
            return await ctx.reply("This guild id is **not** authorized")

        embed = (
            discord.Embed(
                color=self.bot.color,
                title="Authorization Plan",
                description=f"Subscription type: {'monthly' if check['till'] else 'onetime'}",
            )
            .set_author(name=invite)
            .add_field(name="Buyer", value=f"<@!{check['user_id']}>")
        )

        if check["till"]:
            embed.add_field(
                name="billing date",
                value=self.bot.humanize_date(
                    datetime.datetime.fromtimestamp(check["till"].timestamp())
                ),
            )
        else:
            embed.add_field(name="transfers", value=check["transfers"])

        return await ctx.send(embed=embed)

    @auth.command(name="transfer")
    @commands.is_owner()
    async def auth_transfer(
        self,
        ctx: GreedContext,
        old_inv: Union[discord.Invite, int],
        new_inv: Union[discord.Invite, int],
    ):
        """
        transfer a guild authorization to another guild
        """

        if isinstance(old_inv, discord.Invite):
            old_inv = old_inv.guild.id

        if isinstance(new_inv, discord.Invite):
            new_inv = new_inv.guild.id

        check = await self.bot.db.fetchrow(
            "SELECT * FROM authorize WHERE guild_id = $1", old_inv
        )

        if not check:
            return await ctx.reply("The first guild id is **not** authorized")

        transfers = check["transfers"]
        till = check["till"]
        if transfers == 0:
            return await ctx.send_error("This server has ran out of transfers :(")

        if not till:
            await self.bot.db.execute(
                """
      UPDATE authorize
      SET guild_id = $1, 
      transfers = $2
      WHERE guild_id = $3
      """,
                new_inv,
                transfers - 1,
                old_inv,
            )
        else:
            await self.bot.db.execute(
                """
      UPDATE authorize
      SET guild_id = $1
      WHERE guild_id = $2
      """,
                new_inv,
                old_inv,
            )

        if g := self.bot.get_guild(old_inv):
            await g.leave()

        return await ctx.pretend_send(
            f"Transfered from **{old_inv}** to **{new_inv}**. **{transfers-1}** transfers left!"
        )

    @auth.command(name="remove")
    @commands.is_owner()
    async def auth_remove(self, ctx: GreedContext, inv: Union[discord.Invite, int]):
        """
        Remove the authorization from a guild
        """

        if isinstance(inv, discord.Invite):
            inv = inv.guild.id

        check = await self.bot.db.fetchrow(
            "SELECT * FROM authorize WHERE guild_id = $1", inv
        )

        if not check:
            return await ctx.reply("This guild is **not** authorized")

        user = check["user_id"]
        await self.bot.db.execute("DELETE FROM authorize WHERE guild_id = $1", inv)
        if guild := self.bot.get_guild(inv):
            await guild.leave()

        val = await self.bot.db.fetchrow(
            "SELECT * FROM authorize WHERE user_id = $1", user
        )
        if not val:
            if support := self.bot.get_guild(1215100684978880512):
                if member := support.get_member(user):
                    if role := support.get_role(1215866425898696734):
                        await member.remove_roles(role)

        return await ctx.pretend_send(f"Unauthorized **{inv}**")

    @auth.command(name="list")
    @commands.is_owner()
    async def auth_list(self, ctx: GreedContext, *, user: discord.User):
        """
        returns a list of authorized servers by a certain user
        """

        results = await self.bot.db.fetch(
            "SELECT (guild_id) FROM authorize WHERE user_id = $1", user.id
        )

        if not results:
            return await ctx.send_warning(
                "There are no guilds authorized for this member"
            )

        await ctx.paginate(
            [
                f"{f'**{str(self.bot.get_guild(m[0]))}** `{m[0]}`' if self.bot.get_guild(m[0]) else f'`{m[0]}`'}"
                for m in results
            ],
            f"Authorized guilds ({len(results)})",
            {"name": user.name, "icon_url": user.display_avatar.url},
        )

    @commands.command()
    @commands.is_owner()
    @commands.has_permissions(manage_guild=True)
    async def leaveguild(self, ctx, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            await ctx.send("I'm not in that guild.")
            return
        try:
            await guild.leave()
            await ctx.send(f"Successfully left the guild with ID: {guild_id}.")
        except discord.Forbidden:
            await ctx.send("I don't have permission to leave that guild.")


async def setup(bot: commands.AutoShardedBot) -> None:
    await bot.add_cog(Auth(bot))
