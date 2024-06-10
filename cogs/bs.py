import base64
import os

import discord
import requests
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def spic(self, ctx, image_url):
        try:
            # Download the image
            response = requests.get(image_url)
            response.raise_for_status()
            encoded_image = base64.b64encode(response.content).decode("utf-8")

            headers = {
                "Authorization": f"Bot {os.getenv('token')}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:102.0) Gecko/20100101 Firefox/102.0",
                "Content-Type": "application/json",
            }
            data = {"avatar": f"data:image/png;base64,{encoded_image}"}
            url = "https://discord.com/api/v9/users/@me"
            response = requests.patch(url, headers=headers, json=data)

            if response.status_code != 200:
                await ctx.send(f"An error occurred: {response.json()}")
                return

            await ctx.send("Success! Profile Picture Added!")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")


async def setup(bot):
    await bot.add_cog(Profile(bot))
