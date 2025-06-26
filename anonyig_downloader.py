import os
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
        Scrapes and downloads new stories (images and videos) for a given Instagram user from insta-stories-viewer.com.
        Returns a list of (file_path, story_id) and the newest story_id found.
        """
        results = []
        newest_id_found = last_known_id or "0"
        user_dir = os.path.join(self.download_dir, username)
        os.makedirs(user_dir, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                url = f"https://insta-stories-viewer.com/{username}/"
                print(f"Visiting {url}")
                await page.goto(url, timeout=60000)
                # Wait for the stories list to be loaded (not the preload GIF)
                await page.wait_for_selector('ul.profile__tabs-media.profile__stories', timeout=30000)
                story_items = await page.locator('ul.profile__tabs-media.profile__stories > li.profile__tabs-media-item').all()
                print(f"Found {len(story_items)} stories for {username}.")
                initial_id_to_check = int(last_known_id or "0")
                for item in story_items:
                    # Get the span with data-content (media URL), data-media-type, and data-id
                    media_span = item.locator('span.profile__tabs-media-item-link')
                    data_content = await media_span.get_attribute('data-content')
                    data_media_type = await media_span.get_attribute('data-media-type')
                    data_id = await media_span.get_attribute('data-id')
                    if not (data_content and data_id):
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

    async def download_user_stories_stream(self, username: str, last_known_id: str = None):
        """
        Async generator: yields (file_path, story_id) as soon as each story is downloaded.
        """
        newest_id_found = last_known_id or "0"
        user_dir = os.path.join(self.download_dir, username)
        os.makedirs(user_dir, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            try:
                url = f"https://insta-stories-viewer.com/{username}/"
                print(f"Visiting {url}")
                await page.goto(url, timeout=60000)
                await page.wait_for_selector('ul.profile__tabs-media.profile__stories', timeout=30000)
                story_items = await page.locator('ul.profile__tabs-media.profile__stories > li.profile__tabs-media-item').all()
                print(f"Found {len(story_items)} stories for {username}.")
                initial_id_to_check = int(last_known_id or "0")
                for item in story_items:
                    media_span = item.locator('span.profile__tabs-media-item-link')
                    data_content = await media_span.get_attribute('data-content')
                    data_media_type = await media_span.get_attribute('data-media-type')
                    data_id = await media_span.get_attribute('data-id')
                    if not (data_content and data_id):
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
                        if self._download_file(data_content, save_path):
                            print(f"Downloaded: {save_path}")
                            yield save_path, story_id
                            if story_id_int > int(newest_id_found):
                                newest_id_found = story_id
            except Exception as e:
                print(f"An error occurred while processing {username}: {e}")
            finally:
                await context.close()
                await browser.close()
