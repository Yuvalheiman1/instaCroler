import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()
from src.scraper import StoryScraper

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
    """Main entry point for the scraper."""
    try:
        scraper = StoryScraper()
        await scraper.process_all_profiles()
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
