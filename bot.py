import asyncio
import os
import sys
import json
from dotenv import load_dotenv
from anonyig_downloader import AnonyigDownloader
from stories_tracker import StoriesTracker
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

# Load environment variables from a .env file
load_dotenv()

PROFILES_FILE = "monitored_profiles.json"

# --- Persistent profile storage ---
def load_profiles():
    if os.path.exists(PROFILES_FILE):
        with open(PROFILES_FILE, 'r') as f:
            return json.load(f)
    return []

def save_profiles(profiles):
    with open(PROFILES_FILE, 'w') as f:
        json.dump(profiles, f, indent=2)

# --- Bot class using python-telegram-bot async ---
class StoryMonitorBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.downloader = AnonyigDownloader()
        self.stories_tracker = StoriesTracker()
        self.monitored_profiles = load_profiles()
        self.application = Application.builder().token(self.token).build()
        self.add_handlers()

    def add_handlers(self):
        self.application.add_handler(CommandHandler('start', self.cmd_start))
        self.application.add_handler(CommandHandler('help', self.cmd_help))
        self.application.add_handler(CommandHandler('refresh', self.cmd_refresh))
        self.application.add_handler(CommandHandler('start_iteration', self.cmd_refresh))
        self.application.add_handler(CommandHandler('list_profiles', self.cmd_list_profiles))
        self.application.add_handler(CommandHandler('add_profile', self.cmd_add_profile))
        self.application.add_handler(CommandHandler('remove_profile', self.cmd_remove_profile))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("👋 Welcome! I monitor Instagram stories and send them here. Use /help for commands.")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "🤖 *Instagram Story Monitor Bot*\n\n"
            "/refresh or /start_iteration - Check all monitored profiles now\n"
            "/add_profile <username> - Add a profile to monitor\n"
            "/remove_profile <username> - Remove a profile\n"
            "/list_profiles - List all monitored profiles\n"
            "/help - Show this help message"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

    async def cmd_list_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[LOG] /list_profiles command received")
        if not self.monitored_profiles:
            print("[LOG] No profiles are currently being monitored.")
            await update.message.reply_text("📝 No profiles are currently being monitored.")
        else:
            print(f"[LOG] Listing profiles: {self.monitored_profiles}")
            await update.message.reply_text("👀 Currently monitored profiles:\n" + '\n'.join(f"- {p}" for p in self.monitored_profiles))

    async def cmd_add_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"[LOG] /add_profile command received with args: {context.args}")
        if not context.args:
            print("[LOG] No username provided to add.")
            await update.message.reply_text("Usage: /add_profile <username>")
            return
        username = context.args[0].strip()
        if username in self.monitored_profiles:
            print(f"[LOG] {username} is already being monitored.")
            await update.message.reply_text(f"{username} is already being monitored.")
            return
        self.monitored_profiles.append(username)
        save_profiles(self.monitored_profiles)
        print(f"[LOG] Added {username} to monitored profiles.")
        await update.message.reply_text(f"✅ Added {username} to monitored profiles.")

    async def cmd_remove_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"[LOG] /remove_profile command received with args: {context.args}")
        if not context.args:
            print("[LOG] No username provided to remove.")
            await update.message.reply_text("Usage: /remove_profile <username>")
            return
        username = context.args[0].strip()
        if username not in self.monitored_profiles:
            print(f"[LOG] {username} is not in the monitored list.")
            await update.message.reply_text(f"{username} is not in the monitored list.")
            return
        self.monitored_profiles.remove(username)
        save_profiles(self.monitored_profiles)
        print(f"[LOG] Removed {username} from monitored profiles.")
        await update.message.reply_text(f"❌ Removed {username} from monitored profiles.")

    async def cmd_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print("[LOG] /refresh or /start_iteration command received")
        await update.message.reply_text("🔄 Checking all monitored profiles for new stories...")
        await self.check_and_send_stories(update)

    async def send_media(self, context, file_path: str, caption: str = "") -> bool:
        print(f"[LOG] Sending media: {file_path}")
        try:
            bot = context.application.bot if hasattr(context, 'application') else self.application.bot
            if file_path.lower().endswith(('.mp4', '.mov', '.m4v')):
                with open(file_path, 'rb') as video:
                    await bot.send_video(chat_id=self.chat_id, video=video, caption=caption)
            else:
                with open(file_path, 'rb') as photo:
                    await bot.send_photo(chat_id=self.chat_id, photo=photo, caption=caption)
            print(f"[LOG] Successfully sent: {file_path}")
            return True
        except Exception as e:
            print(f"[LOG] Error sending media: {e}")
            await bot.send_message(chat_id=self.chat_id, text=f"⚠️ Error sending media: {e}")
            return False

    async def check_and_send_stories(self, update: Update = None):
        print("[LOG] Starting check_and_send_stories")
        context = update if update else None
        if not self.monitored_profiles:
            print("[LOG] No profiles to check.")
            if context:
                await context.message.reply_text("📝 No profiles to check.")
            return
        msg = f"🔍 Starting check for {len(self.monitored_profiles)} profiles..."
        print(f"[LOG] {msg}")
        if context:
            await context.message.reply_text(msg)
        for username in self.monitored_profiles:
            try:
                print(f"[LOG] Checking @{username}")
                if context:
                    await context.message.reply_text(f"➡️ Checking @{username}...")
                last_id = self.stories_tracker.get_last_story_id(username)
                print(f"[LOG] Last known story ID for @{username}: {last_id}")
                downloaded_files, newest_id = await self.downloader.download_user_stories(
                    username, last_known_id=last_id
                )
                if not downloaded_files:
                    print(f"[LOG] No new stories for @{username}.")
                    if context:
                        await context.message.reply_text(f"😴 No new stories for @{username}.")
                    continue
                print(f"[LOG] Found {len(downloaded_files)} new stories for @{username}.")
                await context.message.reply_text(f"📸 Found {len(downloaded_files)} new stories for @{username}. Sending...")
                downloaded_files.sort(key=lambda x: int(x[1]))
                for file_path, story_id in downloaded_files:
                    print(f"[LOG] Sending story {story_id} for @{username}")
                    await self.send_media(context, file_path, caption=f"New story from @{username}")
                if newest_id and int(newest_id) > int(last_id or "0"):
                    self.stories_tracker.update_last_story_id(username, newest_id)
                    print(f"[LOG] Updated last story ID for @{username} to: {newest_id}")
                    await context.message.reply_text(f"✅ Updated last story ID for @{username} to: {newest_id}")
            except Exception as e:
                print(f"[LOG] Error with @{username}: {e}")
                if context:
                    await context.message.reply_text(f"⚠️ Error with @{username}: {e}")

    def run(self):
        print("Bot is running...")
        self.application.run_polling()

if __name__ == "__main__":
    bot = StoryMonitorBot()
    bot.run()
