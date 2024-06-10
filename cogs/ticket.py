import asyncio
import datetime
import io
import os

from discord import (
    ButtonStyle,
    CategoryChannel,
    Embed,
    File,
    Interaction,
    Member,
    PermissionOverwrite,
    Role,
    SelectOption,
    TextChannel,
)
from discord.abc import GuildChannel
from discord.ext.commands import (
    Cog,
    bot_has_guild_permissions,
    group,
    has_guild_permissions,
)
from discord.ui import Button, Select, View

from tools.bot import Pretend
from tools.helpers import GreedContext
from tools.persistent.tickets import TicketTopic, TicketView
from tools.predicates import get_ticket, manage_ticket, ticket_exists
from tools.tickets import TicketAuthor


class Ticket(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.description = "Manage the ticket system in your server"

    async def cog_load(self):
        await self.bot.db.execute(
            """CREATE TABLE IF NOT EXISTS logs ( key TEXT NOT NULL, guild_id BIGINT NOT NULL, channel_id BIGINT NOT NULL, author JSONB NOT NULL DEFAULT '{}'::JSONB, logs JSONB NOT NULL DEFAULT '{}'::JSONB, PRIMARY KEY(key));"""
        )

    async def make_transcript(self, c: TextChannel):
        user_id = await self.bot.db.fetchval(
            """SELECT user_id FROM opened_tickets WHERE channel_id = $1""", c.id
        )
        user = self.bot.get_user(user_id)
        if not user:
            return None
        author = {
            "id": str(user.id),
            "name": user.name,
            "discriminator": user.discriminator,
            "avatar_url": str(user.display_avatar.url),
            "mod": False,
        }
        return await self.bot.tickets.upload(c, TicketAuthor(**author))

    @Cog.listener()
    async def on_guild_channel_delete(self, channel: GuildChannel):
        if str(channel.type) == "text":
            await self.bot.db.execute(
                "DELETE FROM opened_tickets WHERE guild_id = $1 AND channel_id = $2",
                channel.guild.id,
                channel.id,
            )

    @group(invoke_without_command=True)
    async def ticket(self, ctx):
        return await ctx.create_pages()

    @ticket.command(name="add", brief="ticket support / manage channels")
    @manage_ticket()
    @get_ticket()
    async def ticket_add(self, ctx: GreedContext, *, member: Member):
        """add a person to the ticket"""
        overwrites = PermissionOverwrite()
        overwrites.send_messages = True
        overwrites.view_channel = True
        overwrites.attach_files = True
        overwrites.embed_links = True
        await ctx.channel.set_permissions(
            member, overwrite=overwrites, reason="Added to the ticket"
        )
        return await ctx.send_success(f"Added {member.mention} to the ticket")

    @ticket.command(name="remove", brief="ticket support / manage channels")
    @manage_ticket()
    @get_ticket()
    async def ticket_remove(self, ctx: GreedContext, *, member: Member):
        """remove a member from the ticket"""
        overwrites = PermissionOverwrite()
        overwrites.send_messages = False
        overwrites.view_channel = False
        overwrites.attach_files = False
        overwrites.embed_links = False
        await ctx.channel.set_permissions(
            member, overwrite=overwrites, reason="Removed from the ticket"
        )
        return await ctx.send_success(f"Removed {member.mention} from the ticket")

    @ticket.command(name="close", brief="ticket support / manage channels")
    @manage_ticket()
    @get_ticket()
    async def ticket_close(self, ctx: GreedContext):
        """close the ticket"""
        check = await self.bot.db.fetchrow(
            "SELECT logs FROM tickets WHERE guild_id = $1", ctx.guild.id
        )
        if check:
            channel = ctx.guild.get_channel(check[0])
            if channel:
                file = await self.make_transcript(ctx.channel)
                e = Embed(
                    color=self.bot.color,
                    title=f"Logs for {ctx.channel.name} `{ctx.channel.id}`",
                    url=file,
                    description=f"Closed by **{ctx.author}**",
                    timestamp=datetime.datetime.now(),
                )
                await channel.send(embed=e)

        await ctx.send(content="Deleting this channel in 5 seconds")
        await asyncio.sleep(5)
        await ctx.channel.delete(reason="ticket closed")

    @ticket.command(name="reset", aliases=["disable"], brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @ticket_exists()
    async def ticket_reset(self, ctx: GreedContext):
        """disable the ticket module in the server"""
        for i in ["tickets", "ticket_topics", "opened_tickets"]:
            await self.bot.db.execute(
                f"DELETE FROM {i} WHERE guild_id = $1", ctx.guild.id
            )

        await ctx.send_success("Disabled the tickets module")

    @ticket.command(name="rename", brief="ticket support / manage channels")
    @manage_ticket()
    @get_ticket()
    @bot_has_guild_permissions(manage_channels=True)
    async def ticket_rename(self, ctx: GreedContext, *, name: str):
        """rename a ticket channel"""
        await ctx.channel.edit(
            name=name, reason=f"Ticket channel renamed by {ctx.author}"
        )
        await ctx.send_success(f"Renamed ticket channel to **{name}**")

    @ticket.command(name="support", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @ticket_exists()
    async def ticket_support(self, ctx: GreedContext, *, role: Role = None):
        """configure the ticket support role"""
        if role:
            await self.bot.db.execute(
                "UPDATE tickets SET support_id = $1 WHERE guild_id = $2",
                role.id,
                ctx.guild.id,
            )
            return await ctx.send_success(
                f"Updated ticket support role to {role.mention}"
            )
        else:
            await self.bot.db.execute(
                "UPDATE tickets SET support_id = $1 WHERE guild_id = $2",
                None,
                ctx.guild.id,
            )
            return await ctx.send_success("Removed the ticket support role")

    @ticket.command(name="category", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @ticket_exists()
    async def ticket_category(
        self, ctx: GreedContext, *, category: CategoryChannel = None
    ):
        """configure the category where the tickets should open"""
        if category:
            await self.bot.db.execute(
                "UPDATE tickets SET category_id = $1 WHERE guild_id = $2",
                category.id,
                ctx.guild.id,
            )
            return await ctx.send_success(
                f"Updated ticket category to {category.mention}"
            )
        else:
            await self.bot.db.execute(
                "UPDATE tickets SET category_id = $1 WHERE guild_id = $2",
                None,
                ctx.guild.id,
            )
            return await ctx.send_success("Removed the category channel")

    @ticket.command(name="logs", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @ticket_exists()
    async def ticket_logs(self, ctx: GreedContext, *, channel: TextChannel = None):
        """configure a channel for logging ticket transcripts"""
        if channel:
            await self.bot.db.execute(
                "UPDATE tickets SET logs = $1 WHERE guild_id = $2",
                channel.id,
                ctx.guild.id,
            )
            return await ctx.send_success(f"Updated logs channel to {channel.mention}")
        else:
            await self.bot.db.execute(
                "UPDATE tickets SET logs = $1 WHERE guild_id = $2", None, ctx.guild.id
            )
            return await ctx.send_success("Removed the logs channel")

    @ticket.command(name="opened", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @ticket_exists()
    async def ticket_opened(self, ctx: GreedContext, *, code: str = None):
        """set a message to be sent when a member opens a ticket"""
        await self.bot.db.execute(
            "UPDATE tickets SET open_embed = $1 WHERE guild_id = $2", code, ctx.guild.id
        )
        if code:
            return await ctx.send_success(
                f"Updated the ticket opening message to\n```{code}```"
            )
        else:
            return await ctx.send_success("Removed the custom ticket opening message")

    @ticket.command(brief="administrator")
    @has_guild_permissions(manage_guild=True)
    @ticket_exists()
    async def topics(self, ctx: GreedContext):
        """manage the ticket topics"""
        results = await self.bot.db.fetch(
            "SELECT * FROM ticket_topics WHERE guild_id = $1", ctx.guild.id
        )
        embed = Embed(color=self.bot.color, description=f"🔍 Choose a setting")
        button1 = Button(label="add topic", style=ButtonStyle.gray)
        button2 = Button(
            label="remove topic", style=ButtonStyle.red, disabled=len(results) == 0
        )

        async def interaction_check(interaction: Interaction):
            if interaction.user != ctx.author:
                await interaction.warn(
                    "You are **not** the author of this message", ephemeral=True
                )
            return interaction.user == ctx.author

        async def button1_callback(interaction: Interaction):
            return await interaction.response.send_modal(TicketTopic())

        async def button2_callback(interaction: Interaction):
            e = Embed(color=self.bot.color, description=f"🔍 Select a topic to delete")
            options = [
                SelectOption(label=result[1], description=result[2])
                for result in results
            ]

            select = Select(options=options, placeholder="select a topic...")

            async def select_callback(inter: Interaction):
                await self.bot.db.execute(
                    "DELETE FROM ticket_topics WHERE guild_id = $1 AND name = $2",
                    inter.guild.id,
                    select.values[0],
                )
                await inter.response.send_message(
                    f"Removed **{select.values[0]}** topic", ephemeral=True
                )

            select.callback = select_callback
            v = View()
            v.add_item(select)
            v.interaction_check = interaction_check
            return await interaction.response.edit_message(embed=e, view=v)

        button1.callback = button1_callback
        button2.callback = button2_callback
        view = View()
        view.add_item(button1)
        view.add_item(button2)
        view.interaction_check = interaction_check
        await ctx.reply(embed=embed, view=view)

    @ticket.command(name="config", aliases=["settings"])
    async def ticket_config(self, ctx: GreedContext):
        """check the server's ticket settings"""
        check = await self.bot.db.fetchrow(
            "SELECT * FROM tickets WHERE guild_id = $1", ctx.guild.id
        )

        if not check:
            return await ctx.send_error(
                "Ticket module is **not** enabled in this server"
            )

        results = await self.bot.db.fetch(
            "SELECT * FROM ticket_topics WHERE guild_id = $1", ctx.guild.id
        )

        support = f"<@&{check['support_id']}>" if check["support_id"] else "none"
        embed = Embed(
            color=self.bot.color,
            title="Ticket Settings",
            description=f"Support role: {support}",
        )
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon)
        embed.add_field(
            name="logs", value=f"<#{check['logs']}>" if check["logs"] else "none"
        )
        embed.add_field(
            name="category",
            value=f"<#{check['category_id']}>" if check["category_id"] else "none",
        )
        embed.add_field(name="topics", value=str(len(results)))
        embed.add_field(
            name="opening ticket embed", value=f"```\n{check['open_embed']}```"
        )
        await ctx.reply(embed=embed)

    @ticket.command(name="send", brief="manage server")
    @has_guild_permissions(manage_guild=True)
    @ticket_exists()
    async def ticket_send(
        self,
        ctx: GreedContext,
        channel: TextChannel,
        *,
        code: str = "{embed}{color: #181a14}$v{title: Create a ticket}$v{description: Click on the button below this message to create a ticket}$v{author: name: {guild.name} && icon: {guild.icon}}",
    ):
        """send the ticket panel to a channel"""
        x = await self.bot.embed_build.convert(ctx, code)
        view = TicketView(self.bot)
        view.create_ticket()
        x["view"] = view
        await channel.send(**x)
        return await ctx.send_success(f"Sent ticket panel in {channel.mention}")


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Ticket(bot))
