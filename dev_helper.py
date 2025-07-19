#!/usr/bin/env python3
"""
Development helper script for the Instagram Story Monitor Bot.
Provides utilities for testing and development.
"""
import asyncio
import os
import sys
import argparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def setup_directories():
    """Create necessary directories."""
    dirs = ['data', 'downloads', 'logs', 'debug_videos']
    for dir_name in dirs:
        os.makedirs(dir_name, exist_ok=True)
        print(f"✅ Created directory: {dir_name}")

def check_env():
    """Check if required environment variables are set."""
    required_vars = ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
    missing = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print("❌ Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\nPlease check your .env file.")
        return False
    else:
        print("✅ All required environment variables are set")
        return True

async def test_scraper(username):
    """Test the scraper with a specific username."""
    print(f"🧪 Testing scraper with username: {username}")
    
    sys.path.append('src')
    from src.downloader import AnonyigDownloader
    
    downloader = AnonyigDownloader()
    try:
        results, newest_id = await downloader.download_user_stories(username, "0")
        print(f"✅ Scraper test completed")
        print(f"   - Found {len(results)} stories")
        print(f"   - Newest ID: {newest_id}")
        
        if results:
            print("   - Downloaded files:")
            for file_path, story_id in results:
                print(f"     • {file_path} (ID: {story_id})")
    except Exception as e:
        print(f"❌ Scraper test failed: {e}")

def run_bot():
    """Run the main bot."""
    print("🤖 Starting Instagram Story Monitor Bot...")
    os.system("python bot_main.py")

def run_scraper():
    """Run the scraper once."""
    print("🔍 Running scraper...")
    os.system("python run_scraper.py")

def clean_downloads():
    """Clean the downloads directory."""
    import shutil
    if os.path.exists('downloads'):
        shutil.rmtree('downloads')
    os.makedirs('downloads', exist_ok=True)
    print("🧹 Cleaned downloads directory")

def show_status():
    """Show current bot status."""
    print("📊 Bot Status:")
    
    # Check if bot is paused
    if os.path.exists(os.path.join('data', 'bot_paused.flag')):
        print("   🔴 Bot is PAUSED")
    else:
        print("   🟢 Bot is ACTIVE")
    
    # Check profiles
    profiles_file = os.path.join('data', 'monitored_profiles.json')
    if os.path.exists(profiles_file):
        import json
        with open(profiles_file, 'r') as f:
            data = json.load(f)
        
        total_profiles = 0
        for chat_data in data.values():
            total_profiles += len(chat_data.get('profiles', {}))
        
        print(f"   👥 Monitored profiles: {total_profiles}")
    else:
        print("   👥 No profiles configured")
    
    # Check DLQ
    dlq_file = os.path.join('data', 'dlq.json')
    if os.path.exists(dlq_file):
        import json
        with open(dlq_file, 'r') as f:
            dlq_data = json.load(f)
        
        # Handle both old list format and new dict format
        if isinstance(dlq_data, dict):
            total_errors = sum(len(errors) for errors in dlq_data.values())
        else:
            total_errors = len(dlq_data)  # Old list format
            
        if total_errors > 0:
            print(f"   ⚠️  Recent errors: {total_errors}")

def main():
    parser = argparse.ArgumentParser(description='Instagram Story Monitor Bot Development Helper')
    parser.add_argument('command', choices=[
        'setup', 'check-env', 'test-scraper', 'run-bot', 'run-scraper', 
        'clean', 'status'
    ], help='Command to run')
    parser.add_argument('--username', help='Username for testing scraper')
    
    args = parser.parse_args()
    
    if args.command == 'setup':
        setup_directories()
        check_env()
    elif args.command == 'check-env':
        check_env()
    elif args.command == 'test-scraper':
        if not args.username:
            print("❌ Please provide a username with --username")
            return
        asyncio.run(test_scraper(args.username))
    elif args.command == 'run-bot':
        run_bot()
    elif args.command == 'run-scraper':
        run_scraper()
    elif args.command == 'clean':
        clean_downloads()
    elif args.command == 'status':
        show_status()

if __name__ == "__main__":
    main()
