import uvloop

uvloop.install()

import discord
import uwuify

from tools.bot import Pretend
from tools.helpers import GreedContext

bot = Pretend()


@bot.check
async def restricted_command(ctx: GreedContext):
    if ctx.author.id == ctx.guild.owner.id:
        return True

    if check := await ctx.bot.db.fetch(
        """
    SELECT * FROM restrictcommand
    WHERE guild_id = $1
    AND command = $2
    """,
        ctx.guild.id,
        ctx.command.qualified_name,
    ):
        for row in check:
            role = ctx.guild.get_role(row["role_id"])
            if not role:
                await ctx.bot.db.execute(
                    """
          DELETE FROM restrictcommand
          WHERE role_id = $1
          """,
                    row["role_id"],
                )

            if not role in ctx.author.roles:
                await ctx.send_warning(f"You cannot use `{ctx.command.qualified_name}`")
                return False
            return True
    return True


@bot.check
async def disabled_command(ctx: GreedContext):
    if await ctx.bot.db.fetchrow(
        """
   SELECT * FROM disablecmd
   WHERE guild_id = $1
   AND cmd = $2
   """,
        ctx.guild.id,
        str(ctx.command),
    ):
        await ctx.send_error(
            f"The command **{str(ctx.command)}** is **disabled** in this server"
        )
        return False

    return True


@bot.tree.context_menu(name="avatar")
async def avatar_user(interaction: discord.Interaction, member: discord.Member):
    """
    Get a member's avatar
    """

    embed = discord.Embed(
        color=await interaction.client.dominant_color(member.display_avatar.url),
        title=f"{member.name}'s avatar",
        url=member.display_avatar.url,
    )

    embed.set_image(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.context_menu(name="banner")
async def banner_user(interaction: discord.Interaction, member: discord.Member):
    """
    Get a member's banner
    """

    member = await interaction.client.fetch_user(member.id)

    if not member.banner:
        return await interaction.warn(f"{member.mention} doesn't have a banner")

    banner = member.banner.url
    embed = discord.Embed(
        color=await interaction.client.dominant_color(banner),
        title=f"{member.name}'s banner",
        url=banner,
    )
    embed.set_image(url=member.banner.url)
    return await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    bot.run()
