"""
Instagram Story Monitor Bot with anti-ban measures
This module implements a Telegram bot that safely monitors Instagram stories
and forwards them to a Telegram chat while avoiding detection.
"""

import asyncio
import os
from telegram import Bot
from datetime import datetime, timedelta
import traceback
import sys
from dotenv import load_dotenv
from downloader import InstagramDownloader
from stories_tracker import StoriesTracker
import random

# Load environment variables
load_dotenv()

class StoryMonitorBot:
    def __init__(self):
        self.bot = Bot(os.getenv('TELEGRAM_BOT_TOKEN'))
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.downloader = InstagramDownloader()
        self.stories_tracker = StoriesTracker()  # Initialize the new tracker
        self.monitored_profiles = os.getenv('MONITORED_PROFILES').split(',')
        self.error_count = 0
        self.last_error_time = None
        self.base_check_interval = 300  # 5 minutes
        self.max_check_interval = 3600  # 1 hour
        self.current_interval = self.base_check_interval

    async def send_message(self, text):
        await self.bot.send_message(chat_id=self.chat_id, text=text)

    async def send_media(self, file_path):
        """
        Send a media file (photo or video) to the configured Telegram chat.
        
        Args:
            file_path (str or Path): Path to the media file to send
            
        Returns:
            bool: True if send was successful, False otherwise
        """
        try:
            # Convert path to string if it's a Path object
            file_path_str = str(file_path)
            
            if file_path_str.endswith(('.mp4', '.mov')):
                with open(file_path_str, 'rb') as video:
                    await self.bot.send_video(chat_id=self.chat_id, video=video)
            else:
                with open(file_path_str, 'rb') as photo:
                    await self.bot.send_photo(chat_id=self.chat_id, photo=photo)
            return True
        except Exception as e:
            await self.send_message(f"❌ Error sending media: {str(e)}")
            return False

    def _handle_error(self):
        """Implement exponential backoff for errors"""
        current_time = datetime.now()
        
        if self.last_error_time:
            # Reset error count if last error was more than 1 hour ago
            if current_time - self.last_error_time > timedelta(hours=1):
                self.error_count = 0
                self.current_interval = self.base_check_interval
            else:
                self.error_count += 1
                # Exponential backoff with random jitter
                self.current_interval = min(
                    self.base_check_interval * (2 ** self.error_count) + random.randint(0, 60),
                    self.max_check_interval
                )
        
        self.last_error_time = current_time
        return self.current_interval

    async def check_and_send_stories(self):
        try:
            total_new_stories = 0
            await self.send_message("🔍 Starting story check...")

            # Randomize profile order to appear more natural
            check_profiles = self.monitored_profiles.copy()
            random.shuffle(check_profiles)

            for username in check_profiles:
                try:
                    # Add random delay between checking different profiles
                    await asyncio.sleep(random.uniform(1, 3))
                    
                    # Get last story timestamp for this user
                    last_timestamp = self.stories_tracker.get_last_story_time(username)
                    
                    # Download stories newer than last timestamp
                    downloaded_files, latest_timestamp = self.downloader.download_user_stories(
                        username, 
                        last_timestamp=last_timestamp
                    )
                    
                    for file_path, story_timestamp in downloaded_files:
                        if await self.send_media(file_path):
                            total_new_stories += 1
                            print(f"Sent story from @{username}")
                            # Update the last story timestamp for this user
                            self.stories_tracker.update_last_story_time(username, story_timestamp)
                        # Add small delay between sending media
                        await asyncio.sleep(random.uniform(0.5, 1.5))

                except Exception as e:
                    error_msg = f"❌ Error processing stories from @{username}: {str(e)}"
                    print(f"Error processing stories from @{username}: {str(e)}")
                    await self.send_message(error_msg)

            # Calculate next check time
            jitter = random.uniform(-30, 30)
            next_interval = self.current_interval + jitter
            next_check_time = datetime.now() + timedelta(seconds=next_interval)
            next_check_str = next_check_time.strftime("%H:%M:%S")

            # Send summary message with next check time
            if total_new_stories == 0:
                await self.send_message(f"ℹ️ No new stories found\n⏰ Next check at {next_check_str}")
            else:
                await self.send_message(f"📤 Sent {total_new_stories} new stories\n⏰ Next check at {next_check_str}")

            # Reset error count on successful run
            self.error_count = 0
            self.current_interval = self.base_check_interval
            return next_interval

        except Exception as e:
            error_msg = f"❌ Error during story check: {str(e)}"
            print(f"Error during story check: {str(e)}")
            await self.send_message(error_msg)
            next_interval = self._handle_error()
            next_check_time = datetime.now() + timedelta(seconds=next_interval)
            next_check_str = next_check_time.strftime("%H:%M:%S")
            await self.send_message(f"⏰ Will try again at {next_check_str}")
            return next_interval

    async def cleanup(self):
        try:
            self.downloader.cleanup_files()
            # Clean up old stories from tracker (stories older than 7 days)
            self.stories_tracker.cleanup_old_stories(days=7)
            print("Cleanup completed")
        except Exception as e:
            print(f"Error during cleanup: {str(e)}")

    async def run(self):
        try:
            print("Instagram Story Monitor Bot started")
            await self.send_message("🤖 Instagram Story Monitor Bot started")

            # Initial login to Instagram
            self.downloader.login()
            await self.send_message("✅ Successfully logged into Instagram")

            while True:
                next_interval = await self.check_and_send_stories()
                # Add random jitter to the interval
                jitter = random.uniform(-30, 30)
                await asyncio.sleep(self.current_interval + jitter)
                
                # Run cleanup every 24 hours
                if datetime.now().hour == 0:
                    await self.cleanup()

        except Exception as e:
            error_msg = f"❌ Critical error in main: {str(e)}\n{traceback.format_exc()}"
            print(f"Critical error in main: {str(e)}\n{traceback.format_exc()}")
            await self.send_message(error_msg)
            sys.exit(1)

if __name__ == "__main__":
    bot = StoryMonitorBot()
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("Script interrupted by user")
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        print(traceback.format_exc())
        sys.exit(1)