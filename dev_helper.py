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
    from src.downloader import AnonyigDownloader, ConcurrentDownloader
    
    # Test regular downloader
    print("Testing regular downloader...")
    downloader = AnonyigDownloader()
    try:
        results, newest_id = await downloader.download_user_stories(username, "0")
        print(f"✅ Regular scraper test completed")
        print(f"   - Found {len(results)} stories")
        print(f"   - Newest ID: {newest_id}")
        
        if results:
            print("   - Downloaded files:")
            for file_path, story_id in results:
                print(f"     • {file_path} (ID: {story_id})")
    except Exception as e:
        print(f"❌ Regular scraper test failed: {e}")
    
    # Test concurrent downloader
    print("\nTesting concurrent downloader...")
    concurrent_downloader = ConcurrentDownloader(max_workers=2)
    try:
        profile_data = {username: "0"}
        results_dict = await concurrent_downloader.download_multiple_profiles(profile_data)
        
        if username in results_dict:
            concurrent_results, concurrent_newest_id = results_dict[username]
            print(f"✅ Concurrent scraper test completed")
            print(f"   - Found {len(concurrent_results)} stories")
            print(f"   - Newest ID: {concurrent_newest_id}")
            
            if concurrent_results:
                print("   - Downloaded files:")
                for file_path, story_id in concurrent_results:
                    print(f"     • {file_path} (ID: {story_id})")
        else:
            print(f"❌ No results found for {username} in concurrent test")
    except Exception as e:
        print(f"❌ Concurrent scraper test failed: {e}")

async def test_multiple_profiles(usernames):
    """Test the concurrent downloader with multiple profiles."""
    print(f"🧪 Testing concurrent downloader with {len(usernames)} profiles: {', '.join(usernames)}")
    
    sys.path.append('src')
    from src.downloader import ConcurrentDownloader
    import time
    
    concurrent_downloader = ConcurrentDownloader(max_workers=3)
    
    # Prepare profile data
    profile_data = {username: "0" for username in usernames}
    
    try:
        start_time = time.time()
        results_dict = await concurrent_downloader.download_multiple_profiles(profile_data)
        end_time = time.time()
        
        print(f"✅ Concurrent test completed in {end_time - start_time:.2f} seconds")
        
        total_stories = 0
        for username, (stories, newest_id) in results_dict.items():
            print(f"   - {username}: {len(stories)} stories (newest ID: {newest_id})")
            total_stories += len(stories)
        
        print(f"   - Total stories downloaded: {total_stories}")
        
    except Exception as e:
        print(f"❌ Concurrent multiple profiles test failed: {e}")

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
