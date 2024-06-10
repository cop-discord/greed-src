import discord
from discord import Embed, Guild, Interaction, Message, TextChannel, abc
from discord.ext.commands import (
    BadArgument,
    Cog,
    command,
    group,
    has_guild_permissions,
    has_permissions,
)

from tools.bot import Pretend
from tools.helpers import GreedContext
from tools.predicates import query_limit


class Events(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Event messages commands"
        self.log_channel_id = 1215101028492509234

    def set_log_channel(self, channel_id):
        self.log_channel_id = channel_id

    async def test_message(self, ctx: GreedContext, channel: TextChannel) -> Message:
        table = ctx.command.qualified_name.split(" ")[0]
        check = await self.bot.db.fetchrow(
            f"SELECT * FROM {table} WHERE channel_id = $1", channel.id
        )
        if not check:
            raise BadArgument(f"There is no {table} message in this channel")

        perms = channel.permissions_for(channel.guild.me)
        if not perms.send_messages or not perms.embed_links:
            raise BadArgument(
                f"I do not have permissions to send the {table} message in {channel.mention}"
            )

        x = await self.bot.embed_build.convert(ctx, check["message"])
        mes = await channel.send(**x)
        return await ctx.send_success(f"Sent the message {mes.jump_url}")

    @Cog.listener()
    async def on_command_completion(self, ctx):
        server = ctx.guild.name if ctx.guild else "Direct Message"
        user = ctx.author.name
        command = ctx.message.content
        print(f"Command '{command}' invoked by user '{user}' in server '{server}'")

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: abc.GuildChannel):
        if channel.type.name == "text":
            for q in ["welcome", "boost", "leave"]:
                await self.bot.db.execute(
                    f"DELETE FROM {q} WHERE channel_id = $1", channel.id
                )

    @group(invoke_without_command=True, aliases=["greet", "wlc", "welc"])
    async def welcome(self, ctx: GreedContext):
        return await ctx.create_pages()

    @welcome.command(name="add", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @query_limit("welcome")
    async def welcome_add(self, ctx: GreedContext, channel: TextChannel, *, code: str):
        """add a welcome message to the server"""
        args = (
            ["UPDATE welcome SET message = $1 WHERE channel_id = $2", code, channel.id]
            if await self.bot.db.fetchrow(
                "SELECT * FROM welcome WHERE channel_id = $1", channel.id
            )
            else [
                "INSERT INTO welcome VALUES ($1,$2,$3)",
                ctx.guild.id,
                channel.id,
                code,
            ]
        )
        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Added welcome message to {channel.mention}\n```{code}```"
        )

    @welcome.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def welcome_remove(self, ctx: GreedContext, *, channel: TextChannel):
        """remove a welcome message from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM welcome WHERE channel_id = $1", channel.id
        )
        if not check:
            return await ctx.send_warning(
                "There is no welcome message configured in this channel"
            )

        await self.bot.db.execute(
            "DELETE FROM welcome WHERE channel_id = $1", channel.id
        )
        return await ctx.send_success(
            f"Deleted the welcome message from {channel.mention}"
        )

    @welcome.command(name="config", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def welcome_config(self, ctx: GreedContext):
        """view any welcome message from any channel in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM welcome WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning(
                "There is no welcome message configured in this server"
            )

        embeds = [
            Embed(
                color=self.bot.color,
                title=f"#{ctx.guild.get_channel(result['channel_id'])}",
                description=f"```{result['message']}```",
            ).set_footer(text=f"{results.index(result)+1}/{len(results)}")
            for result in results
        ]

        await ctx.paginator(embeds)

    @welcome.command(name="test", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def welcome_test(self, ctx: GreedContext, *, channel: TextChannel):
        """test the welcome message in a channel"""
        await self.test_message(ctx, channel)

    @welcome.command(name="reset", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def welcome_reset(self, ctx: GreedContext):
        """
        Delete all the welcome messages
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM welcome
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if len(check) == 0:
            return await ctx.send_error(
                "You have **no** welcome messages in this server"
            )

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                """
        DELETE FROM welcome
        WHERE guild_id = $1
        """,
                interaction.guild.id,
            )

            embed = Embed(
                color=interaction.client.yes_color,
                description=f"{interaction.client.yes} {interaction.user.mention}: Deleted all welcome messages in this server",
            )

            await interaction.response.edit_message(embed=embed, view=None)

        async def no_callback(interaction: Interaction):
            embed = Embed(
                color=interaction.client.color, description=f"Action canceled..."
            )

            await interaction.response.edit_message(embed=embed, view=None)

        return await ctx.confirmation_send(
            "Are you sure you want to **RESET** all welcome messages in this server?",
            yes_callback,
            no_callback,
        )

    @group(invoke_without_command=True)
    async def leave(self, ctx: GreedContext):
        return await ctx.create_pages()

    @leave.command(name="add", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @query_limit("leave")
    async def leave_add(self, ctx: GreedContext, channel: TextChannel, *, code: str):
        """add a leave message to the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM leave WHERE channel_id = $1", channel.id
        )
        if check:
            args = [
                "UPDATE leave SET message = $1 WHERE channel_id = $2",
                code,
                channel.id,
            ]
        else:
            args = [
                "INSERT INTO leave VALUES ($1,$2,$3)",
                ctx.guild.id,
                channel.id,
                code,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Added leave message to {channel.mention}\n```{code}```"
        )

    @leave.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def leave_remove(self, ctx: GreedContext, *, channel: TextChannel):
        """remove a leave message from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM leave WHERE channel_id = $1", channel.id
        )
        if not check:
            return await ctx.send_warning(
                "There is no leave message configured in this channel"
            )

        await self.bot.db.execute("DELETE FROM leave WHERE channel_id = $1", channel.id)
        return await ctx.send_success(
            f"Deleted the leave message from {channel.mention}"
        )

    @leave.command(name="config", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def leave_config(self, ctx: GreedContext):
        """view any leave message from any channel in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM leave WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning(
                "There is no leave message configured in this server"
            )

        embeds = [
            Embed(
                color=self.bot.color,
                title=f"#{ctx.guild.get_channel(result['channel_id'])}",
                description=f"```{result['message']}```",
            ).set_footer(text=f"{results.index(result)+1}/{len(results)}")
            for result in results
        ]

        await ctx.paginator(embeds)

    @leave.command(name="test", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def leave_test(self, ctx: GreedContext, *, channel: TextChannel):
        """test the leave message in a channel"""
        await self.test_message(ctx, channel)

    @leave.command(name="reset", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def leave_reset(self, ctx: GreedContext):
        """
        Delete all the leave messages
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM leave
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if len(check) == 0:
            return await ctx.send_error("You have **no** leave messages in this server")

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                """
        DELETE FROM leave
        WHERE guild_id = $1
        """,
                interaction.guild.id,
            )

            embed = Embed(
                color=interaction.client.yes_color,
                description=f"{interaction.client.yes} {interaction.user.mention}: Deleted all leave messages in this server",
            )

            await interaction.response.edit_message(embed=embed, view=None)

        async def no_callback(interaction: Interaction):
            embed = Embed(
                color=interaction.client.color, description=f"Action canceled..."
            )

            await interaction.response.edit_message(embed=embed, view=None)

        return await ctx.confirmation_send(
            "Are you sure you want to **RESET** all leave messages in this server?",
            yes_callback,
            no_callback,
        )

    @group(
        invoke_without_command=True,
    )
    async def boost(self, ctx: GreedContext):
        return await ctx.create_pages()

    @boost.command(name="add", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    @query_limit("boost")
    async def boost_add(self, ctx: GreedContext, channel: TextChannel, *, code: str):
        """add a boost message to the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM boost WHERE channel_id = $1", channel.id
        )
        if check:
            args = [
                "UPDATE boost SET message = $1 WHERE channel_id = $2",
                code,
                channel.id,
            ]
        else:
            args = [
                "INSERT INTO boost VALUES ($1,$2,$3)",
                ctx.guild.id,
                channel.id,
                code,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Added boost message to {channel.mention}\n```{code}```"
        )

    @boost.command(name="remove", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def boost_remove(self, ctx: GreedContext, *, channel: TextChannel):
        """remove a boost message from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM boost WHERE channel_id = $1", channel.id
        )
        if not check:
            return await ctx.send_warning(
                "There is no boost message configured in this channel"
            )

        await self.bot.db.execute("DELETE FROM boost WHERE channel_id = $1", channel.id)
        return await ctx.send_success(
            f"Deleted the boost message from {channel.mention}"
        )

    @boost.command(name="config", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def boost_config(self, ctx: GreedContext):
        """view any boost message from any channel in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM boost WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning(
                "There is no boost message configured in this server"
            )

        embeds = [
            Embed(
                color=self.bot.color,
                title=f"#{ctx.guild.get_channel(result['channel_id'])}",
                description=f"```{result['message']}```",
            ).set_footer(text=f"{results.index(result)+1}/{len(results)}")
            for result in results
        ]

        await ctx.paginator(embeds)

    @boost.command(name="test", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def boost_test(self, ctx: GreedContext, *, channel: TextChannel):
        """test the boost message in a channel"""
        await self.test_message(ctx, channel)

    @boost.command(name="reset", brief="manage guild")
    @has_guild_permissions(manage_guild=True)
    async def boost_reset(self, ctx: GreedContext):
        """
        Delete all the boost messages
        """

        check = await self.bot.db.fetch(
            """
      SELECT * FROM boost
      WHERE guild_id = $1
      """,
            ctx.guild.id,
        )

        if len(check) == 0:
            return await ctx.send_error("You have **no** boost messages in this server")

        async def yes_callback(interaction: Interaction):
            await interaction.client.db.execute(
                """
        DELETE FROM boost
        WHERE guild_id = $1
        """,
                interaction.guild.id,
            )

            embed = Embed(
                color=interaction.client.yes_color,
                description=f"{interaction.client.yes} {interaction.user.mention}: Deleted all boost messages in this server",
            )

            await interaction.response.edit_message(embed=embed, view=None)

        async def no_callback(interaction: Interaction):
            embed = Embed(
                color=interaction.client.color, description=f"Action canceled..."
            )

            await interaction.response.edit_message(embed=embed, view=None)

        return await ctx.confirmation_send(
            "Are you sure you want to **RESET** all boost messages in this server?",
            yes_callback,
            no_callback,
        )

    @group(name="autoping", aliases=["poj", "pingonjoin"], invoke_without_command=True)
    @has_permissions(manage_guild=True)
    async def autoping(self, ctx: GreedContext):
        return await ctx.create_pages()

    @autoping.command(name="add", brief="manage guild")
    @has_permissions(manage_guild=True)
    @query_limit("autoping")
    async def autoping_add(self, ctx: GreedContext, channel: TextChannel, *, code: str):
        """add a ping message to the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoping WHERE channel_id = $1", channel.id
        )
        if check:
            args = [
                "UPDATE autoping SET message = $1 WHERE channel_id = $2",
                code,
                channel.id,
            ]
        else:
            args = [
                "INSERT INTO autoping VALUES ($1,$2,$3)",
                ctx.guild.id,
                channel.id,
                code,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Added ping message to {channel.mention}\n```{code}```"
        )

    @autoping.command(name="remove", brief="manage guild")
    @has_permissions(manage_guild=True)
    async def autoping_remove(self, ctx: GreedContext, *, channel: TextChannel):
        """remove a ping message from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM autoping WHERE channel_id = $1", channel.id
        )
        if not check:
            return await ctx.send_warning(
                "There is no ping message configured in this channel"
            )

        await self.bot.db.execute(
            "DELETE FROM autoping WHERE channel_id = $1", channel.id
        )
        return await ctx.send_success(
            f"Deleted the ping message from {channel.mention}"
        )

    @autoping.command(name="config", brief="manage guild", aliases=["list", "l"])
    @has_permissions(manage_guild=True)
    async def autoping_config(self, ctx: GreedContext):
        """view any ping message from any channel in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM autoping WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning(
                "There is no ping message configured in this server"
            )

        embeds = [
            Embed(
                color=self.bot.color,
                title=f"#{ctx.guild.get_channel(result['channel_id'])}",
                description=f"```{result['message']}```",
            ).set_footer(text=f"{results.index(result)+1}/{len(results)}")
            for result in results
        ]

        await ctx.paginator(embeds)

    @group(
        name="stickymessage",
        aliases=["stickymsg", "sticky"],
        invoke_without_command=True,
    )
    async def stickymessage(self, ctx: GreedContext):
        return await ctx.create_pages()

    @stickymessage.command(name="add", brief="manage guild")
    @has_permissions(manage_guild=True)
    @query_limit("stickymessage")
    async def stickymessage_add(
        self, ctx: GreedContext, channel: TextChannel, *, code: str
    ):
        """add a sticky message to the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM stickymessage WHERE channel_id = $1", channel.id
        )
        if check:
            args = [
                "UPDATE stickymessage SET message = $1 WHERE channel_id = $2",
                code,
                channel.id,
            ]
        else:
            args = [
                "INSERT INTO stickymessage VALUES ($1,$2,$3)",
                ctx.guild.id,
                channel.id,
                code,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(
            f"Added sticky message to {channel.mention}\n```{code}```"
        )

    @stickymessage.command(name="remove", brief="manage guild")
    @has_permissions(manage_guild=True)
    async def stickymessage_remove(self, ctx: GreedContext, *, channel: TextChannel):
        """remove a sticky message from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM stickymessage WHERE channel_id = $1", channel.id
        )
        if not check:
            return await ctx.send_warning(
                "There is no sticky message configured in this channel"
            )

        await self.bot.db.execute(
            "DELETE FROM stickymessage WHERE channel_id = $1", channel.id
        )
        return await ctx.send_success(
            f"Deleted the sticky message from {channel.mention}"
        )

    @stickymessage.command(name="config", brief="manage guild", aliases=["list", "l"])
    @has_permissions(manage_guild=True)
    async def stickymessage_config(self, ctx: GreedContext):
        """view any sticky message from any channel in the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM stickymessage WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning(
                "There is no sticky message configured in this server"
            )

        embeds = [
            Embed(
                color=self.bot.color,
                title=f"#{ctx.guild.get_channel(result['channel_id'])}",
                description=f"```{result['message']}```",
            ).set_footer(text=f"{results.index(result)+1}/{len(results)}")
            for result in results
        ]

        await ctx.paginator(embeds)

    @group(name="joindm", invoke_without_command=True)
    @has_permissions(manage_guild=True)
    async def joindm(self, ctx: GreedContext):
        return await ctx.create_pages()

    @joindm.command(name="set", brief="manage guild")
    @has_permissions(manage_guild=True)
    @query_limit("joindm")
    async def joindm_set(self, ctx: GreedContext, *, code: str):
        """set the join dm message for the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM joindm WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            args = [
                "UPDATE joindm SET message = $1 WHERE guild_id = $2",
                code,
                ctx.guild.id,
            ]
        else:
            args = [
                "INSERT INTO joindm VALUES ($1,$2)",
                ctx.guild.id,
                code,
            ]

        await self.bot.db.execute(*args)
        return await ctx.send_success(f"Set the join dm message to\n```{code}```")

    @joindm.command(name="remove", brief="manage guild")
    @has_permissions(manage_guild=True)
    async def joindm_remove(self, ctx: GreedContext):
        """remove the join dm message from the server"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM joindm WHERE guild_id = $1", ctx.guild.id
        )
        if not check:
            return await ctx.send_warning(
                "There is no join dm message configured in this server"
            )

        await self.bot.db.execute(
            "DELETE FROM joindm WHERE guild_id = $1", ctx.guild.id
        )
        return await ctx.send_success(f"Deleted the join dm message from this server")

    @joindm.command(name="config", brief="manage guild", aliases=["list", "l"])
    @has_permissions(manage_guild=True)
    async def joindm_config(self, ctx: GreedContext):
        """view the join dm message from the server"""
        results = await self.bot.db.fetch(
            "SELECT * FROM joindm WHERE guild_id = $1", ctx.guild.id
        )
        if not results:
            return await ctx.send_warning(
                "There is no join dm message configured in this server"
            )

        embeds = [
            Embed(
                color=self.bot.color,
                description=f"```{result['message']}```",
            ).set_footer(text=f"{results.index(result)+1}/{len(results)}")
            for result in results
        ]

        await ctx.paginator(embeds)


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Events(bot))
