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

from src.database import db
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
        self.db = db
        self.application = Application.builder().token(self.token).build()
        
        # Bot state management
        self.scraper_running = False
        
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
        
        # Handle both direct message commands and callback queries from buttons
        if hasattr(update, 'callback_query') and update.callback_query:
            # Called from button press
            await update.callback_query.message.reply_text(help_msg, parse_mode=ParseMode.HTML)
        else:
            # Called from direct command
            await update.message.reply_text(help_msg, parse_mode=ParseMode.HTML)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - show bot status and statistics."""
        profiles_data = self.db.get_all_profiles()
        total_profiles = sum(len(p) for p in profiles_data.values())
        
        paused_status = "Paused ⏸️" if self.db.is_paused() else "Running ▶️"
        
        status_msg = (
            f"<b>🤖 Bot Status</b>\n\n"
            f"• <b>Monitoring Status:</b> {paused_status}\n"
            f"• <b>Total Profiles:</b> {total_profiles}\n"
            f"• <b>Monitored Chats:</b> {len(profiles_data)}\n"
        )
        
        # Handle both direct message commands and callback queries from buttons
        if hasattr(update, 'callback_query') and update.callback_query:
            # Called from button press
            await update.callback_query.message.reply_text(status_msg, parse_mode=ParseMode.HTML)
        else:
            # Called from direct command
            await update.message.reply_text(status_msg, parse_mode=ParseMode.HTML)
    
    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show an interactive menu."""
        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data='status')],
            [
                InlineKeyboardButton("➕ Add Profile", callback_data='add_profile_prompt'),
                InlineKeyboardButton("➖ Remove Profile", callback_data='remove_profile_prompt')
            ],
            [InlineKeyboardButton("📜 List Profiles", callback_data='list_profiles')],
            [
                InlineKeyboardButton("⏸️ Pause", callback_data='pause'),
                InlineKeyboardButton("▶️ Resume", callback_data='resume')
            ],
            [InlineKeyboardButton("🔄 Refresh Now", callback_data='refresh')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('<b>⚙️ Bot Menu</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    async def cmd_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE, reply_message=None):
        """Handle /refresh command - manually trigger story check."""
        # Handle both direct message commands and callback queries from buttons
        if reply_message:
            target = reply_message
        elif hasattr(update, 'callback_query') and update.callback_query:
            # Called from button press
            target = update.callback_query.message
        else:
            # Called from direct command
            target = update.message
        
        if self.scraper_running:
            await target.reply_text("🔄 Scraper is already running. Please wait...")
            return
        
        profiles_data = self.db.get_all_profiles()
        profiles = profiles_data.get(str(self.chat_id), [])
        
        if not profiles:
            await target.reply_text("📝 No profiles to check. Add some profiles first using /add_profile.")
            return
        
        await target.reply_text(f"🔄 Starting manual check for {len(profiles)} profiles...")
        
        # Trigger external scraper script
        self._trigger_external_scraper()
    
    async def cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command."""
        self.db.pause()
        self.logger.info("Scraping has been paused.")
        await update.message.reply_text("✅ Automatic scraping has been paused.")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        self.db.resume()
        self.logger.info("Scraping has been resumed.")
        await update.message.reply_text("▶️ Automatic scraping has been resumed.")

    async def cmd_list_profiles(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /list_profiles command."""
        # Handle both direct message commands and callback queries from buttons
        if hasattr(update, 'callback_query') and update.callback_query:
            # Called from button press
            chat_id = str(update.callback_query.message.chat_id)
            message_to_reply = update.callback_query.message
        else:
            # Called from direct command
            chat_id = str(update.message.chat_id)
            message_to_reply = update.message
            
        profiles = self.db.get_all_profiles().get(chat_id, {})
        
        if not profiles:
            await message_to_reply.reply_text("No profiles are being monitored for this chat.")
            return
            
        message = "<b>Monitored Profiles:</b>\n"
        for username, data in profiles.items():
            last_story_id = data.get('last_story_id', 'N/A')
            message += f"- <code>{username}</code> (Last story: {last_story_id})\n"
            
        await message_to_reply.reply_text(message, parse_mode=ParseMode.HTML)

    async def cmd_add_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /add_profile command."""
        if not context.args:
            await update.message.reply_text("Please provide a username. Usage: /add_profile <username>")
            return
        
        username = context.args[0].lower()
        chat_id = str(update.message.chat_id)
        
        if self.db.add_profile(chat_id, username):
            self.logger.info(f"Added profile '{username}' for chat {chat_id}")
            await update.message.reply_text(f"✅ Profile <code>{username}</code> added successfully.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"⚠️ Profile <code>{username}</code> is already being monitored.", parse_mode=ParseMode.HTML)

    async def cmd_remove_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /remove_profile command."""
        if not context.args:
            await update.message.reply_text("Please provide a username. Usage: /remove_profile <username>")
            return
            
        username = context.args[0].lower()
        chat_id = str(update.message.chat_id)
        
        if self.db.remove_profile(chat_id, username):
            self.logger.info(f"Removed profile '{username}' for chat {chat_id}")
            await update.message.reply_text(f"🗑️ Profile <code>{username}</code> removed successfully.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ Profile <code>{username}</code> not found in the monitored list.", parse_mode=ParseMode.HTML)

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show an interactive menu."""
        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data='status')],
            [
                InlineKeyboardButton("➕ Add Profile", callback_data='add_profile_prompt'),
                InlineKeyboardButton("➖ Remove Profile", callback_data='remove_profile_prompt')
            ],
            [InlineKeyboardButton("📜 List Profiles", callback_data='list_profiles')],
            [
                InlineKeyboardButton("⏸️ Pause", callback_data='pause'),
                InlineKeyboardButton("▶️ Resume", callback_data='resume')
            ],
            [InlineKeyboardButton("🔄 Refresh Now", callback_data='refresh')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('<b>⚙️ Bot Menu</b>', reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all inline button presses."""
        query = update.callback_query
        await query.answer()  # Acknowledge the button press

        command = query.data

        if command == 'status':
            await self.cmd_status(update, context)
        elif command == 'add_profile_prompt':
            await query.message.reply_text("Please type the username you want to add.")
            context.user_data['next_action'] = 'add_profile'
        elif command == 'remove_profile_prompt':
            await query.message.reply_text("Please type the username you want to remove.")
            context.user_data['next_action'] = 'remove_profile'
        elif command == 'list_profiles':
            # Pass the entire update object to the command handler
            await self.cmd_list_profiles(update, context)
        elif command == 'pause':
            self.db.pause()
            await query.edit_message_text(text="✅ Automatic scraping has been paused.")
        elif command == 'resume':
            self.db.resume()
            await query.edit_message_text(text="▶️ Automatic scraping has been resumed.")
        elif command == 'refresh':
            await self.cmd_refresh(update, context)

    async def text_reply_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text replies for adding/removing profiles after a prompt."""
        next_action = context.user_data.get('next_action')
        if not next_action:
            return

        username = update.message.text.lower()
        chat_id = str(update.message.chat_id)
        
        # Reset the action
        del context.user_data['next_action']

        if next_action == 'add_profile':
            if self.db.add_profile(chat_id, username):
                self.logger.info(f"Added profile '{username}' for chat {chat_id}")
                await update.message.reply_text(f"✅ Profile <code>{username}</code> added successfully.", parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"⚠️ Profile <code>{username}</code> is already being monitored.", parse_mode=ParseMode.HTML)
        
        elif next_action == 'remove_profile':
            if self.db.remove_profile(chat_id, username):
                self.logger.info(f"Removed profile '{username}' for chat {chat_id}")
                await update.message.reply_text(f"🗑️ Profile <code>{username}</code> removed successfully.", parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"❌ Profile <code>{username}</code> not found in the monitored list.", parse_mode=ParseMode.HTML)

    async def get_bot_status(self) -> str:
        """Get a formatted status string for the bot."""
        profiles_data = self.db.get_all_profiles()
        total_profiles = sum(len(p) for p in profiles_data.values())
        
        paused_status = "Paused ⏸️" if self.db.is_paused() else "Running ▶️"
        
        status_msg = (
            f"<b>🤖 Bot Status</b>\n\n"
            f"• <b>Monitoring Status:</b> {paused_status}\n"
            f"• <b>Total Profiles:</b> {total_profiles}\n"
            f"• <b>Monitored Chats:</b> {len(profiles_data)}\n"
        )
        return status_msg

    async def run_scraper_manually(self, chat_id: int):
        """
        Triggers a manual run of the scraper for a specific chat.
        This is a placeholder for the actual scraper logic.
        """
        self.logger.info(f"Manual scraper run triggered for chat_id: {chat_id}")
        
        # In a real implementation, you would trigger the scraper script here.
        # For now, we'll just send a message.
        await self.application.bot.send_message(
            chat_id=chat_id,
            text="⚙️ Manual refresh started... I will check all your monitored profiles now."
        )
        
        # This part should ideally be handled by a separate process
        # to avoid blocking the bot.
        try:
            # Simulate running the scraper
            # In a real scenario, you might use subprocess or a task queue
            # For simplicity, we'll just log it.
            self.logger.info("Simulating scraper run...")
            
            # Example: Get profiles for this chat and "scrape"
            profiles = self.db.get_all_profiles().get(str(chat_id), {})
            if profiles:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"Found {len(profiles)} profiles to check: {', '.join(profiles.keys())}"
                )
            else:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text="No profiles to check."
                )
            
            await self.application.bot.send_message(
                chat_id=chat_id,
                text="✅ Manual refresh complete."
            )
        except Exception as e:
            self.logger.error(f"Error during manual scraper run: {e}")
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=f"❌ An error occurred during the refresh: {e}"
            )

    def run(self):
        """Start the bot's polling loop."""
        self.logger.info("Bot is starting to poll for updates...")
        self.application.run_polling()

if __name__ == '__main__':
    bot = InstagramStoryBot()
    bot.run()
