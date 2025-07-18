import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Tuple, List
import telegram
from .storage import Storage
from .downloader import AnonyigDownloader

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class StoryScraper:
    def __init__(self):
        """Initialize the story scraper with storage and bot."""
        self.storage = Storage()
        self.downloader = AnonyigDownloader()
        self.bot = telegram.Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
        self.max_retries = 3
        self.retry_delay = 5  # Initial delay in seconds

    async def notify_user(self, chat_id: int, message: str):
        """Send a message to a Telegram chat."""
        try:
            await self.bot.send_message(chat_id=chat_id, text=message)
        except Exception as e:
            logger.error(f"Error sending message to chat {chat_id}: {e}")

    async def download_and_enqueue_stories(
        self,
        username: str,
        queue: asyncio.Queue,
        retry_count: int = 0
    ) -> Tuple[bool, Optional[str]]:
        """
        Download stories for a user and send them to Telegram.
        Implements exponential backoff for retries.
        """
        try:
            # Get last known story ID for this username
            last_story_id = self.storage.get_story_tracker().get(username)
            results, newest_id = await self.downloader.download_user_stories(
                username,
                last_story_id
            )
            if results:
                for file_path, story_id in results:
                    await queue.put((username, file_path, story_id))
                if newest_id:
                    self.storage.update_story_tracker(username, newest_id)
            return True, newest_id
        except Exception as e:
            logger.error(f"Error processing stories for {username}: {e}")
            # Implement exponential backoff
            if retry_count < self.max_retries:
                delay = self.retry_delay * (2 ** retry_count)
                logger.info(f"Retrying {username} in {delay} seconds...")
                await asyncio.sleep(delay)
                return await self.download_and_enqueue_stories(
                    username,
                    queue,
                    retry_count + 1
                )
            return False, None
    async def telegram_worker(self, queue: asyncio.Queue):
        """Single worker that sends stories from the queue to Telegram sequentially."""
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        while True:
            try:
                username, file_path, story_id = await queue.get()
                if file_path.endswith('.mp4'):
                    await self.bot.send_video(
                        chat_id=chat_id,
                        video=open(file_path, 'rb'),
                        caption=f"New story from @{username}"
                    )
                else:
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=open(file_path, 'rb'),
                        caption=f"New story from @{username}"
                    )
                os.remove(file_path)
                queue.task_done()
            except Exception as e:
                logger.error(f"Error sending story to chat {chat_id}: {e}")
                queue.task_done()

    async def process_all_profiles(self):
        """Download stories in parallel, send to Telegram sequentially via a queue."""
        all_profiles = self.storage.get_profiles()
        queue = asyncio.Queue()
        # Start the Telegram worker
        worker_task = asyncio.create_task(self.telegram_worker(queue))
        # Download stories in parallel (limit concurrency)
        semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent downloads
        async def sem_download(username):
            async with semaphore:
                await self.download_and_enqueue_stories(username, queue)
        download_tasks = [sem_download(username) for username in all_profiles]
        await asyncio.gather(*download_tasks)
        # Wait for all stories to be sent
        await queue.join()
        worker_task.cancel()
        logger.info(f"Completed batch processing: {len(all_profiles)} profiles checked")
