import os
import shutil
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def cleanup_downloads():
    """Clean up the downloads directory while preserving the data folder."""
    # Get the root directory (parent of src)
    root_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        # Clean up downloads directory
        downloads_dir = "downloads"
        if os.path.exists(downloads_dir):
            logger.info(f"Cleaning up {downloads_dir} directory...")
            shutil.rmtree(downloads_dir)
            os.makedirs(downloads_dir, exist_ok=True)
            logger.info(f"Successfully cleaned up {downloads_dir}")

        # Clean up debug videos
        debug_dir = "debug_videos"
        if os.path.exists(debug_dir):
            logger.info(f"Cleaning up {debug_dir} directory...")
            shutil.rmtree(debug_dir)
            logger.info(f"Successfully cleaned up {debug_dir}")

        # Clean up __pycache__
        for root, dirs, files in os.walk('.'):
            for dir_name in dirs:
                if dir_name == '__pycache__':
                    cache_path = os.path.join(root, dir_name)
                    logger.info(f"Cleaning up {cache_path}...")
                    shutil.rmtree(cache_path)

        # Ensure data directory exists and is preserved
        data_dir = "data"
        os.makedirs(data_dir, exist_ok=True)
        logger.info("Cleanup completed successfully")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        raise

if __name__ == "__main__":
    cleanup_downloads()
