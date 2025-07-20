import redis
import os
import json
import logging

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
            self.redis = redis.from_url(redis_url, decode_responses=True)
            self.redis.ping()
            logger.info("Successfully connected to Redis.")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    # --- Profile Management ---
    def get_all_profiles(self):
        """Retrieves all monitored profiles from Redis."""
        profiles_json = self.redis.get("monitored_profiles")
        return json.loads(profiles_json) if profiles_json else {}

    def save_all_profiles(self, profiles_data):
        """Saves the entire profiles dictionary to Redis."""
        self.redis.set("monitored_profiles", json.dumps(profiles_data))

    def add_profile(self, chat_id, username):
        """Adds a new profile for a given chat_id."""
        profiles = self.get_all_profiles()
        chat_id_str = str(chat_id)
        if chat_id_str not in profiles:
            profiles[chat_id_str] = {}
        if username not in profiles[chat_id_str]:
            profiles[chat_id_str][username] = {"last_story_id": None}
            self.save_all_profiles(profiles)
            return True
        return False

    def remove_profile(self, chat_id, username):
        """Removes a profile for a given chat_id."""
        profiles = self.get_all_profiles()
        chat_id_str = str(chat_id)
        if chat_id_str in profiles and username in profiles[chat_id_str]:
            del profiles[chat_id_str][username]
            if not profiles[chat_id_str]:
                del profiles[chat_id_str]
            self.save_all_profiles(profiles)
            return True
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
            self.save_all_profiles(profiles)
            return True
        return False

    # --- Pause/Resume State ---
    def is_paused(self):
        """Checks if the bot is paused."""
        return self.redis.exists("bot_paused")

    def pause(self):
        """Sets the bot state to paused."""
        self.redis.set("bot_paused", "1")

    def resume(self):
        """Sets the bot state to resumed."""
        self.redis.delete("bot_paused")

    # --- DLQ Management ---
    def get_dlq(self):
        """Retrieves the Dead Letter Queue from Redis."""
        dlq_json = self.redis.get("dlq")
        return json.loads(dlq_json) if dlq_json else []

    def add_to_dlq(self, failed_item):
        """Adds a failed item to the Dead Letter Queue."""
        dlq = self.get_dlq()
        dlq.append(failed_item)
        self.redis.set("dlq", json.dumps(dlq))

# Singleton instance
db = RedisManager()
