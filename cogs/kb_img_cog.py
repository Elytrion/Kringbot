import discord
import time
import os
from discord.ext import commands
from discord.commands import slash_command
from utils import gimg_utils, bot_prefs

REFRESH_IMG_COOLDOWN_SECONDS = 300
DAILY_COOLDOWN_SECONDS = 60 * 60 * 12
KRINGPIC_COOLDOWN_SECONDS = 65

class ImgCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.refresh_img_cooldown = 0
        self.img_folder_name = os.environ.get("DAILY_IMAGE_FOLDER_ID")
        if not self.img_folder_name:
            raise RuntimeError("DAILY_IMAGE_FOLDER_ID not found in environment variables!")
        print("✅ ImgCog loaded!")

    @discord.slash_command(name="refresh-images", description="Reload images from the Kringbot Daily Google Drive folder.")
    async def refresh_images(self, ctx):
        try:
            await ctx.defer(ephemeral=True)
            now = time.time()
            time_since_last = now - self.refresh_img_cooldown
            time_left = REFRESH_IMG_COOLDOWN_SECONDS - time_since_last

            if time_since_last < REFRESH_IMG_COOLDOWN_SECONDS:
                minutes = int((time_left % 3600) // 60)
                seconds = int(time_left % 60)
                await ctx.respond(f"⏳ A refresh was done recently! Try again in {minutes}m {seconds}s.")
                return

            success = gimg_utils.refresh_folder_cache(self.img_folder_name)

            if success:
                self.refresh_img_cooldown = now
                await ctx.respond("✅ Image list has been refreshed.")
            else:
                await ctx.respond("❌ UmU Could not refresh image list. Check folder access or ID.")
        except discord.errors.NotFound:
            print("❌ Interaction expired before response could be sent.")
        except Exception as e:
            print(f"❗ Unexpected error in /refresh-images: {e}")

    @discord.slash_command(name="daily-kringles", description="Get your daily kringle image!")
    async def daily_image(self, ctx):
        try:
            await ctx.defer()
            user_id = ctx.author.id
            no_cd = bot_prefs.get(f"no_cd_daily_{user_id}", False)
            if not no_cd:
                remaining = int(bot_prefs.get(f"daily_img_cd_{user_id}", 0))
                if remaining > 0:
                    hours = remaining // 3600
                    minutes = (remaining % 3600) // 60
                    seconds = remaining % 60
                    await ctx.respond(f"⏳ You've already received your image of the day! Try again in {hours}h {minutes}m {seconds}s.")
                    return

            image_url = gimg_utils.get_random_image_url(self.img_folder_name)
            if not image_url:
                await ctx.respond("⚠️ UmU Could not find images in the daily folder. Try contacting the dev.")
                return
            # Set cooldown for this user
            if not no_cd:
                bot_prefs.set(f"daily_img_cd_{user_id}", DAILY_COOLDOWN_SECONDS, time_based=True)
            embed = discord.Embed(title=f"🖼️ Here's your image of the day, {ctx.author.display_name}!")
            embed.set_image(url=image_url)

            await ctx.respond(embed=embed)
        except discord.errors.NotFound:
            print("❌ Interaction expired before response could be sent.")
        except Exception as e:
            print(f"❗ Unexpected error in /daily-kringles: {e}")

    @discord.slash_command(name="kring-pic", description="Get a randomised kring pic!")
    async def kringpic_image(self, ctx):
        try:
            await ctx.defer()
            user_id = ctx.author.id
            no_cd = bot_prefs.get(f"no_cd_kringpic_{user_id}", False)
            remaining = int(bot_prefs.get(f"kringpic_img_cd_{user_id}", 0))
            if not no_cd:
                if remaining > 0:
                    minutes = (remaining % 3600) // 60
                    seconds = remaining % 60
                    await ctx.respond(f"⏳ You've recently requested a kringpic! Try again in {minutes}m {seconds}s.")
                    return

            image_url = gimg_utils.get_random_image_url(self.img_folder_name)
            if not image_url:
                await ctx.respond("⚠️ UmU Could not find images in the images folder. Try contacting the dev.")
                return
            # Set cooldown for this user
            if not no_cd: 
                bot_prefs.set(f"kringpic_img_cd_{user_id}", KRINGPIC_COOLDOWN_SECONDS, time_based=True)
            embed = discord.Embed(title=f"🖼️ Here's a kring pic, {ctx.author.display_name}!")
            embed.set_image(url=image_url)

            await ctx.respond(embed=embed)
        except discord.errors.NotFound:
            print("❌ Interaction expired before response could be sent.")
        except Exception as e:
            print(f"❗ Unexpected error in /kring-pic: {e}")

    # @discord.slash_command(
    #     name="reduce-cooldown", 
    #     description="Reduce a user's cooldown for daily or kring-pic commands"
    # )
    # @commands.is_owner()
    # async def reduce_cooldown(
    #     self,
    #     ctx: discord.ApplicationContext,
    #     command_id: str,
    #     user: discord.Member,
    #     seconds_to_reduce: int
    # ):
    #     cmd_id = command_id.lower()
    #     if cmd_id == "daily":
    #         key = f"daily_img_cd_{user.id}"
    #     elif cmd_id == "kringpic":
    #         key = f"kringpic_img_cd_{user.id}"
    #     else:
    #         await ctx.respond("Invalid command_id. Use 'daily' or 'kringpic'.", ephemeral=True)
    #         return

    #     current_cd = int(bot_prefs.get(key, 0))
    #     new_cd = max(0, current_cd - seconds_to_reduce)
    #     bot_prefs.set(key, new_cd, time_based=True)
    #     await ctx.respond(
    #         f"Cooldown for {user.display_name} on {command_id} command reduced by {seconds_to_reduce} seconds. New cooldown: {new_cd} seconds.",
    #         ephemeral=True
    #     )
    # reduce_cooldown.callback.hidden = True

    # @reduce_cooldown.error
    # async def reduce_cooldown_error(self, ctx, error):
    #     if isinstance(error, discord.CheckFailure):
    #         await ctx.respond("You are not authorized to reduce image cooldowns.", ephemeral=True)

    # @discord.slash_command(
    #     name="remove-cooldown", 
    #     description="Remove a user's cooldown (and ignore cooldowns) for daily or kring-pic commands"
    # )
    # @commands.is_owner()
    # async def remove_cooldown(
    #     self,
    #     ctx: discord.ApplicationContext,
    #     command_id: str,
    #     user: discord.Member
    # ):
    #     cmd_id = command_id.lower()
    #     if cmd_id == "daily":
    #         key = f"daily_img_cd_{user.id}"
    #         override_key = f"no_cd_daily_{user.id}"
    #     elif cmd_id == "kringpic":
    #         key = f"kringpic_img_cd_{user.id}"
    #         override_key = f"no_cd_kringpic_{user.id}"
    #     else:
    #         await ctx.respond("Invalid command_id. Use 'daily' or 'kringpic'.", ephemeral=True)
    #         return

    #     bot_prefs.set(key, 0, time_based=True)
    #     # Set an override flag that your daily/kring-pic commands can check to bypass cooldowns
    #     bot_prefs.set(override_key, True)
    #     await ctx.respond(
    #         f"Image cooldown for {user.display_name} on {command_id} command removed. They will now ignore cooldowns.",
    #         ephemeral=True
    #     )
    # remove_cooldown.callback.hidden = True

    # @remove_cooldown.error
    # async def remove_cooldown_error(self, ctx, error):
    #     if isinstance(error, discord.CheckFailure):
    #         await ctx.respond("You are not authorized to remove image cooldowns.", ephemeral=True)

    # @discord.slash_command(
    #     name="add-cooldown", 
    #     description="Re-enable cooldowns for a user for daily or kring-pic commands"
    # )
    # @commands.is_owner()
    # async def add_cooldown(
    #     self,
    #     ctx: discord.ApplicationContext,
    #     command_id: str,
    #     user: discord.Member
    # ):
    #     cmd_id = command_id.lower()
    #     if cmd_id == "daily":
    #         override_key = f"no_cd_daily_{user.id}"
    #     elif cmd_id == "kringpic":
    #         override_key = f"no_cd_kringpic_{user.id}"
    #     else:
    #         await ctx.respond("Invalid command_id. Use 'daily' or 'kringpic'.", ephemeral=True)
    #         return

    #     # Remove the override flag so cooldowns apply again
    #     bot_prefs.set(override_key, False)
    #     await ctx.respond(
    #         f"Image cooldown for {user.display_name} on {command_id} command has been re-enabled.",
    #         ephemeral=True
    #     )
    # add_cooldown.callback.hidden = True

    # @add_cooldown.error
    # async def add_cooldown_error(self, ctx, error):
    #     if isinstance(error, discord.CheckFailure):
    #         await ctx.respond("You are not authorized to add image cooldowns.", ephemeral=True)

def setup(bot):
    bot.add_cog(ImgCog(bot))