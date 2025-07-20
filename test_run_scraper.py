#!/usr/bin/env python3
"""
Test script for the run_scraper.py module.
This script tests the StoryScraper functionality locally.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Load environment variables
load_dotenv()

from src.database import db
from run_scraper import StoryScraper

async def test_scraper():
    """Test the StoryScraper functionality."""
    print("🧪 Starting run_scraper test...")
    
    # Create scraper instance
    try:
        scraper = StoryScraper()
        print("✅ StoryScraper initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize StoryScraper: {e}")
        return False
    
    # Test database connection
    try:
        print("\n📊 Testing database connection...")
        all_profiles = scraper.db.get_all_profiles()
        print(f"✅ Database connected. Found {len(all_profiles)} chat(s) with profiles")
        
        # Display current profiles
        if all_profiles:
            for chat_id, profiles in all_profiles.items():
                print(f"  Chat {chat_id}: {len(profiles)} profiles")
                for username, data in profiles.items():
                    last_id = data.get('last_story_id', 'None')
                    print(f"    - {username} (last ID: {last_id})")
        else:
            print("  No profiles found in database")
            
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False
    
    # Test bot connection
    try:
        print("\n🤖 Testing Telegram bot connection...")
        bot_info = await scraper.bot.get_me()
        print(f"✅ Bot connected: @{bot_info.username} ({bot_info.first_name})")
    except Exception as e:
        print(f"❌ Bot connection failed: {e}")
        return False
    
    # Test if bot is paused
    try:
        print("\n⏸️ Checking bot status...")
        is_paused = scraper.db.is_paused()
        status = "Paused" if is_paused else "Running"
        print(f"✅ Bot status: {status}")
    except Exception as e:
        print(f"❌ Failed to check bot status: {e}")
        return False
    
    # Test downloader initialization
    try:
        print("\n📥 Testing downloader...")
        downloader = scraper.downloader
        print(f"✅ Downloader initialized: {type(downloader).__name__}")
    except Exception as e:
        print(f"❌ Downloader test failed: {e}")
        return False
    
    # Test process_all_profiles (dry run)
    try:
        print("\n🔄 Testing process_all_profiles method...")
        if not all_profiles:
            print("⚠️ No profiles to process - adding a test profile")
            # Add a test profile for demonstration
            test_chat_id = str(scraper.bot_token.split(':')[0])  # Use bot ID as test chat
            scraper.db.add_profile(test_chat_id, "test_profile")
            print(f"✅ Added test profile for chat {test_chat_id}")
        
        print("🚀 Running process_all_profiles...")
        await scraper.process_all_profiles()
        print("✅ process_all_profiles completed successfully")
        
    except Exception as e:
        print(f"❌ process_all_profiles failed: {e}")
        return False
    
    # Cleanup
    try:
        await scraper.bot.close()
        print("✅ Bot connection closed")
    except Exception as e:
        print(f"⚠️ Warning during cleanup: {e}")
    
    print("\n🎉 All tests passed! run_scraper.py is working correctly.")
    return True

async def main():
    """Main test function."""
    print("=" * 50)
    print("🔧 Run Scraper Test Suite")
    print("=" * 50)
    
    # Check environment variables
    required_vars = ['TELEGRAM_BOT_TOKEN', 'REDIS_URL']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("Please check your .env file")
        return
    
    # Run tests
    success = await test_scraper()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ TEST RESULT: PASSED")
    else:
        print("❌ TEST RESULT: FAILED")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
