#!/bin/bash

# Railway Deployment Script for Email Intelligence Platform
# This script automates the deployment process to Railway

set -e

echo "🚀 Email Intelligence Platform - Railway Deployment"
echo "================================================="

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Installing..."
    npm install -g @railway/cli
fi

# Function to deploy service
deploy_service() {
    local service=$1
    echo "📦 Deploying $service..."
    railway up -s $service
    echo "✅ $service deployed successfully"
}

# Check environment
ENVIRONMENT=${1:-production}
echo "🌍 Deploying to: $ENVIRONMENT"

# Login to Railway
echo "🔑 Logging into Railway..."
railway login

# Link to project (create if doesn't exist)
echo "🔗 Linking Railway project..."
railway link || railway init

# Set environment variables from .env file
if [ -f ".env.$ENVIRONMENT" ]; then
    echo "📋 Loading environment variables from .env.$ENVIRONMENT"
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        if [[ ! "$key" =~ ^# ]] && [ -n "$key" ]; then
            # Remove quotes from value
            value="${value%\"}"
            value="${value#\"}"
            railway variables set "$key=$value"
        fi
    done < ".env.$ENVIRONMENT"
fi

# Add Redis service
echo "🔄 Setting up Redis..."
railway add redis || echo "Redis already exists"

# Deploy Backend API
echo "🎯 Deploying Backend API..."
deploy_service backend-api

# Deploy Frontend
echo "🌐 Deploying Frontend..."
deploy_service frontend

# Deploy Worker Service
echo "⚙️ Deploying Worker Service..."
deploy_service email-worker

# Run database migrations
echo "🗄️ Running database migrations..."
railway run --service backend-api python -m src.database.migrate

# Health check
echo "🏥 Running health checks..."
sleep 10
BACKEND_URL=$(railway variables get RAILWAY_PUBLIC_DOMAIN)
if curl -f "https://$BACKEND_URL/health" > /dev/null 2>&1; then
    echo "✅ Backend is healthy"
else
    echo "⚠️ Backend health check failed"
fi

# Display deployment info
echo ""
echo "==================================================="
echo "✨ Deployment Complete!"
echo "==================================================="
echo "📍 Backend API: https://$(railway variables get RAILWAY_PUBLIC_DOMAIN)"
echo "📍 Frontend: https://$(railway variables get RAILWAY_PUBLIC_DOMAIN)"
echo "📍 Redis: Connected via internal network"
echo ""
echo "📊 View logs: railway logs"
echo "📈 View metrics: railway metrics"
echo "🔄 Rollback: railway rollback"
echo "==================================================="