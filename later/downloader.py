"""
Instagram Story Downloader Module with anti-ban measures and timestamp tracking
This module provides functionality to download Instagram stories using the instagrapi library
with built-in safety measures to prevent account bans.
"""

from instagrapi import Client
import os
import json
import time
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class InstagramDownloader:
    def __init__(self):
        self.client = None
        self.session_file = os.getenv('SESSION_FILE', 'insta_session.json')
        self.download_path = os.getenv('DOWNLOAD_PATH', './downloaded_stories')
        self.last_request_time = None
        self.request_count = 0
        self.session_start_time = None
        self.max_requests_per_session = 100
        self.min_delay = 2
        self.max_delay = 4
        self.ensure_download_folder()

    def ensure_download_folder(self):
        """Create the download directory if it doesn't exist."""
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

    def _add_random_delay(self):
        """Add a random delay between requests to appear more human-like."""
        if self.last_request_time:
            # Calculate time since last request
            elapsed = time.time() - self.last_request_time
            # If not enough time has passed, wait
            if elapsed < self.min_delay:
                time.sleep(random.uniform(self.min_delay, self.max_delay))
        self.last_request_time = time.time()

    def _should_rotate_session(self):
        """Check if we should rotate the session based on usage."""
        if not self.session_start_time:
            return True
        
        # Rotate if too many requests or session is too old
        too_many_requests = self.request_count >= self.max_requests_per_session
        session_too_old = datetime.now() - self.session_start_time > timedelta(hours=6)
        
        return too_many_requests or session_too_old

    def save_session(self):
        """Save the current Instagram session to avoid frequent logins."""
        if self.client:
            with open(self.session_file, "w") as f:
                json.dump(self.client.get_settings(), f)

    def load_session(self):
        """Load a previously saved Instagram session."""
        if os.path.exists(self.session_file):
            with open(self.session_file, "r") as f:
                settings = json.load(f)
                self.client.set_settings(settings)

    def login(self, force_new_session=False):
        """
        Handle Instagram login process with session management.
        
        Args:
            force_new_session (bool): If True, creates a new session regardless of existing one
        """
        if force_new_session or self._should_rotate_session():
            self.client = Client()
            try:
                print("Logging in with new session...")
                self.client.login(
                    os.getenv('INSTAGRAM_USERNAME'),
                    os.getenv('INSTAGRAM_PASSWORD')
                )
                self.session_start_time = datetime.now()
                self.request_count = 0
                self.save_session()
            except Exception as e:
                print(f"Login failed: {str(e)}")
                raise
        return self.client

    def download_user_stories(self, username, last_timestamp=None):
        """
        Download stories from a user with safety measures and timestamp filtering.
        
        Args:
            username (str): Instagram username whose stories to download
            last_timestamp (str, optional): ISO format timestamp of last seen story
            
        Returns:
            tuple: (list of downloaded file paths, latest story timestamp)
        """
        if not self.client or self._should_rotate_session():
            self.login()

        downloaded_files = []
        latest_timestamp = last_timestamp
        try:
            self._add_random_delay()
            user_id = self.client.user_id_from_username(username)
            
            self._add_random_delay()
            stories = self.client.user_stories(user_id)

            # Sort stories by timestamp to ensure proper tracking
            stories = sorted(stories, key=lambda x: x.taken_at)

            for story in stories:
                story_timestamp = story.taken_at.isoformat()
                
                # Skip stories older than or equal to the last seen timestamp
                if last_timestamp and story_timestamp <= last_timestamp:
                    continue

                self._add_random_delay()
                try:
                    media_path = self.client.story_download(
                        story.pk, 
                        folder=self.download_path
                    )
                    downloaded_files.append((media_path, story_timestamp))
                    self.request_count += 1
                    
                    # Update latest timestamp
                    if not latest_timestamp or story_timestamp > latest_timestamp:
                        latest_timestamp = story_timestamp

                except Exception as e:
                    print(f"Error downloading story: {str(e)}")
                    continue

        except Exception as e:
            print(f"Error downloading stories from {username}: {str(e)}")
            if "login_required" in str(e).lower():
                self.login(force_new_session=True)

        return downloaded_files, latest_timestamp

    def cleanup_files(self):
        """Remove all files from the download directory."""
        for file in os.listdir(self.download_path):
            file_path = os.path.join(self.download_path, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
