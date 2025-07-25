"""
Logging configuration for Instagram Story Scraper
"""
import logging
import os
from datetime import datetime

try:
    from .config import Config
except ImportError:
    # Handle direct execution
    from config import Config

class ProfileLogger:
    """Logger with profile context"""
    def __init__(self, profile_name=None):
        self.profile_name = profile_name
        self.base_logger = logging.getLogger('instagram_scraper')
        
    def _format_message(self, message):
        if self.profile_name:
            return f"[{self.profile_name}] {message}"
        return message
    
    def info(self, message):
        self.base_logger.info(self._format_message(message))
    
    def error(self, message, exc_info=False):
        self.base_logger.error(self._format_message(message), exc_info=exc_info)
    
    def warning(self, message):
        self.base_logger.warning(self._format_message(message))
    
    def debug(self, message):
        self.base_logger.debug(self._format_message(message))

class Logger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # Create logs directory
        os.makedirs(Config.DIRECTORIES['logs'], exist_ok=True)
        
        # Create logger
        self.logger = logging.getLogger('instagram_scraper')
        self.logger.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # Create formatters
        formatter = logging.Formatter(Config.LOG_FORMAT)
        
        # File handler (rotating daily) - UTF-8 encoding
        log_filename = f"scraper_{datetime.now().strftime('%Y%m%d')}.log"
        log_path = os.path.join(Config.DIRECTORIES['logs'], log_filename)
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        # Console handler with Windows-compatible encoding
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # Create a custom formatter that replaces problematic Unicode characters
        class WindowsCompatibleFormatter(logging.Formatter):
            def format(self, record):
                msg = super().format(record)
                # Replace common problematic emoji/unicode chars for Windows console
                emoji_replacements = {
                    '✅': '[OK]',
                    '❌': '[ERROR]',
                    '⚠️': '[WARNING]', 
                    '🎉': '[SUCCESS]',
                    '🚀': '[START]',
                    '📋': '[LIST]',
                    '🔄': '[RUNNING]',
                    '⏸️': '[PAUSED]',
                    '📊': '[STATS]',
                    '🟦': '[ANONYIG]',
                    '🟩': '[INSTA]',
                    '🏆': '[BEST]',
                    '📈': '[TOTAL]',
                    '🧪': '[TEST]',
                    '🔍': '[SEARCH]',
                    '💥': '[FATAL]',
                    '⏹️': '[STOP]',
                    '⏰': '[TIME]'
                }
                for emoji, replacement in emoji_replacements.items():
                    msg = msg.replace(emoji, replacement)
                return msg
        
        windows_formatter = WindowsCompatibleFormatter(Config.LOG_FORMAT)
        console_handler.setFormatter(windows_formatter)
        
        # Add handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def get_logger(self):
        return self.logger
    
    def get_profile_logger(self, profile_name):
        return ProfileLogger(profile_name)

# Convenience functions
def get_logger():
    return Logger().get_logger()

def get_profile_logger(profile_name):
    return Logger().get_profile_logger(profile_name)

def log_info(message):
    get_logger().info(message)

def log_error(message, exc_info=False):
    get_logger().error(message, exc_info=exc_info)

def log_warning(message):
    get_logger().warning(message)

def log_debug(message):
    get_logger().debug(message)
