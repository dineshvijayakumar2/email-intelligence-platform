# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Recent Improvements (Jan 8, 2025)

1. **Single .env file**: All configuration now in root .env file (no more frontend/.env.local)
2. **Google Drive Integration**: Frontend can authenticate and select files from Google Drive
3. **Redis Required**: Redis is now mandatory for job processing (no fallback mode)
4. **Cleaned Structure**: Test files and temporary scripts moved to dev-scripts/
5. **RemoteZip Streaming**: Industry-standard implementation for processing 65GB+ OLM files directly from Google Drive
6. **Progress Tracking with ETA**: Real-time processing speed and estimated time remaining calculations

## Common Development Commands

### Start the Application
```bash
# One-command startup (starts both backend and frontend)
./start-poc.sh

# Manual startup
cd backend && ./run.sh              # Backend API (port 8000)
cd frontend && npm start             # Frontend (port 3000)
```

### Frontend Development
```bash
cd frontend
npm install                          # Install dependencies
npm start                           # Start development server
npm run build                       # Build for production
npm test                            # Run tests
```

### Backend Development
```bash
cd backend
python3 -m venv venv               # Create virtual environment
source venv/bin/activate           # Activate environment
pip install -r requirements.txt    # Install dependencies
uvicorn main:app --reload          # Run development server
```

### Redis (REQUIRED)
```bash
# Install Redis
brew install redis                 # macOS
sudo apt install redis-server      # Ubuntu

# Start Redis
redis-server

# Test Redis connection
redis-cli ping
```

### Testing
```bash
# Test email tagging
python dev-scripts/test_email_tagging.py

# Test MBOX extraction
python -m src.extractors.mbox_extractor /path/to/file.mbox
```

## High-Level Architecture

### System Overview
Email processing platform with FastAPI backend and React frontend, supporting MBOX/PST/OLM formats with **mandatory Redis** for real-time progress tracking and Google Drive integration.

### Core Processing Pipeline
```
Frontend → FastAPI → ThreadPool (20 workers) → Email Processing Pipeline
                            ↓
        Extractor → Normalizer → Tagger → Database Insert
                            ↓
        Redis (REQUIRED progress cache) + Supabase (persistent storage)
```

### Key Components

#### Backend (FastAPI)
- **main.py**: API endpoints, job control, ThreadPoolExecutor for concurrent processing
- **Redis Required**: Application won't start without Redis connection
- **email_processor.py**: Main pipeline orchestrator in src/processors/
- **Extractors** (src/extractors/): Stream-based file processors for MBOX/PST/OLM
- **email_tagger.py**: Rule-based tagging engine (20+ tags) in src/processors/
- **Redis Managers**: JobProgressManager and JobQueueManager for real-time updates

#### Frontend (React/TypeScript)
- **Pages**: dashboard, mailboxes, emails, processing (in frontend/src/pages/)
- **Google Drive Integration**: GoogleDrivePicker component and googleDriveService
- **Services**: API integration layer (frontend/src/services/)
- **Auto-refresh**: Polls job status every 2-5 seconds
- **Config**: Single config.js loads from root .env

#### Data Layer
- **Supabase PostgreSQL**: Primary data storage
- **Redis (REQUIRED)**: Progress cache and job queue management
- **Tables**: emails, email_categories (tags), processing_jobs, mailboxes, folders

### Important Implementation Details

#### Google Drive Integration
- Frontend authenticates with Google OAuth2
- File picker allows selecting email archives from Drive
- **RemoteZip Streaming** (Jan 8, 2025): Large OLM files (65GB+) are streamed directly using HTTP range requests
  - No full download required - uses targeted byte-range requests
  - Central Directory scanning for efficient ZIP navigation
  - Virtual file wrapper for transparent streaming operations
  - Smart retry logic with exponential backoff for network resilience
- Supports MBOX, PST, OLM files in Drive

#### Redis as Primary Job System
- No longer optional - application requires Redis
- Updates on every email processed
- Database sync every 100 emails
- TTL configurable via REDIS_TTL_DAYS
- Connection via REDIS_URL environment variable

#### Environment Configuration

Single .env file in root directory:
```
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_role_key

# Redis Configuration (REQUIRED)
REDIS_URL=redis://localhost:6379
REDIS_TTL_DAYS=7

# Google Drive API Configuration
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback

# API Configuration
API_BASE_URL=http://localhost:8000/api
```

Note: Frontend environment variables are automatically loaded from root .env by start-poc.sh script.

### File Structure Changes

- **dev-scripts/**: Development and test scripts (moved from root)
- **frontend/src/config.js**: Central configuration file
- **frontend/src/services/googleDriveService.ts**: Google Drive API integration
- **frontend/src/components/GoogleDrivePicker.tsx**: File selection UI
- **src/storage/** (Jan 8, 2025): New cloud storage streaming modules
  - **remote_zip_google_drive.py**: RemoteZip implementation for Google Drive
  - **google_drive_stream.py**: Streaming wrapper for Drive files
  - **cloud_stream_wrapper.py**: Base streaming interface
  - **smart_zip_reader.py**: Efficient ZIP Central Directory scanner
- Removed: test_*.py files from root, POC documentation files

### Instructions
Please follow the below best practices while doing coding.
1. Don't hardcode gdrive that may be different in different machines. Please make sure that the code is not too specific for the folder setup during the
  current implementation
2. Make sure that the overall pipeline of email processing activities remains consistent for all mailbox types
3. When suggesting any database changes for fixes, please make sure the original database setup script files are also updated so that when doing new deployment, the issues don't reoccur and doesn't need separate migration.
4. Make sure you don't keep the fix scripts in the main code base
5. When you make changes that require backend to restart, mimic change in main.py that will auto-shutdown and restart the backend service
6. Do git sync to the main branch when performing major changes to the codebase.
7. Create docs only in docs folder. Create a new one only if it's a major functionality newly implemented. Otherwise, update the existing docs. 
8. Keep the environment configuration centralized in the root folder and create separate files for dev and prod
9. 
