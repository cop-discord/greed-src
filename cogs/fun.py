import asyncio
import datetime
import json as orjson
import random
from typing import List, Union

import discord
import humanize
from aiogtts import aiogTTS
from discord import (
    AllowedMentions,
    ButtonStyle,
    Embed,
    File,
    Interaction,
    Member,
    Message,
    TextChannel,
    User,
)
from discord.ext.commands import (
    Author,
    BadArgument,
    BucketType,
    Cog,
    CommandOnCooldown,
    command,
    cooldown,
    group,
    hybrid_command,
    hybrid_group,
)
from discord.ui import Button, View, button

from tools.caption import Caption
from tools.converters import AbleToMarry
from tools.helpers import GreedContext
from tools.misc.views import MarryView
from tools.quote import Quotes


class TicTacToeButton(Button["TicTacToe"]):
    def __init__(self, x: int, y: int, player1: Member, player2: Member):
        super().__init__(style=ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x
        self.y = y
        self.player1 = player1
        self.player2 = player2

    async def callback(self, interaction: Interaction):
        assert self.view is not None
        view: TicTacToe = self.view
        state = view.board[self.y][self.x]
        if state in (view.X, view.O):
            return

        if view.current_player == view.X:
            if interaction.user != self.player1:
                return await interaction.response.send_message(
                    "You cannot interact with this button", ephemeral=True
                )
            self.style = ButtonStyle.danger
            self.label = "X"
            self.disabled = True
            view.board[self.y][self.x] = view.X
            view.current_player = view.O
            content = f"{self.player1} ⚔️ {self.player2}\n\nIt's **{self.player2.name}**'s turn"
        else:
            if interaction.user != self.player2:
                return await interaction.response.send_message(
                    "You cannot interact with this button", ephemeral=True
                )

            self.style = ButtonStyle.success
            self.label = "O"
            self.disabled = True
            view.board[self.y][self.x] = view.O
            view.current_player = view.X
            content = f"{self.player1} ⚔️ {self.player2}\n\nIt's **{self.player1.name}'s** turn"

        winner = view.check_board_winner()
        if winner is not None:
            if winner == view.X:
                content = f"**{self.player1.name}** won!"

                check = await interaction.client.db.fetchrow(
                    """
                SELECT * FROM gamestats
                WHERE user_id = $1
                AND game = $2
                """,
                    self.player1.id,
                    "tictactoe",
                )

                if not check:
                    await interaction.client.db.execute(
                        """
                INSERT INTO gamestats
                VALUES ($1,$2,$3,$4,$5)
                """,
                        self.player1.id,
                        "tictactoe",
                        1,
                        0,
                        1,
                    )
                else:
                    await interaction.client.db.execute(
                        """
                  UPDATE gamestats
                  SET wins = $1,
                  total = $2
                  WHERE user_id = $3
                  AND game = $4
                  """,
                        check["wins"] + 1,
                        check["total"] + 1,
                        self.player1.id,
                        "tictactoe",
                    )

                check2 = await interaction.client.db.fetchrow(
                    """
                SELECT * FROM gamestats 
                WHERE user_id = $1 
                AND game = $2
                """,
                    self.player2.id,
                    "tictactoe",
                )
                if not check2:
                    await interaction.client.db.execute(
                        """
                  INSERT INTO gamestats
                  VALUES ($1,$2,$3,$4,$5)
                  """,
                        self.player2.id,
                        "tictactoe",
                        0,
                        1,
                        1,
                    )
                else:
                    await interaction.client.db.execute(
                        """
                  UPDATE gamestats 
                  SET loses = $1,
                  total = $2
                  WHERE user_id = $3
                  AND game = $4
                  """,
                        check2["loses"] + 1,
                        check2["total"] + 1,
                        self.player2.id,
                        "tictactoe",
                    )

            elif winner == view.O:
                content = f"**{self.player2.name}** won!"

                check = await interaction.client.db.fetchrow(
                    """
                SELECT * FROM gamestats
                WHERE user_id = $1
                AND game = $2
                """,
                    self.player1.id,
                    "tictactoe",
                )
                if not check:
                    await interaction.client.db.execute(
                        """
                INSERT INTO gamestats 
                VALUES ($1,$2,$3,$4,$5)
                """,
                        self.player2.id,
                        "tictactoe",
                        1,
                        0,
                        1,
                    )
                else:
                    await interaction.client.db.execute(
                        """
                  UPDATE gamestats
                  SET wins = $1,
                  total = $2
                  WHERE user_id = $3
                  AND game = $4
                  """,
                        check["wins"] + 1,
                        check["total"] + 1,
                        self.player2.id,
                        "tictactoe",
                    )

                check2 = await interaction.client.db.fetchrow(
                    """
                SELECT * FROM gamestats 
                WHERE user_id = $1
                AND game = $2
                """,
                    self.player1.id,
                    "tictactoe",
                )
                if not check2:
                    await interaction.client.db.execute(
                        """
                  INSERT INTO gamestats
                  VALUES ($1,$2,$3,$4,$5)
                  """,
                        self.player1.id,
                        "tictactoe",
                        0,
                        1,
                        1,
                    )
                else:
                    await interaction.client.db.execute(
                        """
                  UPDATE gamestats 
                  SET loses = $1,
                  total = $2
                  WHERE user_id = $3
                  AND game = $4
                  """,
                        check2["loses"] + 1,
                        check2["total"] + 1,
                        self.player1.id,
                        "tictactoe",
                    )

            else:
                content = "It's a tie!"
                for i in [self.player1.id, self.player2.id]:
                    check = await interaction.client.db.fetchrow(
                        """
                    SELECT * FROM gamestats 
                    WHERE user_id = $1
                    AND game = $2
                    """,
                        i,
                        "tictactoe",
                    )
                    if not check:
                        await interaction.client.db.execute(
                            """
                      INSERT INTO gamestats
                      VALUES ($1,$2,$3,$4,$5)
                      """,
                            i,
                            "tictactoe",
                            0,
                            0,
                            1,
                        )
                    else:
                        await interaction.client.db.execute(
                            """
                      UPDATE gamestats 
                      SET total = $1
                      WHERE user_id = $2
                      AND game = $3
                      """,
                            check["total"] + 1,
                            i,
                            "tictactoe",
                        )

            for child in view.children:
                child.disabled = True

            view.stop()

        await interaction.response.edit_message(content=content, view=view)


class TicTacToe(View):
    children: List[TicTacToeButton]
    X = -1
    O = 1
    Tie = 2

    def __init__(self, player1: Member, player2: Member):
        super().__init__()
        self.current_player = self.X
        self.board = [
            [0, 0, 0],
            [0, 0, 0],
            [0, 0, 0],
        ]

        for x in range(3):
            for y in range(3):
                self.add_item(TicTacToeButton(x, y, player1, player2))

    def check_board_winner(self):
        for across in self.board:
            value = sum(across)
            if value == 3:
                return self.O
            elif value == -3:
                return self.X

        for line in range(3):
            value = self.board[0][line] + self.board[1][line] + self.board[2][line]
            if value == 3:
                return self.O
            elif value == -3:
                return self.X

        diag = self.board[0][2] + self.board[1][1] + self.board[2][0]
        if diag == 3:
            return self.O
        elif diag == -3:
            return self.X

        diag = self.board[0][0] + self.board[1][1] + self.board[2][2]
        if diag == 3:
            return self.O
        elif diag == -3:
            return self.X

        if all(i != 0 for row in self.board for i in row):
            return self.Tie

        return None


class RockPaperScissors(View):
    def __init__(self, ctx: GreedContext):
        self.ctx = ctx
        self.get_emoji = {"rock": "🪨", "paper": "📰", "scissors": "✂️"}
        self.status = False
        super().__init__(timeout=10)

    async def disable_buttons(self):
        await self.message.edit(view=None)

    async def interaction_check(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.warn("This is **not** your game")
        return interaction.user.id == self.ctx.author.id

    async def action(self, interaction: Interaction, selection: str):
        botselection = random.choice(["rock", "paper, scissors"])

        def getwinner():
            if botselection == "rock" and selection == "scissors":
                return interaction.client.user.id
            elif botselection == "rock" and selection == "paper":
                return interaction.user.id
            elif botselection == "paper" and selection == "rock":
                return interaction.client.user.id
            elif botselection == "paper" and selection == "scissors":
                return interaction.user.id
            elif botselection == "scissors" and selection == "rock":
                return interaction.user.id
            elif botselection == "scissors" and selection == "paper":
                return interaction.client.user.id
            else:
                return "tie"

        if getwinner() == "tie":
            check = await interaction.client.db.fetchrow(
                """
        SELECT * FROM gamestats 
        WHERE user_id = $1
        AND game = $2
        """,
                interaction.user.id,
                "rockpaperscissors",
            )
            if not check:
                await interaction.client.db.execute(
                    """
          INSERT INTO gamestats 
          VALUES ($1,$2,$3,$4,$5)
          """,
                    interaction.user.id,
                    "rockpaperscissors",
                    0,
                    0,
                    1,
                )
            else:
                await interaction.client.db.execute(
                    """
          UPDATE gamestats 
          SET total = $1
          WHERE user_id = $2
          AND game = $3
          """,
                    check["total"] + 1,
                    interaction.user.id,
                    "rockpaperscissors",
                )

            await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color,
                    title="Tie!",
                    description=f"You both picked {self.get_emoji.get(selection)}",
                )
            )
        elif getwinner() == interaction.user.id:
            check = await interaction.client.db.fetchrow(
                """
        SELECT * FROM gamestats 
        WHERE user_id = $1
        AND game = $2
        """,
                interaction.user.id,
                "rockpaperscissors",
            )
            if not check:
                await interaction.client.db.execute(
                    """
          INSERT INTO gamestats 
          VALUES ($1,$2,$3,$4,$5)
          """,
                    interaction.user.id,
                    "rockpaperscissors",
                    1,
                    0,
                    1,
                )
            else:
                await interaction.client.db.execute(
                    """
          UPDATE gamestats
          SET wins = $1, 
          total = $2
          WHERE user_id = $3
          AND game = $4
          """,
                    check["wins"] + 1,
                    check["total"] + 1,
                    interaction.user.id,
                    "rockpaperscissors",
                )

            await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color,
                    title="You won!",
                    description=f"You picked {self.get_emoji.get(selection)} and the bot picked {self.get_emoji.get(botselection)}",
                )
            )
        else:
            check = await interaction.client.db.fetchrow(
                """
        SELECT * FROM gamestats
        WHERE user_id = $1 
        AND game = $2
        """,
                interaction.user.id,
                "rockpaperscissors",
            )
            if not check:
                await interaction.client.db.execute(
                    """
          INSERT INTO gamestats 
          VALUES ($1,$2,$3,$4,$5)
          """,
                    interaction.user.id,
                    "rockpaperscissors",
                    0,
                    1,
                    1,
                )
            else:
                await interaction.client.db.execute(
                    """
          UPDATE gamestats 
          SET loses = $1, 
          total = $2 
          WHERE user_id = $3 
          AND game = $4
          """,
                    check["loses"] + 1,
                    check["total"] + 1,
                    interaction.user.id,
                    "rockpaperscissors",
                )

            await interaction.response.edit_message(
                embed=Embed(
                    color=interaction.client.color,
                    title="Bot won!",
                    description=f"You picked {self.get_emoji.get(selection)} and the bot picked {self.get_emoji.get(botselection)}",
                )
            )

        await self.disable_buttons()
        self.status = True

    @button(emoji="🪨")
    async def rock(self, interaction: Interaction, button: Button):
        return await self.action(interaction, "rock")

    @button(emoji="📰")
    async def paper(self, interaction: Interaction, button: Button):
        return await self.action(interaction, "paper")

    @button(emoji="✂️")
    async def scissors(self, interaction: Interaction, button: Button):
        return await self.action(interaction, "scissors")

    async def on_timeout(self):
        if self.status == False:
            await self.disable_buttons()


class BlackTea:
    def __init__(self, bot):
        self.bot = bot
        self.color = 0xA5D287
        self.emoji = "🍵"
        self.MatchStart = []
        self.lifes = {}

        self.players = {}

    def get_string(self):
        words = self.get_words()
        word = random.choice([l for l in words if len(l) > 3])
        return word[:3]

    async def send_embed(self, channel: TextChannel, content: str):
        return await channel.send(embed=Embed(color=self.color, description=content))

    async def lost_a_life(self, member: int, reason: str, channel: TextChannel):
        lifes = self.lifes[f"{channel.guild.id}"].get(f"{member}")
        self.lifes[f"{channel.guild.id}"][f"{member}"] = lifes + 1

        if reason == "timeout":
            await self.send_embed(
                channel,
                f"⏰ <@{member}> time is up! **{3-int(self.lifes[f'{channel.guild.id}'][f'{member}'])}** lifes left..",
            )

        elif reason == "wrong":
            await self.send_embed(
                channel,
                f"💥 <@{member}> wrong answer! **{3-int(self.lifes[f'{channel.guild.id}'][f'{member}'])}** lifes left..",
            )

        if self.lifes[f"{channel.guild.id}"][f"{member}"] == 3:
            await self.send_embed(channel, f"☠️ <@{member}> you're eliminated")
            check = await self.bot.db.fetchrow(
                "SELECT * FROM gamestats WHERE user_id = $1 AND game = $2",
                member,
                "blacktea",
            )

            if not check:
                await self.bot.db.execute(
                    "INSERT INTO gamestats VALUES ($1,$2,$3,$4,$5)",
                    member,
                    "blacktea",
                    0,
                    1,
                    1,
                )
            else:
                await self.bot.db.execute(
                    """
          UPDATE gamestats 
          SET loses = $1,
          total = $2
          WHERE user_id = $3
          AND game = $4
          """,
                    check["loses"] + 1,
                    check["total"] + 1,
                    member,
                    "blacktea",
                )

            del self.lifes[f"{channel.guild.id}"][f"{member}"]
            self.players[f"{channel.guild.id}"].remove(member)
            await self.add_loser(member)

    def match_started(self, guild_id: int):
        if guild_id in self.MatchStart:
            raise BadArgument("A Black Tea match is **already** in progress")
        else:
            self.MatchStart.append(guild_id)

    def get_words(self):
        data = open("./texts/wordlist.txt", encoding="utf-8")
        return [d for d in data.read().splitlines()]

    def clear_all(self):
        self.MatchStart = []
        self.lifes = {}
        self.players = {}

    def remove_stuff(self, guild_id: int):
        del self.players[f"{guild_id}"]
        del self.lifes[f"{guild_id}"]
        self.bot.tea.MatchStart.remove(guild_id)

    async def add_loser(self, player: int):
        check = await self.bot.db.fetchrow(
            "SELECT * FROM gamestats WHERE user_id = $1 AND game = $2",
            player,
            "blacktea",
        )
        if not check:
            return await self.bot.db.execute(
                "INSERT INTO gamestats VALUES ($1,$2,$3,$4,$5)",
                player,
                "blacktea",
                0,
                1,
                1,
            )
        else:
            return await self.bot.db.execute(
                """
        UPDATE gamestats 
        SET loses = $1, 
        total = $2 
        WHERE user_id = $3 
        AND game = $4
        """,
                check["loses"] + 1,
                check["total"] + 1,
                player,
                "blacktea",
            )

    async def add_winner(self, player: int):
        check = await self.bot.db.fetchrow(
            "SELECT * FROM gamestats WHERE user_id = $1 AND game = $2",
            player,
            "blacktea",
        )
        if not check:
            return await self.bot.db.execute(
                "INSERT INTO gamestats VALUES ($1,$2,$3,$4,$5)",
                player,
                "blacktea",
                1,
                0,
                1,
            )
        else:
            return await self.bot.db.execute(
                """
        UPDATE gamestats 
        SET wins = $1, 
        total = $2 
        WHERE user_id = $3 
        AND game = $4
        """,
                check["wins"] + 1,
                check["total"] + 1,
                player,
                "blacktea",
            )


class Fun(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.wedding = "💒"
        self.quoting = Quotes(self.bot)
        self.marry_color = 0xFF819F
        self.description = "Fun commands"

    @command(name="quote")
    async def quote(self, ctx: GreedContext, message: discord.Message = None):
        return await self.quoting.get_caption(ctx, message)

    async def stats_execute(self, ctx: GreedContext, member: User) -> Message:
        """
        Execute any of the stats commands
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM gamestats WHERE game = $1 AND user_id = $2",
            ctx.command.name,
            member.id,
        )

        if not check:
            return await ctx.send_error("There are no stats recorded for this member")

        embed = Embed(
            color=self.bot.color,
            title=f"Stats for {ctx.command.name}",
            description=f"**Wins:** {check['wins']}\n**Loses:** {check['loses']}\n**Matches:** {check['total']}",
        ).set_author(name=member.name, icon_url=member.display_avatar.url)

        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def quran(self, ctx: GreedContext):
        """
        Get a random quran verse
        """

        result = await self.bot.session.get_json(
            "https://api.alquran.cloud/v1/surah/40/en.sahih"
        )
        name = f"{result['data']['name']} ({result['data']['englishName']})"
        number = result["data"]["number"]
        ayah = random.choice(result["data"]["ayahs"])
        numberInSurah = ayah["numberInSurah"]
        text = ayah["text"]

        embed = Embed(
            color=self.bot.color, description=f"**{number}:{numberInSurah}** {text}"
        ).set_author(name=name)

        return await ctx.send(embed=embed)

    @hybrid_command()
    async def bible(self, ctx: GreedContext):
        """
        Get a random bible verse
        """

        params = {"format": "json", "order": "random"}

        result = await self.bot.session.get_json(
            "https://beta.ourmanna.com/api/v1/get", params=params
        )
        embed = Embed(
            color=self.bot.color, description=result["verse"]["details"]["text"]
        )
        embed.set_author(name=result["verse"]["details"]["reference"])
        await ctx.send(embed=embed)

    @hybrid_command(aliases=["bt"])
    async def blacktea(self, ctx: GreedContext):
        """
        Play blacktea with the server members
        """

        self.bot.tea.match_started(ctx.guild.id)
        embed = Embed(color=self.bot.tea.color, title="BlackTea Matchmaking")
        embed.set_thumbnail(
            url="https://cdn.discordapp.com/attachments/1117819522372616352/1118203618978451596/emoji.png"
        )
        embed.add_field(
            name="guide",
            value=f"- React with {self.bot.tea.emoji} to join the round\n- You have 20 seconds to join\n- The game starts only if there are at least 2 joined players\n- Everyone has 3 lives\n- Think about a word that starts with the specific letters given",
        )
        message = await ctx.send(embed=embed)
        await message.add_reaction(self.bot.tea.emoji)
        await asyncio.sleep(20)

        try:
            message = await ctx.channel.fetch_message(message.id)
        except:
            self.bot.tea.MatchStart.remove(ctx.guild.id)
            return await ctx.send("The blacktea message was deleted")

        users = [
            u.id async for u in message.reactions[0].users() if u.id != self.bot.user.id
        ]

        if len(users) < 2:
            self.bot.tea.MatchStart.remove(ctx.guild.id)
            return await ctx.send(
                "<:1_sadcowboy:1204920871253442691> not enough players to start the blacktea match"
            )

        words = self.bot.tea.get_words()
        self.bot.tea.players.update({f"{ctx.guild.id}": users})
        self.bot.tea.lifes.update({f"{ctx.guild.id}": {f"{user}": 3 for user in users}})

        while len(self.bot.tea.players[f"{ctx.guild.id}"]) > 1:
            for user in users:
                rand = self.bot.tea.get_string()
                await self.bot.tea.send_embed(
                    ctx.channel,
                    f"{self.bot.tea.emoji} <@{user}>: Say a word containing **{rand}** in **10 seconds**",
                )
                try:
                    user_message = await self.bot.wait_for(
                        "message",
                        check=lambda m: m.channel.id == ctx.channel.id
                        and m.author.id == user,
                        timeout=10,
                    )
                    if rand in user_message.content and user_message.content in words:
                        await self.bot.tea.send_embed(
                            ctx.channel,
                            f"<a:happy:1204923041386078268> <@{user}> Correct answer!",
                        )
                    else:
                        self.bot.tea.lifes[f"{ctx.guild.id}"][f"{user}"] -= 1
                        if self.bot.tea.lifes[f"{ctx.guild.id}"][f"{user}"] == 0:
                            self.bot.tea.players[f"{ctx.guild.id}"].remove(user)
                        await self.bot.tea.send_embed(
                            ctx.channel,
                            f"<:1_sadcowboy:1204920871253442691> <@{user}> Wrong answer! You have {self.bot.tea.lifes[f'{ctx.guild.id}'][f'{user}']} lives left.",
                        )
                except asyncio.TimeoutError:
                    self.bot.tea.lifes[f"{ctx.guild.id}"][f"{user}"] -= 1
                    if self.bot.tea.lifes[f"{ctx.guild.id}"][f"{user}"] == 0:
                        self.bot.tea.players[f"{ctx.guild.id}"].remove(user)
                    await self.bot.tea.send_embed(
                        ctx.channel,
                        f"<:1_sadcowboy:1204920871253442691> <@{user}> Time's up! You have {self.bot.tea.lifes[f'{ctx.guild.id}'][f'{user}']} lives left.",
                    )

        winner = self.bot.tea.players[f"{ctx.guild.id}"][0]
        await self.bot.tea.send_embed(
            ctx.channel,
            f"👑 <@{winner}> Won the game!!",
        )

        check = await self.bot.db.fetchrow(
            "SELECT * FROM gamestats WHERE user_id = $1 AND game = $2",
            winner,
            "blacktea",
        )

        if not check:
            await self.bot.db.execute(
                "INSERT INTO gamestats VALUES ($1,$2,$3,$4,$5)",
                winner,
                "blacktea",
                1,
                0,
                1,
            )
        else:
            await self.bot.db.execute(
                """
                UPDATE gamestats SET wins = $1, 
                total = $2 
                WHERE user_id = $3 
                AND game = $4
                """,
                check["wins"] + 1,
                check["total"] + 1,
                winner,
                "blacktea",
            )

        self.bot.tea.remove_stuff(ctx.guild.id)

    @command(name="caption", description="create a caption on an image")
    async def caption(
        self,
        ctx: GreedContext,
        url_or_member: Union[discord.Member, str],
        *,
        text: str,
    ):
        if isinstance(url_or_member, discord.Member):
            url = url_or_member.display_avatar.url
        else:
            url = url_or_member
        caption_image = await Caption("impact.ttf").create_captioned_image(url, text)
        await ctx.send(file=discord.File(caption_image, filename="caption.png"))

    @hybrid_group(
        invoke_without_command=True,
        description="check a member's stats for a certain game",
    )
    async def stats(self, ctx: GreedContext):
        """
        check a member's stats for a certain game
        """

        await ctx.create_pages()

    @stats.command(name="tictactoe", aliases=["ttt"])
    async def stats_ttt(self, ctx: GreedContext, *, member: User = Author):
        """
        View a member's stats for tictactoe
        """

        await self.stats_execute(ctx, member)

    @stats.command(name="blacktea")
    async def stats_blacktea(self, ctx: GreedContext, *, member: User = Author):
        """
        View a member's stats for blacktea
        """

        await self.stats_execute(ctx, member)

    @stats.command(name="rockpaperscissors", aliases=["rps"])
    async def stats_rps(self, ctx: GreedContext, *, member: User = Author):
        """
        View a member's stats for rockpaperscissors
        """

        await self.stats_execute(ctx, member)

    @command()
    async def pack(self, ctx: GreedContext, *, member: Member):
        """
        Pack a member
        """

        if member == ctx.author:
            return await ctx.reply("Why do you want to pack yourself ://")

        result = await self.bot.session.get_json(
            "https://evilinsult.com/generate_insult.php?lang=en&type=json"
        )
        await ctx.send(
            f"{member.mention} {result['insult']}",
            allowed_mentions=AllowedMentions.none(),
        )

    @hybrid_command(name="8ball")
    async def eightball(self, ctx: GreedContext, *, question: str):
        """
        Ask the 8ball a question
        """

        await ctx.reply(
            f"question: {question}{'?' if not question.endswith('?') else ''}\n{random.choice(['yes', 'no', 'never', 'most likely', 'absolutely', 'absolutely not', 'of course not'])}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @hybrid_command()
    async def bird(self, ctx: GreedContext):
        """
        Send a random bird image
        """

        data = await self.bot.session.get_json("https://api.alexflipnote.dev/birb")
        await ctx.reply(
            file=File(fp=await self.bot.getbyte(data["file"]), filename="bird.png")
        )

    @hybrid_command()
    async def dog(self, ctx: GreedContext):
        """
        Send a random dog image
        """

        data = await self.bot.session.get_json("https://random.dog/woof.json")
        await ctx.reply(
            file=File(
                fp=await self.bot.getbyte(data["url"]),
                filename=f"dog{data['url'][-4:]}",
            )
        )

    @hybrid_command()
    async def cat(self, ctx: GreedContext):
        """
        Send a random cat image
        """

        data = (
            await self.bot.session.get_json(
                "https://api.thecatapi.com/v1/images/search"
            )
        )[0]
        await ctx.reply(
            file=File(fp=await self.bot.getbyte(data["url"]), filename="cat.png")
        )

    @hybrid_command()
    async def capybara(self, ctx: GreedContext):
        """
        Send a random capybara image
        """

        data = await self.bot.session.get_json(
            "https://api.capy.lol/v1/capybara?json=true"
        )
        await ctx.reply(
            file=File(
                fp=await self.bot.getbyte(data["data"]["url"]), filename="cat.png"
            )
        )

    @hybrid_command(aliases=["fact", "uf"])
    async def uselessfact(self, ctx: GreedContext):
        """
        Returns an useless fact
        """

        data = (
            await self.bot.session.get_json(
                "https://uselessfacts.jsph.pl/random.json?language=en"
            )
        )["text"]
        await ctx.reply(data)

    @hybrid_command(aliases=["rps"])
    async def rockpaperscisssors(self, ctx: GreedContext):
        """
        Play rockpapaerscissors
        """

        view = RockPaperScissors(ctx)
        embed = Embed(
            color=self.bot.color,
            title="Rock Paper Scissors!",
            description="Click a button to play!",
        )
        view.message = await ctx.reply(embed=embed, view=view)

    @command(name="choose")
    async def choose_cmd(self, ctx: GreedContext, *, choices: str):
        """
        Choose between options
        """

        choices1 = choices.split(", ")
        if len(choices1) == 1:
            return await ctx.reply("please put a `,` between your choices")

        final = random.choice(choices1)
        await ctx.reply(final)

    @command(name="quickpoll", aliases=["poll"])
    async def quickpoll_cmd(self, ctx: GreedContext, *, question: str):
        """
        Create a poll
        """

        message = await ctx.reply(
            embed=Embed(color=self.bot.color, description=question).set_author(
                name=f"{ctx.author} asked"
            )
        )

        for m in ["👍", "👎"]:
            await message.add_reaction(m)

    @hybrid_command()
    async def ship(self, ctx, member: Member):
        """
        Check the ship rate between you and a member
        """

        return await ctx.reply(
            f"**{ctx.author.name}** 💞 **{member.name}** = **{random.randrange(101)}%**"
        )

    @hybrid_command()
    async def advice(self, ctx: GreedContext):
        """
        Get a random advice
        """

        data = orjson.loads(
            await self.bot.session.get_text("https://api.adviceslip.com/advice")
        )
        return await ctx.reply(data["slip"]["advice"])

    @hybrid_command(name="tictactoe", aliases=["ttt"])
    async def tictactoe(self, ctx: GreedContext, *, member: Member):
        """
        Play tictactoe with a member
        """

        if member.id == ctx.author.id:
            return await ctx.send_warning("You cannot play against yourself")

        if member.bot:
            return await ctx.send_warning("You cannot play against a bot")

        view = TicTacToe(ctx.author, member)
        view.message = await ctx.send(
            content=f"{ctx.author} ⚔️ {member}\n\nIt's {ctx.author.name}'s turn",
            view=view,
        )

    @command(
        name="bitches",
        description="Show's your bitch rate",
        aliases=["bitchrate"],
        usage="bitchrate [user]",
    )
    async def bitches(self, ctx: GreedContext, *, user: discord.Member = Author):
        choices = ["regular", "still regular", "lol", "xd", "id", "zero", "infinite"]
        if random.choice(choices) == "infinite":
            result = "∞"
        elif random.choice(choices) == "zero":
            result = "0"
        else:
            result = random.randint(0, 100)
        await ctx.reply(f"{user.mention} has `{result}` bitches")

    @command(
        name="eject",
        description="Eject specified user",
        aliases=["imposter"],
        usage="eject [user]",
    )
    async def eject(self, ctx, user: discord.Member = None):
        user = ctx.author if not user else user

        impostor = ["true", "false"]

        crewmate = [
            "black",
            "blue",
            "brown",
            "cyan",
            "darkgreen",
            "lime",
            "orange",
            "pink",
            "purple",
            "red",
            "white",
            "yellow",
        ]

        await ctx.reply(
            f"https://vacefron.nl/api/ejected?name={user.name}&impostor={random.choice(impostor)}&crewmate={random.choice(crewmate)}"
        )

    @command(aliases=["tts"])
    async def textospeech(self, ctx: GreedContext, *, message: str):
        """
        Convert your message into audio
        """

        await aiogTTS().save(message, "tts.mp3", "en")
        await ctx.reply(file=File(r"tts.mp3"))

    @command()
    async def gay(self, ctx: GreedContext, *, member: Member = Author):
        """
        Gay rate a member
        """

        embed = Embed(
            color=self.bot.color,
            description=f"{member.mention} is **{random.randint(0, 100)}%** gay 🏳️‍🌈",
        )
        return await ctx.send(embed=embed)

    @command()
    async def pp(self, ctx: GreedContext, *, member: Member = Author):
        """
        Check someone's pp size
        """

        lol = "================================"
        embed = Embed(
            color=self.bot.color,
            description=f"{member.name}'s penis\n\n8{lol[random.randint(1, 20):]}D",
        )
        await ctx.reply(embed=embed)

    @hybrid_command()
    async def kiss(self, ctx: GreedContext, *, member: Member):
        """
        Kiss a member
        """

        lol = await self.bot.session.get_json(
            "https://api.otakugifs.xyz/gif?reaction=kiss"
        )
        embed = Embed(
            color=self.bot.color,
            description=f"*Aww how cute!* **{ctx.author.name}** kissed **{member.name}**",
        )
        embed.set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def cuddle(self, ctx: GreedContext, *, member: Member):
        """
        Cuddle a member
        """

        lol = await self.bot.session.get_json(
            "https://api.otakugifs.xyz/gif?reaction=cuddle"
        )
        embed = Embed(
            color=self.bot.color,
            description=f"*Aww how cute!* **{ctx.author.name}** cuddles **{member.name}**",
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def hug(self, ctx: GreedContext, *, member: Member):
        """
        Hug a member
        """

        lol = await self.bot.session.get_json(
            f"https://api.otakugifs.xyz/gif?reaction=hug"
        )
        embed = Embed(
            color=self.bot.color,
            description=f"*Aww how cute!* **{ctx.author.name}** hugged **{member.name}**",
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def pat(self, ctx: GreedContext, *, member: Member):
        """
        Pat a member
        """

        lol = await self.bot.session.get_json(
            f"https://api.otakugifs.xyz/gif?reaction=pat"
        )
        embed = Embed(
            color=self.bot.color,
            description=f"*Aww how cute!* **{ctx.author.name}** pats **{member.name}**",
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def slap(self, ctx: GreedContext, *, member: Member):
        """
        Slap a member
        """

        lol = await self.bot.session.get_json(
            f"https://api.otakugifs.xyz/gif?reaction=slap"
        )
        embed = Embed(
            color=self.bot.color,
            description=f"**{ctx.author.name}** slaps **{member.name}***",
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def laugh(self, ctx: GreedContext):
        """
        Start laughing
        """

        lol = await self.bot.session.get_json(
            f"https://api.otakugifs.xyz/gif?reaction=laugh"
        )
        embed = Embed(
            color=self.bot.color, description=f"**{ctx.author.name}** laughs"
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def cry(self, ctx: GreedContext):
        """
        Start crying
        """

        lol = await self.bot.session.get_json(
            f"https://api.otakugifs.xyz/gif?reaction=cry"
        )
        embed = Embed(
            color=self.bot.color, description=f"**{ctx.author.name}** cries"
        ).set_image(url=lol["url"])
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def marry(self, ctx: GreedContext, *, member: AbleToMarry):
        """
        Marry a member
        """

        embed = Embed(
            color=self.marry_color,
            description=f"{self.wedding} {ctx.author.mention} wants to marry you. do you accept?",
        )
        view = MarryView(ctx, member)
        view.message = await ctx.reply(content=member.mention, embed=embed, view=view)

    @hybrid_command()
    async def marriage(self, ctx: GreedContext, *, member: User = Author):
        """
        View an user's marriage
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM marry WHERE $1 IN (author, soulmate)", member.id
        )
        if check is None:
            return await ctx.send_error(
                f"{'You are' if member == ctx.author else f'{member.mention} is'} not **married**"
            )

        embed = Embed(
            color=self.marry_color,
            description=f"{self.wedding} {f'{member.mention} is' if member != ctx.author else 'You are'} currently married to <@!{check[1] if check[1] != member.id else check[0]}> since **{self.bot.humanize_date(datetime.datetime.fromtimestamp(int(check['time'])))}**",
        )
        return await ctx.reply(embed=embed)

    @hybrid_command()
    async def divorce(self, ctx: GreedContext):
        """
        Divorce from your partner
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM marry WHERE $1 IN (author, soulmate)", ctx.author.id
        )
        if check is None:
            return await ctx.send_error("**You** are not **married**")

        async def button1_callback(interaction: Interaction) -> None:
            member = await self.bot.fetch_user(
                check["author"]
                if check["author"] != interaction.user.id
                else check["soulmate"]
            )
            await interaction.client.db.execute(
                "DELETE FROM marry WHERE $1 IN (author, soulmate)", interaction.user.id
            )
            embe = Embed(
                color=interaction.client.color,
                description=f"**{interaction.user.name}** divorced with their partner",
            )

            try:
                await member.send(
                    f"💔 It seems like your partner **{interaction.user}** decided to divorce :(. Your relationship with them lasted **{humanize.precisedelta(datetime.datetime.fromtimestamp(int(check['time'])), format=f'%0.0f')}**"
                )
            except:
                pass

            await interaction.response.edit_message(content=None, embed=embe, view=None)

        async def button2_callback(interaction: Interaction) -> None:
            embe = Embed(
                color=interaction.client.color,
                description=f"**{interaction.user.name}** you changed your mind",
            )
            await interaction.response.edit_message(content=None, embed=embe, view=None)

        await ctx.confirmation_send(
            f"{ctx.author.mention} are you sure you want to divorce?",
            button1_callback,
            button2_callback,
        )

    @hybrid_group(name="vape", aliases=["juul"])
    @cooldown(1, 30, BucketType.member)
    async def vape(self, ctx: GreedContext):
        """
        vape
        """

        await ctx.invoke(self.bot.get_command("juul hit"))

    @vape.command(name="hit", aliases=["smoke"])
    @cooldown(1, 30, BucketType.member)
    async def vape_hit(self, ctx: GreedContext):
        """
        hit the vape
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM vape WHERE guild_id = $1", ctx.guild.id
        )

        if (
            check
            and check["user_id"] != ctx.author.id
            and ctx.guild.get_member(check["user_id"])
        ):
            return await ctx.send_warning(
                "You don't have the **vape**! "
                f"Steal it from {ctx.guild.get_member(check['user_id']).mention}"
            )

        loading_msg = await ctx.pretend_send(f"Hitting the **vape**...")

        if check:
            await self.bot.db.execute(
                "UPDATE vape SET hits = hits + 1 WHERE guild_id = $1", ctx.guild.id
            )
        else:
            await self.bot.db.execute(
                "INSERT INTO vape VALUES ($1, $2, $3)", ctx.guild.id, ctx.author.id, 1
            )

        res = await self.bot.db.fetchrow(
            "SELECT * FROM vape WHERE guild_id = $1", ctx.guild.id
        )

        embed = discord.Embed(
            description=f"{self.bot.yes} {ctx.author.mention}: Hit the **vape**! The server now has `{res['hits']}` hits",
            color=self.bot.yes_color,
        )

        await asyncio.sleep(random.randint(1, 4))
        await loading_msg.edit(embed=embed)

    @vape.command(name="steal", aliases=["take"])
    @cooldown(1, 30, BucketType.guild)
    async def vape_steal(self, ctx: GreedContext):
        """
        steal the vape from a member
        """

        check = await self.bot.db.fetchrow(
            "SELECT * FROM vape WHERE guild_id = $1", ctx.guild.id
        )

        if check["user_id"] == ctx.author.id:
            return await ctx.send_warning("You already have the **vape**!")

        await self.bot.db.execute(
            "UPDATE vape SET user_id = $1 WHERE guild_id = $2",
            ctx.author.id,
            ctx.guild.id,
        )

        if ctx.guild.get_member(check["user_id"]):
            await ctx.send_success(
                f"Stole the **vape** from {ctx.guild.get_member(check['user_id']).mention}"
            )
        else:
            await ctx.send_success(f"Found the **vape** somewhere and took it")

    @vape.command(name="hits")
    async def vape_hits(self, ctx: GreedContext):
        """
        view the amount of hits in the server
        """

        result = await self.bot.db.fetchrow(
            "SELECT * FROM vape WHERE guild_id = $1", ctx.guild.id
        )

        await ctx.pretend_send(f"This server has `{result['hits']}` **vape hits**")

    @vape.error
    async def vape_cooldown(self, ctx: GreedContext, error: Exception):
        if isinstance(error, CommandOnCooldown):
            return await ctx.pretend_send(
                f"Please wait **{error.retry_after:.2f} seconds** before vaping again!"
            )

    @vape_steal.error
    async def vape_cooldown(self, ctx: GreedContext, error: Exception):
        if isinstance(error, CommandOnCooldown):
            return await ctx.pretend_send(
                f"Please wait **{error.retry_after:.2f} seconds** before vaping again!"
            )

    @vape_hit.error
    async def vape_hit_cooldown(self, ctx: GreedContext, error: Exception):
        if isinstance(error, CommandOnCooldown):
            return await ctx.pretend_send(
                f"Please wait **{error.retry_after:.2f} seconds** before vaping again!"
            )


async def setup(bot) -> None:
    await bot.add_cog(Fun(bot))
