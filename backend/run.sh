#!/bin/bash

echo "🚀 Starting Email Intelligence Backend Services"
echo "=============================================="

# Get the script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Check for environment parameter
ENVIRONMENT=${1:-development}  # Default to development if no parameter provided
export PYTHON_ENV=$ENVIRONMENT

echo "🌍 Environment: $ENVIRONMENT"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    echo "   Please install Python 3.8 or higher"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "📌 Python version: $PYTHON_VERSION"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip first
echo "⬆️  Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1

# Install dependencies from backend requirements.txt
echo "📥 Installing dependencies from backend requirements.txt..."
pip install -r requirements.txt

# Check if Redis is running (REQUIRED)
echo "🔍 Checking Redis status..."
if command -v redis-cli &> /dev/null; then
    if redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis is running (REQUIRED)"
    else
        echo "❌ Redis is not running (REQUIRED for job processing)"
        echo "   Please start Redis with: redis-server"
        echo "   Install Redis: brew install redis (macOS) or sudo apt install redis-server (Ubuntu)"
        exit 1
    fi
else
    echo "❌ Redis is not installed (REQUIRED for job processing)"
    echo "   Install Redis: brew install redis (macOS) or sudo apt install redis-server (Ubuntu)"
    echo "   Then start it with: redis-server"
    exit 1
fi

# Load environment variables based on environment
ENV_FILE="$PROJECT_ROOT/.env.$ENVIRONMENT"
if [ -f "$ENV_FILE" ]; then
    echo "📋 Loading environment variables from .env.$ENVIRONMENT..."
    export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
elif [ -f "$PROJECT_ROOT/.env" ]; then
    echo "📋 Loading environment variables from .env (fallback)..."
    export $(cat "$PROJECT_ROOT/.env" | grep -v '^#' | xargs)
else
    echo "⚠️  No .env.$ENVIRONMENT or .env file found in project root"
    echo "   Create .env.$ENVIRONMENT or copy .env.example to .env and configure it"
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
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload