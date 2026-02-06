# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**For detailed development history and recent changes, see [UPDATE_CONTEXT.md](UPDATE_CONTEXT.md)**

## Quick Start

### Start the Application
```bash
# One-command startup (starts both backend and frontend)
./start-platform.bat    # Windows
./start-poc.sh          # macOS/Linux

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

---

## High-Level Architecture

### System Overview
Email processing platform with FastAPI backend and React frontend, supporting MBOX/PST/OLM/Gmail/Outlook formats with **mandatory Redis** for real-time progress tracking and Google Drive integration.

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
- **email_processor.py**: Main pipeline orchestrator in `src/processors/`
- **Extractors** (`src/extractors/`): Stream-based file processors for MBOX/PST/OLM/Gmail
- **email_tagger.py**: Rule-based tagging engine (20+ tags) in `src/processors/`
- **Redis Managers**: JobProgressManager and JobQueueManager for real-time updates
- **Routers** (`src/routers/`): Business hierarchy and API endpoints
- **Auth** (`src/dependencies/auth.py`): Supabase JWT verification with ES256/HS256 support

#### Frontend (React/TypeScript)
- **Pages**: dashboard, mailboxes, emails, processing, clients, users (in `frontend/src/pages/`)
- **Auth**: Supabase Auth with Google/Microsoft OAuth + email/password
- **Components**: MailboxSelector, ProtectedRoute, Layout with role-based access
- **Services**: API integration layer (`frontend/src/services/`)
- **Auto-refresh**: Polls job status every 2-5 seconds

#### Data Layer
- **Supabase PostgreSQL**: Primary data storage with Row-Level Security (RLS)
- **Redis (REQUIRED)**: Progress cache and job queue management
- **Tables**: emails, processing_jobs, mailboxes, folders, user_profiles, user_client_assignments, clients, customer_companies, customer_contacts

---

## Important Implementation Details

### Authentication & Authorization
- **Supabase Auth**: Email/password, Google OAuth, Microsoft OAuth
- **3 User Roles**:
  - **Admin**: Access to all mailboxes, user management
  - **Client Manager**: Access to mailboxes of assigned clients
  - **Account Manager**: Access to own mailboxes only
- **JWT Verification**: Backend supports ES256/RS256 (JWKS) and HS256 (shared secret)
- **RLS Policies**: Row-level security enforces access control at database level

### Route-Based Navigation (Feb 2026)
- **Emails Page**: `/emails/:mailboxId` - Each mailbox has its own URL
- **Processing Page**: `/processing/:mailboxId` - Filter jobs by mailbox
- **Benefits**: Deep linking, browser back/forward, instant skeleton feedback
- **Pattern**: URL as source of truth → Optimistic UI updates → Load fresh data

### Google Drive Integration
- Frontend authenticates with Google OAuth2
- **Unified Streaming Architecture**:
  - **OLM Files**: RemoteZip streaming for large archives (65GB+)
  - **MBOX Files**: Text streaming with line-by-line processing
  - No full download required - processes on-the-fly
  - Cancellable during processing
- Supports MBOX, PST, OLM files in Drive

### Gmail & Outlook LIVE Sync
- **Per-Mailbox Architecture**: Each mailbox stores its own OAuth tokens
- Gmail: OAuth2 with incremental sync using historyId
- Background sync service with configurable interval
- Tokens stored in `mailboxes.connection_config` JSONB

### Redis as Primary Job System
- No longer optional - application requires Redis
- Updates on every email processed
- Database sync every 100 emails
- TTL configurable via REDIS_TTL_DAYS

---

## Environment Configuration

### Backend Environment (`backend/.env.development` or `backend/.env.production`)
```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_role_key
SUPABASE_JWT_SECRET=your_jwt_secret

# Redis Configuration (REQUIRED)
REDIS_URL=redis://localhost:6379  # Development
REDIS_URL=${Redis.REDIS_URL}       # Production (Railway)
REDIS_TTL_DAYS=7

# Google Drive & Gmail API
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
SECRET_KEY=your_secret_key
```

### Frontend Environment (`frontend/.env.development` or `frontend/.env.production`)
```bash
# API Configuration
VITE_API_BASE_URL=http://localhost:8000/api  # Development
VITE_API_BASE_URL=https://${{backend.RAILWAY_PRIVATE_DOMAIN}}/api  # Production

# Supabase Authentication
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_key

# Google Drive & Gmail
VITE_GOOGLE_CLIENT_ID=your_google_client_id
VITE_GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
```

**Note**: Example files are provided as `.env.example` in each directory. Environment files are ignored by git for security.

---

## File Structure

### Key Directories
- **backend/src/**: Python backend source code
  - **extractors/**: Email file processors (MBOX, PST, OLM, Gmail, Outlook)
  - **processors/**: Email processing pipeline (normalizer, tagger)
  - **routers/**: FastAPI route handlers
  - **services/**: Background services (Gmail sync, etc.)
  - **dependencies/**: FastAPI dependencies (auth, etc.)
  - **storage/**: Cloud storage streaming (Google Drive)
- **frontend/src/**: React frontend source code
  - **pages/**: Main application pages
  - **components/**: Reusable React components
  - **services/**: API integration layer
  - **contexts/**: React contexts (AuthContext, etc.)
  - **lib/**: Third-party library initialization (Supabase)
- **docs/**: Documentation
  - **UPDATE_CONTEXT.md**: Comprehensive development history
  - **CHANGELOG.md**: User-facing release notes
  - **TODO.md**: Active task tracking
  - **CLAUDE.md**: This file
- **scripts/**: Utility scripts
  - **migrations/**: Database migration scripts
  - **troubleshooting/**: Diagnostic and fix scripts

---

## Development Best Practices

### Critical Rules

1. **Port Management**:
   - Backend MUST run on port 8000
   - Frontend MUST run on port 3000
   - Check and kill old processes before starting services
   - Never use alternative ports (3001, 8001, etc.)

2. **Documentation**:
   - Create docs ONLY in `docs/` folder
   - Update existing docs instead of creating new ones
   - Reference UPDATE_CONTEXT.md for historical changes

3. **Database Changes**:
   - Update original migration scripts when fixing issues
   - Don't keep fix scripts in main codebase
   - Use `scripts/migrations/` for new migrations
   - Use `scripts/troubleshooting/` for diagnostic scripts

4. **Git Workflow**:
   - Commit to main branch for major changes
   - Include descriptive commit messages
   - Co-author commits: `Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>`

5. **Frontend Service Pattern**:
   - All frontend API services MUST use centralized `apiClient.ts`
   - Use `silentOnNetworkError: true` for polling requests
   - Implement proper timeout and retry logic

6. **Thread Management** (Python):
   - Cannot change thread daemon status after starting
   - Don't use custom ThreadPoolExecutor with daemon threads
   - Use standard ThreadPoolExecutor + proper cancellation

7. **Job Status Handling**:
   - Always include all active statuses: `pending`, `running`, `downloading`
   - Check for active jobs in both frontend and backend

8. **Railway SQL Migrations**:
   - Split large migrations for 10M+ row tables
   - Cannot use `CREATE INDEX CONCURRENTLY` in Railway SQL runner
   - Keep migration files under 5-minute execution time

9. **Environment Configuration**:
   - Keep environment files centralized in service directories
   - Separate files for dev and prod (`*.env.development`, `*.env.production`)
   - Never hardcode paths or credentials

10. **Code Paths**:
    - Don't hardcode paths specific to local machines
    - Ensure pipeline consistency across all mailbox types
    - Use environment variables for configurable paths

### UX Patterns (Feb 2026)

When adding new filters/views:
1. Clear old data immediately (setData([]), setCount(0))
2. Set loading=true
3. Update filters/navigate to new URL
4. Let effects handle data loading
5. Ensure skeleton displays during loading

When adding new routes:
- Use route params for primary filters (mailbox, job, client)
- Use query params for secondary filters (date range, status)
- Always sync URL with component state
- Handle direct URL access (page refresh)

---

## Current Development Focus

**Sprint 1: Foundation (In Progress)**
- ✅ Account Manager & Client Hierarchy
- ✅ Role-Based Access Control with Supabase Auth
- ✅ Gmail OAuth Integration (Per-Mailbox)
- ✅ Mailbox Switching & Filtering UX
- ⏳ Outlook OAuth Integration (Next)

See [UPDATE_CONTEXT.md](UPDATE_CONTEXT.md) for detailed progress and [TODO.md](TODO.md) for active task list.

---

## Environment Notes

- **Platform**: Windows 11
- **Python**: 3.13
- **Node**: Latest LTS
- **Backend Port**: 8000
- **Frontend Port**: 3000
- **Redis**: Required for job tracking
- **Database**: Supabase PostgreSQL
- **Production**: Railway deployment