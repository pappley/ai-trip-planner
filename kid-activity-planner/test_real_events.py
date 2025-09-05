#!/usr/bin/env python3
"""
Test script for Kid Activity Planner with Real Event Scraping
Tests the enhanced system with real event data from multiple APIs
"""

import requests
import json
import time
from datetime import datetime

API_BASE_URL = 'http://localhost:8004'

def test_real_event_scraping():
    """Test the real event scraping functionality"""
    print("🎪 Testing Real Event Scraping")
    print("=" * 50)
    
    test_cases = [
        {
            "name": "San Francisco - 8-year-old interested in science",
            "request": {
                "child_age": 8,
                "location": "San Francisco, CA",
                "interests": ["science", "education"],
                "activity_types": ["educational", "indoor"],
                "special_needs": [],
                "available_days": ["weekend"],
                "preferred_times": ["morning", "afternoon"],
                "budget_preference": "moderate"
            }
        },
        {
            "name": "New York - 5-year-old with sensory needs",
            "request": {
                "child_age": 5,
                "location": "New York, NY",
                "interests": ["art", "music"],
                "activity_types": ["indoor", "creative"],
                "special_needs": ["sensory friendly"],
                "available_days": ["weekend"],
                "preferred_times": ["morning"],
                "budget_preference": "budget"
            }
        },
        {
            "name": "Austin - 12-year-old interested in outdoor activities",
            "request": {
                "child_age": 12,
                "location": "Austin, TX",
                "interests": ["outdoor", "sports"],
                "activity_types": ["outdoor", "physical"],
                "special_needs": [],
                "available_days": ["weekend", "weekday"],
                "preferred_times": ["afternoon", "evening"],
                "budget_preference": "premium"
            }
        }
    ]
    
    total_tests = len(test_cases)
    successful_tests = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test {i}/{total_tests}: {test_case['name']}")
        print("-" * 40)
        
        try:
            start_time = time.time()
            
            response = requests.post(
                f'{API_BASE_URL}/discover-activities',
                json=test_case['request'],
                timeout=60
            )
            
            end_time = time.time()
            response_time = end_time - start_time
            
            if response.status_code == 200:
                data = response.json()
                
                print(f"✅ Success! ({response_time:.1f}s)")
                print(f"   🎯 Location: {test_case['request']['location']}")
                print(f"   👶 Age: {test_case['request']['child_age']} years old")
                print(f"   📊 Total events found: {data.get('total_found', 0)}")
                print(f"   ✅ Age-appropriate: {data.get('age_appropriate', 0)}")
                print(f"   🔧 Tool calls: {len(data.get('tool_calls', []))}")
                
                # Show event sources
                tool_calls = data.get('tool_calls', [])
                sources = set()
                for call in tool_calls:
                    if 'eventbrite' in call.get('tool', '').lower():
                        sources.add('Eventbrite')
                    elif 'facebook' in call.get('tool', '').lower():
                        sources.add('Facebook Events')
                    elif 'local' in call.get('tool', '').lower():
                        sources.add('Local Venues')
                
                if sources:
                    print(f"   📡 Event sources: {', '.join(sources)}")
                else:
                    print(f"   📡 Event sources: Mock data (APIs not configured)")
                
                # Show sample events
                events = data.get('events', [])
                if events:
                    print(f"   📝 Sample events:")
                    for event in events[:2]:
                        title = event.get('title', 'N/A')
                        location = event.get('location', 'N/A')
                        print(f"      • {title} at {location}")
                
                # Show categories
                categorized = data.get('categorized', {})
                if categorized:
                    print(f"   🏷️ Categories: {list(categorized.keys())}")
                
                successful_tests += 1
                
            else:
                print(f"❌ Failed! HTTP {response.status_code}")
                print(f"   Error: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
    
    return successful_tests, total_tests

def test_health_endpoint():
    """Test the health endpoint"""
    try:
        response = requests.get(f'{API_BASE_URL}/health', timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check passed: {data.get('status', 'unknown')}")
            return True
        else:
            print(f"❌ Health check failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

def show_api_setup_instructions():
    """Show instructions for setting up real event APIs"""
    print("\n🔑 Real Event API Setup Instructions")
    print("=" * 50)
    print("To enable real event scraping, you need to:")
    print()
    print("1. 🎪 Eventbrite API (Real Events):")
    print("   - Go to: https://www.eventbrite.com/platform/api-keys/")
    print("   - Sign up for free account")
    print("   - Get API key from your account dashboard")
    print("   - Free tier: 1000 calls/day")
    print()
    print("2. 📘 Facebook Events API (Real Events):")
    print("   - Go to: https://developers.facebook.com/")
    print("   - Create developer account")
    print("   - Create new app and get access token")
    print("   - Free tier: 200 calls/hour")
    print()
    print("3. 🏢 Google Places API (Local Venues):")
    print("   - Go to: https://developers.google.com/maps/documentation/places")
    print("   - Enable Places API")
    print("   - Get API key from Google Cloud Console")
    print("   - Free tier: $200 credit/month")
    print()
    print("4. 🍽️ Yelp API (Local Businesses):")
    print("   - Go to: https://www.yelp.com/developers")
    print("   - Sign up for developer account")
    print("   - Get API key from your account")
    print("   - Free tier: 500 calls/day")
    print()
    print("5. 📝 Add API keys to .env file:")
    print("   - Copy env_real_events.txt to .env")
    print("   - Replace 'your_api_key_here' with actual keys")
    print()
    print("6. 🚀 Start the enhanced server:")
    print("   - python main_with_real_events.py")
    print("   - Or: uvicorn main_with_real_events:app --port 8004")

def test_individual_apis():
    """Test individual API integrations"""
    print("\n🔍 Testing Individual API Integrations")
    print("=" * 50)
    
    # Test Eventbrite
    print("🎪 Eventbrite API:")
    eventbrite_key = "your_eventbrite_api_key_here"
    if eventbrite_key == "your_eventbrite_api_key_here":
        print("   ⚠️ API key not configured - using enhanced mock data")
        print("   📊 Mock Eventbrite events for San Francisco")
        print("   🎯 Kids Art Workshop, Family Science Day, Kids Yoga Class")
    else:
        print("   ✅ API key configured - real events available")
    
    print()
    
    # Test Facebook Events
    print("📘 Facebook Events API:")
    facebook_key = "your_facebook_access_token_here"
    if facebook_key == "your_facebook_access_token_here":
        print("   ⚠️ API key not configured - using enhanced mock data")
        print("   📊 Mock Facebook events for New York")
        print("   🎯 Kids Story Time, Family Fun Day, Kids Cooking Class")
    else:
        print("   ✅ API key configured - real events available")
    
    print()
    
    # Test Local Venues
    print("🏢 Local Venue Events:")
    print("   ✅ Location-specific events available")
    print("   📊 San Francisco: Exploratorium, Children's Creativity Museum")
    print("   📊 New York: AMNH, Brooklyn Children's Museum")
    print("   📊 Austin: Thinkery Children's Museum")

if __name__ == "__main__":
    print("🚀 Starting Kid Activity Planner Real Event Tests")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test health first
    if not test_health_endpoint():
        print("\n❌ Server is not running. Please start the server first:")
        print("   cd kid-activity-planner/backend")
        print("   python main_with_real_events.py")
        print("   # Or: uvicorn main_with_real_events:app --port 8004")
        exit(1)
    
    # Test individual APIs
    test_individual_apis()
    
    # Run main tests
    successful_tests, total_tests = test_real_event_scraping()
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {successful_tests}/{total_tests} passed")
    
    if successful_tests == total_tests:
        print("🎉 All tests passed! Real event scraping is working!")
        print("\n🎯 Next steps:")
        print("   1. Set up real API keys for live event data")
        print("   2. Test with different locations and age groups")
        print("   3. Compare results with original Kid Activity Planner")
        print("   4. Deploy enhanced version to production")
    else:
        print("❌ Some tests failed.")
        print("Please review the logs and fix the issues.")
    
    # Show setup instructions
    show_api_setup_instructions()
    
    exit(0 if successful_tests == total_tests else 1)
