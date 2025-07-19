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
from src.storage import Storage
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
        self.storage = Storage()
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
            if self._is_bot_paused():
                self.logger.info("Bot is paused, skipping scrape")
                return
            
            # Check for manual trigger
            manual_trigger = self._check_manual_trigger()
            
            # Get all profiles to monitor
            all_profiles = self.storage.get_profiles()
            
            if not all_profiles:
                self.logger.info("No profiles to monitor")
                return
            
            # Process each chat's profiles
            for chat_id_str, chat_data in all_profiles.items():
                chat_id = int(chat_id_str)
                profiles = chat_data.get("profiles", {})
                
                if not profiles:
                    continue
                
                self.logger.info(f"Processing {len(profiles)} profiles for chat {chat_id}")
                
                # Process each profile
                for username, profile_data in profiles.items():
                    try:
                        await self._process_profile(chat_id, username, profile_data, manual_trigger)
                    except Exception as e:
                        self.logger.error(f"Error processing profile {username}: {e}")
                        self.storage.update_profile_status(chat_id, username, success=False)
                        self.storage.add_to_dlq(chat_id, username, str(e))
            
            # Clean up manual trigger
            if manual_trigger:
                self._clear_manual_trigger()
            
            self.logger.info("Scraping cycle completed")
            
        except Exception as e:
            self.logger.error(f"Error in process_all_profiles: {e}")
            raise
    
    async def _process_profile(self, chat_id: int, username: str, profile_data: dict, force_check: bool = False):
        """
        Process a single profile for new stories.
        
        Args:
            chat_id: Telegram chat ID
            username: Instagram username
            profile_data: Profile data from storage
            force_check: Whether to force check regardless of timing
        """
        last_story_id = profile_data.get("last_story_id")
        fail_count = profile_data.get("fail_count", 0)
        last_check = profile_data.get("last_check")
        
        # Skip profiles with too many failures unless forced
        if not force_check and fail_count >= 3:
            self.logger.warning(f"Skipping {username} due to {fail_count} consecutive failures")
            return
        
        # Check if we should skip based on timing (avoid too frequent checks)
        if not force_check and last_check:
            try:
                last_check_dt = datetime.fromisoformat(last_check)
                if datetime.now() - last_check_dt < timedelta(minutes=3):
                    self.logger.debug(f"Skipping {username} - checked recently")
                    return
            except:
                pass  # Continue if datetime parsing fails
        
        self.logger.info(f"Checking stories for {username} (last_id: {last_story_id})")
        
        # Download stories with retry logic
        stories, newest_id = await self._download_with_retry(username, last_story_id)
        
        if stories is None:
            # Download failed after all retries
            self.storage.update_profile_status(chat_id, username, success=False)
            return
        
        # Send new stories
        sent_count = 0
        for item in stories:
            try:
                # Ensure we have the right data structure
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    file_path, story_id = item[0], item[1]
                else:
                    self.logger.error(f"Invalid story data structure: {item}")
                    continue
                
                if await self._send_story_with_retry(chat_id, username, file_path, story_id):
                    sent_count += 1
                    # Update last story ID after successful send
                    self.storage.update_profile_status(chat_id, username, last_story_id=story_id, success=True)
                else:
                    self.logger.error(f"Failed to send story {story_id} for {username}")
            except Exception as e:
                self.logger.error(f"Error processing story item {item}: {e}")
                continue
        
        # Update profile status
        if sent_count > 0:
            self.logger.info(f"Successfully sent {sent_count} new stories for {username}")
        else:
            self.logger.info(f"No new stories found for {username}")
        
        # Mark as successful check
        self.storage.update_profile_status(chat_id, username, success=True)
    
    async def _download_with_retry(self, username: str, last_story_id: Optional[str]) -> Tuple[Optional[List], Optional[str]]:
        """
        Download stories with exponential backoff retry.
        
        Returns:
            Tuple of (stories_list, newest_id) or (None, None) if failed
        """
        for attempt in range(self.max_retries):
            try:
                self.logger.debug(f"Download attempt {attempt + 1} for {username}")
                
                stories, newest_id = await self.downloader.download_user_stories(username, last_story_id)
                
                self.logger.info(f"Downloaded {len(stories)} new stories for {username}")
                return stories, newest_id
                
            except Exception as e:
                self.logger.warning(f"Download attempt {attempt + 1} failed for {username}: {e}")
                
                if attempt < self.max_retries - 1:
                    # Exponential backoff: 5s, 10s, 20s
                    wait_time = self.retry_delay * (2 ** attempt)
                    self.logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"All download attempts failed for {username}")
        
        return None, None
    
    async def _send_story_with_retry(self, chat_id: int, username: str, file_path: str, story_id: str) -> bool:
        """
        Send a story to Telegram with retry logic.
        
        Returns:
            bool: True if successful, False otherwise
        """
        from telegram import Bot
        
        bot = Bot(token=self.bot_token)
        
        for attempt in range(self.max_retries):
            try:
                is_video = file_path.lower().endswith(('.mp4', '.mov', '.m4v', '.webm'))
                caption = f"📸 New story from @{username}"
                
                if is_video:
                    with open(file_path, 'rb') as video:
                        await bot.send_video(
                            chat_id=chat_id,
                            video=video,
                            caption=caption,
                            supports_streaming=True,
                            read_timeout=30,
                            write_timeout=30
                        )
                else:
                    with open(file_path, 'rb') as photo:
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=caption,
                            read_timeout=30,
                            write_timeout=30
                        )
                
                self.logger.info(f"Successfully sent story {story_id} from {username}")
                return True
                
            except Exception as e:
                self.logger.warning(f"Send attempt {attempt + 1} failed for story {story_id}: {e}")
                
                if attempt < self.max_retries - 1:
                    wait_time = 2 * (attempt + 1)  # 2s, 4s, 6s
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"All send attempts failed for story {story_id}")
                    self.storage.add_to_dlq(chat_id, username, f"Failed to send story: {e}")
        
        return False
    
    def _is_bot_paused(self) -> bool:
        """Check if the bot is paused."""
        pause_file = os.path.join("data", "bot_paused.flag")
        return os.path.exists(pause_file)
    
    def _check_manual_trigger(self) -> bool:
        """Check if a manual trigger was requested."""
        trigger_file = os.path.join("data", "manual_trigger.flag")
        
        if not os.path.exists(trigger_file):
            return False
        
        try:
            # Check if trigger is recent (within 1 hour)
            with open(trigger_file, 'r') as f:
                timestamp = int(f.read().strip())
            
            trigger_time = datetime.fromtimestamp(timestamp)
            if datetime.now() - trigger_time < timedelta(hours=1):
                self.logger.info("Manual trigger detected")
                return True
            else:
                # Old trigger, remove it
                os.remove(trigger_file)
                return False
                
        except Exception as e:
            self.logger.warning(f"Error checking manual trigger: {e}")
            # Remove invalid trigger file
            try:
                os.remove(trigger_file)
            except:
                pass
            return False
    
    def _clear_manual_trigger(self):
        """Clear the manual trigger flag."""
        trigger_file = os.path.join("data", "manual_trigger.flag")
        try:
            os.remove(trigger_file)
            self.logger.info("Manual trigger cleared")
        except FileNotFoundError:
            pass
        except Exception as e:
            self.logger.warning(f"Error clearing manual trigger: {e}")

async def main():
    """Main entry point for the scraper."""
    try:
        scraper = StoryScraper()
        await scraper.process_all_profiles()
    except Exception as e:
        logging.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    # Set up logging for the script
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    asyncio.run(main())
