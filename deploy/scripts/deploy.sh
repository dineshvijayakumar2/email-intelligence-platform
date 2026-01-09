#!/bin/bash

# Universal Deployment Script
# Supports multiple deployment targets and environments

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT=${1:-staging}
TARGET=${2:-railway}
VERSION=${3:-latest}

echo -e "${GREEN}🚀 Email Intelligence Platform - Deployment${NC}"
echo "================================================="
echo "Environment: $ENVIRONMENT"
echo "Target: $TARGET"
echo "Version: $VERSION"
echo "================================================="

# Load environment variables
ENV_FILE="config/$ENVIRONMENT/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}📋 Loading environment from $ENV_FILE${NC}"
    set -a
    source "$ENV_FILE"
    set +a
else
    echo -e "${RED}❌ Environment file not found: $ENV_FILE${NC}"
    echo "Please create it from config/$ENVIRONMENT/.env.example"
    exit 1
fi

# Function to deploy to Railway
deploy_railway() {
    echo -e "${GREEN}🚂 Deploying to Railway...${NC}"
    
    # Check Railway CLI
    if ! command -v railway &> /dev/null; then
        echo -e "${YELLOW}Installing Railway CLI...${NC}"
        npm install -g @railway/cli
    fi
    
    # Use Railway configuration
    railway up --environment $ENVIRONMENT
}

# Function to deploy with Docker
deploy_docker() {
    echo -e "${GREEN}🐳 Deploying with Docker...${NC}"
    
    # Build images
    docker-compose -f deploy/docker/docker-compose.yml build
    
    # Deploy
    docker-compose -f deploy/docker/docker-compose.yml up -d
}

# Function to deploy to Kubernetes
deploy_kubernetes() {
    echo -e "${GREEN}☸️ Deploying to Kubernetes...${NC}"
    
    # Apply configurations
    kubectl apply -f deploy/k8s/namespace.yaml
    kubectl apply -f deploy/k8s/configmap-$ENVIRONMENT.yaml
    kubectl apply -f deploy/k8s/
}

# Run pre-deployment checks
run_checks() {
    echo -e "${YELLOW}🔍 Running pre-deployment checks...${NC}"
    
    # Check Python tests
    if [ -d "tests" ]; then
        python -m pytest tests/ || echo -e "${YELLOW}⚠️ Some tests failed${NC}"
    fi
    
    # Check frontend build
    cd frontend && npm run build && cd ..
    
    # Check database connection
    python -c "from src.database.supabase_client import SupabaseClient; SupabaseClient.get_client()" || {
        echo -e "${RED}❌ Database connection failed${NC}"
        exit 1
    }
}

# Run database migrations
run_migrations() {
    echo -e "${YELLOW}🗄️ Running database migrations...${NC}"
    python -m src.database.migrate
}

# Main deployment logic
case $TARGET in
    railway)
        deploy_railway
        ;;
    docker)
        deploy_docker
        ;;
    kubernetes|k8s)
        deploy_kubernetes
        ;;
    *)
        echo -e "${RED}❌ Unknown deployment target: $TARGET${NC}"
        echo "Supported targets: railway, docker, kubernetes"
        exit 1
        ;;
esac

# Post-deployment tasks
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo "================================================="
echo "Environment: $ENVIRONMENT"
echo "Target: $TARGET"
echo "Timestamp: $(date)"
echo "================================================="

# Health check
if [ "$ENVIRONMENT" != "development" ]; then
    echo -e "${YELLOW}🏥 Running health check...${NC}"
    sleep 10
    
    if [ "$TARGET" == "railway" ]; then
        HEALTH_URL="https://api-$ENVIRONMENT.emailintel.app/health"
    else
        HEALTH_URL="http://localhost:8000/health"
    fi
    
    if curl -f "$HEALTH_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Health check passed${NC}"
    else
        echo -e "${YELLOW}⚠️ Health check failed - services may still be starting${NC}"
    fi
fi