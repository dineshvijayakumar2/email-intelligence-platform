# Makefile for Email Intelligence Platform
# Provides convenient commands for development and deployment

.PHONY: help install dev deploy test clean

# Default target
help:
	@echo "Email Intelligence Platform - Available Commands"
	@echo "================================================"
	@echo "Development:"
	@echo "  make install     - Install all dependencies"
	@echo "  make dev        - Start development environment"
	@echo "  make test       - Run all tests"
	@echo "  make clean      - Clean build artifacts"
	@echo ""
	@echo "Deployment:"
	@echo "  make deploy-staging    - Deploy to staging"
	@echo "  make deploy-production - Deploy to production"
	@echo "  make deploy-docker     - Deploy with Docker"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate  - Run database migrations"
	@echo "  make db-backup   - Backup database"
	@echo ""
	@echo "Utilities:"
	@echo "  make logs       - Show application logs"
	@echo "  make health     - Check system health"

# Install dependencies
install:
	@echo "📦 Installing dependencies..."
	cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r ../requirements.txt
	cd frontend && npm install
	@echo "✅ Dependencies installed"

# Start development environment
dev:
	@echo "🚀 Starting development environment..."
	./start-poc.sh development

# Deploy to staging
deploy-staging:
	@echo "🚀 Deploying to staging..."
	./deploy/scripts/deploy.sh staging railway

# Deploy to production
deploy-production:
	@echo "🚀 Deploying to production..."
	@read -p "Are you sure you want to deploy to production? (y/N) " confirm && \
	if [ "$$confirm" = "y" ]; then \
		./deploy/scripts/deploy.sh production railway; \
	else \
		echo "Deployment cancelled"; \
	fi

# Deploy with Docker
deploy-docker:
	@echo "🐳 Deploying with Docker..."
	docker-compose -f deploy/docker/docker-compose.yml up -d

# Run tests
test:
	@echo "🧪 Running tests..."
	cd backend && source venv/bin/activate && python -m pytest tests/
	cd frontend && npm test

# Clean build artifacts
clean:
	@echo "🧹 Cleaning build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf frontend/build frontend/node_modules
	rm -rf backend/venv backend/dist
	rm -f *.log
	@echo "✅ Cleaned"

# Database migrations
db-migrate:
	@echo "🗄️ Running database migrations..."
	cd backend && source venv/bin/activate && python -m src.database.migrate

# Database backup
db-backup:
	@echo "💾 Backing up database..."
	@echo "This would connect to Supabase and create a backup"

# Show logs
logs:
	@echo "📋 Showing logs..."
	@if [ -f "backend.log" ]; then tail -f backend.log; fi

# Health check
health:
	@echo "🏥 Checking system health..."
	@curl -s http://localhost:8000/health | python -m json.tool || echo "Backend not running"

# Railway specific commands
railway-login:
	railway login

railway-link:
	railway link

railway-up:
	railway up

railway-logs:
	railway logs --tail

railway-status:
	railway status