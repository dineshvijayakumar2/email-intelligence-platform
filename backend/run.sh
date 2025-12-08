#!/bin/bash

echo "🚀 Starting Email Intelligence Backend Services"
echo "=============================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if Redis is running (optional for POC)
if command -v redis-cli &> /dev/null; then
    if redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis is running"
    else
        echo "⚠️  Redis not running (optional for POC)"
    fi
else
    echo "⚠️  Redis not installed (optional for POC)"
fi

# Start the API server
echo ""
echo "🎯 Starting FastAPI server..."
echo "📍 API will be available at: http://localhost:8000"
echo "📖 API docs at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload