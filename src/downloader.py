import os
import asyncio
import requests
import time
import shutil
from datetime import datetime
from playwright.async_api import async_playwright, Page, BrowserContext, Browser
from typing import Optional, List, Tuple, Dict
from .config import Config
from .logger import get_logger, get_profile_logger

class AnonyigDownloader:
    """
    A class to scrape Instagram stories anonymously using anonyig.com via Playwright.
    """
    def __init__(self):
        """Initializes the downloader."""
        self.logger = get_logger()
        self.logger.info("AnonyigDownloader initialized")
        # Ensure download and debug directories exist
        os.makedirs(Config.DIRECTORIES['downloads'], exist_ok=True)
        os.makedirs(Config.DIRECTORIES['debug_videos'], exist_ok=True)

    def _extract_story_id(self, data_id: str) -> str:
        """
        Uses the data-id attribute as the unique story ID.
        If data_id is None or missing, tries to generate a timestamp-based ID.
        """
        if not data_id or data_id == "None":
            # Generate a timestamp-based ID if no data-id is available
            timestamp = int(time.time())
            return f"ts_{timestamp}_{hash(str(timestamp))}"[:20]
        return str(data_id)

    async def _load_all_stories(self, page: Page) -> int:
        """
        Performs lazy scrolling and triggers to load all available stories.
        Returns the total count of stories found after lazy loading.
        """
        self.logger.info("Starting lazy loading process...")
        last_story_count = 0
        
        start_time = time.time()
        max_lazy_load_time = 60 # Max 60 seconds for lazy loading attempts

        for attempt in range(Config.DOWNLOAD_SETTINGS['max_lazy_load_attempts']):
            # Check timeout
            if time.time() - start_time > max_lazy_load_time:
                self.logger.warning(f"Lazy loading timeout after {max_lazy_load_time} seconds")
                break
                
            # Count current stories
            try:
                current_stories = await page.query_selector_all(Config.SELECTORS['story_items'])
                current_count = len(current_stories)
            except Exception as count_error:
                self.logger.warning(f"Error counting stories on attempt {attempt + 1}: {count_error}")
                current_count = 0
            
            self.logger.debug(f"Lazy load attempt {attempt + 1}: {current_count} stories found")
            
            # Stop if no new stories after several attempts
            if current_count == last_story_count and attempt > 2:
                self.logger.info("No new stories loaded, stopping lazy loading")
                break
                
            last_story_count = current_count
            
            # Scroll to bottom of stories container
            try:
                # Try to scroll the specific container first
                stories_container = await page.query_selector('ul.profile-media-list')
                if stories_container:
                    await page.evaluate('el => el.scrollTop = el.scrollHeight', stories_container)
                else:
                    # Fallback to scrolling the whole page
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                
                # Look for and trigger lazy load elements
                lazy_triggers = await page.query_selector_all(Config.SELECTORS['lazy_load_triggers'])
                for trigger in lazy_triggers:
                    try:
                        if await trigger.is_visible():
                            await trigger.click(timeout=1000)
                            await page.wait_for_timeout(200)
                        else:
                            await trigger.hover()
                            await trigger.focus()
                    except Exception:
                        pass # Ignore if trigger interaction fails
                        
            except Exception as e:
                self.logger.warning(f"Scroll attempt {attempt + 1} failed: {e}")
            
            await page.wait_for_timeout(Config.TIMEOUTS['scroll_delay'])
        
        try:
            final_stories = await page.query_selector_all(Config.SELECTORS['story_items'])
            final_count = len(final_stories)
            self.logger.info(f"Lazy loading complete. Final story count: {final_count}")
            return final_count
        except Exception as final_count_error:
            self.logger.warning(f"Error getting final count: {final_count_error}")
            self.logger.info("Lazy loading complete (count unknown)")
            return last_story_count

    def _download_file(self, url: str, save_path: str) -> bool:
        """
        Helper to download a file from a URL.
        Enhanced with better error handling and diagnostics.
        """
        try:
            # Use a longer timeout for downloads
            headers = {
                'User-Agent': Config.DOWNLOAD_SETTINGS['user_agent'],
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Referer': Config.BASE_URL
            }
            
            response = requests.get(
                url, 
                stream=True, 
                timeout=Config.TIMEOUTS.get('download', 30),
                headers=headers,
                allow_redirects=True
            )
            
            # Log response details for debugging
            self.logger.debug(f"Download response status: {response.status_code}, headers: {response.headers}")
            
            response.raise_for_status()
            
            # Check content type and size
            content_type = response.headers.get('Content-Type', '')
            content_length = int(response.headers.get('Content-Length', 0))
            
            if content_length == 0:
                self.logger.warning(f"Zero content length for {url}")
                return False
                
            if 'text/html' in content_type:
                self.logger.warning(f"Received HTML instead of media file for {url}")
                return False
            
            # Download the file
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=Config.DOWNLOAD_SETTINGS['chunk_size']):
                    if chunk:
                        f.write(chunk)
            
            # Verify file was created successfully
            if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                self.logger.debug(f"Successfully downloaded {url} to {save_path} ({os.path.getsize(save_path)} bytes)")
                return True
            else:
                self.logger.error(f"Downloaded file is empty or missing: {save_path}")
                return False
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Download failed for {url}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error downloading {url}: {e}")
            return False

    async def _download_with_retry(self, url: str, save_path: str, profile_logger, max_retries: int = 3) -> bool:
        """
        Download file with exponential backoff retry mechanism.
        """
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
                profile_logger.error(f"Error during download attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 1000
                    profile_logger.warning(f"Retrying in {wait_time}ms...")
                    await asyncio.sleep(wait_time / 1000)
        profile_logger.error(f"Failed to download {url} after {max_retries} attempts.")
        return False

    async def download_stories(self, username: str, last_seen_story_id: Optional[str] = None):
        """
        Downloads stories for a given username.
        Yields (username, file_path, story_id) for each new story.
        Returns the newest story ID found.
        """
        profile_logger = get_profile_logger(username)
        profile_logger.info(f"Starting download for profile: {username}")
        newest_story_id = last_seen_story_id

        # Create user-specific download directory
        download_dir = os.path.join(Config.DIRECTORIES['downloads'], username)
        os.makedirs(download_dir, exist_ok=True)

        # Ensure debug videos directory exists
        debug_video_dir = Config.DIRECTORIES['debug_videos']
        os.makedirs(debug_video_dir, exist_ok=True)

        browser = None
        try:
            async with async_playwright() as p:
                # Generate a unique debug video filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                debug_video_path = os.path.join(debug_video_dir, f"{username}_{timestamp}.webm")
                
                # Create browser and context - with or without video recording based on settings
                browser = await p.chromium.launch(
                    headless=True,  # True for production
                    args=['--no-sandbox', '--disable-gpu']
                )
                
                context_options = {
                    'user_agent': Config.DOWNLOAD_SETTINGS['user_agent'],
                    'viewport': {'width': 1280, 'height': 720}
                }
                
                # Add video recording if enabled
                if Config.DOWNLOAD_SETTINGS.get('enable_debug_video', False):
                    # Set video size based on quality setting
                    quality = Config.DOWNLOAD_SETTINGS.get('debug_video_quality', 'medium')
                    video_size = {'width': 1280, 'height': 720}  # Default medium quality
                    
                    if quality == 'low':
                        video_size = {'width': 640, 'height': 480}
                    elif quality == 'high':
                        video_size = {'width': 1920, 'height': 1080}
                        
                    context_options['record_video_dir'] = debug_video_dir
                    context_options['record_video_size'] = video_size
                    profile_logger.info(f"Debug video recording enabled: {debug_video_path}")
                
                context = await browser.new_context(**context_options)
                page = await context.new_page()
                page.set_default_timeout(Config.TIMEOUTS['page_load'])

                # 1. Load the page
                profile_logger.info(f"Navigating to {Config.BASE_URL}")
                await page.goto(Config.BASE_URL, timeout=Config.TIMEOUTS['page_load'])
                await page.wait_for_load_state('domcontentloaded')
                await page.wait_for_timeout(2000)  # Extra time for JS

                # 2. Enter Username in search
                profile_logger.info(f"Searching for username: {username}")
                search_input = await page.wait_for_selector(
                    Config.SELECTORS['search_input'],
                    timeout=Config.TIMEOUTS['element_wait']
                )
                
                if not search_input:
                    profile_logger.error("Search input not found")
                    yield username, None, None
                    return

                await search_input.fill(username)
                await page.wait_for_timeout(Config.TIMEOUTS['search_delay'])

                # 3. Click search or press Enter
                try:
                    await search_input.press('Enter')
                    await page.wait_for_timeout(1000)
                    
                    # Try clicking search button as fallback
                    search_button = await page.query_selector('button.search-form__button')
                    if search_button and await search_button.is_visible():
                        await search_button.click()
                    
                    await page.wait_for_load_state('networkidle', timeout=Config.TIMEOUTS['page_load'])
                    profile_logger.info("Search initiated")
                except Exception as e:
                    profile_logger.error(f"Failed to initiate search: {e}")
                    yield username, None, None
                    return

                # 4. Click Stories Tab if needed
                try:
                    stories_tab = await page.query_selector(Config.SELECTORS['stories_tab'])
                    if stories_tab and await stories_tab.is_visible():
                        # Check if tab is already active
                        is_active = await stories_tab.evaluate('node => node.classList.contains("active")')
                        if not is_active:
                            await stories_tab.click()
                            await page.wait_for_timeout(Config.TIMEOUTS['stories_tab_delay'])
                            profile_logger.info("Stories tab clicked")
                    else:
                        profile_logger.info("Stories tab not found or already active")
                except Exception as e:
                    profile_logger.warning(f"Could not interact with stories tab: {e}")

                # 5. Lazy Scroll to load all stories
                await self._load_all_stories(page)

                # 6. Extract and Download Stories
                story_items = await page.query_selector_all(Config.SELECTORS['story_items'])
                profile_logger.info(f"Found {len(story_items)} story items")

                downloaded_any_new = False

                for item in reversed(story_items):  # Process oldest to newest
                    try:
                        # Get story ID
                        data_id = await item.get_attribute('data-id')
                        story_id = self._extract_story_id(data_id)
                        
                        # Skip already seen stories
                        if story_id == "None" or not story_id:
                            profile_logger.warning(f"Invalid story ID found: {story_id}, skipping.")
                            continue
                            
                        # Compare with last seen ID
                        if last_seen_story_id and last_seen_story_id != "None" and story_id != "None":
                            try:
                                # Handle timestamp-based IDs vs numeric IDs
                                if story_id.startswith('ts_') and last_seen_story_id.startswith('ts_'):
                                    # For timestamp-based IDs, extract the timestamp part
                                    current_ts = int(story_id.split('_')[1])
                                    last_ts = int(last_seen_story_id.split('_')[1])
                                    if current_ts <= last_ts:
                                        profile_logger.info(f"Story {story_id} already seen (timestamp), skipping.")
                                        continue
                                elif story_id.isdigit() and last_seen_story_id.isdigit():
                                    # For numeric IDs, compare directly
                                    if int(story_id) <= int(last_seen_story_id):
                                        profile_logger.info(f"Story {story_id} already seen (numeric), skipping.")
                                        continue
                                else:
                                    # Mixed ID types - don't skip, but log it
                                    profile_logger.info(f"Different ID formats: current={story_id}, last={last_seen_story_id}. Processing anyway.")
                            except ValueError as ve:
                                profile_logger.warning(f"Could not compare story IDs ({story_id} vs {last_seen_story_id}): {ve}")
                                # Continue processing the story since we couldn't determine if it's old

                        # Try to get download link directly
                        download_link = await item.query_selector(Config.SELECTORS['download_link'])
                        if download_link:
                            media_url = await download_link.get_attribute('href')
                        else:
                            # Try to get media element source
                            media_element = await item.query_selector(Config.SELECTORS['media_content'])
                            if not media_element:
                                profile_logger.warning(f"No media content found for story {story_id}, skipping.")
                                continue
                                
                            media_url = await media_element.get_attribute('src')
                            
                        # No media URL found
                        if not media_url:
                            profile_logger.warning(f"No media URL found for story {story_id}, skipping.")
                            continue

                        # Determine media type
                        if media_url.endswith(('.mp4', '.webm', '.mov')):
                            media_type = "video"
                        elif media_url.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            media_type = "image"
                        else:
                            # Fallback to tag name check if URL doesn't have clear extension
                            media_element = await item.query_selector(Config.SELECTORS['media_content'])
                            if media_element:
                                media_type = "video" if "video" in await media_element.evaluate('node => node.tagName.toLowerCase()') else "image"
                            else:
                                media_type = "video"  # Default to video if we can't determine
                        
                        file_extension = Config.FILE_EXTENSIONS[media_type]
                        
                        # Generate a safe filename
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"{username}_{story_id}_{timestamp}{file_extension}"
                        save_path = os.path.join(download_dir, filename)

                        # Download the file
                        profile_logger.info(f"Attempting to download story {story_id} from {media_url}")
                        if await self._download_with_retry(media_url, save_path, profile_logger, Config.DOWNLOAD_SETTINGS['max_retries']):
                            profile_logger.info(f"Successfully downloaded story {story_id}")
                            yield username, save_path, story_id
                            # Only update newest_story_id if it's a valid ID
                            if story_id != "None" and story_id:
                                newest_story_id = story_id
                            downloaded_any_new = True
                        else:
                            profile_logger.error(f"Failed to download story {story_id}")
                    except Exception as e:
                        profile_logger.error(f"Error processing story item: {e}")
                        continue
                
                if not downloaded_any_new:
                    profile_logger.info(f"No new stories found for {username}")
                
                # Signal completion with newest ID
                yield username, None, newest_story_id

        except Exception as e:
            profile_logger.error(f"An error occurred during story download for {username}: {e}")
            yield username, None, None
        finally:
            if browser:
                # First close the context to ensure video is saved properly
                if 'context' in locals():
                    await context.close()
                    if Config.DOWNLOAD_SETTINGS.get('enable_debug_video', False):
                        profile_logger.info(f"Debug video recording saved for {username}")
                
                # Then close the browser
                await browser.close()
                profile_logger.info(f"Browser closed for {username}")
                
                # Rename the video file to a more descriptive name if debug video is enabled
                if Config.DOWNLOAD_SETTINGS.get('enable_debug_video', False):
                    try:
                        # Wait for video file to be fully written
                        await asyncio.sleep(2)
                        
                        if os.path.exists(debug_video_dir):
                            # Find all webm files in the directory
                            video_files = [f for f in os.listdir(debug_video_dir) if f.endswith('.webm')]
                            
                            if video_files:
                                # Sort by creation time, newest first
                                video_files.sort(key=lambda x: os.path.getctime(os.path.join(debug_video_dir, x)), reverse=True)
                                
                                # Get the most recently created video file
                                newest_video = video_files[0]
                                newest_video_path = os.path.join(debug_video_dir, newest_video)
                                
                                # Only process files created in the last minute
                                if time.time() - os.path.getctime(newest_video_path) < 60:
                                    # Generate a descriptive name
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    new_name = f"{username}_{timestamp}.webm"
                                    new_path = os.path.join(debug_video_dir, new_name)
                                    
                                    # Copy instead of rename to avoid issues with file being in use
                                    shutil.copy2(newest_video_path, new_path)
                                    profile_logger.info(f"Debug video copied to: {new_name}")
                                    
                                    # Try to remove the original file, but don't error if we can't
                                    try:
                                        os.remove(newest_video_path)
                                        profile_logger.info(f"Original debug video removed: {newest_video}")
                                    except Exception as remove_error:
                                        profile_logger.warning(f"Could not remove original debug video: {remove_error}")
                    except Exception as rename_error:
                        profile_logger.warning(f"Error handling debug video: {rename_error}")

    async def download_user_stories(self, username: str, last_seen_story_id: Optional[str] = None):
        """
        Downloads stories for a given username and returns them in a format compatible with legacy code.
        
        Args:
            username: Instagram username
            last_seen_story_id: Optional ID of the last seen story
            
        Returns:
            Tuple of (list of (file_path, story_id) tuples, newest_story_id)
        """
        self.logger.info(f"Starting legacy download for profile: {username}")
        results = []
        newest_story_id = last_seen_story_id
        
        # Use the async generator to collect all stories
        async for u, file_path, story_id in self.download_stories(username, last_seen_story_id):
            if file_path is None:
                # This is the completion signal or error
                newest_story_id = story_id
            else:
                results.append((file_path, story_id))
                if newest_story_id is None or (
                    story_id and story_id != "None" and 
                    (newest_story_id == "None" or 
                     (story_id.isdigit() and newest_story_id.isdigit() and int(story_id) > int(newest_story_id)))
                ):
                    newest_story_id = story_id
        
        return results, newest_story_id

    async def concurrent_download_stories(self, profile_data: Dict[str, Optional[str]]):
        """
        Manages concurrent downloads for multiple profiles using a queue.
        profile_data: {username: last_seen_story_id}
        """
        self.logger.info("Starting concurrent streaming...")
        
        # Create a queue to manage results from workers
        result_queue = asyncio.Queue()

        # Worker function to run download_stories for each profile
        async def worker_with_queue(username, last_seen_story_id, worker_id):
            self.logger.info(f"Stream worker {worker_id} started for {username}")
            try:
                downloader = AnonyigDownloader() # Create a new instance for each worker
                newest_id = None
                
                async for username, file_path, story_id in downloader.download_stories(username, last_seen_story_id):
                    if file_path is None:
                        # This is the completion signal with newest_id
                        newest_id = story_id
                        await result_queue.put((username, None, newest_id)) # Signal completion with newest_id
                    else:
                        await result_queue.put((username, file_path, story_id))
                
            except Exception as e:
                self.logger.error(f"Stream worker {worker_id} failed for {username}: {e}")
                await result_queue.put((username, None, None))  # Signal failure
        
        # Start all workers with IDs
        tasks = [
            asyncio.create_task(worker_with_queue(username, last_seen_story_id, idx))
            for idx, (username, last_seen_story_id) in enumerate(profile_data.items())
        ]
        
        completed_profiles = set()
        total_profiles = len(profile_data)
        
        # Yield results as they come in
        while len(completed_profiles) < total_profiles:
            try:
                username, file_path, story_id = await asyncio.wait_for(result_queue.get(), timeout=60.0)
                
                if file_path is None:  # Completion signal
                    completed_profiles.add(username)
                    if story_id:  # This is the newest_id, not None for failure
                        self.logger.info(f"Profile {username} completed with newest_id: {story_id}")
                else:
                    yield username, file_path, story_id
                    
            except asyncio.TimeoutError:
                self.logger.warning("Timeout waiting for download results")
                break
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        self.logger.info("Concurrent streaming complete.")


class ConcurrentDownloader:
    """
    Manages concurrent downloads of Instagram stories for multiple profiles.
    Uses the AnonyigDownloader internally.
    """
    
    def __init__(self, max_workers: int = 3):
        """
        Initialize the concurrent downloader.
        
        Args:
            max_workers: Maximum number of concurrent workers
        """
        self.logger = get_logger()
        self.max_workers = max_workers
        self.logger.info(f"ConcurrentDownloader initialized with {max_workers} max workers")
    
    async def download_multiple_profiles(self, profile_data: Dict[str, Optional[str]]):
        """
        Download stories for multiple profiles concurrently.
        
        Args:
            profile_data: Dictionary mapping username to last_seen_story_id
            
        Returns:
            Dictionary mapping username to (stories_list, newest_story_id)
            where stories_list is a list of (file_path, story_id) tuples
        """
        self.logger.info(f"Starting concurrent download for {len(profile_data)} profiles")
        
        results = {}
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def download_with_semaphore(username, last_seen_story_id):
            async with semaphore:
                try:
                    downloader = AnonyigDownloader()  # Create new instance for each profile
                    stories = []
                    newest_id = None
                    
                    async for u, file_path, story_id in downloader.download_stories(username, last_seen_story_id):
                        if file_path is None:
                            # This is the completion or error signal
                            newest_id = story_id
                        else:
                            stories.append((file_path, story_id))
                    
                    return username, stories, newest_id
                except Exception as e:
                    self.logger.error(f"Error downloading stories for {username}: {e}")
                    return username, [], None
        
        # Create download tasks for all profiles
        tasks = [
            asyncio.create_task(download_with_semaphore(username, last_seen_id))
            for username, last_seen_id in profile_data.items()
        ]
        
        # Wait for all tasks to complete
        completed = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for result in completed:
            if isinstance(result, tuple) and len(result) == 3:
                username, stories, newest_id = result
                results[username] = (stories, newest_id)
            else:
                self.logger.error(f"Invalid result from download task: {result}")
        
        return results
    
    async def download_profiles_stream(self, profile_data: Dict[str, Optional[str]]):
        """
        Stream download results for multiple profiles.
        This is a wrapper around AnonyigDownloader.concurrent_download_stories.
        
        Args:
            profile_data: Dictionary mapping username to last_seen_story_id
            
        Yields:
            (username, file_path, story_id) tuples as downloads complete
            If file_path is None, it's a signal that processing for that username is complete
        """
        downloader = AnonyigDownloader()
        async for result in downloader.concurrent_download_stories(profile_data):
            yield result
