"""
Stories Tracker Module
Handles tracking of Instagram story timestamps to prevent duplicate downloads
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional

class StoriesTracker:
    def __init__(self, storage_file: str = "stories_history.json"):
        """
        Initialize the stories tracker
        
        Args:
            storage_file (str): Path to the JSON file for storing timestamps
        """
        self.storage_file = storage_file
        self.user_timestamps: Dict[str, str] = {}  # username -> last_seen timestamp
        self._load_history()

    def _load_history(self):
        """Load user timestamps from storage file"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    self.user_timestamps = json.load(f)
            except json.JSONDecodeError:
                self.user_timestamps = {}
        else:
            self.user_timestamps = {}

    def _save_history(self):
        """Save user timestamps to storage file"""
        with open(self.storage_file, 'w') as f:
            json.dump(self.user_timestamps, f, indent=2)

    def get_last_story_time(self, username: str) -> Optional[str]:
        """
        Get the timestamp of the last story seen for a user
        
        Args:
            username (str): Instagram username
            
        Returns:
            str: ISO format timestamp of last story, or None if no history
        """
        return self.user_timestamps.get(username)

    def update_last_story_time(self, username: str, timestamp: str):
        """
        Update the last story timestamp for a user
        
        Args:
            username (str): Instagram username
            timestamp (str): ISO format timestamp of the story
        """
        current = self.user_timestamps.get(username)
        if not current or timestamp > current:
            self.user_timestamps[username] = timestamp
            self._save_history()