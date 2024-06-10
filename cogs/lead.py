import sqlite3
from io import BytesIO

import discord
import requests
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database("/home/ubuntu/greedrecodetotallynotpretend/leaderboard.db")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        try:
            guild_id = str(message.guild.id)
            user_id = str(message.author.id)

            # Increment the message count for the user in the guild data
            self.db.increment_user_message_count(guild_id, user_id)

        except Exception as e:
            print(f"An error occurred while processing a message: {e}")

    @commands.command(aliases=["lb", "lead"])
    async def leaderboard(self, ctx):
        guild_id = str(ctx.guild.id)
        guild_data = self.db.get_guild_data(guild_id)

        if not guild_data:
            await ctx.send("No messages found for this guild.")
            return

        sorted_data = self.db.get_top_users(guild_id, 10)

        # Create a new image with a custom background
        background_path = "/home/ubuntu/greedrecodetotallynotpretend/images/black.jpg"
        try:
            background_img = Image.open(background_path).convert("RGBA")
        except FileNotFoundError:
            await ctx.send("Background image not found.")
            return

        # Resize background image to fit the leaderboard
        background_img = background_img.resize((1000, 1085))

        # Create a new image using the background image
        img = Image.new("RGBA", (1000, 1085), color=(0, 0, 0, 0))
        img.paste(background_img, (0, 0), background_img)

        draw = ImageDraw.Draw(img)

        # Load font
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font = ImageFont.truetype(font_path, size=24)

        # Draw leaderboard text
        y = 10
        for index, (user_id, message_count) in enumerate(sorted_data, start=1):
            if index > 10:  # Break loop if more than 10 users
                break
            member = ctx.guild.get_member(int(user_id))
            if member and member.avatar and member.display_name:
                # Get user's avatar
                avatar_url = member.avatar
                response = requests.get(avatar_url)
                avatar_img = Image.open(BytesIO(response.content))
                avatar_img = avatar_img.resize((100, 100))

                # Ensure the avatar image mode is RGBA for transparency
                if avatar_img.mode != "RGBA":
                    avatar_img = avatar_img.convert("RGBA")

                # Paste user's avatar
                img.paste(avatar_img, (10, y), avatar_img)

                # Draw user's display name and message count
                draw.text(
                    (120, y + 25),
                    f"{index}. {member.display_name}: {message_count} messages",
                    fill="white",
                    font=font,
                )

                y += 120

        # Save image
        img.save(
            "/home/ubuntu/greedrecodetotallynotpretend/images/leaderboard_image.png"
        )

        # Create and send embed
        embed = discord.Embed(
            description=f"> **{ctx.guild.name}'s** top 10 leaderboard",
            color=self.bot.color,
        )
        await ctx.send(
            embed=embed,
            file=discord.File(
                "/home/ubuntu/greedrecodetotallynotpretend/images/leaderboard_image.png"
            ),
        )


class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS guild_data (
                            guild_id TEXT PRIMARY KEY,
                            total_messages INTEGER
                          )""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS user_data (
                            guild_id TEXT,
                            user_id TEXT,
                            message_count INTEGER,
                            PRIMARY KEY (guild_id, user_id),
                            FOREIGN KEY (guild_id) REFERENCES guild_data(guild_id)
                          )""")
        self.conn.commit()

    def increment_user_message_count(self, guild_id, user_id):
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT OR IGNORE INTO guild_data (guild_id, total_messages)
                          VALUES (?, 0)""",
            (guild_id,),
        )
        cursor.execute(
            """INSERT OR IGNORE INTO user_data (guild_id, user_id, message_count)
                          VALUES (?, ?, 0)""",
            (guild_id, user_id),
        )
        cursor.execute(
            """UPDATE user_data SET message_count = message_count + 1
                          WHERE guild_id = ? AND user_id = ?""",
            (guild_id, user_id),
        )
        cursor.execute(
            """UPDATE guild_data SET total_messages = total_messages + 1
                          WHERE guild_id = ?""",
            (guild_id,),
        )
        self.conn.commit()

    def get_guild_data(self, guild_id):
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT total_messages FROM guild_data WHERE guild_id = ?""", (guild_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def get_top_users(self, guild_id, limit):
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT user_id, message_count FROM user_data
                          WHERE guild_id = ?
                          ORDER BY message_count DESC
                          LIMIT ?""",
            (guild_id, limit),
        )
        return cursor.fetchall()


async def setup(bot):
    await bot.add_cog(Leaderboard(bot))
