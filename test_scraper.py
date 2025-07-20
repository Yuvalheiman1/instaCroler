import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure the src directory is in the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.database import db
from run_scraper import StoryScraper
from src.logger import get_logger

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
TEST_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "12345") # Use your chat ID or a placeholder
TEST_USERNAME = "instagram" # A public profile with frequent stories, good for testing
# ---

async def main():
    """
    A dedicated test script to add a profile to Redis and run the scraper once.
    """
    logger = get_logger()
    
    logger.info("--- Starting Scraper Test ---")
    
    # 1. Add a test profile to the Redis database
    logger.info(f"Attempting to add test profile '{TEST_USERNAME}' for chat ID {TEST_CHAT_ID}...")
    try:
        if db.add_profile(TEST_CHAT_ID, TEST_USERNAME):
            logger.info(f"Successfully added '{TEST_USERNAME}' to the database for testing.")
        else:
            logger.warning(f"'{TEST_USERNAME}' was already in the database.")
        
        # Verify it's there
        profiles = db.get_all_profiles()
        logger.info(f"Current profiles in Redis: {profiles}")

    except Exception as e:
        logger.error(f"Failed to add profile to Redis. Is Redis running? Error: {e}")
        logger.error("Please ensure your local Redis container is running with: docker-compose up -d")
        return

    # 2. Initialize and run the scraper
    logger.info("Initializing the StoryScraper...")
    scraper = StoryScraper()
    
    try:
        logger.info("Starting browser...")
        await scraper.downloader.start_browser()
        
        logger.info("Processing all profiles (will pick up the test profile)...")
        await scraper.process_all_profiles()
        
        logger.info("--- Scraper Test Finished ---")
        
    except Exception as e:
        logger.critical(f"A critical error occurred during the scraper run: {e}")
    finally:
        logger.info("Closing browser...")
        await scraper.downloader.close_browser()

if __name__ == "__main__":
    # Ensure you have a .env file with your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        print("ERROR: TELEGRAM_BOT_TOKEN not found in .env file. Please create one.")
    else:
        asyncio.run(main())
