import discord
import time
from discord.ext import commands
from collections import OrderedDict, defaultdict
from utils import bot_prefs

MAX_TRACKED_MESSAGES = 256
MAX_DELETED_PER_USER = 32
MAX_EDITED_PER_USER = 32
MAX_EDITS_PER_MESSAGE = 8

class BasePaginator(discord.ui.View):
    def __init__(self, pages, author_id, title_prefix="Messages", emoji="", color=discord.Color.blurple()):
        super().__init__(timeout=120)
        self.pages = pages
        self.current = 0
        self.author_id = author_id
        self.title_prefix = title_prefix
        self.emoji = emoji
        self.color = color
        self.update_buttons()

    def update_buttons(self):
        self.children[0].disabled = self.current == 0
        self.children[1].disabled = self.current >= len(self.pages) - 1

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.primary)
    async def go_prev(self, button, interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your command!", ephemeral=True)
        self.current -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.primary)
    async def go_next(self, button, interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your command!", ephemeral=True)
        self.current += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger, row=1)
    async def close(self, button, interaction):
        await interaction.message.delete()

    def make_embed(self):
        return discord.Embed(
            title=f"{self.emoji} {self.title_prefix} (Page {self.current+1}/{len(self.pages)})",
            description=self.pages[self.current],
            color=self.color
        )

    async def interaction_check(self, interaction):
        return interaction.user.id == self.author_id

class MessageManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.message_timestamps = OrderedDict()  # msg.id → (timestamp, author, content, channel)
        self.recent_deletes = defaultdict(list)  # user_id → list of (content, channel_name, timestamp)
        self.recent_edits = defaultdict(list)  # user_id → list of edits (each = dict)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        try:
            if message.author.bot:
                return
            self.message_timestamps[message.id] = (
                message.created_at.timestamp(),
                message.author,
                message.content,
                message.channel
            )
            if len(self.message_timestamps) > MAX_TRACKED_MESSAGES:
                self.message_timestamps.popitem(last=False)
        except Exception as e:
            print(f"❗ Unexpected error when getting messages: {e}")
    
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        try:
            data = self.message_timestamps.pop(message.id, None)
            if data:
                sent_time, author, content, channel = data
            else:
                author = message.author
                content = message.content
                channel = message.channel
                sent_time = message.created_at.timestamp()

            if not author or not content:
                return

            entry = (content, channel.name, sent_time, time.time())
            messages = self.recent_deletes[author.id]
            messages.insert(0, entry)
            self.recent_deletes[author.id] = messages[:MAX_DELETED_PER_USER]
            self._sync_logs_to_prefs(message.guild.id)
        except Exception as e:
            print(f"❗ Unexpected error when getting deleted messages: {e}")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        try:
            if before.author.bot or before.content == after.content:
                return

            user_edits = self.recent_edits[before.author.id]

            # Try to find an existing message entry
            for msg in user_edits:
                if msg["message_id"] == before.id:
                    if len(msg["edits"]) >= MAX_EDITS_PER_MESSAGE:
                        msg["edits"].pop(0)
                    msg["edits"].append((time.time(), after.content))
                    return  # ✅ Don't continue if updated

            # If not found, insert new entry
            if len(user_edits) >= MAX_EDITED_PER_USER:
                user_edits.pop()  # Remove oldest
            user_edits.insert(0, {
                "message_id": before.id,
                "channel": before.channel.name,
                "original": before.content,
                "edits": [(time.time(), after.content)]
            })

            self._sync_logs_to_prefs(after.guild.id)
        except Exception as e:
            print(f"❗ Unexpected error when getting edited messages: {e}")
        
    @discord.slash_command(
        name="deleted",
        description="Show a user's recently deleted messages",
        default_member_permissions=discord.Permissions(manage_messages=True)
    )
    async def show_deleted(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="Select a member")
    ):
        try:
            await ctx.defer()
            deleted = self.recent_deletes.get(member.id)
            if not deleted:
                await ctx.respond(f"✅ No recently deleted messages found for **{member.display_name}**.")
                return

            pages = []
            X = 5
            for i in range(0, len(deleted), X): # 5 messages per page
                chunk = deleted[i:i+X]
                lines = []
                for content, channel, sent_at, deleted_at in chunk:
                    age = int(time.time() - deleted_at)
                    sent_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sent_at))
                    lines.append(
                        f"📄 Sent at `{sent_time_str}` in **#{channel}**\n"
                        f"`{content}`\n"
                        f"*Deleted {age}s ago*"
                    )
                pages.append("\n\n".join(lines))

            await self.show_deleted_pages(ctx, pages, member.display_name)
        except discord.errors.NotFound:
            print("❌ Interaction expired before response could be sent.")
        except Exception as e:
            print(f"❗ Unexpected error in /deleted: {e}")

    async def show_deleted_pages(self, ctx, pages, display_name):
        class DeletedPaginator(BasePaginator):
            def __init__(self, pages, author_id):
                super().__init__(
                    pages,
                    author_id,
                    title_prefix="Deleted Messages",
                    emoji="🗑️",
                    color=discord.Color.red()
                )

        view = DeletedPaginator(pages, ctx.author.id)
        view.update_buttons()
        await ctx.respond(embed=view.make_embed(), view=view)


    @discord.slash_command(
        name="edited",
        description="Show a user's recently edited messages",
        default_member_permissions=discord.Permissions(manage_messages=True)
    )
    async def show_edited(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="Select a member")
    ):
        try:
            await ctx.defer()

            edits = self.recent_edits.get(member.id)
            if not edits:
                await ctx.respond(f"✅ No recent edits found for **{member.display_name}**.")
                return

            pages = []
            for entry in edits:
                lines = [f"**#{entry['channel']}**", f"`{entry['original']}`"]
                for ts, edit in entry["edits"]:
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                    lines.append(f"*was edited at {timestamp} into*")
                    lines.append(f"`{edit}`")
                pages.append("\n".join(lines))

            await self.show_edit_pages(ctx, pages, member.display_name)
        except discord.errors.NotFound:
            print("❌ Interaction expired before response could be sent.")
        except Exception as e:
            print(f"❗ Unexpected error in /edited: {e}")

    async def show_edit_pages(self, ctx, pages, display_name):
        class EditPaginator(BasePaginator):
            def __init__(self, pages, author_id):
                super().__init__(
                    pages,
                    author_id,
                    title_prefix="Edited Messages",
                    emoji="✏️",
                    color=discord.Color.orange()
                )
        view = EditPaginator(pages, ctx.author.id)
        view.update_buttons()
        await ctx.respond(embed=view.make_embed(), view=view)

    def _sync_logs_to_prefs(self, guild_id: int):
        # Deleted messages: (author_id, content, channel_name, sent_at, deleted_at)
        all_deleted = []
        for uid, msgs in self.recent_deletes.items():
            for content, channel, sent_at, deleted_at in msgs:
                all_deleted.append((uid, content, channel, sent_at, deleted_at))

        bot_prefs.set(f"{guild_id}_deleted", all_deleted)

        # Edited messages (no change)
        all_edits = []
        for uid, entries in self.recent_edits.items():
            for entry in entries:
                all_edits.append((
                    uid,
                    entry["message_id"],
                    entry["channel"],
                    entry["original"],
                    entry["edits"]
                ))

        bot_prefs.set(f"{guild_id}_edited", all_edits)

    def _restore_logs_from_prefs(self, guild: discord.Guild):
        gid = guild.id

        deleted = bot_prefs.get(f"{gid}_deleted", [])
        for uid, content, channel, sent_ts, deleted_ts in deleted:
            self.recent_deletes[uid].append((content, channel, sent_ts, deleted_ts))
        edited = bot_prefs.get(f"{gid}_edited", [])
        for uid, msg_id, channel, original, edits in edited:
            self.recent_edits[uid].append({
                "message_id": msg_id,
                "channel": channel,
                "original": original,
                "edits": edits
            })
        if len(deleted) > 0 and len(edited) > 0:
            print(f"[Restore] ✅ Restored logs for guild {guild.name} ({gid})")
        else:
            print(f"[Restore] ⚠️ No restored logs for guild {guild.name} ({gid})")

    @discord.slash_command(
    name="purge-deleted",
    description="Purge all tracked deleted messages for a user in this server.",
    default_member_permissions=discord.Permissions(manage_messages=True)
    )
    async def purge_deleted(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="Select a member")
    ):
        try:
            await ctx.defer(ephemeral=True)

            if member.id in self.recent_deletes:
                del self.recent_deletes[member.id]
                self._sync_logs_to_prefs(ctx.guild.id)
                await ctx.respond(f"🗑️ Deleted message log purged for **{member.display_name}**.")
            else:
                await ctx.respond(f"ℹ️ No deleted messages were logged for **{member.display_name}**.")
        except discord.errors.NotFound:
            print("❌ Interaction expired before response could be sent.")
        except Exception as e:
            print(f"❗ Unexpected error in /purge-deleted: {e}")

    purge_deleted.callback.hidden = True

    @discord.slash_command(
        name="purge-edited",
        description="Purge all tracked edited messages for a user in this server.",
        default_member_permissions=discord.Permissions(manage_messages=True)
    )
    async def purge_edited(
        self,
        ctx: discord.ApplicationContext,
        member: discord.Option(discord.Member, description="Select a member")
    ):
        try:
            await ctx.defer(ephemeral=True)

            if member.id in self.recent_edits:
                del self.recent_edits[member.id]
                self._sync_logs_to_prefs(ctx.guild.id)
                await ctx.respond(f"✏️ Edited message log purged for **{member.display_name}**.")
            else:
                await ctx.respond(f"ℹ️ No edited messages were logged for **{member.display_name}**.")
        except discord.errors.NotFound:
            print("❌ Interaction expired before response could be sent.")
        except Exception as e:
            print(f"❗ Unexpected error in /purge-edited: {e}")

    purge_edited.callback.hidden = True

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            self._restore_logs_from_prefs(guild)
        print("✅ MessageManager Cog loaded!")

def setup(bot):
    bot.add_cog(MessageManager(bot))
