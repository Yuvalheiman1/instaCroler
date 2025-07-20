import os
import requests
import time
from typing import List, Dict, Optional
from datetime import datetime
from playwright.async_api import async_playwright
from urllib.parse import urlparse, parse_qs
from .config import Config
from .logger import get_logger, log_info, log_error, log_warning, log_debug, get_profile_logger
from telegram import Bot

class AnonyigDownloader:
    """
    A class to download Instagram stories anonymously using a website.
    It uses Playwright for browser automation.
    """
    def __init__(self, download_dir=None):
            """
            Initializes the downloader and creates the main download directory.
            """
            self.download_dir = download_dir or Config.DIRECTORIES['downloads']
            self.logger = get_logger()
            os.makedirs(self.download_dir, exist_ok=True)
            
            # Initialize browser attributes to None
            self.playwright = None
            self.browser = None
            self.page = None
            self.bot = None # If you are creating a bot instance here
            
            self.logger.info(f"AnonyigDownloader initialized with download_dir: {self.download_dir}")

    def _extract_story_id(self, data_id: str) -> str:
        """
        Uses the data-id attribute as the unique story ID.
        """
        return str(data_id)

    async def _load_all_stories(self, page):
        """
        Scroll and trigger lazy loading to ensure all stories are loaded.
        """
        self.logger.info("Starting lazy loading process...")
        last_count = 0
        max_attempts = Config.DOWNLOAD_SETTINGS['max_lazy_load_attempts']
        scroll_delay = Config.TIMEOUTS['scroll_delay']
        
        for attempt in range(max_attempts):
            # Count current stories
            current_stories = await page.query_selector_all(Config.SELECTORS['story_items'])
            current_count = len(current_stories)
            
            self.logger.debug(f"Lazy load attempt {attempt + 1}: {current_count} stories found")
            
            if current_count == last_count and attempt > 2:
                self.logger.info("No new stories loaded, stopping lazy loading")
                break
                
            last_count = current_count
            
            # Scroll to bottom of stories container
            try:
                stories_container = await page.query_selector('ul.profile-media-list')
                if stories_container:
                    await page.evaluate('el => el.scrollTop = el.scrollHeight', stories_container)
                
                # Look for and trigger lazy load elements
                lazy_triggers = await page.query_selector_all(Config.SELECTORS['lazy_load_triggers'])
                for trigger in lazy_triggers:
                    try:
                        await trigger.hover()
                        await trigger.focus()
                        await page.wait_for_timeout(500)
                    except:
                        pass
                        
            except Exception as e:
                self.logger.warning(f"Scroll attempt {attempt + 1} failed: {e}")
            
            await page.wait_for_timeout(scroll_delay)
        
        final_count = len(await page.query_selector_all(Config.SELECTORS['story_items']))
        self.logger.info(f"Lazy loading complete. Final story count: {final_count}")

    async def _download_with_retry(self, url: str, save_path: str, profile_logger, max_retries: int = 3) -> bool:
        """
        Download file with exponential backoff retry mechanism.
        """
        import asyncio
        
        for attempt in range(max_retries):
            try:
                if self._download_file(url, save_path):
                    return True
                else:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 1000  # Exponential backoff in ms
                        profile_logger.warning(f"Download failed, retrying in {wait_time}ms...")
                        await asyncio.sleep(wait_time / 1000)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 1000
                    profile_logger.warning(f"Download error: {e}, retrying in {wait_time}ms...")
                    await asyncio.sleep(wait_time / 1000)
                else:
                    profile_logger.error(f"Download failed after {max_retries} attempts: {e}")
        return False

    def _download_file(self, url: str, save_path: str) -> bool:
        """
        Downloads a file from a URL and saves it to a given path.
        """
        try:
            headers = {'User-Agent': Config.DOWNLOAD_SETTINGS['user_agent']}
            with requests.get(url, stream=True, headers=headers) as response:
                response.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=Config.DOWNLOAD_SETTINGS['chunk_size']):
                        f.write(chunk)
            self.logger.info(f"Successfully downloaded file: {save_path}")
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to download file from {url}. Error: {e}")
            return False

    async def download_user_stories(self, username: str, last_seen_story_id: str = None):
        """
        Scrapes and downloads new stories (images and videos) for a given Instagram user from anonyig.com.
        Returns a list of (file_path, story_id) and the newest story_id found.
        """
        # Create profile-specific logger
        profile_logger = get_profile_logger(username)
        
        results = []
        newest_id_found = last_seen_story_id or "0"
        user_dir = os.path.join(self.download_dir, username)
        os.makedirs(user_dir, exist_ok=True)
        os.makedirs(Config.DIRECTORIES['debug_videos'], exist_ok=True)

        # Extract timestamp from last_known_id (format: "timestamp_index")
        if last_seen_story_id and "_" in last_seen_story_id:
            initial_id_to_check = int(last_seen_story_id.split("_")[0])
        else:
            initial_id_to_check = int(last_seen_story_id or "0")
        
        profile_logger.info(f"Starting story download for user: {username}")
        profile_logger.info(f"Last known ID: {last_seen_story_id}, Initial ID to check: {initial_id_to_check}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                record_video_dir=Config.DIRECTORIES['debug_videos'], 
                viewport={'width': 1280, 'height': 720}
            )
            
            # Block ads and tracking to prevent interference
            await context.route("**/*", lambda route: (
                route.abort() if route.request.resource_type in ["image", "media", "font"] and 
                any(ad_domain in route.request.url for ad_domain in [
                    "googlesyndication.com", "googleadservices.com", "doubleclick.net",
                    "googletagmanager.com", "google-analytics.com", "facebook.com/tr",
                    "ads", "analytics", "tracking", "advertisement"
                ]) else route.continue_()
            ))
            
            page = await context.new_page()
            profile_logger.info("Browser started, recording video...")
            
            try:
                url = Config.BASE_URL
                profile_logger.info(f"Visiting {url}")
                await page.goto(url, timeout=Config.TIMEOUTS['page_load'])
                await page.wait_for_timeout(2000)

                # Find and fill the search input
                profile_logger.info("Looking for search input...")
                search_input = await page.wait_for_selector(
                    Config.SELECTORS['search_input'], 
                    timeout=Config.TIMEOUTS['element_wait']
                )
                if search_input:
                    profile_logger.info("Found search input, filling username...")
                    await search_input.fill(username)
                    await page.wait_for_timeout(500)
                    # Press Enter to search
                    await search_input.press('Enter')
                    profile_logger.info("Pressed Enter to search.")
                    await page.wait_for_timeout(Config.TIMEOUTS['search_delay'])
                else:
                    profile_logger.error("Search input not found!")
                    return results, newest_id_found

                # Click the stories tab button
                profile_logger.info("Clicking stories tab button...")
                try:
                    stories_tab = await page.wait_for_selector(
                        Config.SELECTORS['stories_tab'], 
                        timeout=Config.TIMEOUTS['element_wait']
                    )
                    await stories_tab.click()
                    profile_logger.info("Stories tab button clicked.")
                    await page.wait_for_timeout(Config.TIMEOUTS['stories_tab_delay'])
                except Exception as e:
                    profile_logger.warning(f"Stories tab button not found or not clickable: {e}")

                # Wait for stories container to appear
                profile_logger.info("Waiting for stories container to appear...")
                await page.wait_for_selector(Config.SELECTORS['stories_container'], timeout=Config.TIMEOUTS['element_wait'])

                # Scroll and load all stories with lazy loading
                profile_logger.info("Loading all stories with lazy loading...")
                await self._load_all_stories(page)

                # Collect all story items - refresh the list to avoid stale references
                story_items = await page.query_selector_all(Config.SELECTORS['story_items'])
                profile_logger.info(f"Found {len(story_items)} stories for {username}.")
                
                if len(story_items) == 0:
                    profile_logger.warning("No stories found. Checking page structure...")
                    # Debug: check what's actually on the page
                    page_html = await page.content()
                    profile_logger.debug(f"Page HTML contains 'profile-media-list': {'profile-media-list' in page_html}")
                    profile_logger.debug(f"Page HTML contains 'button__download': {'button__download' in page_html}")
                    
                    # Save page HTML for debugging
                    debug_path = os.path.join(Config.DIRECTORIES['debug_videos'], f"debug_{username}.html")
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write(page_html)
                    profile_logger.info(f"Saved page HTML to {debug_path}")
                
                for index, item in enumerate(story_items):
                    profile_logger.info(f"Processing story {index + 1}/{len(story_items)}")
                    
                    try:
                        # Re-query the item to avoid stale element references
                        fresh_items = await page.query_selector_all(Config.SELECTORS['story_items'])
                        if index >= len(fresh_items):
                            profile_logger.warning(f"Story {index + 1} no longer exists, skipping")
                            continue
                        
                        item = fresh_items[index]
                        
                        # Look for the download button to get the actual media URL
                        download_button = await item.query_selector('a.button__download, .button__download')
                        if not download_button:
                            profile_logger.warning(f"No download button found for story {index + 1}")
                            continue
                    except Exception as e:
                        profile_logger.warning(f"Error accessing story {index + 1} element: {e}")
                        continue
                    
                    try:
                        
                        # Look for the download button to get the actual media URL
                        download_button = await item.query_selector('a.button__download, .button__download')
                        if not download_button:
                            profile_logger.warning(f"No download button found for story {index + 1}")
                            continue
                        
                        # Get the direct media URL from the download button's href
                        direct_url = await download_button.get_attribute('href')
                        if not direct_url:
                            profile_logger.warning(f"No href attribute found for story {index + 1}")
                            continue
                        
                        profile_logger.debug(f"Direct media URL: {direct_url}")
                        
                        # Determine media type from URL
                        data_media_type = 'video' if direct_url.lower().endswith(('.mp4', '.mov', '.avi', '.webm')) else 'image'
                        
                        # Determine file extension from URL
                        if '.mp4' in direct_url.lower():
                            ext = '.mp4'
                        elif '.jpg' in direct_url.lower() or '.jpeg' in direct_url.lower():
                            ext = '.jpg'
                        elif '.png' in direct_url.lower():
                            ext = '.png'
                        elif '.webm' in direct_url.lower():
                            ext = '.webm'
                        else:
                            # Default fallback based on media type
                            ext = Config.FILE_EXTENSIONS['video'] if data_media_type == 'video' else Config.FILE_EXTENSIONS['image']
                        
                        # Generate a unique story ID using index and timestamp
                        timestamp = int(time.time())
                        data_id = f"{timestamp}_{index}"
                        story_id = self._extract_story_id(data_id)
                        story_id_int = timestamp + index
                        
                        profile_logger.debug(f"Story ID check: story_id_int={story_id_int}, initial_id_to_check={initial_id_to_check}")
                        
                        if story_id_int > initial_id_to_check:
                            filename = f"story_{username}_{story_id}{ext}"
                            save_path = os.path.join(user_dir, filename)
                            
                            profile_logger.info(f"Attempting to download: {filename}")
                            profile_logger.info(f"Media type detected: {data_media_type}")
                            
                            # Download using requests with the direct URL
                            if await self._download_with_retry(direct_url, save_path, profile_logger):
                                profile_logger.info(f"Downloaded: {save_path}")
                                results.append((save_path, story_id))
                                if story_id_int > int(newest_id_found):
                                    newest_id_found = story_id
                            else:
                                profile_logger.warning(f"Failed to download {filename}")
                                    
                            # Rate limiting: wait between downloads
                            await page.wait_for_timeout(Config.TIMEOUTS['download_delay'])
                        else:
                            profile_logger.info(f"Skipping story {story_id} - already processed")
                    
                    except Exception as story_error:
                        profile_logger.warning(f"Error processing story {index + 1}: {story_error}")
                        continue
            except Exception as e:
                profile_logger.error(f"An error occurred while processing {username}: {e}", exc_info=True)
            finally:
                await context.close()
                await browser.close()
        
        profile_logger.info(f"Download complete. Downloaded {len(results)} new stories.")
        return results, newest_id_found

    async def download_user_stories_stream(self, username: str, last_seen_story_id: str = None):
        """
        Async generator that yields stories as they are downloaded.
        This is used by the bot for real-time processing.
        """
        results, newest_id = await self.download_user_stories(username, last_seen_story_id)
        for file_path, story_id in results:
            yield file_path, story_id

    async def start_browser(self):
        """Starts the Playwright browser and creates a new page."""
        if self.browser:
            self.logger.warning("Browser is already running.")
            return
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.page = await self.browser.new_page()
            self.bot = Bot(token=self.bot_token)
            self.logger.info("Playwright browser started successfully.")
        except Exception as e:
            self.logger.error(f"Failed to start browser: {e}")
            raise

    async def close_browser(self):
        """Closes the Playwright browser."""
        if self.page:
            await self.page.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self.bot:
            await self.bot.close()
        self.logger.info("Playwright browser closed.")

    async def download_user_stories(self, username: str, last_seen_story_id: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Downloads all new stories for a given user.

        Args:
            username: The Instagram username.
            last_seen_story_id: The ID of the last story seen for this user.

        Returns:
            A list of dictionaries, where each dictionary contains the type and path of the downloaded media.
        """
        url = f"https://anonyig.com/profile/{username}"
        self.logger.info(f"Navigating to {url}")
        
        media_items = []
        
        try:
            await self.page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Check for profile not found
            if "Profile not found" in await self.page.text_content('body'):
                self.logger.warning(f"Profile '{username}' not found on Anonyig.")
                return []

            # Wait for stories to load
            await self.page.wait_for_selector('.story-item', timeout=15000)
            
            story_elements = await self.page.query_selector_all('.story-item')
            self.logger.info(f"Found {len(story_elements)} story items for '{username}'.")

            new_stories_found = False
            for story_element in reversed(story_elements): # Process from oldest to newest
                story_id = await story_element.get_attribute('data-id')

                if last_seen_story_id and story_id == last_seen_story_id:
                    new_stories_found = True
                    self.logger.info(f"Found last seen story ID {last_seen_story_id}. Processing subsequent stories.")
                    continue # Skip this one, process the next

                if last_seen_story_id and not new_stories_found:
                    continue # Keep skipping until we find the last seen story

                # Click the story to open the modal
                await story_element.click()
                await self.page.wait_for_selector('.story-modal', timeout=10000)
                
                # Wait for the download button to be ready
                download_button = await self.page.wait_for_selector('a.button__download', timeout=10000)
                media_url = await download_button.get_attribute('href')
                
                media_type = 'video' if media_url.endswith('.mp4') else 'image'
                
                # Download the media
                media_path = await self._download_media(media_url, username, story_id)
                
                if media_path:
                    media_items.append({"type": media_type, "path": media_path, "id": story_id})
                
                # Close the modal
                close_button = await self.page.query_selector('.story-modal .button-close')
                if close_button:
                    await close_button.click()
                await self.page.wait_for_selector('.story-modal', state='hidden', timeout=5000)

            return media_items

        except TimeoutError:
            self.logger.info(f"No stories found for '{username}' or page timed out.")
            return []
        except Exception as e:
            self.logger.error(f"An error occurred while downloading stories for {username}: {e}")
            # Take a screenshot for debugging
            screenshot_path = os.path.join(Config.DOWNLOAD_PATH, f"error_{username}_{datetime.now():%Y%m%d_%H%M%S}.png")
            await self.page.screenshot(path=screenshot_path)
            self.logger.info(f"Saved screenshot to {screenshot_path}")
            return []

    async def _download_media(self, url: str, username: str, story_id: str) -> Optional[str]:
        """Downloads a single media file."""
        try:
            async with self.page.context.new_page() as download_page:
                response = await download_page.goto(url)
                if not response.ok:
                    self.logger.error(f"Failed to download media from {url}. Status: {response.status}")
                    return None
                
                content = await response.body()
                
                file_extension = '.mp4' if url.endswith('.mp4') else '.jpg'
                file_name = f"{username}_{story_id}{file_extension}"
                file_path = os.path.join(Config.DOWNLOAD_PATH, file_name)
                
                with open(file_path, 'wb') as f:
                    f.write(content)
                    
                self.logger.info(f"Successfully downloaded {file_path}")
                return file_path
        except Exception as e:
            self.logger.error(f"Error in _download_media for url {url}: {e}")
            return None