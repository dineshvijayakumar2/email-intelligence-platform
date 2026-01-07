#!/bin/bash

# Email Intelligence Platform - First Time Setup Script
# This script sets up the complete development environment

echo "================================================"
echo "📧 Email Intelligence Platform - Setup"
echo "================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get OS type
OS_TYPE=$(uname -s)
echo "🖥️  Operating System: $OS_TYPE"
echo ""

# Function to check command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check Prerequisites
echo "📋 Checking Prerequisites..."
echo "================================"

# Check Python
if command_exists python3; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    print_success "Python $PYTHON_VERSION found"
    
    # Check minimum version
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
        print_success "Python version meets requirements (3.8+)"
    else
        print_error "Python 3.8+ is required. Current version: $PYTHON_VERSION"
        exit 1
    fi
else
    print_error "Python 3 is not installed"
    echo "   Please install Python 3.8 or higher:"
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        echo "   brew install python3"
    else
        echo "   sudo apt-get install python3 python3-pip"
    fi
    exit 1
fi

# Check Node.js
if command_exists node; then
    NODE_VERSION=$(node -v)
    print_success "Node.js $NODE_VERSION found"
else
    print_error "Node.js is not installed"
    echo "   Please install Node.js 16 or higher:"
    if [[ "$OS_TYPE" == "Darwin" ]]; then
        echo "   brew install node"
    else
        echo "   curl -fsSL https://deb.nodesource.com/setup_16.x | sudo -E bash -"
        echo "   sudo apt-get install -y nodejs"
    fi
    exit 1
fi

# Check npm
if command_exists npm; then
    NPM_VERSION=$(npm -v)
    print_success "npm $NPM_VERSION found"
else
    print_error "npm is not installed"
    exit 1
fi

# Check Redis
echo ""
echo "📋 Checking Redis..."
echo "================================"

REDIS_INSTALLED=false
REDIS_RUNNING=false

if command_exists redis-cli; then
    REDIS_INSTALLED=true
    print_success "Redis is installed"
    
    if redis-cli ping > /dev/null 2>&1; then
        REDIS_RUNNING=true
        print_success "Redis is running"
    else
        print_warning "Redis is installed but not running"
    fi
else
    print_error "Redis is not installed (REQUIRED)"
fi

# Install Redis if needed
if [ "$REDIS_INSTALLED" = false ]; then
    echo ""
    echo "Redis is required for job processing. Would you like to install it now? (y/n)"
    read -r INSTALL_REDIS
    
    if [[ "$INSTALL_REDIS" =~ ^[Yy]$ ]]; then
        if [[ "$OS_TYPE" == "Darwin" ]]; then
            echo "Installing Redis via Homebrew..."
            brew install redis
            brew services start redis
        else
            echo "Installing Redis via apt..."
            sudo apt update
            sudo apt install redis-server -y
            sudo systemctl start redis-server
            sudo systemctl enable redis-server
        fi
        print_success "Redis installed and started"
    else
        print_error "Redis is required. Please install it manually and run setup again"
        exit 1
    fi
elif [ "$REDIS_RUNNING" = false ]; then
    echo ""
    echo "Would you like to start Redis now? (y/n)"
    read -r START_REDIS
    
    if [[ "$START_REDIS" =~ ^[Yy]$ ]]; then
        if [[ "$OS_TYPE" == "Darwin" ]]; then
            brew services start redis
        else
            sudo systemctl start redis-server
        fi
        print_success "Redis started"
    else
        print_warning "Remember to start Redis before running the application"
    fi
fi

# Setup Backend
echo ""
echo "🔧 Setting up Backend..."
echo "================================"

cd backend || exit

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_success "Virtual environment already exists"
fi

# Activate virtual environment and install dependencies
echo "Installing backend dependencies..."
source venv/bin/activate
pip install --upgrade pip > /dev/null 2>&1
pip install -r ../requirements.txt
print_success "Backend dependencies installed"

deactivate
cd ..

# Setup Frontend
echo ""
echo "🎨 Setting up Frontend..."
echo "================================"

cd frontend || exit

# Install dependencies
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
    print_success "Frontend dependencies installed"
else
    echo "Updating frontend dependencies..."
    npm install
    print_success "Frontend dependencies updated"
fi

cd ..

# Setup Environment File
echo ""
echo "⚙️  Setting up Environment Configuration..."
echo "================================"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        print_success "Created .env file from .env.example"
        print_warning "Please edit .env file with your configuration:"
        echo "   - Supabase credentials"
        echo "   - Redis URL (if not using default)"
        echo "   - Google Drive API credentials (optional)"
    else
        print_error "No .env.example file found"
        echo "Please create a .env file with required configuration"
    fi
else
    print_success ".env file already exists"
fi

# Create necessary directories
echo ""
echo "📁 Creating necessary directories..."
echo "================================"

mkdir -p backend/logs
mkdir -p dev-scripts
print_success "Directories created"

# Setup complete
echo ""
echo "================================================"
echo "🎉 Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration"
echo "2. Set up your Supabase database (run migrations)"
echo "3. Start the application with: ./start-poc.sh"
echo ""
echo "To start services individually:"
echo "   Backend:  cd backend && ./run.sh"
echo "   Frontend: cd frontend && npm start"
echo ""

# Check if .env needs configuration
if [ -f ".env" ]; then
    if grep -q "your-project.supabase.co" .env; then
        print_warning "Don't forget to configure your .env file with actual values!"
    fi
fi

echo "Happy coding! 🚀"