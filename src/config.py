"""
Configuration file for Instagram Story Scraper
"""
import os

class Config:
    # Site configuration
    BASE_URL = "https://anonyig.com/en/"
    
    # Selectors (easily updatable when site changes)
    SELECTORS = {
        'search_input': 'input.search.search-form__input',
        'stories_tab': 'button.tabs-component__button:has-text("stories")',
        'stories_container': '.output-profile',
        'story_items': 'ul.profile-media-list > li.profile-media-list__item',
        'download_button': '.button.button--filled.button__download',
        'media_content': '.media-content, .profile-media-list__item img, .profile-media-list__item video',
        'media_container': '.media-content',
        'lazy_load_triggers': '.hide-content__btn, .load-more-btn, .trigger'
    }
    
    # Timeouts and delays (in milliseconds)
    TIMEOUTS = {
        'page_load': 180000,  # Increased to 3 minutes for slow connections
        'element_wait': 60000,  # Increased to 1 minute
        'search_delay': 2000,   # Slightly increased
        'stories_tab_delay': 2000,  # Increased
        'scroll_delay': 1500,   # Slightly increased
        'download_delay': 1000,  # Increased for slower connections
        'retry_base_delay': 2000,  # Increased base delay
        'browser_launch_delay': 5000  # Increased delay between launches for slow connections
    }
    
    # Download settings
    DOWNLOAD_SETTINGS = {
        'max_retries': 3,
        'max_lazy_load_attempts': 15,
        'chunk_size': 4096,  # Reduced chunk size for slower connections
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'max_concurrent_workers': 4,  # Reduced to 1 for slow connections
        'max_concurrent_downloads': 2,  # Reduced for slow connections
        'enable_concurrent': False,  # Disabled by default for slow connections
        'browser_launch_stagger': True,  # Stagger browser launches to avoid timeouts
        'slow_connection_mode': True  # Enable optimizations for slow connections
    }
    
    # File extensions
    FILE_EXTENSIONS = {
        'video': '.mp4',
        'image': '.jpg',
        'supported_video': ['.mp4', '.mov', '.avi'],
        'supported_image': ['.jpg', '.jpeg', '.png', '.webp']
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
