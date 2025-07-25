import os
import requests
import logging
import traceback
import asyncio
import threading
from datetime import datetime
from playwright.async_api import async_playwright
import aiohttp
import time
from concurrent.futures import ThreadPoolExecutor
import queue

try:
    from .config import Config
    from .logger import Logger, ProfileLogger
except ImportError:
    # For direct execution
    from config import Config
    from logger import Logger, ProfileLogger

# Setup logger
logger_instance = Logger()
logger = logger_instance.get_profile_logger('downloader')

class TelegramSender:
    """Class for sending files to Telegram"""
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if not self.bot_token or not self.chat_id:
            logger.error("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in environment")
            
        # Initialize the queue system
        self.send_queue = queue.Queue()
        self.max_workers = Config.DOWNLOAD_SETTINGS.get('max_concurrent_workers', 2)
        self.is_running = False
        self.worker_threads = []
        
    def start_worker_pool(self):
        """Start the worker pool for sending files to Telegram"""
        logger.info(f"[TelegramSender.start_worker_pool] Starting worker pool with {self.max_workers} workers")
        if self.is_running:
            logger.debug(f"[TelegramSender.start_worker_pool] Worker pool already running, skipping")
            return
            
        self.is_running = True
        for i in range(self.max_workers):
            logger.debug(f"[TelegramSender.start_worker_pool] Creating worker thread {i}")
            worker = threading.Thread(target=self._worker_thread, args=(i,), daemon=True)
            worker.start()
            self.worker_threads.append(worker)
        logger.info(f"[TelegramSender.start_worker_pool] Started {self.max_workers} Telegram sender worker threads")
            
    def _worker_thread(self, worker_id):
        """Worker thread for sending files to Telegram"""
        logger.info(f"[TelegramSender._worker_thread] Worker {worker_id} started")
        while self.is_running:
            try:
                # Get an item from the queue
                logger.debug(f"[TelegramSender._worker_thread/{worker_id}] Waiting for item from queue")
                item = self.send_queue.get(block=True, timeout=1)
                if item is None:
                    logger.debug(f"[TelegramSender._worker_thread/{worker_id}] Received None item, skipping")
                    self.send_queue.task_done()
                    continue
                    
                file_path, caption, chat_id = item
                logger.debug(f"[TelegramSender._worker_thread/{worker_id}] Processing file: {file_path}")
                
                # Send the file
                success = self._send_file(file_path, caption, chat_id)
                
                # Mark the task as done
                self.send_queue.task_done()
                
                if not success:
                    logger.warning(f"[TelegramSender._worker_thread/{worker_id}] Failed to send file, adding to DLQ: {file_path}")
                    # Add to DLQ (dead letter queue) for later retry
                    self._add_to_dlq(file_path, caption, chat_id)
                else:
                    logger.debug(f"[TelegramSender._worker_thread/{worker_id}] Successfully processed file: {file_path}")
                    
            except queue.Empty:
                # Queue is empty, just wait for more items
                pass
            except Exception as e:
                logger.error(f"[TelegramSender._worker_thread/{worker_id}] Error in worker: {str(e)}")
                logger.debug(f"[TelegramSender._worker_thread/{worker_id}] Error details: {traceback.format_exc()}")
                
        logger.info(f"[TelegramSender._worker_thread] Worker {worker_id} stopped")
        
    def _send_file(self, file_path, caption, chat_id=None):
        """Send a file to Telegram"""
        logger.debug(f"[TelegramSender._send_file] Starting to send file: {file_path}")
        if not chat_id:
            chat_id = self.chat_id
            logger.debug(f"[TelegramSender._send_file] Using default chat_id: {chat_id}")
            
        try:
            # Determine file type (photo or video)
            file_ext = os.path.splitext(file_path)[1].lower()
            is_video = file_ext in ['.mp4', '.mov', '.avi']
            logger.debug(f"[TelegramSender._send_file] File type: {'video' if is_video else 'photo'}, extension: {file_ext}")
            
            api_endpoint = f"https://api.telegram.org/bot{self.bot_token}/"
            api_endpoint += "sendVideo" if is_video else "sendPhoto"
            logger.debug(f"[TelegramSender._send_file] Using API endpoint: {api_endpoint}")
            
            # Prepare the file for upload
            with open(file_path, 'rb') as file:
                files = {'video' if is_video else 'photo': file}
                data = {
                    'chat_id': chat_id,
                    'caption': caption,
                    'parse_mode': 'HTML'
                }
                logger.debug(f"[TelegramSender._send_file] Prepared data payload with caption length: {len(caption) if caption else 0}")
                
                # Add video-specific parameters
                if is_video:
                    data['supports_streaming'] = 'true'
                    logger.debug(f"[TelegramSender._send_file] Added video-specific parameters")
                    
                # Send the request
                logger.debug(f"[TelegramSender._send_file] Sending HTTP request to Telegram API")
                response = requests.post(api_endpoint, files=files, data=data)
                response.raise_for_status()
                
                logger.info(f"[TelegramSender._send_file] Successfully sent file to Telegram: {file_path}")
                logger.debug(f"[TelegramSender._send_file] Response status code: {response.status_code}")
                return True
                
        except requests.exceptions.HTTPError as e:
            logger.error(f"[TelegramSender._send_file] HTTP error sending file to Telegram: {str(e)}")
            logger.debug(f"[TelegramSender._send_file] Response status code: {e.response.status_code if hasattr(e, 'response') else 'N/A'}")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[TelegramSender._send_file] Connection error sending file to Telegram: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"[TelegramSender._send_file] Unexpected error sending file to Telegram: {str(e)}")
            logger.debug(f"[TelegramSender._send_file] Error details: {traceback.format_exc()}")
            return False
            
    def _add_to_dlq(self, file_path, caption, chat_id):
        """Add a failed message to the dead letter queue"""
        logger.debug(f"[TelegramSender._add_to_dlq] Adding file to DLQ: {file_path}")
        try:
            # Implement DLQ logic here - can use Redis
            logger.warning(f"[TelegramSender._add_to_dlq] Added to DLQ: {file_path}")
        except Exception as e:
            logger.error(f"[TelegramSender._add_to_dlq] Error adding to DLQ: {str(e)}")
            logger.debug(f"[TelegramSender._add_to_dlq] Error details: {traceback.format_exc()}")
            
    def queue_file(self, file_path, caption, chat_id=None):
        """Queue a file to be sent to Telegram"""
        logger.debug(f"[TelegramSender.queue_file] Attempting to queue file: {file_path}")
        if not os.path.exists(file_path):
            logger.error(f"[TelegramSender.queue_file] File does not exist: {file_path}")
            return False
            
        try:
            # Add to the queue
            logger.debug(f"[TelegramSender.queue_file] Adding file to queue: {file_path}")
            self.send_queue.put((file_path, caption, chat_id))
            logger.info(f"[TelegramSender.queue_file] Successfully queued file: {file_path}")
            return True
        except Exception as e:
            logger.error(f"[TelegramSender.queue_file] Error queuing file: {str(e)}")
            logger.debug(f"[TelegramSender.queue_file] Error details: {traceback.format_exc()}")
            return False
            
    def stop_workers(self):
        """Stop the worker threads"""
        logger.info(f"[TelegramSender.stop_workers] Stopping {len(self.worker_threads)} worker threads")
        self.is_running = False
        
        for i, worker in enumerate(self.worker_threads):
            logger.debug(f"[TelegramSender.stop_workers] Joining worker thread {i}")
            worker.join(timeout=2)
            
        remaining_alive = sum(1 for w in self.worker_threads if w.is_alive())
        if remaining_alive > 0:
            logger.warning(f"[TelegramSender.stop_workers] {remaining_alive} worker threads did not terminate properly")
            
        self.worker_threads = []
        logger.info("[TelegramSender.stop_workers] Stopped all Telegram sender worker threads")

class InstagramStoryScraper:
    def __init__(self, download_dir="downloads", enable_telegram=True):
        """
        Initialize the Instagram story scraper.
        
        Args:
            download_dir: Directory to save downloaded stories
            enable_telegram: Whether to enable Telegram sending
        """
        logger.info(f"[InstagramStoryScraper.__init__] Initializing scraper with download_dir={download_dir}, enable_telegram={enable_telegram}")
        self.download_dir = download_dir
        self.timeouts = Config.TIMEOUTS
        self.selectors = Config.SELECTORS
        self.enable_telegram = enable_telegram
        
        # Create download directory if it doesn't exist
        logger.debug(f"[InstagramStoryScraper.__init__] Creating download directory: {self.download_dir}")
        os.makedirs(self.download_dir, exist_ok=True)
        
        # Initialize Telegram sender if enabled
        if self.enable_telegram:
            try:
                logger.debug(f"[InstagramStoryScraper.__init__] Initializing Telegram sender")
                self.telegram_sender = TelegramSender()
                self.telegram_sender.start_worker_pool()
                logger.info(f"[InstagramStoryScraper.__init__] Telegram sender initialized successfully")
            except Exception as e:
                logger.error(f"[InstagramStoryScraper.__init__] Failed to initialize Telegram sender: {str(e)}")
                logger.debug(f"[InstagramStoryScraper.__init__] Error details: {traceback.format_exc()}")
                self.enable_telegram = False
                logger.warning(f"[InstagramStoryScraper.__init__] Disabled Telegram integration due to initialization error")
        else:
            logger.info(f"[InstagramStoryScraper.__init__] Telegram integration is disabled")
        
    async def scrape_stories(self, username, last_known_id=None):
        """
        Scrape stories for a given Instagram username using insta-stories-viewer.com.
        
        Args:
            username: Instagram username to scrape (without @)
            last_known_id: The ID of the last story that was downloaded
            
        Returns:
            Tuple of (results, newest_id_found)
            - results: List of tuples (file_path, story_id)
            - newest_id_found: The ID of the newest story found
        """
        results = []
        newest_id_found = last_known_id or "0"
        
        logger.info(f"[InstagramStoryScraper.scrape_stories] Starting scrape for user {username}, last_known_id={last_known_id}")
        
        try:
            # Create user directory if it doesn't exist
            user_dir = os.path.join(self.download_dir, username)
            logger.debug(f"[InstagramStoryScraper.scrape_stories] Creating user directory: {user_dir}")
            os.makedirs(user_dir, exist_ok=True)
            
            logger.info(f"[InstagramStoryScraper.scrape_stories] Launching browser for {username}")
            
            # Launch browser
            async with async_playwright() as playwright:
                logger.debug(f"[InstagramStoryScraper.scrape_stories] Initializing Playwright for {username}")
                browser = await playwright.chromium.launch(headless=True)
                logger.debug(f"[InstagramStoryScraper.scrape_stories] Browser launched, creating context with user agent")
                context = await browser.new_context(
                    user_agent=Config.DOWNLOAD_SETTINGS['user_agent']
                )
                
                # Create a new page
                logger.debug(f"[InstagramStoryScraper.scrape_stories] Creating new page")
                page = await context.new_page()
                
                # Navigate to the insta-stories-viewer website
                url = f"https://insta-stories-viewer.com/{username}/"
                logger.info(f"[InstagramStoryScraper.scrape_stories] Navigating to {url}")
                logger.debug(f"[InstagramStoryScraper.scrape_stories] Using timeout: {self.timeouts['page_load']}ms")
                await page.goto(url, timeout=self.timeouts['page_load'])
                
                # Wait for the page to load and check if stories exist
                try:
                    # First try with the original selector
                    logger.info(f"[InstagramStoryScraper.scrape_stories] Trying original selector for stories for {username}")
                    logger.debug(f"[InstagramStoryScraper.scrape_stories] Waiting for selector: 'ul.profile__tabs-media.profile__stories' with timeout 10000ms")
                    await page.wait_for_selector('ul.profile__tabs-media.profile__stories', timeout=10000)
                    story_items = await page.locator('ul.profile__tabs-media.profile__stories > li.profile__tabs-media-item').all()
                    logger.info(f"[InstagramStoryScraper.scrape_stories] Found {len(story_items)} story items with original selector")
                except Exception as e:
                    logger.warning(f"[InstagramStoryScraper.scrape_stories] Original selector failed for {username}: {str(e)}")
                    # Try alternative selectors
                    try:
                        # Look for any story containers
                        logger.info(f"[InstagramStoryScraper.scrape_stories] Trying alternative selector for stories for {username}")
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Waiting for generic container selector with timeout 20000ms")
                        await page.wait_for_selector('ul[class*="profile__tabs-media"], div[class*="stories"], .story-container', timeout=20000)
                        
                        # Try different possible selectors for story items
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Attempting multiple alternative selectors for {username}")
                        possible_selectors = [
                            'ul.profile__tabs-media.profile__stories > li.profile__tabs-media-item',
                            'ul[class*="profile__tabs-media"] > li',
                            'div[class*="stories"] > div',
                            '.story-container > div',
                            'li.story-item'
                        ]
                        
                        # Try each selector
                        story_items = []
                        for selector in possible_selectors:
                            try:
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Trying selector: {selector}")
                                items = await page.locator(selector).all()
                                if items:
                                    story_items = items
                                    logger.info(f"[InstagramStoryScraper.scrape_stories] Found {len(items)} stories using selector: {selector}")
                                    break
                            except Exception as selector_error:
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Selector {selector} failed: {str(selector_error)}")
                                continue
                    except Exception as e2:
                        logger.warning(f"[InstagramStoryScraper.scrape_stories] All alternative selectors failed for {username}: {str(e2)}")
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Error details: {traceback.format_exc()}")
                        
                        # Last resort: take a screenshot for debugging
                        try:
                            screenshot_path = os.path.join(user_dir, f"debug_{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                            logger.debug(f"[InstagramStoryScraper.scrape_stories] Capturing debug screenshot to {screenshot_path}")
                            await page.screenshot(path=screenshot_path)
                            logger.info(f"[InstagramStoryScraper.scrape_stories] Saved debug screenshot to {screenshot_path}")
                        except Exception as screenshot_error:
                            logger.error(f"[InstagramStoryScraper.scrape_stories] Failed to save debug screenshot: {str(screenshot_error)}")
                        story_items = []
                
                logger.info(f"[InstagramStoryScraper.scrape_stories] Found {len(story_items)} stories for {username}")
                
                initial_id_to_check = int(last_known_id or "0")
                logger.debug(f"[InstagramStoryScraper.scrape_stories] Using initial_id_to_check={initial_id_to_check} for comparison")
                for i, item in enumerate(story_items):
                    try:
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Processing story item {i+1}/{len(story_items)}")
                        # Try different possible selectors for story media
                        media_span = None
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Looking for media element in story {i+1}")
                        for selector in ['span.profile__tabs-media-item-link', 'a[data-content]', '[data-media-type]', 'a.story-link']:
                            try:
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Trying media selector: {selector}")
                                media_span = item.locator(selector)
                                if await media_span.count() > 0:
                                    logger.debug(f"[InstagramStoryScraper.scrape_stories] Found media using selector: {selector}")
                                    break
                            except Exception as media_selector_error:
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Media selector {selector} failed: {str(media_selector_error)}")
                                continue
                        
                        if not media_span or await media_span.count() == 0:
                            logger.warning(f"[InstagramStoryScraper.scrape_stories] Could not find media element for item {i+1}, skipping")
                            continue
                            
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Extracting data-content attribute")
                        data_content = await media_span.get_attribute('data-content')
                        if not data_content:
                            # Try alternative attribute names
                            logger.debug(f"[InstagramStoryScraper.scrape_stories] data-content not found, trying alternative attributes")
                            for attr in ['href', 'src', 'data-src', 'data-url']:
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Trying attribute: {attr}")
                                data_content = await media_span.get_attribute(attr)
                                if data_content:
                                    logger.debug(f"[InstagramStoryScraper.scrape_stories] Found content in attribute: {attr}")
                                    break
                                    
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Extracting data-media-type attribute")
                        data_media_type = await media_span.get_attribute('data-media-type')
                        if not data_media_type:
                            # Try to determine type from URL or other attributes
                            logger.debug(f"[InstagramStoryScraper.scrape_stories] data-media-type not found, determining from URL")
                            data_media_type = 'video' if data_content and (data_content.endswith('.mp4') or 'video' in data_content) else 'image'
                            logger.debug(f"[InstagramStoryScraper.scrape_stories] Determined media type: {data_media_type}")
                            
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Extracting data-id attribute")
                        data_id = await media_span.get_attribute('data-id')
                        if not data_id:
                            # Try alternative attribute names or generate a timestamp-based ID
                            logger.debug(f"[InstagramStoryScraper.scrape_stories] data-id not found, trying alternative attributes")
                            for attr in ['id', 'data-story-id', 'data-time']:
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Trying ID attribute: {attr}")
                                data_id = await media_span.get_attribute(attr)
                                if data_id:
                                    logger.debug(f"[InstagramStoryScraper.scrape_stories] Found ID in attribute: {attr}")
                                    break
                            if not data_id:
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] No ID found, generating timestamp-based ID")
                                data_id = f"story_{int(datetime.now().timestamp())}"
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Generated ID: {data_id}")
                    except Exception as e:
                        logger.warning(f"[InstagramStoryScraper.scrape_stories] Error processing story item {i+1}: {str(e)}")
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Error details: {traceback.format_exc()}")
                        continue
                    
                    if not (data_content and data_id):
                        logger.warning(f"[InstagramStoryScraper.scrape_stories] Missing data_content or data_id for item {i+1}, skipping")
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] data_content: {data_content is not None}, data_id: {data_id is not None}")
                        continue
                    
                    logger.debug(f"[InstagramStoryScraper.scrape_stories] Extracting story ID from data_id: {data_id}")
                    story_id = self._extract_story_id(data_id)
                    logger.debug(f"[InstagramStoryScraper.scrape_stories] Extracted story ID: {story_id}")
                    
                    try:
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Converting story ID to integer: {story_id}")
                        story_id_int = int(story_id)
                    except ValueError:
                        logger.warning(f"[InstagramStoryScraper.scrape_stories] Invalid story ID format: {story_id}, using 0")
                        story_id_int = 0
                        
                    logger.debug(f"[InstagramStoryScraper.scrape_stories] Comparing story_id_int={story_id_int} > initial_id_to_check={initial_id_to_check}")
                    if story_id_int > initial_id_to_check:
                        logger.info(f"[InstagramStoryScraper.scrape_stories] Found new story {story_id_int} > {initial_id_to_check} for {username}")
                        ext = '.mp4' if data_media_type == 'video' else '.jpg'
                        filename = f"story_{username}_{story_id}{ext}"
                        save_path = os.path.join(user_dir, filename)
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Will save to: {save_path}")
                        
                        logger.info(f"[InstagramStoryScraper.scrape_stories] Downloading {data_media_type} from {data_content}")
                        if self._download_file(data_content, save_path):
                            logger.info(f"[InstagramStoryScraper.scrape_stories] Successfully downloaded story to: {save_path}")
                            results.append((save_path, story_id))
                            
                            # Send to Telegram if enabled
                            if self.enable_telegram:
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Preparing to send to Telegram")
                                caption = f"New story from <b>{username}</b>"
                                send_result = self._send_to_telegram(save_path, caption)
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Telegram send queued: {send_result}")
                            
                            if story_id_int > int(newest_id_found):
                                logger.debug(f"[InstagramStoryScraper.scrape_stories] Updating newest_id_found: {story_id_int} > {newest_id_found}")
                                newest_id_found = story_id
                        else:
                            logger.warning(f"[InstagramStoryScraper.scrape_stories] Failed to download story from: {data_content}")
        
        except Exception as e:
            logger.error(f"[InstagramStoryScraper.scrape_stories] An error occurred while processing {username}: {str(e)}")
            logger.error(f"[InstagramStoryScraper.scrape_stories] Error details: {traceback.format_exc()}")
        finally:
            logger.debug(f"[InstagramStoryScraper.scrape_stories] Cleaning up browser resources for {username}")
            # More careful browser cleanup to avoid "already closed" errors
            try:
                if 'context' in locals() and context:
                    try:
                        # Check if context is still active before closing
                        # This simple test will throw an error if the context is already closed
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Checking if browser context is still active")
                        if await page.evaluate("1"):
                            logger.debug(f"[InstagramStoryScraper.scrape_stories] Closing browser context")
                            await context.close()
                    except Exception as ctx_error:
                        # Context likely already closed, skip silently
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Context likely already closed: {str(ctx_error)}")
                        pass
            except Exception as final_error:
                logger.debug(f"[InstagramStoryScraper.scrape_stories] Error during context cleanup: {str(final_error)}")
                pass
                
            try:
                if 'browser' in locals() and browser:
                    # Try to close the browser without error
                    logger.debug(f"[InstagramStoryScraper.scrape_stories] Attempting to close browser")
                    try:
                        await browser.close()
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Browser closed successfully")
                    except Exception as browser_error:
                        logger.debug(f"[InstagramStoryScraper.scrape_stories] Error closing browser: {str(browser_error)}")
                        pass
            except Exception as outer_error:
                logger.debug(f"[InstagramStoryScraper.scrape_stories] Outer error during browser cleanup: {str(outer_error)}")
                pass
            
            logger.info(f"[InstagramStoryScraper.scrape_stories] Completed scraping for {username}, found {len(results)} new stories")
                
        return results, newest_id_found
    
    def _extract_story_id(self, data_id):
        """
        Extract the story ID from the data-id attribute.
        
        Args:
            data_id: The data-id attribute value
            
        Returns:
            The extracted story ID
        """
        logger.debug(f"[InstagramStoryScraper._extract_story_id] Extracting ID from: {data_id}")
        # Example: "story_123456789" -> "123456789"
        if data_id and isinstance(data_id, str):
            parts = data_id.split('_')
            if len(parts) > 1:
                logger.debug(f"[InstagramStoryScraper._extract_story_id] Found ID parts: {parts}")
                return parts[1]
            else:
                # If no underscore, try to extract numeric part
                logger.debug(f"[InstagramStoryScraper._extract_story_id] No underscore found, trying to extract numeric part")
                import re
                numeric_part = re.search(r'\d+', data_id)
                if numeric_part:
                    logger.debug(f"[InstagramStoryScraper._extract_story_id] Extracted numeric part: {numeric_part.group(0)}")
                    return numeric_part.group(0)
        
        logger.warning(f"[InstagramStoryScraper._extract_story_id] Could not extract ID from: {data_id}, returning 0")
        return "0"
    
    def _download_file(self, url, save_path):
        """
        Download a file from a URL and save it to the specified path.
        
        Args:
            url: URL of the file to download
            save_path: Path to save the file
            
        Returns:
            True if download was successful, False otherwise
        """
        logger.debug(f"[InstagramStoryScraper._download_file] Starting download from {url} to {save_path}")
        max_retries = Config.DOWNLOAD_SETTINGS.get('max_retries', 3)
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Ensure URL is properly formatted
                original_url = url
                if not url.startswith(('http://', 'https://')):
                    if url.startswith('//'):
                        url = 'https:' + url
                        logger.debug(f"[InstagramStoryScraper._download_file] Fixed protocol-relative URL: {original_url} -> {url}")
                    else:
                        url = 'https://' + url
                        logger.debug(f"[InstagramStoryScraper._download_file] Added https protocol: {original_url} -> {url}")
                
                logger.debug(f"[InstagramStoryScraper._download_file] Sending HTTP request to {url}")
                response = requests.get(
                    url, 
                    stream=True,
                    headers={'User-Agent': Config.DOWNLOAD_SETTINGS['user_agent']},
                    timeout=30  # Add timeout
                )
                response.raise_for_status()
                logger.debug(f"[InstagramStoryScraper._download_file] Received response with status code: {response.status_code}")
                
                # Check content type to ensure it's media
                content_type = response.headers.get('Content-Type', '')
                logger.debug(f"[InstagramStoryScraper._download_file] Content-Type: {content_type}")
                if not ('image' in content_type or 'video' in content_type or 'application/octet-stream' in content_type):
                    logger.warning(f"[InstagramStoryScraper._download_file] Unexpected content type: {content_type} for URL: {url}")
                    # Continue anyway as some servers may not set the correct content type
                
                # Get content length if available
                content_length = response.headers.get('Content-Length')
                total_size = int(content_length) if content_length else None
                logger.debug(f"[InstagramStoryScraper._download_file] Content-Length: {total_size} bytes")
                
                logger.debug(f"[InstagramStoryScraper._download_file] Writing file to {save_path}")
                with open(save_path, 'wb') as f:
                    downloaded_size = 0
                    chunk_size = Config.DOWNLOAD_SETTINGS['chunk_size']
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            if downloaded_size % (chunk_size * 10) == 0:  # Log every ~10 chunks
                                logger.debug(f"[InstagramStoryScraper._download_file] Downloaded {downloaded_size} bytes so far")
                
                # Verify file was downloaded and is not empty
                if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                    file_size = os.path.getsize(save_path)
                    logger.debug(f"[InstagramStoryScraper._download_file] File saved with size: {file_size} bytes")
                    
                    if total_size and file_size < total_size * 0.9:  # Allow for some difference
                        logger.warning(f"[InstagramStoryScraper._download_file] File size mismatch: expected {total_size}, got {file_size}")
                        # Continue anyway as the file might be usable
                    
                    logger.info(f"[InstagramStoryScraper._download_file] Successfully downloaded {file_size} bytes to {save_path}")
                    return True
                else:
                    logger.warning(f"[InstagramStoryScraper._download_file] Downloaded file is empty or missing: {save_path}")
                    # Remove empty file
                    try:
                        if os.path.exists(save_path):
                            logger.debug(f"[InstagramStoryScraper._download_file] Removing empty/invalid file: {save_path}")
                            os.remove(save_path)
                    except Exception as rm_error:
                        logger.debug(f"[InstagramStoryScraper._download_file] Error removing file: {str(rm_error)}")
                        pass
                    retry_count += 1
                    logger.info(f"[InstagramStoryScraper._download_file] Retry {retry_count}/{max_retries} for {url}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"[InstagramStoryScraper._download_file] Request error downloading file (attempt {retry_count+1}/{max_retries}): {str(e)}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.debug(f"[InstagramStoryScraper._download_file] Response status code: {e.response.status_code}")
                    if e.response.status_code == 404:
                        logger.error(f"[InstagramStoryScraper._download_file] File not found (404), skipping further retries: {url}")
                        return False
                retry_count += 1
            except Exception as e:
                logger.error(f"[InstagramStoryScraper._download_file] Error downloading file from {url}: {str(e)}")
                logger.debug(f"[InstagramStoryScraper._download_file] Error details: {traceback.format_exc()}")
                retry_count += 1
            
            # Add increasing delay between retries
            if retry_count < max_retries:
                retry_delay = Config.DOWNLOAD_SETTINGS.get('retry_base_delay', 1000) * (retry_count + 1) / 1000
                logger.info(f"[InstagramStoryScraper._download_file] Retrying download in {retry_delay:.1f} seconds...")
                import time
                time.sleep(retry_delay)
        
        logger.error(f"[InstagramStoryScraper._download_file] Failed to download file after {max_retries} attempts: {url}")
        return False
        
    def _send_to_telegram(self, file_path, caption, chat_id=None):
        """
        Send a file to Telegram using the TelegramSender.
        
        Args:
            file_path: Path to the file to send
            caption: Caption for the file
            chat_id: Optional chat ID to send to (defaults to configured chat_id)
            
        Returns:
            True if queued successfully, False otherwise
        """
        logger.debug(f"[InstagramStoryScraper._send_to_telegram] Preparing to send file: {file_path}")
        if not self.enable_telegram:
            logger.warning(f"[InstagramStoryScraper._send_to_telegram] Telegram sending is disabled")
            return False
            
        try:
            logger.debug(f"[InstagramStoryScraper._send_to_telegram] Queuing file for Telegram: {file_path}")
            result = self.telegram_sender.queue_file(file_path, caption, chat_id)
            if result:
                logger.info(f"[InstagramStoryScraper._send_to_telegram] Successfully queued file for Telegram: {file_path}")
            else:
                logger.warning(f"[InstagramStoryScraper._send_to_telegram] Failed to queue file for Telegram: {file_path}")
            return result
        except Exception as e:
            logger.error(f"[InstagramStoryScraper._send_to_telegram] Error queuing file for Telegram: {str(e)}")
            logger.debug(f"[InstagramStoryScraper._send_to_telegram] Error details: {traceback.format_exc()}")
            return False
            
    def cleanup(self):
        """Clean up resources when done"""
        logger.info(f"[InstagramStoryScraper.cleanup] Cleaning up resources")
        if self.enable_telegram:
            try:
                logger.debug(f"[InstagramStoryScraper.cleanup] Stopping Telegram workers")
                self.telegram_sender.stop_workers()
                logger.info(f"[InstagramStoryScraper.cleanup] Successfully stopped Telegram workers")
            except Exception as e:
                logger.warning(f"[InstagramStoryScraper.cleanup] Error stopping Telegram workers: {str(e)}")
                logger.debug(f"[InstagramStoryScraper.cleanup] Error details: {traceback.format_exc()}")
                pass
        logger.info(f"[InstagramStoryScraper.cleanup] Cleanup complete")
