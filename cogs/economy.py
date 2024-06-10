from random import choice, randint

import asyncpg
import discord
from discord import Embed
from discord.ext import commands


class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        with open("./texts/jobs.txt", "r") as file:
            self.jobs = file.read().splitlines()

    @commands.command(aliases=["bal"])
    async def balance(self, ctx):
        user_id = ctx.author.id
        balances = await self.bot.db.fetchrow(
            "SELECT balance, bank_balance FROM users WHERE user_id = $1", user_id
        )
        if balances:
            money_balance = balances["balance"]
            bank_balance = balances["bank_balance"]
            embed = discord.Embed(title=":bank: Balance", color=self.bot.color)
            embed.add_field(
                name="Wallet",
                value=f":money_with_wings: **{money_balance}**",
                inline=False,
            )
            embed.add_field(
                name="Bank", value=f":bank: **{bank_balance}**", inline=False
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send_success(
                "You don't have an account yet. Use `,register` to create one.",
                color=self.bot.color,
            )

    @commands.command()
    async def register(self, ctx):
        user_id = ctx.author.id
        username = ctx.author.display_name
        try:
            await self.bot.db.execute(
                "INSERT INTO users (user_id, username) VALUES ($1, $2)",
                user_id,
                username,
            )
            await self.bot.db.execute(
                "INSERT INTO members (user_id, guild_id) VALUES ($1, $2)",
                user_id,
                ctx.guild.id,
            )
            await ctx.send_success(
                "You have been registered successfully!", color=self.bot.color
            )
        except asyncpg.UniqueViolationError:
            await ctx.send_success("You are already registered.", color=self.bot.color)

    @commands.command()
    async def rob(self, ctx, target: discord.Member):
        user_id = ctx.author.id
        target_id = target.id

        target_balance = await self.bot.db.fetchval(
            "SELECT balance FROM users WHERE user_id = $1", target_id
        )
        if not target_balance:
            await ctx.send_warning("The target doesn't have an account.")
            return

        user_balance = await self.bot.db.fetchval(
            "SELECT balance FROM users WHERE user_id = $1", user_id
        )

        rob_percentage = randint(1, 10) / 100
        rob_amount = int(target_balance * rob_percentage)

        if rob_amount > 0 and rob_amount <= user_balance:
            await self.bot.db.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                rob_amount,
                user_id,
            )
            await self.bot.db.execute(
                "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
                rob_amount,
                target_id,
            )
            await ctx.send_success(
                f"You robbed :money_with_wings: **{rob_amount}** from {target.display_name}!"
            )
        else:
            await ctx.send_warning(f"You failed to rob {target.display_name}")

    @commands.command()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def work(self, ctx):
        user_id = ctx.author.id
        income = randint(125, 4000)
        job = choice(self.jobs)
        await self.bot.db.execute(
            "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
            income,
            user_id,
        )
        ctx.send_success(
            f"You worked as a **{job}** and earned **{income}** :money_with_wings:"
        )

    @commands.command(aliases=["dd"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def dumpsterdive(self, ctx):
        user_id = ctx.author.id
        income = randint(50, 200)
        job = choice(self.jobs)
        await self.bot.db.execute(
            "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
            income,
            user_id,
        )
        ctx.send_success(
            f"You decided to dumpster dive and found **{income}** :money_with_wings: nasty rat.."
        )

    @work.error
    async def work_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send_warning(
                f"You can work again in {error.retry_after:.0f} seconds."
            )

    @commands.command()
    async def deposit(self, ctx, amount: int):
        user_id = ctx.author.id
        if amount <= 0:
            await ctx.send_warning("Amount must be positive.")
            return

        await self.bot.db.execute(
            "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
            amount,
            user_id,
        )
        await self.bot.db.execute(
            "UPDATE users SET bank_balance = bank_balance + $1 WHERE user_id = $2",
            amount,
            user_id,
        )
        await ctx.send_success(
            f"Deposited :money_with_wings: **{amount}** into your bank account!"
        )

    @commands.command(aliases=["depall"])
    async def deposit_all(self, ctx):
        user_id = ctx.author.id

        balance = await self.bot.db.fetchval(
            "SELECT balance FROM users WHERE user_id = $1", user_id
        )

        if balance <= 0:
            await ctx.send_warning("You don't have any money to deposit.")
            return

        await self.bot.db.execute(
            "UPDATE users SET bank_balance = bank_balance + balance WHERE user_id = $1",
            user_id,
        )
        await self.bot.db.execute(
            "UPDATE users SET balance = 0 WHERE user_id = $1", user_id
        )
        await ctx.send_success(
            f"Deposited :money_with_wings: **{balance}** into your bank account!"
        )

    @commands.command()
    async def withdraw(self, ctx, amount: int):
        user_id = ctx.author.id
        bank_balance = await self.bot.db.fetchval(
            "SELECT bank_balance FROM users WHERE user_id = $1", user_id
        )
        if amount <= 0 or amount > bank_balance:
            await ctx.send_warning("Invalid amount or insufficient balance in bank.")
            return

        await self.bot.db.execute(
            "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
            amount,
            user_id,
        )
        await self.bot.db.execute(
            "UPDATE users SET bank_balance = bank_balance - $1 WHERE user_id = $2",
            amount,
            user_id,
        )
        await ctx.send_success(
            f"Withdrew :money_with_wings: **{amount}** from your bank account!"
        )

    @commands.command()
    async def wealthy(self, ctx):
        guild_id = ctx.guild.id
        rows = await self.bot.db.fetch(
            """
            SELECT username, (balance + bank_balance) AS total_balance 
            FROM users 
            WHERE EXISTS (
                SELECT 1 FROM members 
                WHERE users.user_id = members.user_id AND members.guild_id = $1
            ) 
            ORDER BY total_balance DESC 
            LIMIT 10
        """,
            guild_id,
        )

        if not rows:
            await ctx.send_warning("There are no users with balances in this guild.")
            return

        leaderboard_text = "\n".join(
            f"{index + 1}. **{row['username']}  ${row['total_balance']}**"
            for index, row in enumerate(rows)
        )
        embed = discord.Embed(
            title=f"Richest users in {ctx.guild.name}",
            description=leaderboard_text,
            color=self.bot.color,
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def close(self, ctx):
        user_id = ctx.author.id
        await self.bot.db.execute("DELETE FROM users WHERE user_id = $1", user_id)
        await self.bot.db.execute("DELETE FROM members WHERE user_id = $1", user_id)
        await ctx.send_success("Your account has been closed.")

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def gamble(self, ctx, amount: int):
        user_id = ctx.author.id
        user_balance = await self.bot.db.fetchval(
            "SELECT balance FROM users WHERE user_id = $1", user_id
        )

        if amount <= 0:
            await ctx.send_warning("Amount must be positive.")
            return

        if amount > user_balance:
            await ctx.send_warning("You don't have enough money to gamble.")
            return

        outcome = randint(0, 1)
        if outcome == 1:
            await self.bot.db.execute(
                "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
                amount,
                user_id,
            )
            await ctx.send_success(f"You won :money_with_wings: **{amount}**!")
        else:
            await self.bot.db.execute(
                "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
                amount,
                user_id,
            )
            await ctx.send_warning(f"You lost :money_with_wings: **{amount}**.")

    @commands.command()
    async def give(self, ctx, recipient: discord.Member, amount: int):
        if amount <= 0:
            await ctx.send_warning("Invalid amount.")
            return

        sender_id = ctx.author.id
        recipient_id = recipient.id

        sender_balance = await self.bot.db.fetchval(
            "SELECT balance FROM users WHERE user_id = $1", sender_id
        )
        if amount > sender_balance:
            await ctx.send_warning("You don't have enough balance to give.")
            return

        await self.bot.db.execute(
            "UPDATE users SET balance = balance - $1 WHERE user_id = $2",
            amount,
            sender_id,
        )
        await self.bot.db.execute(
            "UPDATE users SET balance = balance + $1 WHERE user_id = $2",
            amount,
            recipient_id,
        )
        await ctx.send_success(
            f"You gave :money_with_wings: **{amount}** to {recipient.display_name}."
        )


async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
