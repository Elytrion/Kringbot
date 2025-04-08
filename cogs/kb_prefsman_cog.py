import discord
import atexit
import os
from discord.ext import commands
from utils import bot_prefs, drive_prefs

LOCAL_PREF_PATH = "kringbot_prefs.json"

def _save_prefs():
    if not bot_prefs.all_keys():
        print("[PrefsManager] 💤 No prefs to save — skipping Drive upload.")
        return
    
    bot_prefs.save(LOCAL_PREF_PATH)
    drive_prefs.upload_to_drive(LOCAL_PREF_PATH)
    print("[PrefsManager] 🧷 Saved prefs via atexit.")

atexit.register(_save_prefs)

class PrefsManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Load from Drive on first ready
        if os.path.exists(LOCAL_PREF_PATH):
            bot_prefs.load(LOCAL_PREF_PATH)
            print("[PrefsManager] ✅ Loaded local preferences.")
        elif drive_prefs.download_from_drive(LOCAL_PREF_PATH):
            bot_prefs.load(LOCAL_PREF_PATH)
            print("[PrefsManager] ✅ No local pref found. Loaded cloud preferences.")
        else:
            print("[PrefsManager] ⚠️ No local or remote prefs found. Starting fresh.")

    @commands.Cog.listener()
    async def on_disconnect(self):
        _save_prefs()

    @commands.Cog.listener()
    async def on_close(self):
        _save_prefs()

    # @discord.slash_command(name="save-db", escription="Save current bot prefs to Drive")
    # async def save_db(self, ctx):
    #     await ctx.defer()
    #     self._save_prefs()
    #     await ctx.respond("✅ Preferences saved to Google Drive.")

    # @discord.slash_command(name="load-db",description="Load bot prefs from Drive (manual override)")
    # async def load_db(self, ctx):
    #     await ctx.defer()
    #     success = drive_prefs.download_from_drive(LOCAL_PREF_PATH)
    #     if success:
    #         bot_prefs.load(LOCAL_PREF_PATH)
    #         await ctx.respond("✅ Preferences loaded from Google Drive.")
    #     else:
    #         await ctx.respond("⚠️ Could not load prefs from Drive.")

def setup(bot):
    bot.add_cog(PrefsManager(bot))
