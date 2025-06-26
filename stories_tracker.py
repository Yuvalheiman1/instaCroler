import json
import os
import threading

class StoriesTracker:
    """
    A thread-safe class to track the last story ID for each user.
    It persists the data to a JSON file.
    """
    def __init__(self, filepath="stories_tracker.json"):
        """
        Initializes the tracker.

        Args:
            filepath (str): The path to the JSON file for storing data.
        """
        self.filepath = filepath
        self._lock = threading.Lock()
        self.data = self._load_data()

    def _load_data(self) -> dict:
        """Loads the tracking data from the JSON file."""
        with self._lock:
            if os.path.exists(self.filepath):
                with open(self.filepath, 'r') as f:
                    try:
                        return json.load(f)
                    except json.JSONDecodeError:
                        # Return an empty dictionary if the file is corrupt or empty
                        return {}
            return {}

    def _save_data(self):
        """Saves the current tracking data to the JSON file."""
        with self._lock:
            with open(self.filepath, 'w') as f:
                json.dump(self.data, f, indent=4)

    def get_last_story_id(self, username: str) -> str | None:
        """
        Retrieves the last known story ID for a given username.

        Args:
            username (str): The Instagram username.

        Returns:
            str or None: The last story ID, or None if not found.
        """
        return self.data.get(username)

    def update_last_story_id(self, username: str, story_id: str):
        """
        Updates the last story ID for a username and saves it to the file.

        Args:
            username (str): The Instagram username.
            story_id (str): The new latest story ID.
        """
        self.data[username] = story_id
        self._save_data()

