import asyncio
import os
import json
import logging
import re
from datetime import datetime
from typing import Optional, Dict, List
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, ContextTypes, 
    CallbackQueryHandler, MessageHandler, filters
)

from src.storage import Storage
from src.config import Config
from src.logger import get_logger

# Load environment variables
load_dotenv()

class InstagramStoryBot:
    """
    Main Telegram bot class for Instagram story monitoring.
    Handles user commands, profile management, and bot interaction.
    """
    
    def __init__(self):
        """Initialize the bot with configuration and storage."""
        self.logger = get_logger()
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = int(os.getenv('TELEGRAM_CHAT_ID'))
        
        if not self.token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in environment")
        
        # Initialize storage and application
        self.storage = Storage()
        self.application = Application.builder().token(self.token).build()
        
        # Bot state management
        self.scraper_running = False
        self.bot_paused = False
        
        # Add command handlers
        self._add_handlers()
        
        self.logger.info("Instagram Story Bot initialized successfully")
    
    def _add_handlers(self):
        """Register all command and callback handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler('start', self.cmd_start))
        self.application.add_handler(CommandHandler('help', self.cmd_help))
        self.application.add_handler(CommandHandler('status', self.cmd_status))
        self.application.add_handler(CommandHandler('refresh', self.cmd_refresh))
        self.application.add_handler(CommandHandler('pause', self.cmd_pause))
        self.application.add_handler(CommandHandler('resume', self.cmd_resume))
        self.application.add_handler(CommandHandler('list_profiles', self.cmd_list_profiles))
        self.application.add_handler(CommandHandler('add_profile', self.cmd_add_profile))
        self.application.add_handler(CommandHandler('remove_profile', self.cmd_remove_profile))
        self.application.add_handler(CommandHandler('menu', self.cmd_menu))
        
        # Callback query handler for inline buttons
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Message handler for text replies
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.text_reply_handler
        ))
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_msg = (
            "👋 <b>Welcome to Instagram Story Monitor Bot!</b>\n\n"
            "I can monitor Instagram profiles and send you their new stories automatically.\n\n"
            "Use /help to see all available commands or /menu for quick actions."
        )
        await update.message.reply_text(welcome_msg, parse_mode=ParseMode.HTML)
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_msg = (
            "<b>🤖 Instagram Story Monitor Bot Help</b>\n\n"
            "<b>📋 Commands:</b>\n"
            "• /start — Welcome message\n"
            "• /help — Show this help message\n"
            "• /status — Show bot status and statistics\n"
            "• /menu — Show interactive menu\n\n"
            "<b>👀 Profile Management:</b>\n"
            "• /add_profile &lt;username&gt; — Add a profile to monitor\n"
            "• /remove_profile &lt;username&gt; — Remove a profile\n"
            "• /list_profiles — List all monitored profiles\n\n"
            "<b>🔄 Scraping Control:</b>\n"
            "• /refresh — Check all profiles now\n"
            "• /pause — Pause automatic scraping\n"
            "• /resume — Resume automatic scraping\n\n"
            "<b>💡 Tips:</b>\n"
            "• The bot automatically checks for new stories every 5 minutes\n"
            "• Use /menu for quick actions with buttons\n"
            "• Check /status to see current bot state\n"
        )
        await update.message.reply_text(help_msg, parse_mode=ParseMode.HTML)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - show bot status and statistics."""
        profiles_data = self.storage.get_profiles(self.chat_id)
        profiles = profiles_data.get(str(self.chat_id), {}).get("profiles", {})
        
        total_profiles = len(profiles)
        active_profiles = sum(1 for p in profiles.values() if p.get("fail_count", 0) < 3)
        
        status_emoji = "⏸️" if self.bot_paused else "▶️"
        scraper_emoji = "🔄" if self.scraper_running else "⏹️"
        
        status_msg = (
            f"<b>📊 Bot Status</b>\n\n"
            f"{status_emoji} <b>Bot State:</b> {'Paused' if self.bot_paused else 'Active'}\n"
            f"{scraper_emoji} <b>Scraper:</b> {'Running' if self.scraper_running else 'Idle'}\n\n"
            f"<b>📈 Statistics:</b>\n"
            f"• Total Profiles: {total_profiles}\n"
            f"• Active Profiles: {active_profiles}\n"
            f"• Failed Profiles: {total_profiles - active_profiles}\n\n"
        )
        
        if profiles:
            status_msg += "<b>👤 Profile Status:</b>\n"
            for username, data in profiles.items():
                fail_count = data.get("fail_count", 0)
                last_check = data.get("last_check")
                if last_check:
                    try:
                        last_check_dt = datetime.fromisoformat(last_check)
                        last_check_str = last_check_dt.strftime("%H:%M")
                    except:
                        last_check_str = "Unknown"
                else:
                    last_check_str = "Never"
                
                status_icon = "✅" if fail_count == 0 else "⚠️" if fail_count < 3 else "❌"
                status_msg += f"{status_icon} @{username} (Last: {last_check_str})\n"
        
        await update.message.reply_text(status_msg, parse_mode=ParseMode.HTML)
    
    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command - show interactive menu."""
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data='refresh'),
                InlineKeyboardButton("📊 Status", callback_data='status')
            ],
            [
                InlineKeyboardButton("👀 List Profiles", callback_data='list_profiles'),
                InlineKeyboardButton("➕ Add Profile", callback_data='add_profile')
            ],
            [
                InlineKeyboardButton("➖ Remove Profile", callback_data='remove_profile'),
                InlineKeyboardButton("⏸️ Pause" if not self.bot_paused else "▶️ Resume", callback_data='pause_resume')
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🎛️ <b>Bot Control Menu</b>\n\nChoose an action:", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    async def cmd_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE, reply_message=None):
        """Handle /refresh command - manually trigger story check."""
        target = reply_message if reply_message else update.message
        
        if self.scraper_running:
            await target.reply_text("🔄 Scraper is already running. Please wait...")
            return
        
        profiles_data = self.storage.get_profiles(self.chat_id)
        profiles = profiles_data.get(str(self.chat_id), {}).get("profiles", {})
        
        if not profiles:
            await target.reply_text("📝 No profiles to check. Add some profiles first using /add_profile.")
            return
        
        await target.reply_text(f"🔄 Starting manual check for {len(profiles)} profiles...")
        
        # Trigger external scraper script
        self._trigger_external_scraper()
    
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command - pause automatic scraping."""
        if self.bot_paused:
            await update.message.reply_text("⏸️ Bot is already paused.")
            return
        
        self.bot_paused = True
        
        # Create pause flag file for the external scraper
        pause_file = os.path.join("data", "bot_paused.flag")
        os.makedirs("data", exist_ok=True)
        with open(pause_file, 'w') as f:
            f.write(str(int(datetime.now().timestamp())))
        
        await update.message.reply_text("⏸️ <b>Bot paused.</b>\n\nAutomatic scraping is now disabled. Use /resume to continue.", parse_mode=ParseMode.HTML)
        self.logger.info("Bot paused by user command")
    
    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command - resume automatic scraping."""
        if not self.bot_paused:
            await update.message.reply_text("▶️ Bot is already running.")
            return
        
        self.bot_paused = False
        
        # Remove pause flag file
        pause_file = os.path.join("data", "bot_paused.flag")
        try:
            os.remove(pause_file)
        except FileNotFoundError:
            pass
        
        await update.message.reply_text("▶️ <b>Bot resumed.</b>\n\nAutomatic scraping is now enabled.", parse_mode=ParseMode.HTML)
        self.logger.info("Bot resumed by user command")
    
    async def cmd_list_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE, reply_message=None):
        """Handle /list_profiles command."""
        target = reply_message if reply_message else update.message
        
        profiles_data = self.storage.get_profiles(self.chat_id)
        profiles = profiles_data.get(str(self.chat_id), {}).get("profiles", {})
        
        if not profiles:
            await target.reply_text("📝 No profiles are currently being monitored.")
            return
        
        profile_list = "👀 <b>Monitored Profiles:</b>\n\n"
        for username, data in profiles.items():
            fail_count = data.get("fail_count", 0)
            status_icon = "✅" if fail_count == 0 else "⚠️" if fail_count < 3 else "❌"
            profile_list += f"{status_icon} @{username}\n"
        
        await target.reply_text(profile_list, parse_mode=ParseMode.HTML)
    
    async def cmd_add_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE, username=None):
        """Handle /add_profile command."""
        if username is None and context.args:
            username = context.args[0].strip()
        
        if username is None:
            await update.message.reply_text("Usage: /add_profile &lt;username&gt;\n\nExample: /add_profile israel_bidur", parse_mode=ParseMode.HTML)
            return
        
        # Validate Instagram username
        if not self._validate_username(username):
            await update.message.reply_text(
                "❌ Invalid username format.\n\n"
                "Instagram usernames can only contain:\n"
                "• Letters (a-z, A-Z)\n"
                "• Numbers (0-9)\n"
                "• Periods (.)\n"
                "• Underscores (_)\n"
                "• Max 30 characters"
            )
            return
        
        # Check if already monitored
        profiles_data = self.storage.get_profiles(self.chat_id)
        profiles = profiles_data.get(str(self.chat_id), {}).get("profiles", {})
        
        if username in profiles:
            await update.message.reply_text(f"👀 @{username} is already being monitored.")
            return
        
        # Add profile
        if self.storage.add_profile(self.chat_id, username):
            await update.message.reply_text(f"✅ Added @{username} to monitored profiles.")
            self.logger.info(f"Added profile {username} for chat {self.chat_id}")
        else:
            await update.message.reply_text("❌ Failed to add profile. Please try again.")
    
    async def cmd_remove_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE, username=None, reply_message=None):
        """Handle /remove_profile command."""
        target = reply_message if reply_message else update.message
        
        if username is None and context.args:
            username = context.args[0].strip()
        
        if username is None:
            await target.reply_text("Usage: /remove_profile &lt;username&gt;\n\nExample: /remove_profile israel_bidur", parse_mode=ParseMode.HTML)
            return
        
        # Check if profile exists
        profiles_data = self.storage.get_profiles(self.chat_id)
        profiles = profiles_data.get(str(self.chat_id), {}).get("profiles", {})
        
        if username not in profiles:
            await target.reply_text(f"❌ @{username} is not in the monitored list.")
            return
        
        # Remove profile
        if self.storage.remove_profile(self.chat_id, username):
            await target.reply_text(f"➖ Removed @{username} from monitored profiles.")
            self.logger.info(f"Removed profile {username} for chat {self.chat_id}")
        else:
            await target.reply_text("❌ Failed to remove profile. Please try again.")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks."""
        query = update.callback_query
        await query.answer()
        
        message = query.message
        data = query.data
        
        if data == 'refresh':
            await self.cmd_refresh(update, context, reply_message=message)
        elif data == 'status':
            await self.cmd_status(update, context)
        elif data == 'list_profiles':
            await self.cmd_list_profiles(update, context, reply_message=message)
        elif data == 'add_profile':
            await message.reply_text("What is the Instagram username to add?\n\nSend me the username (without @):")
            context.user_data['awaiting_add'] = True
        elif data == 'remove_profile':
            await self._show_remove_profile_menu(message)
        elif data == 'pause_resume':
            if self.bot_paused:
                await self.cmd_resume(update, context)
            else:
                await self.cmd_pause(update, context)
        elif data.startswith('remove_profile:'):
            username = data.split(':', 1)[1]
            await self.cmd_remove_profile(update, context, username=username, reply_message=message)
    
    async def text_reply_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (for profile addition)."""
        text = update.message.text.strip()
        
        if context.user_data.get('awaiting_add'):
            context.user_data['awaiting_add'] = False
            await self.cmd_add_profile(update, context, username=text)
    
    async def _show_remove_profile_menu(self, message):
        """Show inline keyboard for profile removal."""
        profiles_data = self.storage.get_profiles(self.chat_id)
        profiles = profiles_data.get(str(self.chat_id), {}).get("profiles", {})
        
        if not profiles:
            await message.reply_text("📝 No profiles are currently being monitored.")
            return
        
        keyboard = [
            [InlineKeyboardButton(f"@{username}", callback_data=f'remove_profile:{username}')]
            for username in profiles.keys()
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("Select a profile to remove:", reply_markup=reply_markup)
    
    def _validate_username(self, username: str) -> bool:
        """Validate Instagram username format."""
        if not username or len(username) > 30:
            return False
        
        pattern = r'^[A-Za-z0-9._]{1,30}$'
        return bool(re.match(pattern, username))
    
    def _trigger_external_scraper(self):
        """Trigger the external scraper script."""
        # This could be implemented as a file flag or database flag
        # that the run_scraper.py checks for manual triggers
        flag_file = os.path.join("data", "manual_trigger.flag")
        with open(flag_file, 'w') as f:
            f.write(str(int(datetime.now().timestamp())))
        self.logger.info("Manual scraper trigger created")
    
    def is_paused(self) -> bool:
        """Check if bot is paused."""
        return self.bot_paused
    
    async def send_story_notification(self, username: str, file_path: str, story_id: str):
        """
        Send a story notification to the chat.
        This method is called by the external scraper.
        """
        if self.bot_paused:
            self.logger.info(f"Bot is paused, skipping notification for {username}")
            return False
        
        try:
            is_video = file_path.lower().endswith(('.mp4', '.mov', '.m4v', '.webm'))
            caption = f"📸 New story from @{username}"
            
            bot = self.application.bot
            
            if is_video:
                with open(file_path, 'rb') as video:
                    await bot.send_video(
                        chat_id=self.chat_id,
                        video=video,
                        caption=caption,
                        supports_streaming=True
                    )
            else:
                with open(file_path, 'rb') as photo:
                    await bot.send_photo(
                        chat_id=self.chat_id,
                        photo=photo,
                        caption=caption
                    )
            
            self.logger.info(f"Successfully sent story {story_id} from {username}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send story {story_id} from {username}: {e}")
            self.storage.add_to_dlq(self.chat_id, username, str(e))
            return False
    
    def run(self):
        """Start the bot."""
        self.logger.info("Starting Instagram Story Bot...")
        
        try:
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            self.logger.error(f"Bot error: {e}")
            raise

if __name__ == "__main__":
    bot = InstagramStoryBot()
    bot.run()
