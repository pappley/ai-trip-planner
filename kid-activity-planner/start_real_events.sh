#!/bin/bash

# Kid Activity Planner with Real Event Scraping Startup Script
# This script starts the enhanced Kid Activity Planner with real event API integrations

echo "🎪 Starting Kid Activity Planner with Real Event Scraping"
echo "========================================================"

# Check if we're in the right directory
if [ ! -f "backend/main_with_real_events.py" ]; then
    echo "❌ Error: Please run this script from the kid-activity-planner directory"
    echo "   Current directory: $(pwd)"
    echo "   Expected: kid-activity-planner/"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "backend/.venv" ]; then
    echo "📦 Creating virtual environment..."
    cd backend
    python3 -m venv .venv
    cd ..
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source backend/.venv/bin/activate

# Install dependencies
echo "📚 Installing dependencies..."
cd backend
pip install -r requirements.txt
cd ..

# Check for .env file
if [ ! -f "backend/.env" ]; then
    echo "⚠️  Warning: No .env file found"
    echo "   Copy env_real_events.txt to .env and add your API keys:"
    echo "   cp backend/env_real_events.txt backend/.env"
    echo ""
    echo "   Required for full functionality:"
echo "   - OPENAI_API_KEY or OPENROUTER_API_KEY"
echo "   - PREDICTHQ_API_KEY (for real events) ✅"
echo "   - GOOGLE_PLACES_API_KEY (for local venues) ✅"
echo "   - YELP_API_KEY (for local businesses) ✅"
echo "   - ARIZE_SPACE_ID and ARIZE_API_KEY (optional)"
echo ""
echo "   Disabled integrations:"
echo "   - EVENTBRITE_API_KEY (disabled) ❌"
echo "   - FACEBOOK_ACCESS_TOKEN (disabled) ❌"
    echo ""
    echo "   The system will work with enhanced mock data if API keys are not provided."
    echo ""
fi

# Start the enhanced server
echo "🌐 Starting Cleveland MVP server on http://localhost:8004"
echo "   Frontend: http://localhost:8004"
echo "   API docs: http://localhost:8004/docs"
echo "   Health: http://localhost:8004/health"
echo ""
echo "🏙️  CLEVELAND MVP - Focused on Cleveland, Ohio"
echo "🎪 Real Event API Integrations:"
echo "   - PredictHQ API (Cleveland events) ✅"
echo "   - Local Venue Events (Cleveland venues) ✅"
echo "   - Google Places API (Cleveland venues) ✅"
echo "   - Yelp API (Cleveland businesses) ✅"
echo "   - Eventbrite API (disabled) ❌"
echo "   - Facebook Events API (disabled) ❌"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

cd backend
python3 main_with_real_events.py
