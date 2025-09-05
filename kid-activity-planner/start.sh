#!/bin/bash

# Kid Activity Planner Startup Script
# This script starts the Kid Activity Planner backend server

echo "🚀 Starting Kid Activity Planner MVP"
echo "=================================="

# Check if we're in the right directory
if [ ! -f "backend/main.py" ]; then
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
    echo "   Copy env_example.txt to .env and add your API keys:"
    echo "   cp backend/env_example.txt backend/.env"
    echo ""
    echo "   Required for full functionality:"
    echo "   - OPENAI_API_KEY or OPENROUTER_API_KEY"
    echo "   - ARIZE_SPACE_ID and ARIZE_API_KEY (optional)"
    echo ""
fi

# Start the server
echo "🌐 Starting server on http://localhost:8001"
echo "   Frontend: http://localhost:8001"
echo "   API docs: http://localhost:8001/docs"
echo "   Health: http://localhost:8001/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

cd backend
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
