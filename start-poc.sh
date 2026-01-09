#!/bin/bash

echo "🚀 Email Intelligence POC Startup"
echo "================================="

# Check for environment parameter
ENVIRONMENT=${1:-development}  # Default to development if no parameter provided
echo "🌍 Environment: $ENVIRONMENT"
echo ""

# Check for environment file
ENV_FILE=".env.$ENVIRONMENT"
if [ ! -f "$ENV_FILE" ]; then
    echo "⚠️  Environment file not found: $ENV_FILE"
    echo "   📋 For Google Drive integration, create $ENV_FILE with:"
    echo "      GOOGLE_CLIENT_ID=your_google_client_id"
    echo "      GOOGLE_CLIENT_SECRET=your_google_client_secret"
    echo "      GOOGLE_REDIRECT_URI=http://localhost:3000"
    echo "   📖 See README.md for complete setup instructions"
    echo ""
else
    echo "✅ Found environment file: $ENV_FILE"
    # Check for Google Drive configuration
    if grep -q "GOOGLE_CLIENT_ID" "$ENV_FILE"; then
        echo "🌐 Google Drive OAuth2 integration configured"
    else
        echo "📋 Google Drive OAuth2 not configured (optional)"
    fi
    echo ""
fi

# Function to check if port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null ; then
        echo "⚠️  Port $1 is already in use"
        return 1
    else
        return 0
    fi
}

# Function to kill process on port
kill_port() {
    echo "🛑 Killing process on port $1..."
    lsof -ti:$1 | xargs kill -9 2>/dev/null || true
    sleep 2
}

# Check and handle port conflicts
if ! check_port 3000; then
    echo "   Would you like to kill the process? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        kill_port 3000
    else
        echo "   Please stop the process manually and try again"
        exit 1
    fi
fi

if ! check_port 8000; then
    echo "   Would you like to kill the process? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        kill_port 8000
    else
        echo "   Please stop the process manually and try again"
        exit 1
    fi
fi

echo "🔍 Starting Email Intelligence POC..."
echo ""

# Check if we're in the right directory
if [ ! -d "frontend" ] || [ ! -d "backend" ]; then
    echo "❌ Please run this script from the Email Intelligence root directory"
    echo "   Expected structure:"
    echo "   📁 Email Intelligence/"
    echo "   ├── 📁 frontend/"
    echo "   ├── 📁 backend/"
    echo "   └── 📄 start-poc.sh"
    exit 1
fi

# Function to start backend
start_backend() {
    echo "🔧 Starting Backend API Server..."
    cd backend
    
    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 is required but not installed."
        echo "   Please install Python 3.8+ and try again"
        exit 1
    fi
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        echo "📦 Creating Python virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment and install dependencies
    source venv/bin/activate
    echo "📥 Installing Python dependencies..."
    pip install -r requirements.txt > /dev/null 2>&1
    
    echo "🌐 Backend API starting at http://localhost:8000"
    echo "📖 API docs will be available at http://localhost:8000/docs"
    echo ""
    
    # Start the backend server in background with environment
    PYTHON_ENV=$ENVIRONMENT python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload > ../backend.log 2>&1 &
    BACKEND_PID=$!
    
    # Wait a moment for server to start
    sleep 3
    
    # Check if backend started successfully
    if curl -s http://localhost:8000/health > /dev/null; then
        echo "✅ Backend API is running (PID: $BACKEND_PID)"
    else
        echo "❌ Backend API failed to start. Check backend.log for details."
        exit 1
    fi
    
    cd ..
}

# Function to start frontend
start_frontend() {
    echo "🎨 Starting Frontend Development Server..."
    cd frontend
    
    # Check if Node.js is available
    if ! command -v npm &> /dev/null; then
        echo "❌ Node.js/npm is required but not installed."
        echo "   Please install Node.js and try again"
        exit 1
    fi
    
    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        echo "📦 Installing Node.js dependencies..."
        npm install > /dev/null 2>&1
    fi
    
    # Load environment variables from environment-specific file
    ENV_FILE="../.env.$ENVIRONMENT"
    if [ -f "$ENV_FILE" ]; then
        echo "📋 Loading environment variables from .env.$ENVIRONMENT file..."
        export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
    elif [ -f "../.env" ]; then
        echo "📋 Loading environment variables from .env file (fallback)..."
        export $(cat ../.env | grep -v '^#' | xargs)
    fi
    
    echo "🌐 Frontend starting at http://localhost:3000"
    echo ""
    
    # Start the frontend server in background with appropriate mode
    if [ "$ENVIRONMENT" = "production" ]; then
        npm run build > ../frontend.log 2>&1
        npm run preview >> ../frontend.log 2>&1 &
    else
        npm run dev > ../frontend.log 2>&1 &
    fi
    FRONTEND_PID=$!
    
    # Wait a moment for server to start
    sleep 5
    
    echo "✅ Frontend is running (PID: $FRONTEND_PID)"
    cd ..
}

# Start both services
start_backend
start_frontend

# Display startup summary
echo ""
echo "🎉 Email Intelligence POC is now running!"
echo "========================================"
echo ""
echo "📱 Frontend:     http://localhost:3000"
echo "🔧 Backend API:  http://localhost:8000" 
echo "📖 API Docs:     http://localhost:8000/docs"
echo ""
echo "📄 Logs:"
echo "   Frontend: frontend.log"
echo "   Backend:  backend.log"
echo ""
echo "🔧 To test the POC:"
echo "   1. Open http://localhost:3000 in your browser"
echo "   2. Navigate to Mailboxes -> Add Mailbox"
echo "   3. Choose file source:"
echo "      📁 Local File: Enter file path directly"
echo "      🌐 Google Drive: Connect with OAuth2 and browse files"
echo "   4. For Google Drive: Click 'Connect Google Drive' → Authenticate → Select file"
echo "   5. Test connection and create mailbox"
echo "   6. Use the 'Process' button to start email analysis"
echo "   7. Monitor progress in real-time on Dashboard"
echo ""
echo "🛑 To stop all services:"
echo "   kill $BACKEND_PID $FRONTEND_PID"
echo ""
echo "Press Ctrl+C to stop monitoring..."

# Monitor both services
tail -f frontend.log backend.log