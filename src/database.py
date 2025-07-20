import redis
import os
import json
import logging
from datetime import datetime

try:
    from .config import Config
except ImportError:
    # Handle direct execution
    from config import Config

# Configure logging
logger = logging.getLogger(__name__)

class RedisManager:
    def __init__(self):
        """
        Initializes the RedisManager, connecting to the Redis instance.
        It expects the REDIS_URL environment variable to be set,
        which Railway provides automatically when a Redis service is added.
        """
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.error("REDIS_URL environment variable not set. Please provision a Redis database in Railway.")
            raise ValueError("REDIS_URL not set")
            
        try:
            # Use config settings if available
            redis_settings = getattr(Config, 'REDIS_SETTINGS', {})
            self.redis = redis.from_url(redis_url, **redis_settings)
            self.redis.ping()
            logger.info("Successfully connected to Redis.")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis: {e}")
            raise

    # --- Profile Management ---
    def get_all_profiles(self):
        """Retrieves all monitored profiles from Redis."""
        try:
            profiles_json = self.redis.get("monitored_profiles")
            return json.loads(profiles_json) if profiles_json else {}
        except (redis.exceptions.RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error retrieving profiles from Redis: {e}")
            return {}

    def save_all_profiles(self, profiles_data):
        """Saves the entire profiles dictionary to Redis."""
        try:
            self.redis.set("monitored_profiles", json.dumps(profiles_data))
            return True
        except (redis.exceptions.RedisError, json.JSONEncodeError) as e:
            logger.error(f"Error saving profiles to Redis: {e}")
            return False

    def add_profile(self, chat_id, username):
        """Adds a new profile for a given chat_id."""
        try:
            profiles = self.get_all_profiles()
            chat_id_str = str(chat_id)
            if chat_id_str not in profiles:
                profiles[chat_id_str] = {}
            if username not in profiles[chat_id_str]:
                profiles[chat_id_str][username] = {
                    "last_story_id": None,
                    "added_at": datetime.now().isoformat(),
                    "last_check": None,
                    "fail_count": 0
                }
                return self.save_all_profiles(profiles)
            return False
        except Exception as e:
            logger.error(f"Error adding profile {username} for chat {chat_id}: {e}")
            return False

    def remove_profile(self, chat_id, username):
        """Removes a profile for a given chat_id."""
        try:
            profiles = self.get_all_profiles()
            chat_id_str = str(chat_id)
            if chat_id_str in profiles and username in profiles[chat_id_str]:
                del profiles[chat_id_str][username]
                if not profiles[chat_id_str]:
                    del profiles[chat_id_str]
                return self.save_all_profiles(profiles)
            return False
        except Exception as e:
            logger.error(f"Error removing profile {username} for chat {chat_id}: {e}")
            return False

    def get_profile_data(self, chat_id, username):
        """Retrieves all data for a specific profile."""
        profiles = self.get_all_profiles()
        return profiles.get(str(chat_id), {}).get(username)

    def update_last_story_id(self, chat_id, username, last_story_id):
        """Updates the last seen story ID for a profile."""
        profiles = self.get_all_profiles()
        chat_id_str = str(chat_id)
        if chat_id_str in profiles and username in profiles[chat_id_str]:
            profiles[chat_id_str][username]['last_story_id'] = last_story_id
            profiles[chat_id_str][username]['last_check'] = datetime.now().isoformat()
            self.save_all_profiles(profiles)
            return True
        return False

    def update_profile_status(self, chat_id, username, success=True, last_story_id=None):
        """Update the status of a profile after checking its stories."""
        profiles = self.get_all_profiles()
        chat_id_str = str(chat_id)
        
        if chat_id_str in profiles and username in profiles[chat_id_str]:
            profile = profiles[chat_id_str][username]
            profile["last_check"] = datetime.now().isoformat()
            
            if success:
                profile["fail_count"] = 0
                if last_story_id:
                    profile["last_story_id"] = last_story_id
            else:
                profile["fail_count"] = profile.get("fail_count", 0) + 1
            
            self.save_all_profiles(profiles)
            return True
        return False

    # --- Pause/Resume State ---
    def is_paused(self):
        """Checks if the bot is paused."""
        try:
            return self.redis.exists("bot_paused")
        except redis.exceptions.RedisError as e:
            logger.error(f"Error checking pause state: {e}")
            return False

    def pause(self):
        """Sets the bot state to paused."""
        try:
            self.redis.set("bot_paused", "1")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Error setting pause state: {e}")
            return False

    def resume(self):
        """Sets the bot state to resumed."""
        try:
            self.redis.delete("bot_paused")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Error removing pause state: {e}")
            return False

    # --- DLQ Management ---
    def get_dlq(self):
        """Retrieves the Dead Letter Queue from Redis."""
        try:
            dlq_json = self.redis.get("dlq")
            return json.loads(dlq_json) if dlq_json else []
        except (redis.exceptions.RedisError, json.JSONDecodeError) as e:
            logger.error(f"Error retrieving DLQ from Redis: {e}")
            return []

    def add_to_dlq(self, failed_item):
        """Adds a failed item to the Dead Letter Queue."""
        try:
            dlq = self.get_dlq()
            # Ensure the failed_item has a timestamp
            if isinstance(failed_item, dict):
                failed_item["timestamp"] = datetime.now().isoformat()
            dlq.append(failed_item)
            # Keep only last 100 errors
            dlq = dlq[-100:]
            self.redis.set("dlq", json.dumps(dlq))
            return True
        except (redis.exceptions.RedisError, json.JSONEncodeError) as e:
            logger.error(f"Error adding item to DLQ: {e}")
            return False

# Singleton instance
db = RedisManager()
