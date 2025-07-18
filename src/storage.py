import json
import os
import logging
from typing import List, Dict, Optional
from datetime import datetime

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Storage:
    def get_story_tracker(self) -> dict:
        """Get the last known story IDs for each username."""
        tracker_file = os.path.join(self.data_dir, "stories_tracker.json")
        if not os.path.exists(tracker_file):
            with open(tracker_file, 'w') as f:
                json.dump({}, f)
        try:
            with open(tracker_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading {tracker_file}: {e}")
            data = {}
        return data

    def update_story_tracker(self, username: str, last_story_id: str):
        """Update the last known story ID for a username."""
        tracker_file = os.path.join(self.data_dir, "stories_tracker.json")
        data = self.get_story_tracker()
        data[username] = last_story_id
        try:
            with open(tracker_file, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving to {tracker_file}: {e}")
            return False
    """
    Handles persistent storage for tracked profiles and their states.
    Supports both JSON file and PostgreSQL storage backends.
    """
    def __init__(self, storage_type: str = "json"):
        """
        Initialize storage backend.
        Args:
            storage_type: Either "json" or "postgres"
        """
        self.storage_type = storage_type
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Files for JSON storage
        self.profiles_file = os.path.join(self.data_dir, "monitored_profiles.json")
        self.dlq_file = os.path.join(self.data_dir, "dlq.json")  # Dead Letter Queue for failed attempts
        
        # Initialize storage files if they don't exist
        self._init_storage()
    
    def _init_storage(self):
        """Initialize storage files with empty data if they don't exist."""
        if self.storage_type == "json":
            for file_path in [self.profiles_file, self.dlq_file]:
                if not os.path.exists(file_path):
                    with open(file_path, 'w') as f:
                        json.dump({}, f)
    
    def _load_json(self, file_path: str) -> dict:
        """Load data from a JSON file with error handling."""
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
            return {}

    def _save_json(self, data: dict, file_path: str) -> bool:
        """Save data to a JSON file with error handling."""
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving to {file_path}: {e}")
            return False

    def add_profile(self, chat_id: int, username: str) -> bool:
        """
        Add a profile to be monitored for a specific chat.
        
        Args:
            chat_id: Telegram chat ID
            username: Instagram username to monitor
        
        Returns:
            bool: True if successful, False otherwise
        """
        data = self._load_json(self.profiles_file)
        chat_id_str = str(chat_id)
        
        if chat_id_str not in data:
            data[chat_id_str] = {"profiles": {}}
        
        if username not in data[chat_id_str]["profiles"]:
            data[chat_id_str]["profiles"][username] = {
                "added_at": datetime.now().isoformat(),
                "last_story_id": None,
                "last_check": None,
                "fail_count": 0
            }
            return self._save_json(data, self.profiles_file)
        return True

    def remove_profile(self, chat_id: int, username: str) -> bool:
        """Remove a monitored profile for a specific chat."""
        data = self._load_json(self.profiles_file)
        chat_id_str = str(chat_id)
        
        if chat_id_str in data and username in data[chat_id_str]["profiles"]:
            del data[chat_id_str]["profiles"][username]
            if not data[chat_id_str]["profiles"]:  # Remove chat if no profiles left
                del data[chat_id_str]
            return self._save_json(data, self.profiles_file)
        return False

    def get_profiles(self, chat_id: Optional[int] = None) -> Dict:
        """
        Get all monitored profiles, optionally filtered by chat_id.
        Supports both dict and list formats for backward compatibility.
        """
        data = self._load_json(self.profiles_file)
        # If data is a list, convert to dict format
        if isinstance(data, list):
            logger.info("monitored_profiles.json is a list, converting to dict format.")
            # Convert list of profiles to dict format
            converted = {}
            for entry in data:
                # Each entry should be a dict with chat_id and profiles
                if isinstance(entry, dict):
                    chat_id = str(entry.get('chat_id', 'unknown'))
                    profiles = entry.get('profiles', {})
                    converted[chat_id] = {'profiles': profiles}
            data = converted
        elif not isinstance(data, dict):
            logger.warning("monitored_profiles.json was not a dict or list, resetting to empty dict.")
            data = {}
            self._save_json(data, self.profiles_file)
        if chat_id is not None:
            return {str(chat_id): data.get(str(chat_id), {"profiles": {}})}
        return data

    def update_profile_status(self, chat_id: int, username: str, 
                            last_story_id: Optional[str] = None,
                            success: bool = True) -> bool:
        """Update the status of a profile after checking its stories."""
        data = self._load_json(self.profiles_file)
        chat_id_str = str(chat_id)
        
        if chat_id_str in data and username in data[chat_id_str]["profiles"]:
            profile = data[chat_id_str]["profiles"][username]
            profile["last_check"] = datetime.now().isoformat()
            
            if success:
                profile["fail_count"] = 0
                if last_story_id:
                    profile["last_story_id"] = last_story_id
            else:
                profile["fail_count"] = profile.get("fail_count", 0) + 1
            
            return self._save_json(data, self.profiles_file)
        return False

    def add_to_dlq(self, chat_id: int, username: str, error: str):
        """Add a failed attempt to the Dead Letter Queue."""
        data = self._load_json(self.dlq_file)
        entry = {
            "timestamp": datetime.now().isoformat(),
            "chat_id": chat_id,
            "username": username,
            "error": str(error)
        }
        
        if str(chat_id) not in data:
            data[str(chat_id)] = []
        data[str(chat_id)].append(entry)
        
        # Keep only last 100 errors per chat
        data[str(chat_id)] = data[str(chat_id)][-100:]
        
        return self._save_json(data, self.dlq_file)

    def get_dlq_entries(self, chat_id: int, limit: int = 10) -> List[Dict]:
        """Get recent DLQ entries for a chat."""
        data = self._load_json(self.dlq_file)
        return data.get(str(chat_id), [])[-limit:]
