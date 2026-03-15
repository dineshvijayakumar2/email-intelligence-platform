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
cd frontend && npm start             # Frontend (port 3001)
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
- **Analytics Router** (`src/routers/analytics.py`): 30 REST endpoints for extraction and analytics
- **Extraction Services** (`src/services/`): 8 specialized services for 13-step pipeline
- **Auth** (`src/dependencies/auth.py`): Supabase JWT verification with ES256/HS256 support

#### Frontend (React/TypeScript)
- **Pages**: dashboard, mailboxes, emails, processing, clients, users, analytics (6 pages), admin data view
- **Auth**: Supabase Auth with Google/Microsoft OAuth + email/password
- **Components**: MailboxSelector, ProtectedRoute, Layout with role-based access, AnalyticsTable, EngagementBadge, ChartCard, MetricCard, ClientSelector
- **Services**: API integration layer (`frontend/src/services/`) including analyticsService (30 endpoint wrappers with caching + deduplication)
- **Auto-refresh**: Polls job status every 2-5 seconds

#### Data Layer
- **Supabase PostgreSQL**: Primary data storage with Row-Level Security (RLS)
- **Redis (REQUIRED)**: Progress cache and job queue management
- **Core Tables**: emails, processing_jobs, mailboxes, folders, user_profiles, user_client_assignments, clients
- **Sprint 2 Tables**: customer_companies, customer_contacts, extraction_jobs, email_response_metrics, thread_status, unified_email_rules, internal_domains, free_email_providers
- **Sprint 3 Tables**: ai_email_intelligence, ai_usage_log, ai_daily_digests, business_entities, qb_sync_config, qb_customers, qb_contacts, qb_quotes, qb_jobs, qb_sales_line_items, relationship_context_cache, ai_strategic_digests, am_performance_snapshots
- **Database Schema**: v1.8+ (12 Sprint 2 + 5 Sprint 3 migrations)

---

## Important Implementation Details

### Authentication & Authorization
- **Supabase Auth**: Email/password, Google OAuth, Microsoft OAuth
- **3 User Roles**:
  - **Admin**: Access to all mailboxes, user management, invite users
  - **Client Manager**: Access to mailboxes of assigned clients, invite users
  - **Account Manager**: Access to own mailboxes only
- **JWT Verification**: Backend supports ES256/RS256 (JWKS) and HS256 (shared secret)
- **RLS Policies**: Row-level security enforces access control at database level
- **User Onboarding**: Invite-only (no open sign-up). See `docs/INVITE_USER_SMTPLESS.md` for design.
  - Admin creates invite → assigns role + client
  - User accepts via magic link, shared link, or direct OAuth login
  - On acceptance: user_profiles created, client assigned, mailbox auto-created (inactive)
  - Dashboard prompts new user to authorize Gmail/Outlook OAuth to activate mailbox
  - **Status:** Planned — implementation pending

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
- Outlook: OAuth2 with delta sync using deltaLink
- Background sync service with configurable interval
- Tokens stored in `mailboxes.connection_config` JSONB
- **Email Address Guardrails**: Auto-populated from OAuth, read-only in forms, backend-validated
- **MBOX/OLM + LIVE Sync**: File-based mailboxes can link live Gmail/Outlook for ongoing sync
- `last_sync_at` updated on both `connection_config` (nested) and `mailboxes` table (top-level)

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
GOOGLE_REDIRECT_URI=http://localhost:3001/auth/google/callback

# Microsoft Azure API
MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret

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
VITE_GOOGLE_REDIRECT_URI=http://localhost:3001/auth/google/callback

# Microsoft Azure
VITE_MICROSOFT_CLIENT_ID=your_microsoft_client_id
VITE_MICROSOFT_REDIRECT_URI=http://localhost:3001/auth/microsoft/callback
```

**Note**: Example files are provided as `.env.example` in each directory. Environment files are ignored by git for security.

---

## File Structure

### Key Directories
- **backend/src/**: Python backend source code
  - **extractors/**: Email file processors (MBOX, PST, OLM, Gmail, Outlook)
  - **processors/**: Email processing pipeline (normalizer, tagger)
  - **routers/**: FastAPI route handlers (including analytics.py with 30 endpoints)
  - **services/**: Extraction pipeline services (8 services) + background sync services
  - **models/**: Pydantic models (analytics.py with 41 models + 5 enums)
  - **utils/**: Domain parser, name parser, title parser
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
  - **AI_MVP_PLAN.md**: Sprint 3 AI MVP plan (final)
  - **INVITE_USER_SMTPLESS.md**: Invite user system design (SMTP-less)
- **scripts/**: Utility scripts
  - **migrations/**: Stage 1 database migration scripts
  - **sprint2/**: Sprint 2 migrations (001-012) + master schema v1.8+
  - **troubleshooting/**: Diagnostic and fix scripts

---

## Development Best Practices

### Critical Rules

1. **Port Management**:
   - Backend MUST run on port 8000
   - Frontend MUST run on port 3001 (changed from 3000 in Feb 2026)
   - Check and kill old processes before starting services
   - CORS ALLOWED_ORIGINS and OAuth redirect URIs must match frontend port

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
   - Co-author commits: `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`

5. **Frontend Service Pattern**:
   - All frontend API services MUST use centralized `apiClient.ts`
   - Use `silentOnNetworkError: true` for polling requests
   - apiClient has built-in retry (2 retries, 300ms delay) — do NOT add nested retries in service layers
   - Use in-flight deduplication pattern (shared Promise) to prevent duplicate API calls
   - Default timeout: 15s (apiClient), 10s (mailboxService), 15s (dashboardService), 30s (rulesService analytics)
   - Use `Promise.all()` for independent parallel API calls — never fire-and-forget multiple async calls
   - Analytics pages should be read-only on load (DB only) — external API calls (Gmail/Outlook) only on manual user action

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

**Sprint 1: Foundation** - ✅ **COMPLETE**
- ✅ Account Manager & Client Hierarchy
- ✅ Role-Based Access Control with Supabase Auth
- ✅ Gmail OAuth Integration (Per-Mailbox)
- ✅ Outlook OAuth Integration
- ✅ Mailbox Switching & Filtering UX

**Sprint 2: Customer Data Extraction** - ✅ **COMPLETE** (Backend + Frontend + Production)
- ✅ Phase 1-4: Core extraction pipeline (13 steps) with engagement analytics
- ✅ Phase 5A: Analytics API (30 REST endpoints - all tested)
- ✅ Phase 5B: Incremental extraction mode (Migration 010)
- ✅ Phase 6: Production deployment with 5 critical fixes
- ✅ **Production verified:** 26,654 emails across 54 pages processed successfully
- ✅ **Stability Fixes**: Performance, WebSocket, email guardrails, pagination, NULL handling, retry
- ✅ **Analytics Frontend**: 6 pages (dashboard, contacts, companies, threads, contact-detail, company-detail) with sorting, filtering, engagement badges
- ✅ **Admin Data View**: Raw table browser with search, sort, pagination, CSV export
- ✅ **Post-Production Fixes** (Feb 26-27): Scoring accuracy, slider UX, label clarity, backfill migrations 011-012

### Sprint 2 Backend Architecture

**13-Step Extraction Pipeline** (`backend/src/services/extraction_orchestrator.py`):
```
Validate → Extract Contacts → Deduplicate → Resolve Companies
→ Upsert Contacts → Upsert Companies → Classify Roles → Update Roles
→ Link Emails → Calculate Engagement → Track Threads → Analyze Patterns → Complete
```

**8 Backend Services:**
- `contact_extractor.py` — Email address extraction + deduplication + type classification
- `company_resolver.py` — Domain → company grouping with free provider handling
- `role_classifier.py` — Job title → seniority + functional role + decision-maker flag
- `email_linker.py` — Batch FK backfill (emails → contacts/companies), 100% link rate
- `engagement_scorer.py` — 8-factor scoring (0-100 scale)
- `response_time_tracker.py` — Response time calculations with auto-reply detection
- `thread_tracker.py` — Thread status evaluation (6 states)
- `comm_pattern_analyzer.py` — Initiation ratio, reply rate, frequency trends

**30 Analytics API Endpoints** at `/api/v1/analytics/`:
- Extraction Control (5) | Contact Analytics (6) | Company Analytics (5)
- Thread Analytics (4) | Response Times (4) | Comm Patterns (4) | Dashboard (2)

**Critical Production Patterns:**
1. Python-side filtering for NULL handling (NOT Supabase `.neq()`)
2. `len(batch) == 0` break condition (NOT `< PAGE_SIZE`)
3. `_execute_with_retry()` for transient Supabase/SSL errors
4. Lowercase strings `'true'`/`'false'` for Supabase boolean filters
5. Batch limits: 100/update, 500/`.in_()` filter
6. Cast float params to `int()` before Supabase `.gte()` on INTEGER columns
7. Ant Design v5 Slider: use `onChangeComplete` for API triggers, `onChange` only for visual state
8. `nullsfirst=False` in Supabase `.order()` to push NULLs to end in DESC sort
9. Column `has_response_urgency` replaces `has_buying_signal` for AM-centric signals
10. `json_repair` library for fixing malformed LLM JSON responses
11. ThreadPoolExecutor limited to 3 workers for Supabase connection safety
12. ZoneInfo requires `tzdata` package on containers without system timezone data

### Upcoming: Invite User System (Planned)

Restrict open sign-up — admin-controlled user onboarding via invite system.
- **Design doc:** `docs/INVITE_USER_SMTPLESS.md`
- **Key features:** 3-path invite flow (magic link, shared link, direct OAuth), auto-mailbox creation on acceptance, dashboard connection prompt
- **Backend:** `invites.py` router (6 endpoints), `pending_invites` table, migration 014
- **Frontend:** InviteUserModal, InviteAcceptPage, Users page integration, login page sign-up removal

### Sprint 3: AI Semantic Intelligence — ✅ COMPLETE (March 15, 2026)

**Three-Layer Architecture:**
1. **Per-Email AI** (Claude Haiku, ~$0.001/email) — classify + extract entities + justify in ONE API call
2. **Action Signal Engine** (pure Python, $0) — 6 AM-centric signals: response_urgency, deal_at_risk, retention_risk, revenue_opportunity, new_relationship, account_neglect
3. **Strategic Digest** (LangChain/LangGraph) — ReAct agent with company/contact/thread/quote lookup tools

**What's Built (Sprint 3 Complete):**
- 15 backend services: `ai_client.py`, `ai_privacy_filter.py`, `ai_usage_tracker.py`, `ai_email_analyzer.py`, `ai_action_bucket_engine.py` (v3), `ai_entity_aggregator.py`, `ai_digest_generator.py`, `ai_insights_engine.py`, `quickbase_client.py`, `quickbase_sync.py`, `langchain_core.py`, `langchain_tools.py`, `strategic_context_builder.py`, `strategic_digest_pipeline.py`, `am_efficiency_analyzer.py`
- 25+ API endpoints in `ai.py` + 6 in `quickbase.py` + 5 in `rules.py`
- 5 frontend pages: Smart Inbox, Daily Digest, Opportunities, Usage, Strategic Digest
- 4 shared components: `ActionBucketTag`, `FeedbackButtons`, `LifecycleBadge`, `AIInsightsCard`
- Frontend services: `aiService.ts`, `strategicDigestService.ts`, `rulesService.ts`
- Types: `ai.ts` (6 AM signals + lifecycle tiers), `strategic-digest.ts`
- Multi-model AI: Claude Haiku/Sonnet + Gemini 2.0 Flash (free tier)
- QuickBase integration: 5-table sync, 4-tier company matching, data propagation
- Customer lifecycle tiers: prospect, new_customer, active_customer, at_risk, dormant, champion
- AM efficiency: business-hours response times, quote conversion, revenue attribution
- Migrations: 021 (9 QB tables), 021a (enrichment columns), 026 (AM lifecycle rehaul)

**Sprint 4: Power Mode — PLANNED**
- Deal Radar, Ghost Writer, Heatmap, War Room, Alerts, Scoreboard, Executive Report
- Plan doc: `docs/SPRINT3_4_IMPLEMENTATION_PLAN.md`

See [TODO.md](TODO.md) for task list, [CONTINUATION_GUIDE.md](CONTINUATION_GUIDE.md) for handoff.

---

## Environment Notes

- **Platform**: Windows 11
- **Python**: 3.13
- **Node**: Latest LTS
- **Backend Port**: 8000
- **Frontend Port**: 3001
- **Redis**: Required for job tracking
- **Database**: Supabase PostgreSQL
- **Production**: Railway deployment