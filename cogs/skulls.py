import json
import os

import discord
from discord.ext import commands


class SkullCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = "/home/ubuntu/greedrecodetotallynotpretend/events/skulls.json"
        self.ensure_file_exists()

    def ensure_file_exists(self):
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w") as f:
                json.dump({"servers": {}}, f)

    async def log_servers(self):
        await self.bot.wait_until_ready()
        current_servers = {guild.id: {"skull_users": []} for guild in self.bot.guilds}
        data = {"servers": current_servers}
        self.save_data(data)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        data = self.load_data()
        guild_id = str(guild.id)
        if guild_id not in data["servers"]:
            data["servers"][guild_id] = {"skull_users": []}
            self.save_data(data)

    @commands.group()
    async def skull(self, ctx):
        if ctx.invoked_subcommand is None:
            embed = self.generate_skull_help_embed()
            await ctx.send(embed=embed)

    @skull.command()
    @commands.has_permissions(manage_messages=True)
    async def add(self, ctx, user: discord.User):
        if ctx.guild is None:
            return await ctx.send("This command can only be used in a server.")

        data = self.load_data()
        guild_id = str(ctx.guild.id)
        if guild_id not in data["servers"]:
            data["servers"][guild_id] = {"skull_users": []}

        if str(user.id) not in data["servers"][guild_id]["skull_users"]:
            data["servers"][guild_id]["skull_users"].append(str(user.id))
            self.save_data(data)
            await ctx.send(embed=self.generate_embed(user, added=True))
        else:
            await ctx.send(f"{user.name} is already in the skull list.")

    @skull.command()
    @commands.has_permissions(manage_messages=True)
    async def remove(self, ctx, user: discord.User):
        if ctx.guild is None:
            return await ctx.send("This command can only be used in a server.")

        data = self.load_data()
        guild_id = str(ctx.guild.id)
        if guild_id not in data["servers"]:
            return await ctx.send(
                "There are no users in the skull list for this server."
            )

        if str(user.id) in data["servers"][guild_id]["skull_users"]:
            data["servers"][guild_id]["skull_users"].remove(str(user.id))
            self.save_data(data)
            await ctx.send(embed=self.generate_embed(user, added=False))
        else:
            await ctx.send(f"{user.name} is not in the skull list for this server.")

    async def skull_message(self, message):
        if not message.guild:
            return

        data = self.load_data()
        guild_id = str(message.guild.id)
        if guild_id in data["servers"]:
            if str(message.author.id) in data["servers"][guild_id]["skull_users"]:
                await message.add_reaction("☠️")

    def generate_embed(self, user, added=True):
        action = "added to" if added else "removed from"
        embed = discord.Embed(
            title="skull update",
            description=f"<:check_white:1204583868435271731> skull reactions {action} {user.mention}'s messages.",
            color=self.bot.color if added else self.bot.color,
        )
        return embed

    def generate_skull_help_embed(self):
        embed = discord.Embed(
            title="Skull Command Help",
            description="Manage the skull list.",
            color=self.bot.color,
        )
        embed.add_field(
            name="Add User to Skull List", value="`skull add <@user>`", inline=False
        )
        embed.add_field(
            name="Remove User from Skull List",
            value="`skull remove <@user>`",
            inline=False,
        )
        return embed

    def load_data(self):
        with open(self.file_path, "r") as f:
            return json.load(f)

    def save_data(self, data):
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=4)

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild:
            return

        data = self.load_data()
        guild_id = str(message.guild.id)
        if guild_id in data["servers"]:
            if str(message.author.id) in data["servers"][guild_id]["skull_users"]:
                await message.add_reaction("☠️")


async def setup(bot):
    cog = SkullCog(bot)
    await bot.add_cog(cog)
    await cog.log_servers()
