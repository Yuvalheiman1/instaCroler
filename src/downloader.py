import os
import requests
import time
import asyncio
from typing import Optional, List, Tuple, Dict
from datetime import datetime
from playwright.async_api import async_playwright
from .config import Config
from .logger import get_logger, get_profile_logger

class AnonyigDownloader:
    """
    A class to download Instagram stories anonymously using a website.
    It uses Playwright for browser automation and combines the best logic
    from both the old downloader and the copy version.
    """
    def __init__(self):
        """Initializes the downloader."""
        self.logger = get_logger()
        self.logger.info("AnonyigDownloader initialized")

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
        
        # Add timeout to prevent hanging
        start_time = time.time()
        max_lazy_load_time = 60  # Maximum 60 seconds for lazy loading
        
        for attempt in range(max_attempts):
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
        
        try:
            final_count = len(await page.query_selector_all(Config.SELECTORS['story_items']))
            self.logger.info(f"Lazy loading complete. Final story count: {final_count}")
        except Exception as final_count_error:
            self.logger.warning(f"Error getting final count: {final_count_error}")
            self.logger.info("Lazy loading complete (count unknown)")

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
        
        This method combines the reliable Playwright logic from old_downloader with 
        the Redis-compatible interface from downloader copy.
        """
        # Create profile-specific logger
        profile_logger = get_profile_logger(username)
        
        results = []
        newest_id_found = last_seen_story_id or "0"
        user_dir = os.path.join(Config.DIRECTORIES['downloads'], username)
        os.makedirs(user_dir, exist_ok=True)
        os.makedirs(Config.DIRECTORIES['debug_videos'], exist_ok=True)

        # Extract timestamp from last_seen_story_id (format: "timestamp_index")
        if last_seen_story_id and "_" in last_seen_story_id:
            initial_id_to_check = int(last_seen_story_id.split("_")[0])
        else:
            initial_id_to_check = int(last_seen_story_id or "0")
        
        profile_logger.info(f"Starting story download for user: {username}")
        profile_logger.info(f"Last known ID: {last_seen_story_id}, Initial ID to check: {initial_id_to_check}")

        async with async_playwright() as p:
            # Optimize browser for constrained environments (reduced memory usage)
            browser_args = [
                '--disable-web-security', 
                '--disable-features=VizDisplayCompositor',
                '--disable-background-networking',
                '--disable-background-timer-throttling',
                '--disable-renderer-backgrounding',
                '--disable-backgrounding-occluded-windows',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-gpu',
                '--memory-pressure-off',
                '--disable-extensions',
                '--disable-plugins'
            ]
            
            # Additional conservative args for stability
            if Config.DOWNLOAD_SETTINGS.get('slow_connection_mode', False):
                browser_args.extend([
                    '--aggressive-cache-discard',
                    '--disable-background-mode'
                ])
            
            browser = await p.chromium.launch(
                headless=True,
                args=browser_args
            )
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
            
            # Add page crash handler
            page.on("crash", lambda: profile_logger.error(f"Page crashed for {username}"))
            
            profile_logger.info("Browser started, recording video...")
            
            try:
                url = Config.BASE_URL
                profile_logger.info(f"Visiting {url}")
                
                # Use different wait strategy for slow connections (from copy version)
                if Config.DOWNLOAD_SETTINGS.get('slow_connection_mode', False):
                    profile_logger.info("Using slow connection mode - waiting for 'domcontentloaded' instead of 'load'")
                    await page.goto(url, timeout=Config.TIMEOUTS['page_load'], wait_until='domcontentloaded')
                    # Extra wait for slow connections
                    await page.wait_for_timeout(5000)  # Extra 5 second wait
                else:
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
                    
                    # Check if search worked by looking for URL change or content change
                    current_url = page.url
                    profile_logger.info(f"URL after search: {current_url}")
                    
                    # Wait a bit more and check if we're on a profile page
                    await page.wait_for_timeout(2000)
                    final_url = page.url
                    profile_logger.info(f"Final URL: {final_url}")
                    
                    # Check if URL changed or if we found profile content
                    if username.lower() in final_url.lower() or current_url != final_url:
                        profile_logger.info("Search appears to have worked - URL changed or contains username")
                    else:
                        profile_logger.warning("Search may not have worked - trying alternative approach")
                        # Try clicking search button if it exists
                        try:
                            search_btn = await page.query_selector('button[type="submit"], .search-btn, input[type="submit"]')
                            if search_btn:
                                profile_logger.info("Found search button, clicking...")
                                await search_btn.click()
                                await page.wait_for_timeout(3000)
                        except Exception as btn_error:
                            profile_logger.debug(f"Search button click failed: {btn_error}")
                else:
                    profile_logger.error("Search input not found!")
                    return results, newest_id_found

                # Click the stories tab button
                profile_logger.info("Clicking stories tab button...")
                stories_tab_found = False
                
                # Try multiple approaches to find and click the stories tab
                stories_tab_selectors = [
                    Config.SELECTORS['stories_tab'],  # 'button.tabs-component__button:has-text("stories")'
                    'button:has-text("Stories")',
                    'button:has-text("stories")', 
                    'button:has-text("STORIES")',
                    '.tabs-component__button:has-text("stories")',
                    '.tab-button',
                    '[data-tab="stories"]',
                    'a[href*="stories"]',
                    'button[role="tab"]'
                ]
                
                for selector in stories_tab_selectors:
                    try:
                        profile_logger.debug(f"Trying stories tab selector: {selector}")
                        stories_tab = await page.wait_for_selector(selector, timeout=5000)
                        if stories_tab:
                            # Check if it's visible and clickable
                            is_visible = await stories_tab.is_visible()
                            if is_visible:
                                await stories_tab.click()
                                profile_logger.info(f"Stories tab clicked using selector: {selector}")
                                await page.wait_for_timeout(Config.TIMEOUTS['stories_tab_delay'])
                                stories_tab_found = True
                                break
                    except Exception as tab_error:
                        profile_logger.debug(f"Selector {selector} failed: {tab_error}")
                        continue
                
                if not stories_tab_found:
                    profile_logger.warning("Stories tab not found with any selector")
                    # Check if stories are already visible without clicking tab
                    existing_stories = await page.query_selector_all(Config.SELECTORS['story_items'])
                    if existing_stories:
                        profile_logger.info(f"Found {len(existing_stories)} stories already visible, proceeding without tab click")
                    else:
                        # Try direct navigation to stories section
                        try:
                            current_url = page.url
                            if not current_url.endswith('/stories'):
                                stories_url = current_url.rstrip('/') + '/stories'
                                profile_logger.info(f"Trying direct navigation to: {stories_url}")
                                await page.goto(stories_url, timeout=15000)
                                await page.wait_for_timeout(2000)
                        except Exception as nav_error:
                            profile_logger.warning(f"Direct navigation failed: {nav_error}")

                # Wait for stories container to appear
                profile_logger.info("Waiting for stories container to appear...")
                container_found = False
                
                # Try multiple selectors for the stories container with shorter timeouts
                container_selectors = [
                    Config.SELECTORS['stories_container'],  # '.output-profile'
                    '.profile-content',
                    '.user-profile', 
                    'ul.profile-media-list',
                    '.media-container',
                    '.stories-container',
                    '.profile-media'
                ]
                
                for selector in container_selectors:
                    try:
                        profile_logger.debug(f"Trying container selector: {selector}")
                        await page.wait_for_selector(selector, timeout=10000)  # Shorter timeout per selector
                        profile_logger.info(f"Found stories container with: {selector}")
                        container_found = True
                        break
                    except Exception as container_error:
                        profile_logger.debug(f"Container selector {selector} failed: {container_error}")
                        continue
                
                if not container_found:
                    profile_logger.warning("Stories container not found with any selector")
                    # Check page content to understand what's there
                    page_text = await page.text_content('body')
                    profile_logger.debug(f"Page contains text: {page_text[:200]}...")
                    
                    # Check if there are any obvious error messages
                    if any(error_text in page_text.lower() for error_text in ['not found', 'error', 'private', 'does not exist']):
                        profile_logger.warning("Page seems to contain error message")
                        
                    # Save debug info
                    debug_path = os.path.join(Config.DIRECTORIES['debug_videos'], f"debug_stuck_{username}.html")
                    page_html = await page.content()
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write(page_html)
                    profile_logger.info(f"Saved debug HTML to: {debug_path}")
                    
                    # Continue anyway - maybe stories are there but container selector is wrong

                # Scroll and load all stories with lazy loading
                profile_logger.info("Loading all stories with lazy loading...")
                await self._load_all_stories(page)

                # Collect all story items - try multiple selectors
                story_items = []
                story_selectors = [
                    Config.SELECTORS['story_items'],  # 'ul.profile-media-list > li.profile-media-list__item'
                    'ul.profile-media-list > li',
                    '.profile-media-list__item',
                    '.story-item',
                    '.media-item',
                    'li[data-media]',
                    'li:has(.button__download)',
                    'li:has(a[href*="download"])',
                    'li:has(img)',
                    'li:has(video)'
                ]
                
                for selector in story_selectors:
                    try:
                        items = await page.query_selector_all(selector)
                        if items:
                            story_items = items
                            profile_logger.info(f"Found {len(story_items)} stories using selector: {selector}")
                            break
                    except Exception as selector_error:
                        profile_logger.debug(f"Selector {selector} failed: {selector_error}")
                        continue
                
                profile_logger.info(f"Total stories found for {username}: {len(story_items)}")
                
                if len(story_items) == 0:
                    profile_logger.warning("No stories found. Performing comprehensive page analysis...")
                    
                    # Check page URL to ensure we're on the right page
                    current_url = page.url
                    profile_logger.info(f"Current page URL: {current_url}")
                    
                    # Get page title
                    try:
                        page_title = await page.title()
                        profile_logger.info(f"Page title: {page_title}")
                    except:
                        pass
                    
                    # Check what's actually on the page
                    page_html = await page.content()
                    profile_logger.debug(f"Page HTML contains 'profile-media-list': {'profile-media-list' in page_html}")
                    profile_logger.debug(f"Page HTML contains 'button__download': {'button__download' in page_html}")
                    profile_logger.debug(f"Page HTML contains 'stories': {'stories' in page_html.lower()}")
                    profile_logger.debug(f"Page HTML contains username '{username}': {username in page_html.lower()}")
                    
                    # Look for any download links or media
                    all_links = await page.query_selector_all('a[href]')
                    download_links = []
                    for link in all_links:
                        href = await link.get_attribute('href')
                        if href and ('download' in href.lower() or '.mp4' in href.lower() or '.jpg' in href.lower()):
                            download_links.append(href)
                    
                    profile_logger.info(f"Found {len(download_links)} potential download links")
                    if download_links:
                        for i, link in enumerate(download_links[:3]):  # Log first 3
                            profile_logger.debug(f"Download link {i+1}: {link}")
                    
                    # Check for error messages on the page
                    error_selectors = ['.error', '.alert', '.warning', '.no-content', '.not-found']
                    for error_sel in error_selectors:
                        error_el = await page.query_selector(error_sel)
                        if error_el:
                            error_text = await error_el.text_content()
                            profile_logger.warning(f"Found error message: {error_text}")
                    
                    # Save page HTML for debugging
                    debug_path = os.path.join(Config.DIRECTORIES['debug_videos'], f"debug_no_stories_{username}.html")
                    with open(debug_path, 'w', encoding='utf-8') as f:
                        f.write(page_html)
                    profile_logger.info(f"Saved page HTML to {debug_path}")
                    
                    # Take a screenshot for visual debugging
                    try:
                        screenshot_path = os.path.join(Config.DIRECTORIES['debug_videos'], f"debug_screenshot_{username}.png")
                        await page.screenshot(path=screenshot_path, full_page=True)
                        profile_logger.info(f"Saved screenshot to {screenshot_path}")
                    except Exception as screenshot_error:
                        profile_logger.warning(f"Failed to save screenshot: {screenshot_error}")
                    
                    # Try alternative URL approach if direct search fails
                    profile_logger.info("Trying alternative URL approach...")
                    try:
                        # Try navigating directly to user's page
                        direct_url = f"https://anonyig.com/en/profile/{username}"
                        profile_logger.info(f"Trying direct URL: {direct_url}")
                        await page.goto(direct_url, timeout=Config.TIMEOUTS['page_load'], wait_until='domcontentloaded')
                        await page.wait_for_timeout(3000)
                        
                        # Try to find stories again
                        items = await page.query_selector_all(Config.SELECTORS['story_items'])
                        if items:
                            story_items = items
                            profile_logger.info(f"Found {len(story_items)} stories via direct URL")
                                
                    except Exception as direct_error:
                        profile_logger.warning(f"Direct URL approach failed: {direct_error}")
                
                # If still no stories, try one more alternative approach
                if len(story_items) == 0:
                    profile_logger.info("Trying to find any media elements as fallback...")
                    # Look for any media elements that might be stories
                    media_elements = await page.query_selector_all('img[src*="instagram"], video[src*="instagram"], a[href*=".mp4"], a[href*=".jpg"]')
                    if media_elements:
                        profile_logger.info(f"Found {len(media_elements)} potential media elements as fallback")
                        # We'll process these as story items
                        story_items = media_elements
                
                # Process stories sequentially (from old_downloader - more reliable)
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
                                if story_id_int > int(newest_id_found.split("_")[0] if "_" in newest_id_found else newest_id_found):
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


class ConcurrentDownloader:
    """
    Concurrent downloader that manages multiple AnonyigDownloader workers
    to process multiple profiles simultaneously, with Redis DB compatibility.
    
    This class is taken from the copy version which works well with Redis.
    """
    
    def __init__(self, max_workers: int = None):
        """
        Initialize the concurrent downloader.
        
        Args:
            max_workers: Maximum number of concurrent workers (defaults to config value)
        """
        self.max_workers = max_workers or Config.DOWNLOAD_SETTINGS['max_concurrent_workers']
        self.logger = get_logger()
        self.semaphore = asyncio.Semaphore(self.max_workers)
        self.logger.info(f"ConcurrentDownloader initialized with {self.max_workers} workers")
    
    async def _download_profile_worker(self, username: str, last_seen_story_id: str = None, worker_id: int = 0) -> Tuple[str, List[Tuple[str, str]], str]:
        """
        Worker function to download stories for a single profile.
        
        Args:
            username: Instagram username
            last_seen_story_id: Last seen story ID for this profile
            worker_id: Worker identifier for staggered launches
            
        Returns:
            Tuple of (username, results, newest_id)
        """
        async with self.semaphore:
            # Stagger browser launches to avoid overwhelming the site
            if Config.DOWNLOAD_SETTINGS.get('browser_launch_stagger', True):
                stagger_delay = worker_id * (Config.TIMEOUTS.get('browser_launch_delay', 2000) / 1000)
                if stagger_delay > 0:
                    self.logger.info(f"Worker {worker_id} waiting {stagger_delay:.1f}s before launching browser for {username}")
                    await asyncio.sleep(stagger_delay)
            
            downloader = AnonyigDownloader()
            max_retries = Config.DOWNLOAD_SETTINGS.get('max_retries', 3)
            
            for attempt in range(max_retries):
                try:
                    self.logger.info(f"Worker {worker_id} started for profile: {username} (attempt {attempt + 1})")
                    results, newest_id = await downloader.download_user_stories(username, last_seen_story_id)
                    self.logger.info(f"Worker {worker_id} completed for profile: {username} - {len(results)} stories downloaded")
                    return username, results, newest_id
                except Exception as e:
                    error_msg = str(e).lower()
                    if "page crashed" in error_msg or "crash" in error_msg:
                        self.logger.error(f"Worker {worker_id} page crashed for profile {username} (attempt {attempt + 1})")
                        # Longer wait for page crashes to allow system to recover
                        wait_time = (3 ** attempt) + (worker_id * 2.0)  # Exponential backoff with longer delays
                    else:
                        self.logger.warning(f"Worker {worker_id} attempt {attempt + 1} failed for profile {username}: {e}")
                        wait_time = (2 ** attempt) + (worker_id * 0.5)  # Add worker-specific jitter
                    
                    if attempt < max_retries - 1:
                        self.logger.info(f"Retrying {username} in {wait_time:.1f} seconds...")
                        await asyncio.sleep(wait_time)
                    else:
                        self.logger.error(f"Worker {worker_id} failed for profile {username} after {max_retries} attempts")
            
            return username, [], last_seen_story_id or "0"
    
    async def download_multiple_profiles(self, profile_data: Dict[str, str]) -> Dict[str, Tuple[List[Tuple[str, str]], str]]:
        """
        Download stories for multiple profiles concurrently.
        
        Args:
            profile_data: Dictionary mapping username to last_seen_story_id
            
        Returns:
            Dictionary mapping username to (results, newest_id) tuples
        """
        if not profile_data:
            return {}
        
        self.logger.info(f"Starting concurrent download for {len(profile_data)} profiles")
        
        # Create tasks for all profiles with worker IDs
        tasks = [
            self._download_profile_worker(username, last_seen_story_id, idx)
            for idx, (username, last_seen_story_id) in enumerate(profile_data.items())
        ]
        
        # Execute all tasks concurrently
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"Error in concurrent download: {e}")
            return {}
        
        # Process results
        download_results = {}
        successful_downloads = 0
        
        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Task failed with exception: {result}")
                continue
                
            username, stories, newest_id = result
            download_results[username] = (stories, newest_id)
            if stories:
                successful_downloads += len(stories)
        
        self.logger.info(f"Concurrent download completed: {successful_downloads} total stories from {len(download_results)} profiles")
        return download_results
    
    async def download_profiles_stream(self, profile_data: Dict[str, str]):
        """
        Stream stories as they are downloaded from multiple profiles concurrently.
        
        Args:
            profile_data: Dictionary mapping username to last_seen_story_id
            
        Yields:
            Tuples of (username, file_path, story_id)
        """
        if not profile_data:
            return
        
        self.logger.info(f"Starting concurrent streaming download for {len(profile_data)} profiles")
        
        # Create a queue to collect results from workers
        result_queue = asyncio.Queue()
        
        async def worker_with_queue(username: str, last_seen_story_id: str = None, worker_id: int = 0):
            """Worker that puts results into the queue as they complete"""
            try:
                username_result, stories, newest_id = await self._download_profile_worker(username, last_seen_story_id, worker_id)
                for file_path, story_id in stories:
                    await result_queue.put((username_result, file_path, story_id))
                await result_queue.put((username_result, None, newest_id))  # Signal completion for this profile
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
        self.logger.info("Concurrent streaming download completed")
