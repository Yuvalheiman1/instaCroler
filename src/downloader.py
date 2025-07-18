import os
import time
import requests
from playwright.async_api import async_playwright
from urllib.parse import urlparse, parse_qs

class AnonyigDownloader:
    """
    A class to download Instagram stories anonymously using a website.
    It uses Playwright for browser automation.
    """
    def __init__(self, download_dir="downloads"):
        """
        Initializes the downloader and creates the main download directory.
        """
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)

    def _extract_story_id(self, data_id: str) -> str:
        """
        Uses the data-id attribute as the unique story ID.
        """
        return str(data_id)

    def _download_file(self, url: str, save_path: str) -> bool:
        """
        Downloads a file from a URL and saves it to a given path.
        """
        try:
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to download file from {url}. Error: {e}")
            return False

    async def download_user_stories(self, username: str, last_known_id: str = None):
        """
        Scrapes and downloads new stories (images and videos) for a given Instagram user from storiesig.info.
        Returns a list of (file_path, story_id) and the newest story_id found.
        """
        results = []
        newest_id_found = last_known_id or "0"
        user_dir = os.path.join(self.download_dir, username)
        os.makedirs(user_dir, exist_ok=True)
        os.makedirs("debug_videos", exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                record_video_dir="debug_videos",
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            print("Recording video of the browser interaction...")
            try:
                url = "https://storiesig.info/en/"
                print(f"Visiting {url}")
                await page.goto(url, timeout=60000)
                print("Page loaded, waiting for 5 seconds...")
                await page.wait_for_timeout(5000)  # Wait for 5 seconds for any dynamic content

                # Find and fill the search input
                print("Looking for search input...")
                search_input = await page.wait_for_selector('input.search.search-form__input', timeout=30000)
                if search_input:
                    print("Found search input, filling username...")
                    await search_input.fill(username)
                    await page.wait_for_timeout(1000)  # Wait a bit after typing

                # Try to find the button in multiple ways
                print("Looking for search button...")
                button = None
                for selector in ['button.tabs-component__button', 'button:has-text("Search")', '.tabs-component__button']:
                    try:
                        button = await page.wait_for_selector(selector, timeout=5000)
                        print(f"Found button with selector: {selector}")
                        break
                    except Exception:
                        print(f"Button not found with selector: {selector}")
                        continue

                if button:
                    print("Clicking search button...")
                    await button.click()
                    print("Button clicked, waiting for results...")
                else:
                    raise Exception("Could not find the search button")


                # Click the stories tab button to ensure stories are shown
                print("Ensuring stories tab is active...")
                try:
                    # Find the stories tab by text
                    stories_tab = await page.wait_for_selector('button.tabs-component__button:has-text("Stories")', timeout=10000)
                    # Check if it's already active
                    is_active = await stories_tab.evaluate("el => el.classList.contains('tabs-component__button--active')")
                    if not is_active:
                        await stories_tab.click()
                        print("Stories tab button clicked.")
                    else:
                        print("Stories tab already active.")
                except Exception as e:
                    print(f"Stories tab button not found or not clickable: {e}")

                # Wait for stories container to appear
                print("Waiting for stories container to appear...")
                await page.wait_for_selector('.output-profile', timeout=30000)

                # Improved lazy-load: scroll the stories container and trigger loading until no new items appear
                print("Scrolling stories container and triggering lazy-load...")
                max_scroll_attempts = 15
                scroll_delay_ms = 1200
                last_count = -1
                for i in range(max_scroll_attempts):
                    # Get current number of story items
                    items = await page.query_selector_all('ul.profile-media-list > li.profile-media-list__item')
                    count = len(items)
                    print(f"Scroll attempt {i+1}: {count} story items found.")
                    if count == last_count:
                        print("No new stories loaded, stopping scroll.")
                        break
                    last_count = count
                    # Scroll the container to bottom
                    await page.evaluate('el => el.scrollTop = el.scrollHeight', await page.query_selector('ul.profile-media-list'))
                    # Try to trigger the lazy-load div if present
                    trigger = await page.query_selector('ul.profile-media-list > div.trigger')
                    if trigger:
                        await trigger.hover()
                        print("Hovered trigger div to load more stories.")
                    await page.wait_for_timeout(scroll_delay_ms)
                print("Finished scrolling and triggering lazy-load.")

                # Now collect all download buttons
                download_buttons = await page.locator('.button.button--filled.button__download').all()
                print(f"Found {len(download_buttons)} stories for {username}.")

                initial_id_to_check = int(last_known_id or "0")
                for index, button in enumerate(download_buttons):
                    try:
                        # Get the parent container (story preview)
                        parent = button.locator('..')
                        has_video = await parent.locator('video').count() > 0
                        has_img = await parent.locator('img').count() > 0
                        data_media_type = 'video' if has_video else 'image' if has_img else 'unknown'

                        # Get download URL from the button's data attribute or href
                        data_content = await button.get_attribute('data-url') or await button.get_attribute('href')
                        if not data_content:
                            print(f"No download URL found for story {index + 1}")
                            continue

                        # Use timestamp or index as ID
                        data_id = str(int(time.time())) + str(index)

                    except Exception as e:
                        print(f"Error processing story {index + 1}: {str(e)}")
                        continue

                    if not data_id:
                        continue
                    story_id = self._extract_story_id(data_id)
                    try:
                        story_id_int = int(story_id)
                    except Exception:
                        story_id_int = 0
                    if story_id_int > initial_id_to_check:
                        ext = '.mp4' if data_media_type == 'video' else '.jpg'
                        filename = f"story_{username}_{story_id}{ext}"
                        save_path = os.path.join(user_dir, filename)
                        if data_media_type == 'video':
                            print(f"Downloading video via browser: {filename}")
                            try:
                                async with page.expect_download() as download_info:
                                    await button.click()
                                download = await download_info.value
                                await download.save_as(save_path)
                                print(f"Downloaded: {save_path}")
                                results.append((save_path, story_id))
                                if story_id_int > int(newest_id_found):
                                    newest_id_found = story_id
                            except Exception as e:
                                print(f"Failed browser video download: {e}")
                        else:
                            if self._download_file(data_content, save_path):
                                print(f"Downloaded: {save_path}")
                                results.append((save_path, story_id))
                                if story_id_int > int(newest_id_found):
                                    newest_id_found = story_id
            except Exception as e:
                print(f"An error occurred while processing {username}: {e}")
            finally:
                await context.close()
                await browser.close()
        return results, newest_id_found
