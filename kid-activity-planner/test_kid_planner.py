#!/usr/bin/env python3
"""
Test script for Kid Activity Planner MVP
Tests the parallel agent architecture with real API calls
"""

import requests
import json
import time
from datetime import datetime

API_BASE_URL = 'http://localhost:8001'

def test_kid_activity_planner():
    """Test the Kid Activity Planner with various scenarios"""
    
    test_cases = [
        {
            "name": "Basic 8-year-old in San Francisco",
            "request": {
                "child_age": 8,
                "location": "San Francisco, CA",
                "interests": ["science", "art"],
                "activity_types": ["indoor", "educational"],
                "budget_preference": "moderate",
                "special_needs": [],
                "available_days": ["weekend"],
                "preferred_times": ["morning", "afternoon"],
                "transportation": "car"
            }
        },
        {
            "name": "Teenager with special needs",
            "request": {
                "child_age": 14,
                "location": "Downtown",
                "interests": ["sports", "music"],
                "activity_types": ["outdoor", "social"],
                "budget_preference": "budget",
                "special_needs": ["wheelchair accessible"],
                "available_days": ["weekend", "weekday"],
                "preferred_times": ["afternoon", "evening"],
                "transportation": "car"
            }
        },
        {
            "name": "Toddler with sensory needs",
            "request": {
                "child_age": 3,
                "location": "Midtown",
                "interests": ["music", "play"],
                "activity_types": ["indoor", "quiet"],
                "budget_preference": "moderate",
                "special_needs": ["sensory friendly"],
                "available_days": ["weekend"],
                "preferred_times": ["morning"],
                "transportation": "car"
            }
        }
    ]
    
    print("🧪 Testing Kid Activity Planner MVP")
    print("=" * 50)
    
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
                print(f"   📊 Found {data.get('total_found', 0)} activities")
                print(f"   👶 {data.get('age_appropriate', 0)} age-appropriate")
                print(f"   🏷️ Categories: {list(data.get('categorized', {}).keys())}")
                print(f"   🔧 Tool calls: {len(data.get('tool_calls', []))}")
                
                # Show sample activities
                events = data.get('events', [])
                if events:
                    print(f"   📝 Sample activities:")
                    for event in events[:2]:  # Show first 2
                        title = event.get('title', 'Unknown')
                        category = event.get('category', 'Other')
                        price = event.get('price', 'Unknown')
                        print(f"      • {title} ({category}) - {price}")
                
                successful_tests += 1
                
            else:
                print(f"❌ Failed! HTTP {response.status_code}")
                print(f"   Error: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {successful_tests}/{total_tests} passed")
    
    if successful_tests == total_tests:
        print("🎉 All tests passed! Kid Activity Planner MVP is working!")
    else:
        print("⚠️ Some tests failed. Check the server and try again.")
    
    return successful_tests == total_tests

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

if __name__ == "__main__":
    print("🚀 Starting Kid Activity Planner Tests")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Test health first
    if not test_health_endpoint():
        print("\n❌ Server is not running. Please start the server first:")
        print("   cd kid-activity-planner/backend")
        print("   uvicorn main:app --host 0.0.0.0 --port 8001 --reload")
        exit(1)
    
    # Run main tests
    success = test_kid_activity_planner()
    
    if success:
        print("\n🎯 Next steps:")
        print("   1. Open http://localhost:8001 in your browser")
        print("   2. Test the frontend interface")
        print("   3. Try different child profiles and preferences")
        print("   4. Deploy to production when ready")
    else:
        print("\n🔧 Troubleshooting:")
        print("   1. Check server logs for errors")
        print("   2. Verify API keys are set in .env file")
        print("   3. Ensure all dependencies are installed")
    
    exit(0 if success else 1)
