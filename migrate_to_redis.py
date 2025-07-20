#!/usr/bin/env python3
"""
Migration script to move data from JSON files to Redis database.
Run this script once when upgrading to Redis-based storage.

Usage:
    python migrate_to_redis.py
"""

import os
import json
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.database import db
    from src.logger import get_logger
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)

def migrate_profiles():
    """Migrate monitored profiles from JSON to Redis."""
    logger = get_logger()
    profiles_file = os.path.join("data", "monitored_profiles.json")
    
    if not os.path.exists(profiles_file):
        logger.info("No monitored_profiles.json file found. Nothing to migrate.")
        return True
    
    try:
        with open(profiles_file, 'r') as f:
            json_data = json.load(f)
        
        # Handle different JSON formats
        if isinstance(json_data, list):
            # Convert list format to dict format
            redis_data = {}
            for entry in json_data:
                if isinstance(entry, dict) and 'chat_id' in entry:
                    chat_id = str(entry['chat_id'])
                    profiles = entry.get('profiles', {})
                    redis_data[chat_id] = profiles
        elif isinstance(json_data, dict):
            # Already in dict format, check if it needs conversion
            redis_data = {}
            for chat_id, chat_data in json_data.items():
                if isinstance(chat_data, dict) and 'profiles' in chat_data:
                    # New format with metadata
                    redis_data[chat_id] = chat_data['profiles']
                else:
                    # Old format, direct profiles
                    redis_data[chat_id] = chat_data
        else:
            logger.error("Unknown JSON format in monitored_profiles.json")
            return False
        
        # Ensure all profiles have required fields
        for chat_id, profiles in redis_data.items():
            for username, profile_data in profiles.items():
                if isinstance(profile_data, str):
                    # Old format: just story ID
                    redis_data[chat_id][username] = {
                        "last_story_id": profile_data,
                        "added_at": datetime.now().isoformat(),
                        "last_check": None,
                        "fail_count": 0
                    }
                elif isinstance(profile_data, dict):
                    # Ensure all required fields exist
                    profile_data.setdefault("added_at", datetime.now().isoformat())
                    profile_data.setdefault("last_check", None)
                    profile_data.setdefault("fail_count", 0)
        
        # Save to Redis
        if db.save_all_profiles(redis_data):
            logger.info(f"Successfully migrated {len(redis_data)} chats with profiles to Redis.")
            
            # Backup original file
            backup_file = profiles_file + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(profiles_file, backup_file)
            logger.info(f"Original file backed up to {backup_file}")
            
            return True
        else:
            logger.error("Failed to save profiles to Redis")
            return False
            
    except Exception as e:
        logger.error(f"Error migrating profiles: {e}")
        return False

def migrate_dlq():
    """Migrate Dead Letter Queue from JSON to Redis."""
    logger = get_logger()
    dlq_file = os.path.join("data", "dlq.json")
    
    if not os.path.exists(dlq_file):
        logger.info("No dlq.json file found. Nothing to migrate.")
        return True
    
    try:
        with open(dlq_file, 'r') as f:
            json_data = json.load(f)
        
        # Handle different DLQ formats
        if isinstance(json_data, list):
            dlq_items = json_data
        elif isinstance(json_data, dict):
            # Flatten dict format to list
            dlq_items = []
            for chat_id, items in json_data.items():
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            item.setdefault("chat_id", int(chat_id))
                        dlq_items.append(item)
        else:
            logger.warning("Unknown DLQ format, skipping migration")
            return True
        
        # Save to Redis (only last 100 items)
        dlq_items = dlq_items[-100:]
        
        if dlq_items:
            db.redis.set("dlq", json.dumps(dlq_items))
            logger.info(f"Successfully migrated {len(dlq_items)} DLQ items to Redis.")
            
            # Backup original file
            backup_file = dlq_file + f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.rename(dlq_file, backup_file)
            logger.info(f"Original DLQ file backed up to {backup_file}")
        else:
            logger.info("No DLQ items to migrate.")
        
        return True
        
    except Exception as e:
        logger.error(f"Error migrating DLQ: {e}")
        return False

def main():
    """Main migration function."""
    logger = get_logger()
    
    print("Starting migration from JSON to Redis...")
    logger.info("Starting migration from JSON to Redis")
    
    # Test Redis connection
    try:
        db.redis.ping()
        print("✅ Redis connection successful")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("Please check your REDIS_URL environment variable and Redis service.")
        return False
    
    # Migrate profiles
    print("Migrating monitored profiles...")
    if not migrate_profiles():
        print("❌ Failed to migrate profiles")
        return False
    print("✅ Profiles migrated successfully")
    
    # Migrate DLQ
    print("Migrating Dead Letter Queue...")
    if not migrate_dlq():
        print("❌ Failed to migrate DLQ")
        return False
    print("✅ DLQ migrated successfully")
    
    print("\n🎉 Migration completed successfully!")
    print("Your data has been moved to Redis. Original files have been backed up.")
    print("You can now delete the backed up files once you've verified everything works correctly.")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
