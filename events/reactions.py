import datetime
import io

import discord
from discord.ext import commands
from discord.ext.commands import BucketType, Cog, CooldownMapping

from tools.bot import Pretend


class Reactions(Cog):
    def __init__(self, bot: Pretend):
        self.bot = bot
        self.cooldown = CooldownMapping.from_cooldown(4, 6, BucketType.user)

    def is_rate_limited(self, message: discord.Message):
        bucket = self.cooldown.get_bucket(message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            return retry_after
        return None

    # reaction roles
    @Cog.listener("on_raw_reaction_add")
    async def on_reactionrole_add(self, payload: discord.RawReactionActionEvent):
        retry_after = self.is_rate_limited(payload)
        if retry_after:
            await asyncio.sleep(2)

        m = self.bot.get_guild(payload.guild_id).get_member(payload.user_id)
        if not m:
            return
        if m.bot:
            return

        check = await self.bot.db.fetchrow(
            "SELECT role_id FROM reactionrole WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji = $4",
            payload.guild_id,
            payload.channel_id,
            payload.message_id,
            str(payload.emoji),
        )
        if check:
            role = self.bot.get_guild(payload.guild_id).get_role(check[0])
            if role:
                if role.is_assignable():
                    if (
                        not role
                        in self.bot.get_guild(payload.guild_id)
                        .get_member(payload.user_id)
                        .roles
                    ):
                        await (
                            self.bot.get_guild(payload.guild_id)
                            .get_member(payload.user_id)
                            .add_roles(role, reason="Reaction Role")
                        )

    @Cog.listener("on_raw_reaction_remove")
    async def on_reactionrole_remove(self, payload: discord.RawReactionActionEvent):
        retry_after = self.is_rate_limited(payload)
        if retry_after:
            await asyncio.sleep(2)

        m = self.bot.get_guild(payload.guild_id).get_member(payload.user_id)
        if not m:
            return
        if m.bot:
            return

        check = await self.bot.db.fetchrow(
            "SELECT role_id FROM reactionrole WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3 AND emoji = $4",
            payload.guild_id,
            payload.channel_id,
            payload.message_id,
            str(payload.emoji),
        )
        if check:
            role = self.bot.get_guild(payload.guild_id).get_role(check[0])
            if role:
                if role.is_assignable():
                    if (
                        role
                        in self.bot.get_guild(payload.guild_id)
                        .get_member(payload.user_id)
                        .roles
                    ):
                        await (
                            self.bot.get_guild(payload.guild_id)
                            .get_member(payload.user_id)
                            .remove_roles(role, reason="Reaction Role")
                        )

    # starboard
    @Cog.listener("on_raw_reaction_remove")
    async def on_starboard_remove(self, payload: discord.RawReactionActionEvent):
        retry_after = self.is_rate_limited(payload)
        if retry_after:
            await asyncio.sleep(2)

        res = await self.bot.db.fetchrow(
            "SELECT * FROM starboard WHERE guild_id = $1", payload.guild_id
        )
        if res:
            if not res["emoji"]:
                return
            if str(payload.emoji) == res["emoji"]:
                mes = await self.bot.get_channel(payload.channel_id).fetch_message(
                    payload.message_id
                )
                reactions = [
                    r.count for r in mes.reactions if str(r.emoji) == res["emoji"]
                ]
                if len(reactions) > 0:
                    reaction = reactions[0]
                    if not res["channel_id"]:
                        return
                    channel = self.bot.get_channel(res["channel_id"])
                    if channel:
                        check = await self.bot.db.fetchrow(
                            "SELECT * FROM starboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                            payload.guild_id,
                            payload.channel_id,
                            payload.message_id,
                        )
                        if check:
                            try:
                                m = await channel.fetch_message(
                                    check["starboard_message_id"]
                                )
                                await m.edit(
                                    content=f"{payload.emoji} **#{reaction}** {mes.channel.mention}"
                                )
                            except:
                                await self.bot.db.execute(
                                    "DELETE FROM starboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                                    payload.guild_id,
                                    payload.channel_id,
                                    payload.message_id,
                                )

    @Cog.listener("on_raw_reaction_add")
    async def on_starboard_add(self, payload: discord.RawReactionActionEvent):
        retry_after = self.is_rate_limited(payload)
        if retry_after:
            await asyncio.sleep(2)

        res = await self.bot.db.fetchrow(
            "SELECT * FROM starboard WHERE guild_id = $1", payload.guild_id
        )
        if not res:
            return

        if str(payload.emoji) != res.get("emoji"):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return

        reactions = [r.count for r in message.reactions if str(r.emoji) == res["emoji"]]
        if not reactions or reactions[0] < res.get("count", 0):
            return

        starboard_channel = guild.get_channel(res["channel_id"])
        if not starboard_channel or payload.channel_id == starboard_channel.id:
            return

        check = await self.bot.db.fetchrow(
            "SELECT * FROM starboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
            payload.guild_id,
            payload.channel_id,
            payload.message_id,
        )

        embed = discord.Embed(
            color=self.bot.color,
            description=message.content,
            timestamp=message.created_at,
        )
        embed.set_author(
            name=str(message.author), icon_url=message.author.display_avatar.url
        )

        file = None
        if message.attachments:
            attachment = message.attachments[0]
            if attachment.filename.endswith(("png", "jpeg", "jpg")):
                embed.set_image(url=attachment.proxy_url)
            elif attachment.filename.endswith(("mp3", "mp4", "mov")):
                async with self.bot.session.get(attachment.url) as resp:
                    if resp.status == 200:
                        data = io.BytesIO(await resp.read())
                        file = discord.File(data, filename=attachment.filename)

        if message.embeds:
            original_embed = message.embeds[0]
            embed.title = original_embed.title
            embed.url = original_embed.url
            embed.description = original_embed.description or message.content
            embed.color = original_embed.color

            if original_embed.author:
                embed.set_author(
                    name=original_embed.author.name,
                    icon_url=original_embed.author.icon_url,
                    url=original_embed.author.url,
                )
            if original_embed.thumbnail:
                embed.set_thumbnail(url=original_embed.thumbnail.url)
            if original_embed.image:
                embed.set_image(url=original_embed.image.url)
            if original_embed.footer:
                embed.set_footer(
                    text=original_embed.footer.text,
                    icon_url=original_embed.footer.icon_url,
                )

        if message.reference:
            embed.description = f"{embed.description}\n[Replying to {message.reference.resolved.author}]({message.reference.resolved.jump_url})"

        if not check:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Message", url=message.jump_url))

            perms = starboard_channel.permissions_for(guild.me)
            if perms.send_messages and perms.embed_links and perms.attach_files:
                starboard_message = await starboard_channel.send(
                    content=f"{payload.emoji} **#{reactions[0]}** {message.channel.mention}",
                    embed=embed,
                    view=view,
                    file=file,
                )
                await self.bot.db.execute(
                    "INSERT INTO starboard_messages VALUES ($1,$2,$3,$4)",
                    payload.guild_id,
                    payload.channel_id,
                    payload.message_id,
                    starboard_message.id,
                )
                if role_id := res.get("role_id"):
                    if role := guild.get_role(role_id):
                        if role not in message.author.roles:
                            await message.author.add_roles(
                                role, reason="User is in the starboard"
                            )
        else:
            try:
                starboard_message = await starboard_channel.fetch_message(
                    check["starboard_message_id"]
                )
                await starboard_message.edit(
                    content=f"{payload.emoji} **#{reactions[0]}** {message.channel.mention}"
                )
            except discord.NotFound:
                await self.bot.db.execute(
                    "DELETE FROM starboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                    payload.guild_id,
                    payload.channel_id,
                    payload.message_id,
                )

    @Cog.listener("on_raw_reaction_remove")
    async def on_clownboard_remove(self, payload: discord.RawReactionActionEvent):
        retry_after = self.is_rate_limited(payload)
        if retry_after:
            await asyncio.sleep(2)

        res = await self.bot.db.fetchrow(
            "SELECT * FROM clownboard WHERE guild_id = $1", payload.guild_id
        )
        if res:
            if not res["emoji"]:
                return
            if str(payload.emoji) == res["emoji"]:
                mes = await self.bot.get_channel(payload.channel_id).fetch_message(
                    payload.message_id
                )
                reactions = [
                    r.count for r in mes.reactions if str(r.emoji) == res["emoji"]
                ]
                if len(reactions) > 0:
                    reaction = reactions[0]
                    if not res["channel_id"]:
                        return
                    channel = self.bot.get_channel(res["channel_id"])
                    if channel:
                        check = await self.bot.db.fetchrow(
                            "SELECT * FROM clownboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                            payload.guild_id,
                            payload.channel_id,
                            payload.message_id,
                        )
                        if check:
                            try:
                                m = await channel.fetch_message(
                                    check["clownboard_message_id"]
                                )
                                await m.edit(
                                    content=f"{payload.emoji} **#{reaction}** {mes.channel.mention}"
                                )
                            except:
                                await self.bot.db.execute(
                                    "DELETE FROM clownboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                                    payload.guild_id,
                                    payload.channel_id,
                                    payload.message_id,
                                )

    @Cog.listener("on_raw_reaction_add")
    async def on_clownboard_add(self, payload: discord.RawReactionActionEvent):
        retry_after = self.is_rate_limited(payload)
        if retry_after:
            await asyncio.sleep(2)

        res = await self.bot.db.fetchrow(
            "SELECT * FROM clownboard WHERE guild_id = $1", payload.guild_id
        )
        if not res:
            return

        if str(payload.emoji) != res.get("emoji"):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return

        reactions = [r.count for r in message.reactions if str(r.emoji) == res["emoji"]]
        if not reactions or reactions[0] < res.get("count", 0):
            return

        clownboard_channel = guild.get_channel(res["channel_id"])
        if not clownboard_channel or payload.channel_id == clownboard_channel.id:
            return

        check = await self.bot.db.fetchrow(
            "SELECT * FROM clownboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
            payload.guild_id,
            payload.channel_id,
            payload.message_id,
        )

        embed = discord.Embed(
            color=self.bot.color,
            description=message.content,
            timestamp=message.created_at,
        )
        embed.set_author(
            name=str(message.author), icon_url=message.author.display_avatar.url
        )

        file = None
        if message.attachments:
            attachment = message.attachments[0]
            if attachment.filename.endswith(("png", "jpeg", "jpg")):
                embed.set_image(url=attachment.proxy_url)
            elif attachment.filename.endswith(("mp3", "mp4", "mov")):
                async with self.bot.session.get(attachment.url) as resp:
                    if resp.status == 200:
                        data = io.BytesIO(await resp.read())
                        file = discord.File(data, filename=attachment.filename)

        if message.embeds:
            original_embed = message.embeds[0]
            embed.title = original_embed.title
            embed.url = original_embed.url
            embed.description = original_embed.description or message.content
            embed.color = original_embed.color

            if original_embed.author:
                embed.set_author(
                    name=original_embed.author.name,
                    icon_url=original_embed.author.icon_url,
                    url=original_embed.author.url,
                )
            if original_embed.thumbnail:
                embed.set_thumbnail(url=original_embed.thumbnail.url)
            if original_embed.image:
                embed.set_image(url=original_embed.image.url)
            if original_embed.footer:
                embed.set_footer(
                    text=original_embed.footer.text,
                    icon_url=original_embed.footer.icon_url,
                )

        if message.reference:
            embed.description = f"{embed.description}\n[Replying to {message.reference.resolved.author}]({message.reference.resolved.jump_url})"

        if not check:
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Message", url=message.jump_url))

            perms = clownboard_channel.permissions_for(guild.me)
            if perms.send_messages and perms.embed_links and perms.attach_files:
                clownboard_message = await clownboard_channel.send(
                    content=f"{payload.emoji} **#{reactions[0]}** {message.channel.mention}",
                    embed=embed,
                    view=view,
                    file=file,
                )
                await self.bot.db.execute(
                    "INSERT INTO clownboard_messages VALUES ($1, $2, $3, $4)",
                    payload.guild_id,
                    payload.channel_id,
                    payload.message_id,
                    clownboard_message.id,
                )
                if role_id := res.get("role_id"):
                    if role := guild.get_role(role_id):
                        if role not in message.author.roles:
                            await message.author.add_roles(
                                role, reason="User is in the clownboard"
                            )
        else:
            try:
                clownboard_message = await clownboard_channel.fetch_message(
                    check["clownboard_message_id"]
                )
                await clownboard_message.edit(
                    content=f"{payload.emoji} **#{reactions[0]}** {message.channel.mention}"
                )
            except discord.NotFound:
                await self.bot.db.execute(
                    "DELETE FROM clownboard_messages WHERE guild_id = $1 AND channel_id = $2 AND message_id = $3",
                    payload.guild_id,
                    payload.channel_id,
                    payload.message_id,
                )

    @Cog.listener("on_reaction_remove")
    async def reaction_snipe_event(
        self, reaction: discord.Reaction, user: discord.Member
    ):
        retry_after = self.is_rate_limited(reaction.message)
        if retry_after:
            await asyncio.sleep(2)

        if user.bot:
            return

        get_snipe = self.bot.cache.get("reaction_snipe")
        if get_snipe:
            lol = get_snipe
            lol.append(
                {
                    "channel": reaction.message.channel.id,
                    "message": reaction.message.id,
                    "reaction": str(reaction.emoji),
                    "user": str(user),
                    "created_at": datetime.datetime.now().timestamp(),
                }
            )
            await self.bot.cache.set("reaction_snipe", lol)
        else:
            payload = [
                {
                    "channel": reaction.message.channel.id,
                    "message": reaction.message.id,
                    "reaction": str(reaction.emoji),
                    "user": str(user),
                    "created_at": datetime.datetime.now().timestamp(),
                }
            ]
            await self.bot.cache.set("reaction_snipe", payload)


async def setup(bot: Pretend) -> None:
    return await bot.add_cog(Reactions(bot))
