"""
Configuration file for Instagram Story Scraper
"""
import os

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, use system env vars

class Config:
    # Support for both insta-stories-viewer.com and anonyig.com
    
    # Smart downloader settings - now supports comparison between sources
    SMART_DOWNLOAD = {
        'enabled': True,  # Now compares between sources
        'count_timeout': 30,  # seconds for counting stories
        'prefer_anonyig': False,  # Set to True to prefer anonyig when counts are equal
    }
    
    # Selectors for both sources
    SELECTORS = {
        # insta-stories-viewer.com specific selectors
        'insta_stories': {
            'stories_container': 'ul.profile__tabs-media.profile__stories',
            'story_items': 'ul.profile__tabs-media.profile__stories > li.profile__tabs-media-item',
            'story_link': 'span.profile__tabs-media-item-link',
        },
        # anonyig.com specific selectors
        'anonyig': {
            'search_textbox': '@username or link',
            'search_button': 'button[text=""]',  # Empty text button
            'stories_button': 'button[name="stories"]',
            'story_items': 'li > .media-content__info > .button',
            'download_link': 'a[href*="download"], .download-btn, [download]',
        }
    }
    
    # Timeouts and delays (in milliseconds) - optimized for both sources
    TIMEOUTS = {
        'page_load': 30000,         # 30 seconds for page loading
        'element_wait': 20000,      # 20 seconds for elements to appear
        'search_delay': 2000,       # 2 seconds after search input
        'stories_tab_delay': 2000,  # 2 seconds after clicking stories tab
        'lazy_load_wait': 5000,     # 5 seconds for lazy loading content
        'lazy_load_scroll_delay': 1000,  # 1 second between lazy load scrolls
        'scroll_delay': 1000,       # 1 second between scrolls
        'download_delay': 500,
        'retry_base_delay': 1000,
        'browser_launch_delay': 5000,
        'download': 30000,          # 30 seconds for file downloads
        'new_page_wait': 10000,     # 10 seconds for new pages to load
        'anonyig_story_delay': 500, # Delay between story processing on anonyig
        'anonyig_lazy_load_max_scrolls': 10,  # Max scrolls for lazy loading
        'anonyig_lazy_load_scroll_step': 500,  # Pixels per scroll step
    }
    
    # Download settings
    DOWNLOAD_SETTINGS = {
        'max_retries': 3,
        'max_lazy_load_attempts': 15,
        'chunk_size': 8192,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'max_concurrent_workers': 2,  # Reduced from 5 to 2 to prevent page crashes
        'max_concurrent_downloads': 2,  # Also reduced to be safer
        'enable_concurrent': True,
        'browser_launch_stagger': True,
        'slow_connection_mode': False,
        'enable_debug_video': True,  # Set to True to record browser sessions for debugging
        'debug_video_quality': 'high'  # Can be 'low', 'medium', or 'high'
    }
    
    # File extensions
    FILE_EXTENSIONS = {
        'video': '.mp4',
        'image': '.jpg',
        'supported_video': ['.mp4', '.mov', '.avi'],
        'supported_image': ['.jpg', '.jpeg', '.png', '.webp']
    }
    
    # File extensions for different media types
    FILE_EXTENSIONS = {
        'video': '.mp4',
        'image': '.jpg'
    }
    
    # Directories
    DIRECTORIES = {
        'downloads': 'downloads',
        'debug_videos': 'debug_videos',
        'data': 'data',
        'logs': 'logs'
    }
    
    # Environment variables
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
    REDIS_URL = os.getenv('REDIS_URL')
    
    # Logging configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Redis configuration
    REDIS_SETTINGS = {
        'decode_responses': True,
        'socket_connect_timeout': 5,
        'socket_timeout': 5,
        'retry_on_timeout': True,
        'health_check_interval': 30
    }
