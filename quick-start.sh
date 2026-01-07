#!/bin/bash

# Quick Start Script for Email Intelligence POC
# This script provides shortcuts for common development tasks

echo "🚀 Email Intelligence POC - Quick Start"
echo "======================================="
echo ""

# Show available commands
show_help() {
    echo "Available commands:"
    echo ""
    echo "  ./quick-start.sh start          # Start both frontend and backend"
    echo "  ./quick-start.sh frontend       # Start frontend only"
    echo "  ./quick-start.sh backend        # Start backend only"
    echo "  ./quick-start.sh stop           # Stop all services"
    echo "  ./quick-start.sh logs           # Show logs"
    echo "  ./quick-start.sh status         # Check service status"
    echo "  ./quick-start.sh setup          # First-time setup"
    echo "  ./quick-start.sh help           # Show this help"
    echo ""
    echo "🌐 Google Drive Integration:"
    echo "  - Configure OAuth2 in .env.development file"
    echo "  - See README.md for Google Cloud Console setup"
    echo ""
}

# Check if services are running
check_status() {
    echo "🔍 Checking service status..."
    
    # Check backend
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend: Running (http://localhost:8000)"
    else
        echo "❌ Backend: Not running"
    fi
    
    # Check frontend
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo "✅ Frontend: Running (http://localhost:3000)"
    else
        echo "❌ Frontend: Not running"
    fi
    
    # Check Redis
    if redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis: Running"
    else
        echo "❌ Redis: Not running (run 'redis-server')"
    fi
    echo ""
}

# Stop all services
stop_services() {
    echo "🛑 Stopping all services..."
    
    # Kill backend processes
    pkill -f "python.*main.py" 2>/dev/null
    pkill -f "uvicorn.*main:app" 2>/dev/null
    
    # Kill frontend processes
    pkill -f "npm.*dev" 2>/dev/null
    pkill -f "vite" 2>/dev/null
    
    # Kill processes on specific ports
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    lsof -ti:3000 | xargs kill -9 2>/dev/null
    
    echo "✅ All services stopped"
}

# Start backend only
start_backend() {
    echo "🔧 Starting Backend..."
    cd backend
    
    # Activate venv and start
    source venv/bin/activate 2>/dev/null || {
        echo "❌ Virtual environment not found. Run './quick-start.sh setup' first"
        exit 1
    }
    
    echo "🌐 Backend starting at http://localhost:8000"
    python main.py &
    echo "✅ Backend started"
    cd ..
}

# Start frontend only
start_frontend() {
    echo "🎨 Starting Frontend..."
    cd frontend
    
    if [ ! -d "node_modules" ]; then
        echo "❌ Node modules not found. Run './quick-start.sh setup' first"
        exit 1
    fi
    
    echo "🌐 Frontend starting at http://localhost:3000"
    npm run dev &
    echo "✅ Frontend started"
    cd ..
}

# First-time setup
setup() {
    echo "🔧 First-time setup..."
    echo ""
    
    # Backend setup
    echo "📦 Setting up backend..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    echo "✅ Backend dependencies installed"
    cd ..
    
    # Frontend setup
    echo "📦 Setting up frontend..."
    cd frontend
    npm install
    echo "✅ Frontend dependencies installed"
    cd ..
    
    # Environment file check
    if [ ! -f ".env.development" ]; then
        echo ""
        echo "⚠️  Creating sample .env.development file..."
        cat > .env.development << 'EOF'
# Database Configuration
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Google Drive OAuth2 Integration (optional)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000

# API Configuration
API_BASE_URL=http://localhost:8000/api
EOF
        echo "📋 Please update .env.development with your configuration"
        echo "📖 See README.md for detailed setup instructions"
    fi
    
    echo ""
    echo "✅ Setup complete! You can now run './quick-start.sh start'"
}

# Show logs
show_logs() {
    echo "📄 Service logs (Press Ctrl+C to exit):"
    echo "======================================="
    
    # Check if log files exist
    if [ -f "backend.log" ] && [ -f "frontend.log" ]; then
        tail -f backend.log frontend.log
    elif [ -f "backend/logs/backend.log" ]; then
        tail -f backend/logs/backend.log
    else
        echo "❌ No log files found. Start services first."
    fi
}

# Handle command line arguments
case "$1" in
    "start")
        echo "🚀 Starting Email Intelligence POC..."
        ./start-poc.sh
        ;;
    "frontend")
        stop_services
        start_frontend
        echo "🎨 Frontend only mode. Backend must be started separately."
        ;;
    "backend")
        stop_services
        start_backend
        echo "🔧 Backend only mode. Frontend must be started separately."
        ;;
    "stop")
        stop_services
        ;;
    "status")
        check_status
        ;;
    "logs")
        show_logs
        ;;
    "setup")
        setup
        ;;
    "help"|"-h"|"--help")
        show_help
        ;;
    "")
        show_help
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo ""
        show_help
        exit 1
        ;;
esac