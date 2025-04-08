import discord
import platform
import psutil
import time
from discord.ext import commands
from discord.commands import slash_command, Option
from discord.ui import View, Button

BOT_VERSION = "1.3.4"

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()  # For uptime tracking
        print("✅ HelpCog loaded!")

    @discord.slash_command(name="help", description="Show help info for all commands or a specific command.")
    async def help(
        self,
        ctx,
        command_name: Option(str, "Optional command to get detailed help", required=False)
    ):
        try:
            await ctx.defer(ephemeral=True)
            if command_name:
                # Show help for a specific command
                cmd = self.bot.get_application_command(command_name)
                if not cmd:
                    await ctx.respond(f"❌ Command `{command_name}` not found.")
                    return

                embed = discord.Embed(
                    title=f"❔ Help: /{cmd.name}",
                    description=cmd.description or "No description provided.",
                    color=discord.Color.green()
                )

                # Optionally list parameters
                if hasattr(cmd, "options") and cmd.options:
                    for opt in cmd.options:
                        opt_type = str(opt.input_type).split('.')[-1].capitalize()
                        required = "✅" if opt.required else "❌"
                        embed.add_field(
                            name=f"`{opt.name}` ({opt_type}, Required: {required})",
                            value=opt.description or "No description.",
                            inline=False
                        )

                await ctx.respond(embed=embed)

            else:
                # Show paginated general command list
                await self.show_paginated_help(ctx)
        except discord.errors.NotFound:
            print("❌ Interaction expired before response could be sent.")
        except Exception as e:
            print(f"❗ Unexpected error in /help: {e}")

    async def show_paginated_help(self, ctx):
        seen = set()
        unique_commands = []
        for cmd in self.bot.application_commands:
            if isinstance(cmd, discord.SlashCommandGroup):
                unique_commands.append(cmd)
                seen.add(cmd.name)
                continue
            # hiddenattr = getattr(cmd.callback, "hidden", False)
            # print(f"{cmd} is hidden? {hiddenattr}")
            if getattr(cmd.callback, "hidden", False):
                continue  # Skip commands marked as hidden
            if cmd.name not in seen:
                unique_commands.append(cmd)
                seen.add(cmd.name)

        per_page = 5
        pages = [
            unique_commands[i:i + per_page]
            for i in range(0, len(unique_commands), per_page)
        ]

        current_page = 0
        embed = self.make_help_embed(pages[current_page], current_page, len(pages))
        view = HelpPaginationView(pages, self.make_help_embed, ctx.author.id)

        await ctx.respond(embed=embed, view=view)

    def make_help_embed(self, commands, page, total_pages):
        embed = discord.Embed(
            title=f"📚 Kringbot Commands (Page {page + 1}/{total_pages})",
            color=discord.Color.blurple()
        )
        for cmd in commands:
            embed.add_field(
                name=f"/{cmd.name}",
                value=cmd.description or "No description",
                inline=False
            )
        return embed

    @slash_command(
        name="status",
        description="Show kringbot status info.",
        default_member_permissions=discord.Permissions(administrator=True)
    )
    async def status(self, ctx: discord.ApplicationContext):
        try:
            await ctx.defer(ephemeral=True)

            bot = self.bot
            user_id = ctx.author.id
            now = time.time()

            uptime_seconds = int(now - self.start_time)
            uptime_str = time.strftime("%Hh %Mm %Ss", time.gmtime(uptime_seconds))

            process = psutil.Process()
            mem_mb = process.memory_info().rss / 1024 / 1024

            embed = discord.Embed(title="🤖 Kringbot Status", color=discord.Color.green())
            embed.add_field(name="🆔 Bot ID", value=bot.user.id, inline=True)
            embed.add_field(name="📡 Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
            embed.add_field(name="🌐 Guilds", value=len(bot.guilds), inline=True)
            embed.add_field(name="👥 Users", value=sum(g.member_count or 0 for g in bot.guilds), inline=True)
            embed.add_field(name="📋 Slash Commands", value=len(bot.application_commands), inline=True)
            embed.add_field(name="🕓 Uptime", value=uptime_str, inline=True)
            embed.add_field(name="💾 RAM Usage", value=f"{mem_mb:.2f} MB", inline=True)
            embed.add_field(name="🧠 Python", value=platform.python_version(), inline=True)
            embed.add_field(name="📦 Pycord", value=discord.__version__, inline=True)
            embed.add_field(name="🔧 Bot Version", value=BOT_VERSION, inline=True)
            embed.set_footer(text=f"{bot.user.name} is online!")

            await ctx.respond(embed=embed, ephemeral=True)
        except discord.errors.NotFound:
            print("❌ Interaction expired before response could be sent.")
        except Exception as e:
            print(f"❗ Unexpected error in /status: {e}")

class HelpPaginationView(discord.ui.View):
    def __init__(self, pages, make_embed_fn, author_id):
        super().__init__(timeout=120)
        self.pages = pages
        self.make_embed_fn = make_embed_fn
        self.current = 0
        self.author_id = author_id
        self.update_button_states()
    
    def update_button_states(self):
        self.children[0].disabled = self.current == 0
        self.children[1].disabled = self.current >= len(self.pages) - 1

    @discord.ui.button(label="⬅️ Previous", style=discord.ButtonStyle.primary)
    async def go_prev(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You're not the one who requested this help message!", ephemeral=True)
            return

        if self.current > 0:
            self.current -= 1
            embed = self.make_embed_fn(self.pages[self.current], self.current, len(self.pages))
            self.update_button_states()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next ➡️", style=discord.ButtonStyle.primary)
    async def go_next(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You're not the one who requested this help message!", ephemeral=True)
            return

        if self.current < len(self.pages) - 1:
            self.current += 1
            embed = self.make_embed_fn(self.pages[self.current], self.current, len(self.pages))
            self.update_button_states()
            await interaction.response.edit_message(embed=embed, view=self)


def setup(bot):
    bot.add_cog(HelpCog(bot))
