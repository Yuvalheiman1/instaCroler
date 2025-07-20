import asyncio
import os
import sys
import time
import logging
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from telegram import Bot

# Load environment variables FIRST
load_dotenv()

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.downloader import AnonyigDownloader, ConcurrentDownloader
from src.database import db
from src.config import Config
from src.logger import get_logger

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
        self.concurrent_downloader = ConcurrentDownloader()
        self.use_concurrent = True  # Flag to enable/disable concurrent processing
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN must be set")
        
        self.bot = Bot(token=self.bot_token)
        self.max_retries = Config.DOWNLOAD_SETTINGS.get('max_retries', 3)
        
        self.logger.info("Story Scraper initialized")
    
    def set_concurrent_mode(self, use_concurrent: bool):
        """
        Enable or disable concurrent processing.
        
        Args:
            use_concurrent: True to use concurrent processing, False for sequential
        """
        self.use_concurrent = use_concurrent
        mode = "concurrent" if use_concurrent else "sequential"
        self.logger.info(f"Download mode set to: {mode}")
    
    def set_max_workers(self, max_workers: int):
        """
        Set the maximum number of concurrent workers.
        
        Args:
            max_workers: Maximum number of concurrent workers
        """
        self.concurrent_downloader = ConcurrentDownloader(max_workers)
        self.logger.info(f"Max workers set to: {max_workers}")
    
    def auto_adjust_concurrency(self, error_rate: float):
        """
        Automatically adjust concurrency settings based on error rate.
        
        Args:
            error_rate: Error rate (0.0 to 1.0)
        """
        if error_rate > 0.5:  # More than 50% errors
            self.logger.warning(f"High error rate ({error_rate:.1%}), disabling concurrent processing")
            self.use_concurrent = False
        elif error_rate > 0.3:  # More than 30% errors
            current_workers = self.concurrent_downloader.max_workers
            new_workers = max(1, current_workers - 1)
            self.logger.warning(f"Moderate error rate ({error_rate:.1%}), reducing workers from {current_workers} to {new_workers}")
            self.set_max_workers(new_workers)
        elif error_rate < 0.1 and not self.use_concurrent:  # Less than 10% errors
            self.logger.info(f"Low error rate ({error_rate:.1%}), re-enabling concurrent processing")
            self.use_concurrent = True
    
    async def process_all_profiles(self):
        """
        Main entry point for processing all monitored profiles.
        This is called by Railway Cron every 5 minutes.
        Uses concurrent downloading for better performance.
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
            
            # Process each chat's profiles concurrently
            for chat_id_str, profiles in all_profiles.items():
                chat_id = int(chat_id_str)
                
                if not profiles:
                    continue
                
                self.logger.info(f"Processing {len(profiles)} profiles for chat {chat_id}")
                
                # Prepare profile data for concurrent downloading
                profile_data = {}
                for username, profile_data_dict in profiles.items():
                    last_seen_story_id = profile_data_dict.get("last_story_id")
                    profile_data[username] = last_seen_story_id
                
                # Choose processing method based on configuration and connection speed
                use_concurrent = (
                    self.use_concurrent and 
                    Config.DOWNLOAD_SETTINGS.get('enable_concurrent', True) and 
                    not Config.DOWNLOAD_SETTINGS.get('slow_connection_mode', False) and  # Disable for slow connections
                    len(profile_data) > 1
                )
                
                if use_concurrent:
                    # Use concurrent downloader for better performance when multiple profiles
                    try:
                        await self._process_profiles_concurrent(chat_id, profile_data)
                    except Exception as e:
                        self.logger.error(f"Error in concurrent processing for chat {chat_id}: {e}")
                        # Fallback to sequential processing
                        self.logger.info("Falling back to sequential processing")
                        await self._process_profiles_sequential(chat_id, profile_data)
                else:
                    # Use sequential processing
                    await self._process_profiles_sequential(chat_id, profile_data)
            
            self.logger.info("Scraping cycle completed")
            
        except Exception as e:
            self.logger.error(f"Error in process_all_profiles: {e}")
            raise
    
    async def _process_profiles_concurrent(self, chat_id: int, profile_data: dict):
        """
        Process multiple profiles concurrently for a single chat.
        
        Args:
            chat_id: Telegram chat ID
            profile_data: Dictionary mapping username to last_seen_story_id
        """
        if not profile_data:
            return
        
        self.logger.info(f"Starting concurrent processing for {len(profile_data)} profiles")
        
        # Download stories for all profiles concurrently
        download_results = await self.concurrent_downloader.download_multiple_profiles(profile_data)
        
        # Process results and send to Telegram
        for username, (stories, newest_id) in download_results.items():
            try:
                if not stories:
                    self.logger.info(f"No new stories found for '{username}'.")
                    continue
                
                self.logger.info(f"Found {len(stories)} new stories for '{username}'.")
                
                # Send stories to Telegram
                for file_path, story_id in stories:
                    media_item = {
                        "file_path": file_path,
                        "id": story_id,
                        "type": "video" if file_path.lower().endswith(('.mp4', '.mov', '.avi', '.webm')) else "image"
                    }
                    await self._send_media_to_telegram(chat_id, username, media_item)
                
                # Update the last story ID in the database
                if newest_id and newest_id != profile_data.get(username, "0"):
                    self.db.update_last_story_id(chat_id, username, newest_id)
                    self.logger.info(f"Updated last story ID for '{username}' to {newest_id}")
                    
            except Exception as e:
                self.logger.error(f"Error processing results for {username}: {e}")
                self.db.add_to_dlq({
                    "chat_id": chat_id,
                    "username": username,
                    "error": str(e),
                    "timestamp": time.time()
                })
    
    async def _process_profiles_sequential(self, chat_id: int, profile_data: dict):
        """
        Process profiles sequentially (one by one) as a fallback.
        
        Args:
            chat_id: Telegram chat ID
            profile_data: Dictionary mapping username to last_seen_story_id
        """
        self.logger.info(f"Processing {len(profile_data)} profiles sequentially")
        
        for username, last_seen_story_id in profile_data.items():
            try:
                await self._process_profile(chat_id, username, {"last_story_id": last_seen_story_id})
            except Exception as profile_error:
                self.logger.error(f"Error processing profile {username}: {profile_error}")
                self.db.add_to_dlq({
                    "chat_id": chat_id, 
                    "username": username, 
                    "error": str(profile_error),
                    "timestamp": time.time()
                })
    
    async def process_profiles_stream(self, chat_id: int, profile_data: dict):
        """
        Process multiple profiles with streaming results for real-time processing.
        
        Args:
            chat_id: Telegram chat ID
            profile_data: Dictionary mapping username to last_seen_story_id
        """
        if not profile_data:
            return
        
        self.logger.info(f"Starting streaming processing for {len(profile_data)} profiles")
        
        profile_newest_ids = {}
        
        # Stream download results as they come in
        async for username, file_path, story_id in self.concurrent_downloader.download_profiles_stream(profile_data):
            try:
                if file_path:  # This is a new story
                    media_item = {
                        "file_path": file_path,
                        "id": story_id,
                        "type": "video" if file_path.lower().endswith(('.mp4', '.mov', '.avi', '.webm')) else "image"
                    }
                    await self._send_media_to_telegram(chat_id, username, media_item)
                    
                    # Track the newest ID for each profile
                    if username not in profile_newest_ids or story_id > profile_newest_ids[username]:
                        profile_newest_ids[username] = story_id
                        
            except Exception as e:
                self.logger.error(f"Error processing streamed result for {username}: {e}")
        
        # Update last story IDs for all profiles
        for username, newest_id in profile_newest_ids.items():
            try:
                if newest_id and newest_id != profile_data.get(username, "0"):
                    self.db.update_last_story_id(chat_id, username, newest_id)
                    self.logger.info(f"Updated last story ID for '{username}' to {newest_id}")
            except Exception as e:
                self.logger.error(f"Error updating last story ID for {username}: {e}")
        
        self.logger.info(f"Streaming processing completed for {len(profile_data)} profiles")
    
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
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=open(media_path, 'rb'),
                        caption=caption,
                        parse_mode='HTML'
                    )
                elif media_type == 'video':
                    await self.bot.send_video(
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
                    await asyncio.sleep(5)  # Fixed 5 second delay between retries
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
        await scraper.process_all_profiles()
    except Exception as e:
        scraper.logger.critical(f"A critical error occurred: {e}")
    finally:
        await scraper.bot.close()
        scraper.logger.info("Scraper run finished.")

if __name__ == "__main__":
    asyncio.run(main())
