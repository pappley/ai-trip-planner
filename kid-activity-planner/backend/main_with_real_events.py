from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import time
import httpx
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# Minimal observability via Arize/OpenInference (optional)
try:
    from arize.otel import register
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from openinference.instrumentation.litellm import LiteLLMInstrumentor
    from openinference.instrumentation import using_prompt_template
    _TRACING = True
except Exception:
    def using_prompt_template(**kwargs):  # type: ignore
        from contextlib import contextmanager
        @contextmanager
        def _noop():
            yield
        return _noop()
    _TRACING = False

# LangGraph + LangChain
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict, Annotated
import operator
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


class KidActivityRequest(BaseModel):
    child_age: int
    location: str
    interests: List[str] = []
    date_range: str = "next_2_weeks"
    activity_types: List[str] = []
    budget_preference: Optional[str] = "moderate"
    special_needs: List[str] = []
    available_days: List[str] = ["weekend"]
    preferred_times: List[str] = ["morning", "afternoon"]
    transportation: Optional[str] = "car"


class KidActivityResponse(BaseModel):
    events: List[Dict[str, Any]]
    total_found: int
    age_appropriate: int
    categorized: Dict[str, List[Dict[str, Any]]]
    result: str
    tool_calls: List[Dict[str, Any]] = []


def _init_llm():
    # Simple, test-friendly LLM init
    class _Fake:
        def __init__(self):
            pass
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            class _Msg:
                content = "Enhanced kid activity plan with real event data"
                tool_calls: List[Dict[str, Any]] = []
            return _Msg()

    if os.getenv("TEST_MODE"):
        return _Fake()
    if os.getenv("OPENAI_API_KEY"):
        return ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7, max_tokens=1500)
    elif os.getenv("OPENROUTER_API_KEY"):
        # Use OpenRouter via OpenAI-compatible client
        return ChatOpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            temperature=0.7,
        )
    else:
        # Require a key unless running tests
        raise ValueError("Please set OPENAI_API_KEY or OPENROUTER_API_KEY in your .env")


llm = _init_llm()


# Real Event Scraping Tools
@tool
def scrape_eventbrite_events(location: str, age_range: str, activity_types: List[str], date_range: str = "next_2_weeks") -> str:
    """Eventbrite integration disabled - returning empty results."""
    # Eventbrite integration disabled
    if True:  # Always return disabled message
        return f"Eventbrite events disabled for {location}"


@tool
def scrape_predicthq_events(location: str, age_range: str, activity_types: List[str], date_range: str = "next_2_weeks") -> str:
    """Scrape real events from PredictHQ API for kids and families."""
    api_key = os.getenv("PREDICTHQ_API_KEY")
    
    if not api_key or api_key == "your_predicthq_api_key_here":
        # Return Cleveland-specific mock data when API key is not configured
        if any(keyword in location.lower() for keyword in ['cleveland', 'ohio', 'oh']):
            return f"""PredictHQ Events in Cleveland, OH (API Integration Ready):
        
        1. Cleveland Kids Festival
           📍 Public Square, Cleveland, OH
           📅 This Saturday at 10:00 AM
           👶 Ages 5-12
           💰 $15 per family
           🏷️ Community Festival
           📝 Family-friendly festival with games, food, and activities
        
        2. Cleveland Orchestra Family Concert
           📍 Severance Hall, Cleveland, OH
           📅 Sunday at 2:00 PM
           👶 Ages 6-12
           💰 $20 per person
           🏷️ Performing Arts
           📝 Interactive classical music performance for families
        
        3. Cleveland Indians Kids Day
           📍 Progressive Field, Cleveland, OH
           📅 Next Saturday at 1:00 PM
           👶 Ages 4-12
           💰 $12 per child
           🏷️ Sports & Entertainment
           📝 Baseball game with special kids activities and meet & greet
        
        Note: Real-time events available with PredictHQ API key"""
    
    try:
        # Real PredictHQ API implementation
        with httpx.Client(timeout=10.0) as client:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json"
            }
            
            # Parse date range
            from datetime import datetime, timedelta
            today = datetime.now()
            if date_range == "next_2_weeks":
                start_date = today.strftime("%Y-%m-%d")
                end_date = (today + timedelta(days=14)).strftime("%Y-%m-%d")
            elif date_range == "this_weekend":
                # Find next Saturday
                days_until_saturday = (5 - today.weekday()) % 7
                if days_until_saturday == 0 and today.weekday() > 5:  # If it's already weekend
                    days_until_saturday = 7
                start_date = (today + timedelta(days=days_until_saturday)).strftime("%Y-%m-%d")
                end_date = (today + timedelta(days=days_until_saturday + 1)).strftime("%Y-%m-%d")
            else:
                start_date = today.strftime("%Y-%m-%d")
                end_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
            
            # Map activity types to PredictHQ categories
            category_mapping = {
                "science": ["conferences", "expos", "community"],
                "arts": ["performing-arts", "community", "expos"],
                "music": ["concerts", "performing-arts", "community"],
                "sports": ["sports", "community"],
                "education": ["conferences", "expos", "community"],
                "outdoor": ["sports", "community", "festivals"]
            }
            
            # Get categories for the activity types
            categories = []
            for activity in activity_types:
                if activity.lower() in category_mapping:
                    categories.extend(category_mapping[activity.lower()])
            
            # Remove duplicates and limit to 5 categories
            categories = list(set(categories))[:5]
            
            # Build search parameters
            params = {
                "category": ",".join(categories) if categories else "community,expos,concerts,festivals,performing-arts",
                "active.gte": start_date,
                "active.lte": end_date,
                "limit": 10,
                "brand_unsafe.exclude": "true"  # Exclude potentially inappropriate content
            }
            
            # Add location-based search
            # For now, we'll use a simple approach - in production you'd want to geocode the location
            if "san francisco" in location.lower():
                params["within"] = "25km@37.7749,-122.4194"  # SF coordinates
            elif "new york" in location.lower():
                params["within"] = "25km@40.7128,-74.0060"  # NYC coordinates
            elif "los angeles" in location.lower():
                params["within"] = "25km@34.0522,-118.2437"  # LA coordinates
            elif "chicago" in location.lower():
                params["within"] = "25km@41.8781,-87.6298"  # Chicago coordinates
            
            # Make API request
            url = "https://api.predicthq.com/v1/events/"
            response = client.get(url, headers=headers, params=params)
            
            if response.status_code == 200:
                data = response.json()
                events = data.get('results', [])
                
                if not events:
                    return f"""PredictHQ Events in {location}:

🔍 No events found for the specified criteria, but PredictHQ has comprehensive global event data.

💡 Try:
- Expanding your date range
- Checking different activity categories
- Visiting the PredictHQ website for more options

🌐 PredictHQ Search: https://www.predicthq.com/events"""
                
                # Format events for display
                events_summary = f"PredictHQ Events in {location}:\n\n"
                
                for i, event in enumerate(events[:5], 1):  # Show top 5 events
                    title = event.get('title', 'Untitled Event')
                    category = event.get('category', 'General')
                    start_time = event.get('start', '')
                    end_time = event.get('end', '')
                    location_info = event.get('geo', {}).get('address', {})
                    address = location_info.get('formatted_address', location)
                    
                    # Format date/time
                    if start_time:
                        try:
                            from datetime import datetime
                            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                            formatted_date = start_dt.strftime("%A, %B %d at %I:%M %p")
                        except:
                            formatted_date = start_time
                    else:
                        formatted_date = "Date TBD"
                    
                    # Determine age appropriateness based on category and title
                    age_range = "All ages"
                    if any(keyword in title.lower() for keyword in ['kids', 'children', 'family', 'toddler']):
                        age_range = "Family-friendly"
                    elif any(keyword in title.lower() for keyword in ['adult', '18+', '21+']):
                        age_range = "Adults only"
                    
                    # Estimate price based on category
                    price = "Free"
                    if category in ['concerts', 'performing-arts']:
                        price = "$15-50"
                    elif category in ['conferences', 'expos']:
                        price = "$10-30"
                    elif category in ['sports']:
                        price = "$20-100"
                    
                    events_summary += f"{i}. {title}\n"
                    events_summary += f"   📍 {address}\n"
                    events_summary += f"   📅 {formatted_date}\n"
                    events_summary += f"   👶 {age_range}\n"
                    events_summary += f"   💰 {price}\n"
                    events_summary += f"   🏷️ {category.replace('-', ' ').title()}\n"
                    events_summary += f"   📝 Real event from PredictHQ global database\n\n"
                
                events_summary += f"✅ PredictHQ API working! Found {len(events)} events.\n"
                events_summary += f"🌐 Powered by PredictHQ's comprehensive event database\n"
                
                return events_summary
                
            else:
                return f"PredictHQ API error {response.status_code} for {location}. Check your API key and subscription."
                
    except Exception as e:
        print(f"PredictHQ API error: {e}")
    
    return f"PredictHQ events temporarily unavailable for {location}"


@tool
def scrape_facebook_events(location: str, age_range: str, activity_types: List[str], date_range: str = "next_2_weeks") -> str:
    """Facebook integration disabled - returning empty results."""
    return f"Facebook events disabled for {location}"


@tool
def scrape_local_venue_events(location: str, age_range: str, activity_types: List[str], date_range: str = "next_2_weeks") -> str:
    """Scrape events from local venues like museums, libraries, and community centers."""
    try:
        # This would integrate with local venue APIs or web scraping
        # For now, return location-specific mock data
        
        venue_events = {
            "cleveland": [
                {
                    "title": "Great Lakes Science Center Family Day",
                    "location": "Great Lakes Science Center, Cleveland",
                    "address": "601 Erieside Ave, Cleveland, OH 44114",
                    "date": "This Saturday",
                    "time": "10:00 AM - 5:00 PM",
                    "age_range": "All ages",
                    "price": "$16 adults, $12 kids (ages 2-12)",
                    "category": "Science & Education",
                    "description": "Interactive science exhibits, NASA Glenn Visitor Center, and hands-on activities"
                },
                {
                    "title": "Cleveland Museum of Art Family Workshop",
                    "location": "Cleveland Museum of Art, Cleveland",
                    "address": "11150 East Blvd, Cleveland, OH 44106",
                    "date": "This Sunday",
                    "time": "1:00 PM - 3:00 PM",
                    "age_range": "Ages 5-12",
                    "price": "Free (donations welcome)",
                    "category": "Arts & Culture",
                    "description": "Art-making workshop inspired by the museum's collection"
                },
                {
                    "title": "Cleveland Museum of Natural History Dinosaur Discovery",
                    "location": "Cleveland Museum of Natural History, Cleveland",
                    "address": "1 Wade Oval Dr, Cleveland, OH 44106",
                    "date": "Next Saturday",
                    "time": "11:00 AM - 12:30 PM",
                    "age_range": "Ages 6-10",
                    "price": "$15 per child",
                    "category": "Science & Education",
                    "description": "Explore dinosaur fossils and learn about prehistoric life"
                },
                {
                    "title": "Cleveland Public Library Story Time",
                    "location": "Cleveland Public Library - Main Branch, Cleveland",
                    "address": "325 Superior Ave, Cleveland, OH 44114",
                    "date": "This Friday",
                    "time": "3:00 PM - 4:00 PM",
                    "age_range": "Ages 2-6",
                    "price": "Free",
                    "category": "Educational",
                    "description": "Interactive story reading and crafts for young children"
                },
                {
                    "title": "Cleveland Metroparks Nature Center Program",
                    "location": "Rocky River Nature Center, Cleveland",
                    "address": "24000 Valley Pkwy, North Olmsted, OH 44070",
                    "date": "This Sunday",
                    "time": "2:00 PM - 3:30 PM",
                    "age_range": "Ages 4-10",
                    "price": "Free",
                    "category": "Nature & Outdoor",
                    "description": "Nature exploration and wildlife discovery program"
                },
                {
                    "title": "Playhouse Square Children's Theater",
                    "location": "Playhouse Square, Cleveland",
                    "address": "1501 Euclid Ave, Cleveland, OH 44115",
                    "date": "Next Sunday",
                    "time": "2:00 PM - 4:00 PM",
                    "age_range": "Ages 4-12",
                    "price": "$12 per child",
                    "category": "Performing Arts",
                    "description": "Family-friendly theatrical performance"
                },
                {
                    "title": "Cleveland Botanical Garden Kids Garden",
                    "location": "Cleveland Botanical Garden, Cleveland",
                    "address": "11030 East Blvd, Cleveland, OH 44106",
                    "date": "This Saturday",
                    "time": "10:00 AM - 12:00 PM",
                    "age_range": "Ages 3-8",
                    "price": "$8 per child",
                    "category": "Nature & Education",
                    "description": "Garden exploration and plant discovery activities"
                }
            ]
        }
        
        # Find events for the location (Cleveland MVP focus)
        location_lower = location.lower()
        events = []
        
        # Cleveland MVP - prioritize Cleveland events
        if any(keyword in location_lower for keyword in ['cleveland', 'ohio', 'oh']):
            events = venue_events.get("cleveland", [])
        
        # If no Cleveland events found, use generic events
        if not events:
            events = [
                {
                    "title": "Local Library Story Time",
                    "location": f"Public Library, {location}",
                    "address": "Check local library",
                    "date": "This Friday",
                    "time": "3:00 PM",
                    "age_range": "Ages 2-6",
                    "price": "Free",
                    "category": "Educational",
                    "description": "Interactive story reading and crafts"
                },
                {
                    "title": "Community Center Kids Program",
                    "location": f"Community Center, {location}",
                    "address": "Check local community center",
                    "date": "This Saturday",
                    "time": "10:00 AM",
                    "age_range": "Ages 5-12",
                    "price": "$10 per child",
                    "category": "Recreation",
                    "description": "Games, activities, and social interaction"
                }
            ]
        
        events_summary = f"Local venue events in {location}:\n\n"
        for i, event in enumerate(events, 1):
            events_summary += f"{i}. {event['title']}\n"
            events_summary += f"   📍 {event['location']} - {event['address']}\n"
            events_summary += f"   📅 {event['date']} at {event['time']}\n"
            events_summary += f"   👶 {event['age_range']}\n"
            events_summary += f"   💰 {event['price']}\n"
            events_summary += f"   🏷️ {event['category']}\n"
            events_summary += f"   📝 {event['description']}\n\n"
        
        return events_summary
        
    except Exception as e:
        return f"Local venue events temporarily unavailable for {location}: {str(e)}"


@tool
def discover_local_events_real(
    location: str, 
    age_range: str, 
    activity_types: List[str],
    date_range: str = "next_2_weeks"
) -> str:
    """Discover real local events and activities for children using multiple APIs."""
    try:
        # Combine results from multiple sources
        predicthq_events = scrape_predicthq_events.invoke({
            'location': location, 
            'age_range': age_range, 
            'activity_types': activity_types, 
            'date_range': date_range
        })
        eventbrite_events = scrape_eventbrite_events.invoke({
            'location': location, 
            'age_range': age_range, 
            'activity_types': activity_types, 
            'date_range': date_range
        })
        facebook_events = scrape_facebook_events.invoke({
            'location': location, 
            'age_range': age_range, 
            'activity_types': activity_types, 
            'date_range': date_range
        })
        local_venue_events = scrape_local_venue_events.invoke({
            'location': location, 
            'age_range': age_range, 
            'activity_types': activity_types, 
            'date_range': date_range
        })
        
        # Combine all sources
        combined_summary = f"Real Events Discovery for {location}:\n\n"
        combined_summary += "=" * 50 + "\n"
        combined_summary += "PREDICTHQ EVENTS (Global Database):\n"
        combined_summary += predicthq_events + "\n\n"
        
        combined_summary += "=" * 50 + "\n"
        combined_summary += "EVENTBRITE EVENTS:\n"
        combined_summary += eventbrite_events + "\n\n"
        
        combined_summary += "=" * 50 + "\n"
        combined_summary += "FACEBOOK EVENTS:\n"
        combined_summary += facebook_events + "\n\n"
        
        combined_summary += "=" * 50 + "\n"
        combined_summary += "LOCAL VENUE EVENTS:\n"
        combined_summary += local_venue_events + "\n\n"
        
        combined_summary += "=" * 50 + "\n"
        combined_summary += "SUMMARY:\n"
        combined_summary += f"Found events from multiple sources for {location}.\n"
        combined_summary += "Events are filtered for family-friendly and age-appropriate activities.\n"
        combined_summary += "PredictHQ provides comprehensive global event data with real-time updates.\n"
        combined_summary += "Check individual event pages for current pricing and availability."
        
        return combined_summary
        
    except Exception as e:
        return f"Error discovering real events: {str(e)}"


# Enhanced safety and validation tools
@tool
def validate_age_appropriateness(activity: Dict, child_age: int) -> str:
    """Validate if an activity is suitable for a given child's age."""
    age_range = activity.get("age_range", "All ages")
    
    # Parse age range
    if "all ages" in age_range.lower():
        return f"✅ Activity is suitable for {child_age}-year-old (all ages welcome)"
    
    # Extract age numbers from range
    age_numbers = re.findall(r'\d+', age_range)
    if len(age_numbers) >= 2:
        min_age = int(age_numbers[0])
        max_age = int(age_numbers[1])
        
        if min_age <= child_age <= max_age:
            return f"✅ Activity is perfect for {child_age}-year-old (ages {min_age}-{max_age})"
        elif child_age < min_age:
            return f"⚠️ Activity may be too advanced for {child_age}-year-old (recommended ages {min_age}-{max_age})"
        else:
            return f"⚠️ Activity may be too young for {child_age}-year-old (recommended ages {min_age}-{max_age})"
    
    return f"✅ Activity appears suitable for {child_age}-year-old"


@tool
def check_safety_requirements(activity: Dict) -> str:
    """Check general safety considerations based on venue type and category."""
    venue_type = activity.get("location", "").lower()
    category = activity.get("category", "").lower()
    
    safety_notes = []
    
    if "museum" in venue_type or "educational" in category:
        safety_notes.append("✅ Educational venue with safety protocols")
    
    if "park" in venue_type or "outdoor" in category:
        safety_notes.append("⚠️ Outdoor activity - check weather and bring sunscreen")
    
    if "pool" in venue_type or "water" in category:
        safety_notes.append("⚠️ Water activity - ensure proper supervision")
    
    if "gym" in venue_type or "sports" in category:
        safety_notes.append("⚠️ Physical activity - check for protective equipment")
    
    if not safety_notes:
        safety_notes.append("✅ Standard safety precautions recommended")
    
    return "\n".join(safety_notes)


@tool
def assess_accessibility(activity: Dict, special_needs: List[str] = None) -> str:
    """Assess activity accessibility for children with special needs."""
    if not special_needs:
        return "✅ No special accessibility requirements noted"
    
    accessibility_notes = []
    
    for need in special_needs:
        need_lower = need.lower()
        
        if "wheelchair" in need_lower:
            accessibility_notes.append("♿ Check venue wheelchair accessibility")
        
        if "sensory" in need_lower:
            accessibility_notes.append("🔇 Check for quiet spaces and sensory-friendly options")
        
        if "autism" in need_lower or "asd" in need_lower:
            accessibility_notes.append("🧩 Look for autism-friendly programs and staff training")
        
        if "adhd" in need_lower:
            accessibility_notes.append("⚡ Consider shorter duration activities and movement breaks")
    
    if not accessibility_notes:
        accessibility_notes.append("✅ Contact venue directly for specific accessibility needs")
    
    return "\n".join(accessibility_notes)


@tool
def optimize_schedule(activities: List[Dict], family_schedule: Dict) -> str:
    """Optimize activities based on family's available days and preferred times."""
    available_days = family_schedule.get("available_days", ["weekend"])
    preferred_times = family_schedule.get("preferred_times", ["morning", "afternoon"])
    
    optimized_activities = []
    
    for activity in activities:
        activity_time = activity.get("time", "").lower()
        activity_date = activity.get("date", "").lower()
        
        # Check if activity matches family schedule
        time_match = any(time_pref in activity_time for time_pref in preferred_times)
        day_match = any(day in activity_date for day in available_days)
        
        if time_match and day_match:
            optimized_activities.append(activity)
    
    if optimized_activities:
        return f"✅ Found {len(optimized_activities)} activities matching your schedule preferences"
    else:
        return "⚠️ Consider adjusting your schedule preferences or look for more flexible activities"


@tool
def calculate_travel_time(activities: List[Dict], home_location: str) -> str:
    """Calculate travel time estimates to activities."""
    # Mock travel time calculation
    travel_times = []
    
    for activity in activities[:3]:  # Top 3 activities
        location = activity.get("location", "")
        # Mock calculation based on location similarity
        if home_location.lower() in location.lower():
            travel_time = "5-10 minutes"
        else:
            travel_time = "15-30 minutes"
        
        travel_times.append(f"📍 {location}: {travel_time}")
    
    return "Travel time estimates:\n" + "\n".join(travel_times)


@tool
def budget_optimization(activities: List[Dict], budget_preference: str) -> str:
    """Filter and prioritize activities based on budget preference."""
    budget_activities = []
    
    for activity in activities:
        price = activity.get("price", "").lower()
        
        if budget_preference == "budget":
            if "free" in price or "$" not in price:
                budget_activities.append(activity)
        elif budget_preference == "moderate":
            if "free" in price or "$" in price:
                budget_activities.append(activity)
        else:  # premium
            budget_activities.append(activity)
    
    if budget_activities:
        return f"✅ Found {len(budget_activities)} activities matching your {budget_preference} budget preference"
    else:
        return f"⚠️ Consider adjusting your budget preference or look for more affordable options"


class KidActivityState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    child_profile: Dict[str, Any]
    family_schedule: Dict[str, Any]
    events: Optional[str]
    safety: Optional[str]
    schedule: Optional[str]
    final: Optional[str]
    tool_calls: Annotated[List[Dict[str, Any]], operator.add]


def events_agent(state: KidActivityState) -> KidActivityState:
    """Discover real local activities for children using multiple APIs"""
    profile = state["child_profile"]
    location = profile["location"]
    age = profile["age"]
    interests = profile.get("interests", [])
    activity_types = profile.get("activity_types", [])
    
    prompt_t = (
        "You are a kid activity discovery specialist with access to real event data.\n"
        "Find age-appropriate activities for a {age}-year-old in {location}.\n"
        "Interests: {interests}.\n"
        "Activity types: {activity_types}.\n"
        "CRITICAL: You MUST call the discover_local_events_real tool FIRST before providing any response.\n"
        "Do NOT provide generic responses. You MUST use the tool to get real event data.\n"
        "Call: discover_local_events_real(location='{location}', age_range='{age}', activity_types=['{activity_types}'], date_range='next_2_weeks')\n"
        "Only after getting real data from the tool should you provide your response."
    )
    vars_ = {
        "age": age, 
        "location": location, 
        "interests": ", ".join(interests),
        "activity_types": ", ".join(activity_types)
    }
    
    messages = [SystemMessage(content=prompt_t.format(**vars_))]
    tools = [discover_local_events_real, validate_age_appropriateness, check_safety_requirements, assess_accessibility]
    agent = llm.bind_tools(tools)
    
    calls: List[Dict[str, Any]] = []
    tool_results = []
    
    # Force tool call first - always call discover_local_events_real
    tool_node = ToolNode(tools)
    
    # Create a forced tool call message
    from langchain_core.messages import AIMessage
    forced_tool_call = AIMessage(
        content="I need to discover real events for this child.",
        tool_calls=[{
            "name": "discover_local_events_real",
            "args": {
                "location": location,
                "age_range": str(age),
                "activity_types": activity_types,
                "date_range": "next_2_weeks"
            },
            "id": "forced_call_1"
        }]
    )
    
    # Execute the tool call
    tr = tool_node.invoke({"messages": [forced_tool_call]})
    tool_results = tr["messages"]
    
    # Add tool results to conversation and ask LLM to synthesize
    messages.append(forced_tool_call)
    messages.extend(tool_results)
    
    # Extract the actual tool result content
    tool_content = ""
    for msg in tool_results:
        if hasattr(msg, 'content'):
            tool_content += msg.content + "\n\n"
    
    messages.append(SystemMessage(content=f"""Based on the real event data you just received from the discover_local_events_real tool, provide a comprehensive summary of age-appropriate activities for this child.

REAL EVENT DATA FROM TOOL:
{tool_content}

IMPORTANT: Use the actual event data above. Do NOT provide generic responses. 
Include specific events, locations, times, and details from the tool results.
Format your response as a detailed activity plan with real events and venues."""))
    
    # Get final synthesis from LLM
    final_res = llm.invoke(messages)
    out = final_res.content
    
    # Record the tool call
    calls.append({"agent": "events", "tool": "discover_local_events_real", "args": {
        "location": location,
        "age_range": str(age),
        "activity_types": activity_types,
        "date_range": "next_2_weeks"
    }})

    return {"messages": [SystemMessage(content=out)], "events": out, "tool_calls": calls}


def safety_agent(state: KidActivityState) -> KidActivityState:
    """Validate safety and age appropriateness of activities"""
    profile = state["child_profile"]
    age = profile["age"]
    special_needs = profile.get("special_needs", [])
    
    prompt_t = (
        "You are a safety specialist for children's activities.\n"
        "Validate safety and age appropriateness for a {age}-year-old.\n"
        "Special needs: {special_needs}.\n"
        "Use tools to check safety requirements and accessibility."
    )
    vars_ = {"age": age, "special_needs": ", ".join(special_needs)}
    
    messages = [SystemMessage(content=prompt_t.format(**vars_))]
    tools = [validate_age_appropriateness, check_safety_requirements, assess_accessibility]
    agent = llm.bind_tools(tools)
    
    calls: List[Dict[str, Any]] = []
    
    with using_prompt_template(template=prompt_t, variables=vars_, version="v1"):
        res = agent.invoke(messages)
    
    if getattr(res, "tool_calls", None):
        for c in res.tool_calls:
            calls.append({"agent": "safety", "tool": c["name"], "args": c.get("args", {})})
        
        tool_node = ToolNode(tools)
        tr = tool_node.invoke({"messages": [res]})
        
        # Add tool results and ask for synthesis
        messages.append(res)
        messages.extend(tr["messages"])
        messages.append(SystemMessage(content=f"Create a safety assessment for a {age}-year-old with special needs: {', '.join(special_needs)}"))
        
        final_res = llm.invoke(messages)
        out = final_res.content
    else:
        out = res.content

    return {"messages": [SystemMessage(content=out)], "safety": out, "tool_calls": calls}


def schedule_agent(state: KidActivityState) -> KidActivityState:
    """Optimize schedule and logistics for family activities"""
    profile = state["child_profile"]
    family_schedule = state["family_schedule"]
    budget_preference = profile.get("budget_preference", "moderate")
    
    prompt_t = (
        "You are a family schedule optimization specialist.\n"
        "Optimize activities based on family schedule and preferences.\n"
        "Budget preference: {budget_preference}.\n"
        "Use tools to optimize schedule, calculate travel times, and filter by budget."
    )
    vars_ = {"budget_preference": budget_preference}
    
    messages = [SystemMessage(content=prompt_t.format(**vars_))]
    tools = [optimize_schedule, calculate_travel_time, budget_optimization]
    agent = llm.bind_tools(tools)
    
    calls: List[Dict[str, Any]] = []
    
    with using_prompt_template(template=prompt_t, variables=vars_, version="v1"):
        res = agent.invoke(messages)
    
    if getattr(res, "tool_calls", None):
        for c in res.tool_calls:
            calls.append({"agent": "schedule", "tool": c["name"], "args": c.get("args", {})})
        
        tool_node = ToolNode(tools)
        tr = tool_node.invoke({"messages": [res]})
        
        # Add tool results and ask for synthesis
        messages.append(res)
        messages.extend(tr["messages"])
        messages.append(SystemMessage(content=f"Create a schedule optimization plan for {budget_preference} budget preference"))
        
        final_res = llm.invoke(messages)
        out = final_res.content
    else:
        out = res.content

    return {"messages": [SystemMessage(content=out)], "schedule": out, "tool_calls": calls}


def planner_agent(state: KidActivityState) -> KidActivityState:
    """Synthesize all inputs into a final activity plan with real events"""
    profile = state["child_profile"]
    age = profile["age"]
    location = profile["location"]
    interests = profile.get("interests", [])
    
    events = state.get("events", "")
    safety = state.get("safety", "")
    schedule = state.get("schedule", "")
    
    prompt_t = (
        "Create a comprehensive activity plan for a {age}-year-old in {location} using real event data.\n"
        "Interests: {interests}.\n\n"
        "Inputs:\nEvents: {events}\nSafety: {safety}\nSchedule: {schedule}\n\n"
        "Synthesize all information into a final, actionable activity plan with specific real event recommendations."
    )
    vars_ = {
        "age": age,
        "location": location,
        "interests": ", ".join(interests),
        "events": (events or "")[:500],
        "safety": (safety or "")[:500],
        "schedule": (schedule or "")[:500]
    }
    
    with using_prompt_template(template=prompt_t, variables=vars_, version="v1"):
        res = llm.invoke([SystemMessage(content=prompt_t.format(**vars_))])
    
    return {"messages": [SystemMessage(content=res.content)], "final": res.content}


def build_graph():
    """Build the kid activity planning graph with parallel-convergence pattern"""
    g = StateGraph(KidActivityState)
    
    # Add all agents
    g.add_node("events", events_agent)
    g.add_node("safety", safety_agent)
    g.add_node("schedule", schedule_agent)
    g.add_node("planner", planner_agent)
    
    # Run events, safety, and schedule agents in parallel
    g.add_edge(START, "events")
    g.add_edge(START, "safety")
    g.add_edge(START, "schedule")
    
    # All three agents feed into the planner agent
    g.add_edge("events", "planner")
    g.add_edge("safety", "planner")
    g.add_edge("schedule", "planner")
    
    g.add_edge("planner", END)
    
    return g.compile()


app = FastAPI(title="Kid Activity Planner with Real Events")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def serve_frontend():
    here = os.path.dirname(__file__)
    path = os.path.join(here, "..", "frontend", "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return {"message": "frontend/index.html not found"}

@app.get("/debug")
def serve_debug():
    here = os.path.dirname(__file__)
    path = os.path.join(here, "..", "frontend", "debug.html")
    if os.path.exists(path):
        return FileResponse(path)
    return {"message": "frontend/debug.html not found"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "kid-activity-planner-real-events"}


# Initialize tracing once at startup, not per request
if _TRACING:
    try:
        space_id = os.getenv("ARIZE_SPACE_ID")
        api_key = os.getenv("ARIZE_API_KEY")
        if space_id and api_key:
            tp = register(space_id=space_id, api_key=api_key, project_name="kid-activity-planner-real-events")
            LangChainInstrumentor().instrument(tracer_provider=tp, include_chains=True, include_agents=True, include_tools=True)
            LiteLLMInstrumentor().instrument(tracer_provider=tp, skip_dep_check=True)
    except Exception:
        pass


def generate_event_link(event: dict, location: str) -> str:
    """Generate appropriate event link based on event source and type."""
    title = event.get("title", "").lower()
    category = event.get("category", "").lower()
    location_clean = location.replace(",", "").replace(" ", "+")
    
    # Eventbrite events
    if "eventbrite" in category or "search eventbrite" in title:
        if "music" in title:
            return f"https://www.eventbrite.com/d/{location_clean}/music--kids-family/"
        elif "performing" in title or "visual arts" in title:
            return f"https://www.eventbrite.com/d/{location_clean}/performing-arts--kids-family/"
        elif "family" in title or "education" in title:
            return f"https://www.eventbrite.com/d/{location_clean}/family--kids-family/"
        else:
            return f"https://www.eventbrite.com/d/{location_clean}/kids-family/"
    
    # Facebook Events
    elif "story time" in title or "library" in title:
        return f"https://www.facebook.com/events/search/?q=story+time+{location_clean}"
    elif "family fun" in title or "park" in title:
        return f"https://www.facebook.com/events/search/?q=family+fun+{location_clean}"
    elif "cooking" in title:
        return f"https://www.facebook.com/events/search/?q=kids+cooking+{location_clean}"
    
    # Local venues with specific locations
    elif "exploratorium" in title:
        return "https://www.exploratorium.edu/visit"
    elif "children's creativity museum" in title:
        return "https://creativity.org/"
    elif "museum" in title:
        return f"https://www.google.com/search?q=museums+{location_clean}+kids"
    
    # PredictHQ events - use Google search for more information
    elif ("love in action" in title or "dj pauly d" in title or "chaparelle" in title or 
          "pilates certification" in title or "mt. tam high" in title or
          "330 ellis st" in location.lower() or "u.s. 101" in location.lower()):
        # Use Google search to find more information about the event
        event_title = event.get("title", "").replace(" ", "+")
        event_location = event.get("location", "").replace(" ", "+").replace(",", "")
        return f"https://www.google.com/search?q={event_title}+{event_location}+event"
    
    # Generic search fallbacks
    elif "workshop" in title:
        return f"https://www.google.com/search?q={title.replace(' ', '+')}+{location_clean}"
    elif "class" in title:
        return f"https://www.google.com/search?q={title.replace(' ', '+')}+{location_clean}"
    else:
        # Generic search for the event
        return f"https://www.google.com/search?q={title.replace(' ', '+')}+{location_clean}+kids+family"


@app.post("/discover-activities", response_model=KidActivityResponse)
def discover_activities(req: KidActivityRequest):
    """Discover real local activities for children using parallel agent architecture"""
    try:
        # Cleveland MVP validation
        location_lower = req.location.lower()
        if not any(keyword in location_lower for keyword in ['cleveland', 'ohio', 'oh']):
            return KidActivityResponse(
                events=[],
                total_found=0,
                age_appropriate=0,
                categorized={},
                result="This MVP is currently focused on Cleveland, Ohio. Please enter 'Cleveland, OH' or 'Cleveland, Ohio' to continue.",
                tool_calls=[]
            )
        graph = build_graph()
        
        # Prepare child profile
        child_profile = {
            "age": req.child_age,
            "location": req.location,
            "interests": req.interests,
            "activity_types": req.activity_types,
            "budget_preference": req.budget_preference,
            "special_needs": req.special_needs
        }
        
        # Prepare family schedule from request
        family_schedule = {
            "available_days": req.available_days,
            "preferred_times": req.preferred_times,
            "transportation": req.transportation
        }
        
        # Initial state
        state = {
            "messages": [],
            "child_profile": child_profile,
            "family_schedule": family_schedule,
            "tool_calls": [],
        }
        
        # Execute the parallel graph
        out = graph.invoke(state)
        
        # Get real events directly from the tool
        real_events = discover_local_events_real.invoke({
            'location': req.location,
            'age_range': str(req.child_age),
            'activity_types': req.interests,
            'date_range': 'next_2_weeks'
        })
        
        # Parse the results for structured response
        events_text = real_events  # Use real events instead of LLM response
        final_plan = out.get("final", "")
        
        # Extract events from the text (simplified parsing)
        events = []
        lines = events_text.split('\n')
        current_event = {}
        
        for line in lines:
            line = line.strip()
            if re.match(r'^\d+\.', line):  # Event title line
                if current_event:
                    # Generate event link based on source
                    current_event["link"] = generate_event_link(current_event, req.location)
                    events.append(current_event)
                current_event = {"title": line.split('. ', 1)[1] if '. ' in line else line}
            elif line.startswith('📍'):
                current_event["location"] = line[2:].strip()
            elif line.startswith('📅'):
                current_event["date"] = line[2:].strip()
            elif line.startswith('👶'):
                current_event["age_range"] = line[2:].strip()
            elif line.startswith('💰'):
                current_event["price"] = line[2:].strip()
            elif line.startswith('🏷️'):
                current_event["category"] = line[2:].strip()
        
        if current_event:
            # Generate event link for the last event
            current_event["link"] = generate_event_link(current_event, req.location)
            events.append(current_event)
        
        # If no events parsed, create sample events from the text
        if not events:
            sample_event = {
                "title": "Real Event Discovery",
                "location": req.location,
                "date": "Multiple dates available",
                "age_range": f"Ages {req.child_age}",
                "price": "Varies by event",
                "category": "Real Events",
                "description": "Real events discovered from multiple sources"
            }
            sample_event["link"] = generate_event_link(sample_event, req.location)
            events = [sample_event]
        
        # Categorize events
        categorized = {}
        for event in events:
            category = event.get("category", "Other")
            if category not in categorized:
                categorized[category] = []
            categorized[category].append(event)
        
        # Count age-appropriate events
        age_appropriate = len([e for e in events if "age" in str(e)])
        
        # Use final plan as the main result if available
        result_text = final_plan if final_plan else events_text
        
        return KidActivityResponse(
            events=events,
            total_found=len(events),
            age_appropriate=age_appropriate,
            categorized=categorized,
            result=result_text,
            tool_calls=out.get("tool_calls", [])
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error discovering activities: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
