import asyncio
import os
import sys
import json
from dotenv import load_dotenv
from anonyig_downloader import AnonyigDownloader
from stories_tracker import StoriesTracker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Load environment variables from a .env file
load_dotenv()

# File paths configuration
DATA_DIR = "data"
PROFILES_FILE = os.path.join(DATA_DIR, "monitored_profiles.json")
DLQ_FILE = os.path.join(DATA_DIR, "dlq.json")
STORIES_HISTORY_FILE = os.path.join(DATA_DIR, "stories_history.json")

# --- Persistent profile storage ---
def load_profiles():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    if os.path.exists(PROFILES_FILE):
        with open(PROFILES_FILE, 'r') as f:
            return json.load(f)
    return []

def save_profiles(profiles):
    with open(PROFILES_FILE, 'w') as f:
        json.dump(profiles, f, indent=2)

# --- Bot class using python-telegram-bot async ---
class StoryMonitorBot:
    def add_handlers(self):
        from telegram.ext import MessageHandler, filters
        self.application.add_handler(CommandHandler('start', self.cmd_start))
        self.application.add_handler(CommandHandler('help', self.cmd_help))
        self.application.add_handler(CommandHandler('refresh', self.cmd_refresh))
        self.application.add_handler(CommandHandler('start_iteration', self.cmd_refresh))
        self.application.add_handler(CommandHandler('list_profiles', self.cmd_list_profiles))
        self.application.add_handler(CommandHandler('add_profile', self.cmd_add_profile))
        self.application.add_handler(CommandHandler('remove_profile', self.cmd_remove_profile))
        self.application.add_handler(CommandHandler('menu', self.cmd_menu))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        # Add MessageHandler for text replies after Add/Remove button
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_reply_handler))
    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data='refresh')],
            [InlineKeyboardButton("👀 List Profiles", callback_data='list_profiles')],
            [InlineKeyboardButton("➕ Add Profile", callback_data='add_profile')],
            [InlineKeyboardButton("➖ Remove Profile", callback_data='remove_profile')]
        ]
        print("[LOG] /menu command received, showing menu")
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose an action:", reply_markup=reply_markup)

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        message = query.message
        if query.data == 'refresh':
            await self.cmd_refresh(update, context, reply_message=message)
        elif query.data == 'list_profiles':
            await self.cmd_list_profiles(update, context, reply_message=message)
        elif query.data == 'add_profile':
            await message.reply_text("What is the username to add?")
            context.user_data['awaiting_add'] = True
        elif query.data == 'remove_profile':
            # Send inline keyboard with each profile as a button
            if not self.monitored_profiles:
                await message.reply_text("📝 No profiles are currently being monitored.")
            else:
                keyboard = [
                    [InlineKeyboardButton(p, callback_data=f'remove_profile:{p}')]
                    for p in self.monitored_profiles
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await message.reply_text("Select a profile to remove:", reply_markup=reply_markup)
        elif query.data.startswith('remove_profile:'):
            # Extract username and call cmd_remove_profile
            username = query.data.split(':', 1)[1]
            await self.cmd_remove_profile(update, context, username=username, reply_message=message)
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.download_path = os.getenv('DOWNLOAD_PATH', 'downloads')
        self.downloader = AnonyigDownloader(download_dir=self.download_path)
        self.stories_tracker = StoriesTracker()
        self.monitored_profiles = load_profiles()
        self.application = Application.builder().token(self.token).build()
        self.add_handlers()
        self.media_queue = asyncio.Queue()
        self.sending_task = None

    # Duplicate add_handlers removed

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("👋 Welcome! I monitor Instagram stories and send them here. Use /help for commands.")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "<b>🤖 Instagram Story Monitor Bot Help</b>\n\n"
            "<b>Commands:</b>\n"
            "• /refresh — Check all monitored profiles now (sends new stories to this chat)\n"
            "• /add_profile &lt;username&gt; — Add a profile to monitor (e.g. /add_profile israel_bidur)\n"
            "• /remove_profile &lt;username&gt; — Remove a profile (e.g. /remove_profile israel_bidur)\n"
            "• /list_profiles — List all monitored profiles\n"
            "• /menu — Show a menu with Telegram buttons for quick actions (Refresh, List, Add, Remove)\n"
            "• /help — Show this help message\n\n"
            "<i>Note: The /menu command will show Telegram buttons for quick actions. Button actions are limited to Refresh and List Profiles. For Add/Remove, use the commands above.</i>"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

    async def cmd_list_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE, reply_message=None):
        print("[LOG] /list_profiles command received")
        target = reply_message if reply_message else update.message
        if not self.monitored_profiles:
            print("[LOG] No profiles are currently being monitored.")
            await target.reply_text("📝 No profiles are currently being monitored.")
        else:
            print(f"[LOG] Listing profiles: {self.monitored_profiles}")
            await target.reply_text("👀 Currently monitored profiles:\n" + '\n'.join(f"- {p}" for p in self.monitored_profiles))

    async def cmd_add_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE, username=None):
        print(f"[LOG] /add_profile command received")
        # Accept username directly for button/text reply, or from context.args for command
        if hasattr(context, 'args') and context.args and not username:
            username = context.args[0].strip()
        if username is None:
            print("[LOG] No username provided to add.")
            await update.message.reply_text("Usage: /add_profile <username>")
            return
        if username in self.monitored_profiles:
            print(f"[LOG] {username} is already being monitored.")
            await update.message.reply_text(f"{username} is already being monitored.")
            return
        self.monitored_profiles.append(username)
        save_profiles(self.monitored_profiles)
        print(f"[LOG] Added {username} to monitored profiles.")
        await update.message.reply_text(f"✅ Added {username} to monitored profiles.")

    async def cmd_remove_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE, username=None, reply_message=None):
        # Accept username as argument for inline button callback, fallback to context.args for command
        # reply_message allows sending response to button message
        print(f"[LOG] /remove_profile command received")
        reply_target = reply_message if reply_message is not None else update.message
        if username is None:
            # Called from command, get from context.args
            if not context.args:
                print("[LOG] No username provided to remove.")
                await reply_target.reply_text("Usage: /remove_profile <username>")
                return
            username = context.args[0].strip()
        if username not in self.monitored_profiles:
            print(f"[LOG] {username} is not in the monitored list.")
            await reply_target.reply_text(f"{username} is not in the monitored list.")
            return
        self.monitored_profiles.remove(username)
        save_profiles(self.monitored_profiles)
        print(f"[LOG] Removed {username} from monitored profiles.")
        await reply_target.reply_text(f"❌ Removed {username} from monitored profiles.")

    async def cmd_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE, reply_message=None):
        print("[LOG] /refresh or /start_iteration command received")
        target = reply_message if reply_message else update.message
        await target.reply_text("🔄 Checking all monitored profiles for new stories...")
        # Run scraping as a background task in the main event loop
        asyncio.create_task(self.check_and_send_stories(update, reply_message=target))
    async def text_reply_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Handles replies after Add/Remove button prompt
        text = update.message.text.strip()
        if context.user_data.get('awaiting_add'):
            # Instagram username validation: 30 chars max, only letters, numbers, periods, underscores
            import re
            username_pattern = r'^[A-Za-z0-9._]{1,30}$'
            if text:
                if not re.match(username_pattern, text):
                    await update.message.reply_text("❌ Invalid username. Only letters, numbers, periods, and underscores allowed. Max 30 characters.")
                else:
                    await self.cmd_add_profile(update, context, username=text)
            else:
                await update.message.reply_text("No username provided.")
            context.user_data['awaiting_add'] = False
        elif context.user_data.get('awaiting_remove'):
            if text:
                if text not in self.monitored_profiles:
                    await update.message.reply_text(f"{text} is not in the monitored list.")
                else:
                    self.monitored_profiles.remove(text)
                    save_profiles(self.monitored_profiles)
                    await update.message.reply_text(f"❌ Removed {text} from monitored profiles.")
            else:
                await update.message.reply_text("No username provided.")
            context.user_data['awaiting_remove'] = False

    async def start_sending_worker(self, app):
        print("[LOG] Starting background media sending worker...")
        self.sending_task = asyncio.create_task(self.media_sending_worker())

    async def media_sending_worker(self):
        while True:
            file_path, caption, username, story_id = await self.media_queue.get()
            print(f"[LOG] [PIPE] Sending from queue: {file_path}")
            try:
                sent_success = await self._send_media_from_worker(file_path, caption)
                if sent_success:
                    # Update tracker immediately after successful send
                    last_id = self.stories_tracker.get_last_story_id(username)
                    if last_id is None or int(story_id) > int(last_id or "0"):
                        self.stories_tracker.update_last_story_id(username, story_id)
                        print(f"[LOG] [PIPE] Updated last story ID for @{username} to: {story_id}")
            except Exception as e:
                print(f"[LOG] [PIPE] Error sending from queue: {e}")
            self.media_queue.task_done()

    async def _send_media_from_worker(self, file_path, caption, max_retries=4, doc_retries=2):
        """
        Robust media sending with exponential backoff, fallback to send_document, and DLQ.
        Only returns True if media was sent successfully.
        Prevents duplicate sends if Telegram times out but delivers the video.
        """
        import time
        bot = self.application.bot
        is_video = file_path.lower().endswith(('.mp4', '.mov', '.m4v'))
        attempt = 0
        delay = 5
        last_error = None
        sent_once = False
        # Try send_video with exponential backoff
        while attempt < max_retries and is_video:
            try:
                with open(file_path, 'rb') as video:
                    await bot.send_video(chat_id=self.chat_id, video=video, caption=caption)
                print(f"[LOG] [PIPE] Successfully sent (video): {file_path}")
                sent_once = True
                break
            except Exception as e:
                last_error = str(e)
                print(f"[LOG] [PIPE] Error sending video (attempt {attempt+1}): {e}")
                attempt += 1
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2
        if sent_once:
            return True
        # Fallback to send_document for video
        if is_video:
            doc_attempt = 0
            doc_delay = 10
            while doc_attempt < doc_retries:
                try:
                    with open(file_path, 'rb') as doc:
                        await bot.send_document(chat_id=self.chat_id, document=doc, caption=caption)
                    print(f"[LOG] [PIPE] Successfully sent (document): {file_path}")
                    sent_once = True
                    break
                except Exception as e:
                    last_error = str(e)
                    print(f"[LOG] [PIPE] Error sending document (attempt {doc_attempt+1}): {e}")
                    doc_attempt += 1
                    if doc_attempt < doc_retries:
                        await asyncio.sleep(doc_delay)
                        doc_delay *= 2
        if sent_once:
            return True
        # For images, use send_photo with exponential backoff
        if not is_video:
            attempt = 0
            delay = 5
            while attempt < max_retries:
                try:
                    with open(file_path, 'rb') as photo:
                        await bot.send_photo(chat_id=self.chat_id, photo=photo, caption=caption)
                    print(f"[LOG] [PIPE] Successfully sent (photo): {file_path}")
                    sent_once = True
                    break
                except Exception as e:
                    last_error = str(e)
                    print(f"[LOG] [PIPE] Error sending photo (attempt {attempt+1}): {e}")
                    attempt += 1
                    if attempt < max_retries:
                        await asyncio.sleep(delay)
                        delay *= 2
        if sent_once:
            return True
        # If all attempts fail, log to DLQ
        await bot.send_message(chat_id=self.chat_id, text=f"⚠️ Error sending media: {last_error}")
        self._log_dlq(self.chat_id, file_path, last_error)
        return False

    def _log_dlq(self, chat_id, file_path, error):
        """Log failed send jobs to a persistent DLQ JSON file."""
        import time
        entry = {
            "chat_id": chat_id,
            "file_path": file_path,
            "error": error,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            if os.path.exists(DLQ_FILE):
                with open(DLQ_FILE, "r") as f:
                    dlq = json.load(f)
            else:
                dlq = []
        except Exception:
            dlq = []
        dlq.append(entry)
        with open(DLQ_FILE, "w") as f:
            json.dump(dlq, f, indent=2)

    async def check_and_send_stories(self, update: Update = None, reply_message=None):
        print("[LOG] Starting check_and_send_stories")
        # reply_message is used for button-triggered actions
        target = reply_message if reply_message else (update.message if update else None)
        if not self.monitored_profiles:
            print("[LOG] No profiles to check.")
            if target:
                await target.reply_text("📝 No profiles to check.")
            return
        msg = f"🔍 Starting check for {len(self.monitored_profiles)} profiles..."
        print(f"[LOG] {msg}")
        if target:
            await target.reply_text(msg)
        for username in self.monitored_profiles:
            try:
                print(f"[LOG] Checking @{username}")
                if target:
                    await target.reply_text(f"➡️ Checking @{username}...")
                last_id = self.stories_tracker.get_last_story_id(username)
                print(f"[LOG] Last known story ID for @{username}: {last_id}")
                # Download stories and enqueue each file as soon as it's ready
                async for file_path, story_id in self._download_and_enqueue_stories(username, last_id):
                    if int(story_id) > int(last_id or "0"):
                        await self.media_queue.put((file_path, f"New story from @{username}", username, story_id))
            except Exception as e:
                print(f"[LOG] Error with @{username}: {e}")
                if target:
                    await target.reply_text(f"⚠️ Error with @{username}: {e}")

    async def _download_and_enqueue_stories(self, username, last_id):
        # This async generator yields (file_path, story_id) as soon as each story is downloaded
        async for file_path, story_id in self.downloader.download_user_stories_stream(username, last_known_id=last_id):
            print(f"[LOG] [PIPE] Queueing story {story_id} for @{username}")
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

        async def shutdown_callback(app):
            print("[LOG] Shutting down, cancelling background tasks...")
            tasks = []
            if hasattr(self, 'sending_task') and self.sending_task:
                self.sending_task.cancel()
                tasks.append(self.sending_task)
            if hasattr(self, 'periodic_task') and self.periodic_task:
                self.periodic_task.cancel()
                tasks.append(self.periodic_task)
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            print("[LOG] Background tasks cancelled.")

        self.application.post_init = post_init_callback
        self.application.post_shutdown = shutdown_callback
        self.application.run_polling()

if __name__ == "__main__":
    bot = StoryMonitorBot()
    bot.run()
