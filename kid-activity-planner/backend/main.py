from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import time
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
import httpx
import json
import re


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
    categorized: Dict[str, List[Dict]]
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
                content = "Test activity recommendations"
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


# Mock data for development
MOCK_EVENTS = [
    {
        "title": "Kids Science Workshop",
        "location": "Science Center",
        "address": "123 Science St, Downtown",
        "date": "2025-01-15",
        "time": "10:00 AM",
        "age_range": "6-12",
        "price": "$15",
        "category": "STEM",
        "description": "Hands-on science experiments for kids",
        "url": "https://example.com/science-workshop",
        "venue_type": "Museum"
    },
    {
        "title": "Art & Craft Session",
        "location": "Community Center",
        "address": "456 Art Ave, Midtown",
        "date": "2025-01-16",
        "time": "2:00 PM",
        "age_range": "4-10",
        "price": "Free",
        "category": "Arts",
        "description": "Creative art projects for children",
        "url": "https://example.com/art-session",
        "venue_type": "Community Center"
    },
    {
        "title": "Soccer Skills Clinic",
        "location": "Sports Complex",
        "address": "789 Sports Blvd, Eastside",
        "date": "2025-01-17",
        "time": "9:00 AM",
        "age_range": "8-14",
        "price": "$25",
        "category": "Sports",
        "description": "Learn soccer fundamentals",
        "url": "https://example.com/soccer-clinic",
        "venue_type": "Sports Facility"
    },
    {
        "title": "Story Time at Library",
        "location": "Public Library",
        "address": "321 Book St, Westside",
        "date": "2025-01-18",
        "time": "11:00 AM",
        "age_range": "2-6",
        "price": "Free",
        "category": "Educational",
        "description": "Interactive story reading for toddlers",
        "url": "https://example.com/story-time",
        "venue_type": "Library"
    },
    {
        "title": "Coding for Kids",
        "location": "Tech Hub",
        "address": "654 Code Ave, Tech District",
        "date": "2025-01-19",
        "time": "3:00 PM",
        "age_range": "10-16",
        "price": "$30",
        "category": "STEM",
        "description": "Introduction to programming concepts",
        "url": "https://example.com/coding-kids",
        "venue_type": "Educational Center"
    },
    {
        "title": "Dance Party",
        "location": "Dance Studio",
        "address": "987 Dance St, Arts Quarter",
        "date": "2025-01-20",
        "time": "4:00 PM",
        "age_range": "5-12",
        "price": "$20",
        "category": "Arts",
        "description": "Fun dance session for kids",
        "url": "https://example.com/dance-party",
        "venue_type": "Dance Studio"
    }
]


# Core tools for event discovery
@tool
def discover_local_events(
    location: str, 
    age_range: str, 
    activity_types: List[str],
    date_range: str = "next_2_weeks"
) -> str:
    """Discover local events and activities for children using mock data and APIs."""
    try:
        # For now, return mock data filtered by location
        # In production, this would call Eventbrite API, Facebook Events, etc.
        filtered_events = []
        
        for event in MOCK_EVENTS:
            # Simple location matching (in production, use geocoding)
            if location.lower() in event["location"].lower() or "downtown" in location.lower():
                filtered_events.append(event)
        
        # If no location matches, return all events as fallback
        if not filtered_events:
            filtered_events = MOCK_EVENTS[:3]  # Return first 3 as fallback
        
        events_summary = f"Found {len(filtered_events)} events in {location}:\n\n"
        for i, event in enumerate(filtered_events, 1):
            events_summary += f"{i}. {event['title']}\n"
            events_summary += f"   📍 {event['location']} - {event['address']}\n"
            events_summary += f"   📅 {event['date']} at {event['time']}\n"
            events_summary += f"   👶 Ages {event['age_range']}\n"
            events_summary += f"   💰 {event['price']}\n"
            events_summary += f"   🏷️ {event['category']}\n"
            events_summary += f"   📝 {event['description']}\n\n"
        
        return events_summary
        
    except Exception as e:
        return f"Error discovering events: {str(e)}"


@tool
def filter_by_age_appropriateness(
    events: List[Dict], 
    child_age: int
) -> str:
    """Filter events by age appropriateness for the child."""
    try:
        # Parse age ranges and filter
        appropriate_events = []
        
        for event in events:
            age_range = event.get("age_range", "")
            if not age_range:
                continue
                
            # Parse age range (e.g., "6-12", "4-10", "2-6")
            age_match = re.search(r'(\d+)-(\d+)', age_range)
            if age_match:
                min_age = int(age_match.group(1))
                max_age = int(age_match.group(2))
                
                if min_age <= child_age <= max_age:
                    appropriate_events.append(event)
        
        result = f"Age-appropriate events for {child_age}-year-old:\n\n"
        for i, event in enumerate(appropriate_events, 1):
            result += f"{i}. {event['title']} (Ages {event['age_range']})\n"
            result += f"   📅 {event['date']} at {event['time']}\n"
            result += f"   💰 {event['price']}\n\n"
        
        return result
        
    except Exception as e:
        return f"Error filtering by age: {str(e)}"


@tool
def categorize_activities(
    events: List[Dict], 
    interests: List[str]
) -> str:
    """Categorize and prioritize activities by child's interests."""
    try:
        # Define interest categories
        interest_categories = {
            "STEM": ["science", "coding", "technology", "math", "engineering"],
            "Arts": ["art", "craft", "dance", "music", "creative", "painting"],
            "Sports": ["soccer", "basketball", "swimming", "tennis", "fitness"],
            "Educational": ["library", "reading", "story", "learning", "book"],
            "Social": ["play", "party", "group", "community", "friends"]
        }
        
        categorized = {category: [] for category in interest_categories.keys()}
        categorized["Other"] = []
        
        for event in events:
            title_desc = (event.get("title", "") + " " + event.get("description", "")).lower()
            category = event.get("category", "Other")
            
            if category in categorized:
                categorized[category].append(event)
            else:
                categorized["Other"].append(event)
        
        # Prioritize based on interests
        prioritized_events = []
        for interest in interests:
            interest_lower = interest.lower()
            for category, events_list in categorized.items():
                if any(keyword in interest_lower for keyword in interest_categories.get(category, [])):
                    prioritized_events.extend(events_list)
        
        # Add remaining events
        for events_list in categorized.values():
            for event in events_list:
                if event not in prioritized_events:
                    prioritized_events.append(event)
        
        result = f"Activities categorized by interests ({', '.join(interests)}):\n\n"
        for i, event in enumerate(prioritized_events, 1):
            result += f"{i}. {event['title']} ({event['category']})\n"
            result += f"   📅 {event['date']} at {event['time']}\n"
            result += f"   💰 {event['price']}\n\n"
        
        return result
        
    except Exception as e:
        return f"Error categorizing activities: {str(e)}"


@tool
def get_weather_impact(activities: List[Dict], location: str) -> str:
    """Analyze weather impact on outdoor activities."""
    # Mock weather data - in production, use OpenWeatherMap API
    weather_conditions = {
        "sunny": "Perfect for outdoor activities",
        "rainy": "Consider indoor alternatives",
        "cold": "Dress warmly for outdoor activities",
        "hot": "Stay hydrated and seek shade"
    }
    
    current_weather = "sunny"  # Mock data
    impact = weather_conditions.get(current_weather, "Weather conditions normal")
    
    outdoor_activities = [event for event in activities if event.get("venue_type") in ["Sports Facility", "Park"]]
    
    result = f"Weather in {location}: {current_weather.title()}\n"
    result += f"Impact: {impact}\n\n"
    
    if outdoor_activities:
        result += "Outdoor activities affected:\n"
        for event in outdoor_activities:
            result += f"- {event['title']} on {event['date']}\n"
    else:
        result += "No outdoor activities scheduled.\n"
    
    return result


# Safety Agent Tools
@tool
def validate_age_appropriateness(activity: Dict, child_age: int) -> str:
    """Validate that an activity is age-appropriate for the child."""
    age_range = activity.get("age_range", "")
    title = activity.get("title", "")
    description = activity.get("description", "")
    
    # Parse age range
    age_match = re.search(r'(\d+)-(\d+)', age_range)
    if age_match:
        min_age = int(age_match.group(1))
        max_age = int(age_match.group(2))
        
        if min_age <= child_age <= max_age:
            return f"✅ {title} is age-appropriate for {child_age}-year-old (ages {age_range})"
        else:
            return f"❌ {title} is NOT age-appropriate for {child_age}-year-old (ages {age_range})"
    
    # If no age range specified, check for age indicators in title/description
    age_indicators = {
        "toddler": [1, 2, 3],
        "preschool": [3, 4, 5],
        "elementary": [6, 7, 8, 9, 10, 11],
        "middle school": [11, 12, 13, 14],
        "teen": [13, 14, 15, 16, 17]
    }
    
    text = (title + " " + description).lower()
    for indicator, ages in age_indicators.items():
        if indicator in text:
            if child_age in ages:
                return f"✅ {title} appears age-appropriate for {child_age}-year-old (indicated for {indicator})"
            else:
                return f"⚠️ {title} may not be age-appropriate for {child_age}-year-old (indicated for {indicator})"
    
    return f"⚠️ {title} - age appropriateness unclear, please verify"


@tool
def check_safety_requirements(activity: Dict) -> str:
    """Check safety requirements and considerations for an activity."""
    title = activity.get("title", "")
    venue_type = activity.get("venue_type", "")
    category = activity.get("category", "")
    
    safety_checks = []
    
    # Venue-specific safety considerations
    if venue_type == "Sports Facility":
        safety_checks.append("✅ Ensure proper safety equipment is provided")
        safety_checks.append("✅ Check if supervision is adequate for age group")
        safety_checks.append("✅ Verify first aid availability")
    elif venue_type == "Museum":
        safety_checks.append("✅ Generally safe environment")
        safety_checks.append("✅ Check for age-appropriate exhibits")
    elif venue_type == "Community Center":
        safety_checks.append("✅ Verify staff background checks")
        safety_checks.append("✅ Check supervision ratios")
    elif venue_type == "Library":
        safety_checks.append("✅ Very safe environment")
        safety_checks.append("✅ Quiet, supervised setting")
    
    # Category-specific safety considerations
    if category == "STEM":
        safety_checks.append("✅ Check for chemical/material safety")
        safety_checks.append("✅ Ensure proper supervision for experiments")
    elif category == "Sports":
        safety_checks.append("✅ Verify physical safety measures")
        safety_checks.append("✅ Check for injury prevention protocols")
    elif category == "Arts":
        safety_checks.append("✅ Check for safe art materials")
        safety_checks.append("✅ Ensure proper ventilation if needed")
    
    result = f"Safety considerations for {title}:\n"
    for check in safety_checks:
        result += f"  {check}\n"
    
    return result


@tool
def assess_accessibility(activity: Dict, special_needs: List[str] = None) -> str:
    """Assess accessibility for children with special needs."""
    title = activity.get("title", "")
    venue_type = activity.get("venue_type", "")
    
    if not special_needs:
        return f"✅ {title} - No special accessibility requirements specified"
    
    accessibility_info = []
    
    for need in special_needs:
        need_lower = need.lower()
        if "wheelchair" in need_lower or "mobility" in need_lower:
            if venue_type in ["Museum", "Library", "Community Center"]:
                accessibility_info.append("✅ Wheelchair accessible (typical for this venue type)")
            else:
                accessibility_info.append("⚠️ Contact venue to confirm wheelchair accessibility")
        
        if "sensory" in need_lower or "autism" in need_lower:
            if venue_type == "Library":
                accessibility_info.append("✅ Quiet environment, good for sensory needs")
            else:
                accessibility_info.append("⚠️ May be noisy - contact venue about sensory accommodations")
        
        if "learning" in need_lower or "adhd" in need_lower:
            accessibility_info.append("✅ Check if venue offers learning support or accommodations")
    
    result = f"Accessibility assessment for {title}:\n"
    for info in accessibility_info:
        result += f"  {info}\n"
    
    return result


# Schedule Agent Tools
@tool
def optimize_schedule(activities: List[Dict], family_schedule: Dict) -> str:
    """Optimize activity schedule based on family availability."""
    available_days = family_schedule.get("available_days", ["weekend"])
    preferred_times = family_schedule.get("preferred_times", ["morning", "afternoon"])
    transportation = family_schedule.get("transportation", "car")
    
    optimized_activities = []
    
    for activity in activities:
        date = activity.get("date", "")
        time = activity.get("time", "")
        
        # Simple optimization logic
        is_weekend = "saturday" in date.lower() or "sunday" in date.lower()
        is_weekday = any(day in date.lower() for day in ["monday", "tuesday", "wednesday", "thursday", "friday"])
        
        time_period = "morning" if "am" in time.lower() else "afternoon" if "pm" in time.lower() else "unknown"
        
        # Check if activity fits family schedule
        fits_schedule = False
        if "weekend" in available_days and is_weekend:
            fits_schedule = True
        elif "weekday" in available_days and is_weekday:
            fits_schedule = True
        elif "any" in available_days:
            fits_schedule = True
        
        if fits_schedule and time_period in preferred_times:
            activity["schedule_fit"] = "✅ Perfect fit"
        elif fits_schedule:
            activity["schedule_fit"] = "⚠️ Good fit, but time may not be ideal"
        else:
            activity["schedule_fit"] = "❌ Doesn't fit current schedule"
        
        optimized_activities.append(activity)
    
    result = f"Schedule optimization for family availability ({', '.join(available_days)}):\n\n"
    for activity in optimized_activities:
        result += f"{activity['title']} on {activity['date']} at {activity['time']}\n"
        result += f"  {activity['schedule_fit']}\n\n"
    
    return result


@tool
def calculate_travel_time(activities: List[Dict], home_location: str) -> str:
    """Calculate travel times from home to activities."""
    result = f"Travel time estimates from {home_location}:\n\n"
    
    for activity in activities:
        location = activity.get("location", "")
        address = activity.get("address", "")
        
        # Mock travel time calculation (in production, use Google Maps API)
        if "downtown" in location.lower() or "downtown" in address.lower():
            travel_time = "15-20 minutes"
        elif "midtown" in location.lower() or "midtown" in address.lower():
            travel_time = "10-15 minutes"
        elif "eastside" in location.lower() or "eastside" in address.lower():
            travel_time = "20-25 minutes"
        elif "westside" in location.lower() or "westside" in address.lower():
            travel_time = "25-30 minutes"
        else:
            travel_time = "15-25 minutes"
        
        result += f"{activity['title']} at {location}\n"
        result += f"  🚗 Travel time: {travel_time}\n"
        result += f"  📍 Address: {address}\n\n"
    
    return result


@tool
def budget_optimization(activities: List[Dict], budget_preference: str) -> str:
    """Optimize activities based on budget preferences."""
    budget_levels = {
        "budget": {"max_per_activity": 15, "preferred": "Free"},
        "moderate": {"max_per_activity": 30, "preferred": "Under $20"},
        "premium": {"max_per_activity": 50, "preferred": "Any price"}
    }
    
    budget_info = budget_levels.get(budget_preference, budget_levels["moderate"])
    max_price = budget_info["max_per_activity"]
    
    result = f"Budget optimization for {budget_preference} preference (max ${max_price}/activity):\n\n"
    
    within_budget = []
    over_budget = []
    
    for activity in activities:
        price_str = activity.get("price", "Free")
        if price_str == "Free":
            within_budget.append(activity)
        else:
            # Extract numeric price
            price_match = re.search(r'\$(\d+)', price_str)
            if price_match:
                price = int(price_match.group(1))
                if price <= max_price:
                    within_budget.append(activity)
                else:
                    over_budget.append(activity)
            else:
                within_budget.append(activity)  # Assume within budget if can't parse
    
    result += "✅ Within budget:\n"
    for activity in within_budget:
        result += f"  - {activity['title']} ({activity['price']})\n"
    
    if over_budget:
        result += "\n⚠️ Over budget:\n"
        for activity in over_budget:
            result += f"  - {activity['title']} ({activity['price']})\n"
    
    return result


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
    """Discover and filter local activities for children"""
    profile = state["child_profile"]
    location = profile["location"]
    age = profile["age"]
    interests = profile.get("interests", [])
    
    prompt_t = (
        "You are a kid activity discovery specialist.\n"
        "Find age-appropriate activities for a {age}-year-old in {location}.\n"
        "Interests: {interests}.\n"
        "Use tools to discover local events, filter by age, and categorize by interests."
    )
    vars_ = {"age": age, "location": location, "interests": ", ".join(interests)}
    
    messages = [SystemMessage(content=prompt_t.format(**vars_))]
    tools = [discover_local_events, filter_by_age_appropriateness, categorize_activities, get_weather_impact]
    agent = llm.bind_tools(tools)
    
    calls: List[Dict[str, Any]] = []
    tool_results = []
    
    with using_prompt_template(template=prompt_t, variables=vars_, version="v1"):
        res = agent.invoke(messages)
    
    # Collect tool calls and execute them
    if getattr(res, "tool_calls", None):
        for c in res.tool_calls:
            calls.append({"agent": "events", "tool": c["name"], "args": c.get("args", {})})
        
        tool_node = ToolNode(tools)
        tr = tool_node.invoke({"messages": [res]})
        tool_results = tr["messages"]
        
        # Add tool results to conversation and ask LLM to synthesize
        messages.append(res)
        messages.extend(tool_results)
        messages.append(SystemMessage(content="Based on the discovered activities, provide a comprehensive summary of age-appropriate events for this child."))
        
        # Get final synthesis from LLM
        final_res = llm.invoke(messages)
        out = final_res.content
    else:
        out = res.content

    return {"messages": [SystemMessage(content=out)], "events": out, "tool_calls": calls}


def safety_agent(state: KidActivityState) -> KidActivityState:
    """Validate safety and age appropriateness of activities"""
    profile = state["child_profile"]
    age = profile["age"]
    special_needs = profile.get("special_needs", [])
    
    # Get events from the events agent (if available)
    events_text = state.get("events", "")
    
    prompt_t = (
        "You are a child safety specialist.\n"
        "Validate the safety and age appropriateness of activities for a {age}-year-old child.\n"
        "Special needs: {special_needs}.\n"
        "Use tools to check age appropriateness, safety requirements, and accessibility."
    )
    vars_ = {"age": age, "special_needs": ", ".join(special_needs) if special_needs else "None"}
    
    messages = [SystemMessage(content=prompt_t.format(**vars_))]
    if events_text:
        messages.append(SystemMessage(content=f"Activities to validate:\n{events_text}"))
    
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
        messages.append(SystemMessage(content=f"Provide a comprehensive safety assessment for the {age}-year-old child, including age appropriateness, safety considerations, and accessibility needs."))
        
        final_res = llm.invoke(messages)
        out = final_res.content
    else:
        out = res.content

    return {"messages": [SystemMessage(content=out)], "safety": out, "tool_calls": calls}


def schedule_agent(state: KidActivityState) -> KidActivityState:
    """Optimize activities based on family schedule and logistics"""
    profile = state["child_profile"]
    family_schedule = state["family_schedule"]
    location = profile["location"]
    budget_preference = profile.get("budget_preference", "moderate")
    
    # Get events from the events agent (if available)
    events_text = state.get("events", "")
    
    prompt_t = (
        "You are a family schedule optimization specialist.\n"
        "Optimize activities for a family in {location} with budget preference: {budget_preference}.\n"
        "Family schedule: {family_schedule}.\n"
        "Use tools to optimize schedule, calculate travel times, and budget optimization."
    )
    vars_ = {
        "location": location, 
        "budget_preference": budget_preference,
        "family_schedule": str(family_schedule)
    }
    
    messages = [SystemMessage(content=prompt_t.format(**vars_))]
    if events_text:
        messages.append(SystemMessage(content=f"Activities to optimize:\n{events_text}"))
    
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
        messages.append(SystemMessage(content="Provide a comprehensive schedule optimization including timing, travel logistics, and budget considerations."))
        
        final_res = llm.invoke(messages)
        out = final_res.content
    else:
        out = res.content

    return {"messages": [SystemMessage(content=out)], "schedule": out, "tool_calls": calls}


def planner_agent(state: KidActivityState) -> KidActivityState:
    """Synthesize all inputs into a final activity plan"""
    profile = state["child_profile"]
    age = profile["age"]
    location = profile["location"]
    interests = profile.get("interests", [])
    
    events = state.get("events", "")
    safety = state.get("safety", "")
    schedule = state.get("schedule", "")
    
    prompt_t = (
        "Create a comprehensive activity plan for a {age}-year-old in {location}.\n"
        "Interests: {interests}.\n\n"
        "Inputs:\nEvents: {events}\nSafety: {safety}\nSchedule: {schedule}\n\n"
        "Synthesize all information into a final, actionable activity plan with specific recommendations."
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


app = FastAPI(title="Kid Activity Planner")
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


@app.get("/health")
def health():
    return {"status": "healthy", "service": "kid-activity-planner"}


# Initialize tracing once at startup, not per request
if _TRACING:
    try:
        space_id = os.getenv("ARIZE_SPACE_ID")
        api_key = os.getenv("ARIZE_API_KEY")
        if space_id and api_key:
            tp = register(space_id=space_id, api_key=api_key, project_name="kid-activity-planner")
            LangChainInstrumentor().instrument(tracer_provider=tp, include_chains=True, include_agents=True, include_tools=True)
            LiteLLMInstrumentor().instrument(tracer_provider=tp, skip_dep_check=True)
    except Exception:
        pass


@app.post("/discover-activities", response_model=KidActivityResponse)
def discover_activities(req: KidActivityRequest):
    """Discover local activities for children using parallel agent architecture"""
    try:
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
        
        # Parse the results for structured response
        events_text = out.get("events", "")
        final_plan = out.get("final", "")
        
        # Extract events from the text (simplified parsing)
        events = []
        lines = events_text.split('\n')
        current_event = {}
        
        for line in lines:
            line = line.strip()
            if re.match(r'^\d+\.', line):  # Event title line
                if current_event:
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
            events.append(current_event)
        
        # If no events parsed from events_text, use mock data as fallback
        if not events:
            events = MOCK_EVENTS[:3]  # Use first 3 mock events as fallback
        
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
    uvicorn.run(app, host="0.0.0.0", port=8001)