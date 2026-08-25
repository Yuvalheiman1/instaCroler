#!/usr/bin/env python3
"""
Instagram Story Scraper - Scheduled Scraper
This script runs periodically to check for new Instagram stories from monitored profiles.
It downloads new stories and sends them to the configured Telegram chat.
"""

import os
import sys
import logging
import asyncio
import traceback
from datetime import datetime
from argparse import ArgumentParser

# Set up path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import project modules
from src.downloader import InstagramStoryScraper
from src.database import RedisManager
from src.config import Config
from src.logger import Logger, ProfileLogger

# Set up logging
logger_instance = Logger()
logger = logger_instance.get_profile_logger('run_scraper')

# Initialize Redis Manager
db = RedisManager()

# Check if the bot is paused
def is_bot_paused():
    """Check if the bot is currently paused."""
    try:
        paused = db.redis.get("bot_paused")
        return paused == "1"
    except Exception as e:
        logger.error(f"Error checking if bot is paused: {e}")
        return False

# Process a single profile
async def process_profile(chat_id, username, profile_data):
    """
    Process a single Instagram profile to check for new stories.
    
    Args:
        chat_id: Telegram chat ID
        username: Instagram username
        profile_data: Profile data from Redis
        
    Returns:
        Tuple of (success, stories_found, new_last_id)
    """
    last_known_id = profile_data.get("last_story_id")
    logger.info(f"Processing {username} (Last known ID: {last_known_id})")
    
    try:
        # Initialize scraper
        scraper = InstagramStoryScraper(enable_telegram=True)
        
        # Scrape stories
        story_results, newest_id = await scraper.scrape_stories(username, last_known_id)
        
        # Update last check time
        profiles = db.get_all_profiles()
        if str(chat_id) in profiles and username in profiles[str(chat_id)]:
            profiles[str(chat_id)][username]["last_check"] = datetime.now().isoformat()
            
            # Only update last_story_id if we found new stories
            if newest_id != last_known_id:
                profiles[str(chat_id)][username]["last_story_id"] = newest_id
                
            # Reset fail count on success
            profiles[str(chat_id)][username]["fail_count"] = 0
            
            db.save_all_profiles(profiles)
        
        # Clean up resources
        scraper.cleanup()
        
        return True, len(story_results), newest_id
        
    except Exception as e:
        logger.error(f"Error processing profile {username}: {e}")
        logger.error(traceback.format_exc())
        
        # Increment fail count
        try:
            profiles = db.get_all_profiles()
            if str(chat_id) in profiles and username in profiles[str(chat_id)]:
                profiles[str(chat_id)][username]["fail_count"] = profiles[str(chat_id)][username].get("fail_count", 0) + 1
                db.save_all_profiles(profiles)
        except Exception as e_inner:
            logger.error(f"Error updating fail count: {e_inner}")
            
        return False, 0, last_known_id

# Main function to process all profiles
async def process_all_profiles(only_profile=None, only_chat=None):
    """
    Process the monitored profiles, one after another.

    Args:
        only_profile: If set, process only this Instagram username
        only_chat: If set, process only the profiles of this Telegram chat ID
    """
    if is_bot_paused():
        logger.info("Bot is currently paused. Skipping scrape.")
        return
        
    logger.info("Starting scheduled Instagram story scrape")
    
    # Get all profiles from Redis
    profiles = db.get_all_profiles()
    if not profiles:
        logger.info("No profiles to monitor. Exiting.")
        return

    if only_chat is not None:
        profiles = {k: v for k, v in profiles.items() if str(k) == str(only_chat)}
        if not profiles:
            logger.warning(f"No monitored profiles for chat {only_chat}. Exiting.")
            return

    # Process each chat's profiles
    for chat_id, chat_profiles in profiles.items():
        for username, profile_data in chat_profiles.items():
            if only_profile is not None and username != only_profile:
                continue

            # Process the profile
            success, stories_count, new_last_id = await process_profile(chat_id, username, profile_data)
            
            if success:
                if stories_count > 0:
                    logger.info(f"Found {stories_count} new stories for {username}")
                else:
                    logger.info(f"No new stories for {username}")
            else:
                logger.warning(f"Failed to process {username}")
                
    logger.info("Finished scheduled Instagram story scrape")

# Cleanup resources
def cleanup_resources():
    """Clean up any resources before exiting"""
    # Implement any cleanup logic here
    logger.info("Cleaning up resources")

# Entry point
if __name__ == "__main__":
    parser = ArgumentParser(description="Instagram Story Scraper")
    parser.add_argument("--profile", help="Process only the specified profile")
    parser.add_argument("--chat", help="Process only profiles for the specified chat ID")
    args = parser.parse_args()
    
    try:
        # Run the scraper
        asyncio.run(process_all_profiles(only_profile=args.profile, only_chat=args.chat))
    finally:
        # Ensure resources are cleaned up
        cleanup_resources()
