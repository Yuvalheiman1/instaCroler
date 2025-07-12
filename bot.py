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
        self.media_queue = asyncio.Queue()
        self.sending_task = None

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

    async def start_sending_worker(self, app):
        print("[LOG] Starting background media sending worker...")
        self.sending_task = asyncio.create_task(self.media_sending_worker())

    async def media_sending_worker(self):
        while True:
            file_path, caption = await self.media_queue.get()
            print(f"[LOG] [PIPE] Sending from queue: {file_path}")
            try:
                await self._send_media_from_worker(file_path, caption)
            except Exception as e:
                print(f"[LOG] [PIPE] Error sending from queue: {e}")
            self.media_queue.task_done()

    async def _send_media_from_worker(self, file_path, caption, max_retries=3):
        bot = self.application.bot
        attempt = 0
        while attempt < max_retries:
            try:
                if file_path.lower().endswith(('.mp4', '.mov', '.m4v')):
                    with open(file_path, 'rb') as video:
                        await bot.send_video(chat_id=self.chat_id, video=video, caption=caption)
                else:
                    with open(file_path, 'rb') as photo:
                        await bot.send_photo(chat_id=self.chat_id, photo=photo, caption=caption)
                print(f"[LOG] [PIPE] Successfully sent: {file_path}")
                return
            except Exception as e:
                print(f"[LOG] [PIPE] Error sending media (attempt {attempt+1}): {e}")
                attempt += 1
                if attempt < max_retries:
                    await asyncio.sleep(10)  # Wait before retrying
                else:
                    await bot.send_message(chat_id=self.chat_id, text=f"⚠️ Error sending media after {max_retries} attempts: {e}")

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
                # Download stories and enqueue each file as soon as it's ready
                newest_id = last_id
                async for file_path, story_id in self._download_and_enqueue_stories(username, last_id):
                    if newest_id is None or int(story_id) > int(newest_id or "0"):
                        newest_id = story_id
                if newest_id and int(newest_id) > int(last_id or "0"):
                    self.stories_tracker.update_last_story_id(username, newest_id)
                    print(f"[LOG] Updated last story ID for @{username} to: {newest_id}")
                    if context:
                        await context.message.reply_text(f"✅ Updated last story ID for @{username} to: {newest_id}")
            except Exception as e:
                print(f"[LOG] Error with @{username}: {e}")
                if context:
                    await context.message.reply_text(f"⚠️ Error with @{username}: {e}")

    async def _download_and_enqueue_stories(self, username, last_id):
        # This async generator yields (file_path, story_id) as soon as each story is downloaded
        async for file_path, story_id in self.downloader.download_user_stories_stream(username, last_known_id=last_id):
            print(f"[LOG] [PIPE] Queueing story {story_id} for @{username}")
            await self.media_queue.put((file_path, f"New story from @{username}"))
            yield file_path, story_id

    async def periodic_scrape_worker(self):
        while True:
            print("[LOG] [SCHEDULER] Running periodic scrape...")
            try:
                await self.check_and_send_stories()
                # Notify user when next automatic scrape will happen
                next_time = 300  # 5 minutes in seconds
                minutes = next_time // 60
                await self.application.bot.send_message(
                    chat_id=self.chat_id,
                    text=f"⏰ Next automatic scrape will happen in {minutes} minutes."
                )
            except Exception as e:
                print(f"[LOG] [SCHEDULER] Error in periodic scrape: {e}")
            await asyncio.sleep(300)  # 5 minutes

    def run(self):
        print("Bot is running...")
        # Use post_init to start background workers inside the event loop
        async def post_init_callback(app):
            self.sending_task = asyncio.create_task(self.media_sending_worker())
            self.periodic_task = asyncio.create_task(self.periodic_scrape_worker())
        self.application.post_init = post_init_callback
        self.application.run_polling()

if __name__ == "__main__":
    bot = StoryMonitorBot()
    bot.run()
