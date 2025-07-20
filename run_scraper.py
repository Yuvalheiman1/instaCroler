import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.downloader import AnonyigDownloader
from src.database import db
from src.config import Config
from src.logger import get_logger

# Load environment variables
load_dotenv()

class StoryScraper:
    """
    Handles the scheduled scraping of Instagram stories.
    Runs as a separate process via Railway Cron.
    """
    
    def __init__(self):
        """Initialize the scraper with configuration."""
        self.logger = get_logger()
        self.db = db
        self.downloader = AnonyigDownloader()
        self.chat_id = int(os.getenv('TELEGRAM_CHAT_ID'))
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        
        if not self.chat_id or not self.bot_token:
            raise ValueError("TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN must be set")
        
        self.max_retries = Config.DOWNLOAD_SETTINGS.get('max_retries', 3)
        self.retry_delay = Config.DOWNLOAD_SETTINGS.get('retry_delay', 5)
        
        self.logger.info("Story Scraper initialized")
    
    async def process_all_profiles(self):
        """
        Main entry point for processing all monitored profiles.
        This is called by Railway Cron every 5 minutes.
        """
        try:
            # Check if bot is paused
            if self.db.is_paused():
                self.logger.info("Bot is paused, skipping scrape")
                return
            
            # Get all profiles to monitor
            all_profiles = self.db.get_all_profiles()
            
            if not all_profiles:
                self.logger.info("No profiles to monitor")
                return
            
            # Process each chat's profiles
            for chat_id_str, profiles in all_profiles.items():
                chat_id = int(chat_id_str)
                
                if not profiles:
                    continue
                
                self.logger.info(f"Processing {len(profiles)} profiles for chat {chat_id}")
                
                # Process each profile
                for username, profile_data in profiles.items():
                    try:
                        await self._process_profile(chat_id, username, profile_data)
                    except Exception as e:
                        self.logger.error(f"Error processing profile {username}: {e}")
                        self.db.add_to_dlq({"chat_id": chat_id, "username": username, "error": str(e)})
            
            self.logger.info("Scraping cycle completed")
            
        except Exception as e:
            self.logger.error(f"Error in process_all_profiles: {e}")
            raise
    
    async def _process_profile(self, chat_id: int, username: str, profile_data: dict):
        """
        Process a single profile for new stories.
        
        Args:
            chat_id: Telegram chat ID
            username: Instagram username
            profile_data: Profile data from the database
        """
        last_seen_story_id = profile_data.get("last_story_id")
        self.logger.info(f"Checking for new stories for '{username}' (last seen: {last_seen_story_id})...")
        
        try:
            # Download stories, passing the last seen ID to the downloader
            media_items = await self.downloader.download_user_stories(username, last_seen_story_id)
            
            if not media_items:
                self.logger.info(f"No new stories found for '{username}'.")
                return
            
            self.logger.info(f"Found {len(media_items)} new stories for '{username}'.")
            
            # Send stories to Telegram and get the new last story ID
            new_last_story_id = None
            for item in media_items:
                await self._send_media_to_telegram(chat_id, username, item)
                new_last_story_id = item.get("id") # Assume the last item's ID is the latest
            
            # Update the last story ID in the database
            if new_last_story_id:
                self.db.update_last_story_id(chat_id, username, new_last_story_id)
                self.logger.info(f"Updated last story ID for '{username}' to {new_last_story_id}")
                
        except Exception as e:
            self.logger.error(f"An unexpected error occurred while processing {username}: {e}")
            self.db.add_to_dlq({
                "chat_id": chat_id,
                "username": username,
                "error": f"Failed during processing: {e}"
            })

    async def _send_media_to_telegram(self, chat_id: int, username: str, media_item: dict):
        """
        Send a downloaded media item to the specified Telegram chat.
        
        Args:
            chat_id: The Telegram chat ID.
            username: The Instagram username.
            media_item: A dictionary containing media type and path.
        """
        media_type = media_item.get("type")
        media_path = media_item.get("path")
        
        if not media_type or not media_path:
            self.logger.warning(f"Missing media type or path for item from {username}. Skipping.")
            return
            
        caption = f"New story from <b>{username}</b>"
        
        for attempt in range(self.max_retries):
            try:
                self.logger.info(f"Sending {media_type} from {username} to chat {chat_id}. Attempt {attempt + 1}.")
                
                if media_type == 'image':
                    await self.downloader.bot.send_photo(
                        chat_id=chat_id,
                        photo=open(media_path, 'rb'),
                        caption=caption,
                        parse_mode='HTML'
                    )
                elif media_type == 'video':
                    await self.downloader.bot.send_video(
                        chat_id=chat_id,
                        video=open(media_path, 'rb'),
                        caption=caption,
                        parse_mode='HTML'
                    )
                
                self.logger.info(f"Successfully sent {media_type} from {username}.")
                
                # Clean up the downloaded file
                try:
                    os.remove(media_path)
                    self.logger.info(f"Cleaned up file: {media_path}")
                except OSError as e:
                    self.logger.error(f"Error cleaning up file {media_path}: {e}")
                
                return  # Success, exit the loop
                
            except Exception as e:
                self.logger.error(f"Failed to send {media_type} from {username} (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                else:
                    self.logger.error(f"Max retries reached for sending {media_type} from {username}. Adding to DLQ.")
                    self.db.add_to_dlq({
                        "chat_id": chat_id,
                        "username": username,
                        "media_path": media_path,
                        "error": f"Failed to send to Telegram: {e}"
                    })

async def main():
    """Main function to run the scraper."""
    scraper = StoryScraper()
    try:
        await scraper.downloader.start_browser()
        await scraper.process_all_profiles()
    except Exception as e:
        scraper.logger.critical(f"A critical error occurred: {e}")
    finally:
        await scraper.downloader.close_browser()
        scraper.logger.info("Scraper run finished.")

if __name__ == "__main__":
    asyncio.run(main())
