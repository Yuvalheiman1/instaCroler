#!/usr/bin/env python3
"""
Redis health check and diagnostics script.
Useful for debugging Redis connection issues.

Usage:
    python redis_health_check.py
"""

import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.database import db
except ImportError as e:
    print(f"Error importing database module: {e}")
    print("Make sure you're running this from the project root directory.")
    sys.exit(1)
except ValueError as e:
    if "REDIS_URL not set" in str(e):
        print("❌ REDIS_URL environment variable not set")
        print("\n💡 To fix this:")
        print("1. For LOCAL development:")
        print("   - Install Redis: https://redis.io/download")
        print("   - Start Redis: redis-server")
        print("   - Add to .env file: REDIS_URL=redis://localhost:6379")
        print("   - Or use Docker: docker run -d -p 6379:6379 redis:alpine")
        print("\n2. For RAILWAY deployment:")
        print("   - Add Redis service in Railway dashboard")
        print("   - Railway will set REDIS_URL automatically")
        sys.exit(1)
    else:
        print(f"Database initialization error: {e}")
        sys.exit(1)

def test_redis_connection():
    """Test basic Redis connection."""
    try:
        db.redis.ping()
        print("✅ Redis connection: OK")
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def test_redis_operations():
    """Test basic Redis read/write operations."""
    test_key = "health_check_test"
    test_value = {"timestamp": datetime.now().isoformat(), "test": True}
    
    try:
        # Test write
        db.redis.set(test_key, json.dumps(test_value))
        print("✅ Redis write: OK")
        
        # Test read
        retrieved = db.redis.get(test_key)
        if retrieved:
            data = json.loads(retrieved)
            if data.get("test") == True:
                print("✅ Redis read: OK")
            else:
                print("❌ Redis read: Data corruption detected")
                return False
        else:
            print("❌ Redis read: No data retrieved")
            return False
        
        # Test delete
        db.redis.delete(test_key)
        print("✅ Redis delete: OK")
        
        return True
    except Exception as e:
        print(f"❌ Redis operations failed: {e}")
        return False

def check_existing_data():
    """Check existing data in Redis."""
    try:
        # Check profiles
        profiles = db.get_all_profiles()
        total_profiles = sum(len(p) for p in profiles.values()) if profiles else 0
        print(f"📊 Monitored profiles: {total_profiles} across {len(profiles)} chats")
        
        # Check pause state
        paused = db.is_paused()
        print(f"⏸️ Bot paused: {'Yes' if paused else 'No'}")
        
        # Check DLQ
        dlq = db.get_dlq()
        print(f"💀 DLQ entries: {len(dlq)}")
        
        return True
    except Exception as e:
        print(f"❌ Error checking existing data: {e}")
        return False

def show_redis_info():
    """Show Redis server information."""
    try:
        info = db.redis.info()
        print("\n📋 Redis Server Info:")
        print(f"   Version: {info.get('redis_version', 'Unknown')}")
        print(f"   Mode: {info.get('redis_mode', 'Unknown')}")
        print(f"   Connected clients: {info.get('connected_clients', 'Unknown')}")
        print(f"   Used memory: {info.get('used_memory_human', 'Unknown')}")
        print(f"   Max memory: {info.get('maxmemory_human', 'Unknown') or 'No limit'}")
        
        # Check keyspace
        keyspace_info = []
        for key in info.keys():
            if key.startswith('db'):
                keyspace_info.append(f"{key}: {info[key]}")
        
        if keyspace_info:
            print(f"   Keyspace: {', '.join(keyspace_info)}")
        else:
            print("   Keyspace: Empty")
            
        return True
    except Exception as e:
        print(f"❌ Error getting Redis info: {e}")
        return False

def main():
    """Main health check function."""
    print("🔍 Redis Health Check Starting...\n")
    
    # Check environment
    redis_url = os.getenv('REDIS_URL')
    if redis_url:
        print(f"🔗 REDIS_URL: {redis_url}")
    else:
        print("❌ REDIS_URL environment variable not set")
        print("💡 For local development:")
        print("   1. Install Redis locally: https://redis.io/download")
        print("   2. Start Redis server: redis-server")
        print("   3. Set REDIS_URL=redis://localhost:6379 in your .env file")
        print("   4. Or use Docker: docker run -d -p 6379:6379 redis:alpine")
        return False
    
    print()
    
    # Run tests
    tests_passed = 0
    total_tests = 4
    
    if test_redis_connection():
        tests_passed += 1
    
    if test_redis_operations():
        tests_passed += 1
    
    if check_existing_data():
        tests_passed += 1
    
    if show_redis_info():
        tests_passed += 1
    
    print(f"\n📊 Health Check Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Redis is healthy and ready to use.")
        return True
    else:
        print("⚠️ Some tests failed. Please check the errors above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
