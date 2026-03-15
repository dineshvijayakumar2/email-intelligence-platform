# Email Intelligence Platform

**Advanced Email Analysis Platform with AI Enrichment & Cloud Integration**

A comprehensive email intelligence platform for processing, analyzing, and extracting insights from business email archives with support for multiple formats, cloud storage, and automated tagging.

---

## Project Status

### Stage 1: Complete - Email Extraction & Rule-Based Tagging
**Status**: Production-ready deployment (January 14, 2026)

**Delivered Capabilities**:
- Multi-format email extraction (MBOX, PST, OLM) with Google Drive streaming
- Rule-based tagging system (20+ tags: spam, marketing, system, automated, etc.)
- Real-time processing with Redis progress tracking
- Modern React UI with email preview and filtering
- Production deployment on Railway with Supabase database
- Google Drive OAuth2 integration for seamless file access

### Stage 2: Complete - Business Intelligence Layer
**Status**: Sprint 1 & Sprint 2 FULLY COMPLETE (February 26, 2026)

**Sprint 1 - Foundation (Weeks 1-3)** - **COMPLETE**:
- Account Manager & Client Hierarchy (Production Deployed)
- Role-Based Access Control with Supabase Auth (Production Deployed)
- Gmail LIVE Sync Integration (Production Deployed)
- Outlook LIVE Sync Integration (Production Deployed)
- Date Range Processing (Gmail & Outlook)

**Sprint 2 - Customer Data Extraction (Weeks 4-6)** - **COMPLETE**:
- 13-step extraction pipeline processing 26,000+ emails
- Contact database with auto-extraction, deduplication, role classification
- Company resolution with domain grouping and engagement scoring
- Email linking with 100% link rate across all contacts
- Engagement analytics (response times, thread tracking, communication patterns)
- 8-factor engagement scoring (0-100 scale)
- 30 REST API analytics endpoints (all tested)
- Incremental extraction mode (full + incremental with configurable lookback)
- Production-grade pagination, retry logic, and batch processing
- Analytics Frontend: 6 pages (Dashboard, Contacts, Companies, Threads, Response Times, Email Rules)
- Analytics UX: Cross-page drilldown (threads→emails, contacts→emails/threads, companies→all), period selector, search, column filters
- Threading overhaul: Multi-priority thread ID (provider→headers→heuristic), confidence scoring
- Navigation: 5 top-level items (Dashboard, Emails, Intelligence, Analytics, Manage)

### Stage 3: Complete - AI Semantic Intelligence
**Status**: Sprint 3 COMPLETE including AM-centric rehaul (March 15, 2026)

**Sprint 3 - AI Layer + QB Integration + AM Rehaul (COMPLETE)**:
- Three-layer AI architecture: Per-Email AI → AM Signal Engine → Strategic Digest
- Claude API (Haiku/Sonnet) + LangChain/LangGraph + Gemini 2.0 Flash (free tier)
- 6 AM-centric action signals: response_urgency, deal_at_risk, retention_risk, revenue_opportunity, new_relationship, account_neglect
- Customer lifecycle tiers: prospect, new_customer, active_customer, at_risk, dormant, champion
- QuickBase CRM integration (5-table sync, 4-tier company matching, data propagation)
- AM efficiency analyzer (business-hours response times, quote conversion, revenue attribution)
- Strategic digest: LangGraph ReAct agent with 8-section executive output
- Multi-axis email classification (intent, action_type, business_signal, sentiment, urgency)
- Entity extraction (competitors, products, amounts, dates)
- Email rules engine (auto-tag, auto-forward, priority escalation)
- 25+ AI API endpoints + 6 QB endpoints + 5 rules endpoints
- AI Usage & Cost monitoring dashboard

**Sprint 3 - Frontend (COMPLETE)**:
- Smart Inbox with AI annotations, column filters/sorting, Re-bucket button
- Strategic Digest page with 8-section AM-centric analysis
- Daily Digest page with AI-generated summaries
- Opportunities page (4 tabs: Action Items, Opportunities, Competitors, Entities)
- Usage & Monitoring dashboard (cost tracking, model usage, processing stats)
- Lifecycle badges on company/contact list and detail pages

**Analytics UX Overhaul (COMPLETE)**:
- Cross-page drilldown: thread→emails, contact→emails/threads, company→all pages
- Dashboard period selector (7d/30d/90d/6m/1y) with client-scoped queries
- Search on companies and threads pages (server-side)
- Clickable counts everywhere (emails, contacts, decision makers, threads)
- ClientSelector: module-level cache for instant page loads

---

## Stage 1 Features (Completed)

### Email Processing Pipeline
- **Multi-Format Support**: MBOX, PST, OLM archives
- **Streaming Architecture**: Process large files (65GB+) without downloading
- **Google Drive Integration**: OAuth2 authentication with automatic token refresh
- **Real-time Progress**: Redis-backed job tracking with ETA calculations
- **Concurrent Processing**: ThreadPool executor with 20 workers
- **Cancellable Jobs**: Stop processing at any time
- **Parallel Download**: Optional multi-threaded download for large files (5GB+)

### Rule-Based Tagging System
**20+ Automated Tags**:
- **Direction**: `inbound`, `outbound`
- **Thread Type**: `new_thread`, `reply`, `forward`
- **Classification**: `spam`, `marketing`, `system`, `automated`
- **Sender Type**: `sender_human`, `sender_marketing`, `sender_system`
- **Priority**: `high_priority`, `low_priority`, `urgent`
- **Content**: `has_attachments`, `financial`, `meeting`, `newsletter`
- **Social**: `social_notification`, `account_action`, `ecommerce`

### Modern Web Interface
- **Responsive Dashboard**: Real-time metrics and processing status
- **Email Browser**: Filter by tags, folders, mailboxes, dates
- **Email Preview Modal**: Two-column layout with metadata and content
- **Mailbox Management**: Create, edit, process email sources
- **Google Drive Picker**: Browse and select files from Drive
- **Job Monitoring**: Live progress with speed and ETA
- **Connection Status**: Auto-detect backend disconnection and reconnect

### Sprint 2: Customer Data Extraction Pipeline (Stage 2)

The 13-step extraction pipeline automatically processes all emails in a mailbox to build a complete customer intelligence database:

| Step | Service | Description | Performance |
|------|---------|-------------|-------------|
| 1 | Orchestrator | Validate mailbox, load configs, determine email scope | <1s |
| 2 | ContactExtractor | Scan all emails, extract unique addresses + display names | Paginated (500/batch) |
| 3 | ContactExtractor | Deduplicate contacts, classify types (person/automated/shared/mailing_list) | Tag-instead-of-filter |
| 4 | CompanyResolver | Group contacts by domain, resolve company names | Domain classification |
| 5 | CompanyResolver | Upsert customer_companies with email_domains JSONB | Batch upsert |
| 6 | ContactExtractor | Upsert customer_contacts, link to companies, parse names | Batch upsert |
| 7 | RoleClassifier | Parse job titles into seniority + functional role + decision-maker flag | Pattern matching |
| 8 | RoleClassifier | Update contacts with classified roles | Batch update |
| 9 | EmailLinker | Link emails to contacts and companies (set foreign keys) | Chunked batches (100/batch) |
| 10 | EngagementScorer | Calculate 8-factor engagement scores (0-100 scale) | Database-side RPC |
| 11 | ResponseTimeTracker + ThreadTracker | Compute response times, evaluate thread status | Database-side calculations |
| 12 | CommunicationPatternAnalyzer | Calculate initiation ratio, reply rate, frequency trends | 3 RPC calls (~250x faster) |
| 13 | StatsUpdater | Update company aggregate stats, mark job complete | Batch RPC |

**Production Stats:**
- Processes 26,000+ emails across 54 pages reliably
- 100% email link rate maintained
- Full extraction: ~1.5 minutes | Incremental (7-day): ~15-30 seconds
- Batch operations: 25x faster than individual requests
- Database-side calculations: ~250x faster than client-side

**30 Analytics API Endpoints** at `/api/v1/analytics/`:
- Extraction Control (5): run, job status, job list, cancel, real-time progress
- Contact Analytics (6): list, detail, top-engaged, at-risk, decision-makers, by-type
- Company Analytics (5): list, detail, top-engaged, at-risk, by-engagement
- Thread Analytics (4): status, overdue, by-status, by-contact
- Response Times (4): list, stats, slowest, by-contact
- Communication Patterns (4): initiation, frequency, trends, by-contact
- Dashboard (2): full dashboard summary, client summary

### Gmail LIVE Sync (Stage 2)
- **OAuth2 Authentication**: Google consent screen with proper scopes
- **Automatic Sync**: Background service syncs new emails every 15 minutes (configurable 1-1440 min)
- **Incremental Sync**: Uses Gmail historyId to fetch only new emails
- **Mailbox Linking**: Link existing archive mailboxes to Gmail for continuous updates
- **Frontend Controls**: Connect/disconnect, sync now, configure interval
- **Date Range Fetch**: Pull historical emails from specific date ranges on-demand
- **Persistent Config**: Sync settings stored in database, changes apply immediately

### Outlook LIVE Sync (Stage 2)
- **OAuth2 Authentication**: Azure AD with support for O365 and personal Microsoft accounts
- **Microsoft Graph API**: Full access to Outlook emails with HTML content preservation
- **Automatic Sync**: Background service syncs new emails (configurable interval)
- **Mailbox Linking**: Link archive mailboxes to Outlook for continuous updates
- **Frontend Controls**: Connect/disconnect, sync now, fetch date range
- **Date Range Fetch**: Pull historical emails from specific date ranges on-demand
- **Token Management**: Automatic refresh with secure storage in Supabase

### Role-Based Access Control (Stage 2)
- **Supabase Authentication**: Google OAuth, Microsoft OAuth, email/password login
- **3 User Roles**:
  - **Admin**: Full access to all mailboxes and user management
  - **Client Manager**: Access to assigned client mailboxes only
  - **Account Manager**: Access to own mailboxes only
- **Row Level Security**: Database-level access control with RLS policies
- **User Management**: Admin interface for role assignment and client assignments
- **Protected Routes**: Frontend route guards based on user role
- **JWT Verification**: ES256 (JWKS) and HS256 token support with automatic fallback

### Error Tracking & Monitoring (Stage 2)
- **Dedicated Errors Page**: View and manage processing errors by job
- **Error Analysis**: Categorization (timeout, duplicate, constraint violation)
- **Batch Error Logs**: View raw error logs from processing jobs
- **Failed Message Tracking**: Track and retry failed email imports
- **Job-level Filtering**: Filter errors by phase and type

### Performance Optimizations
- **Download Before Processing**: Multi-threaded parallel download for large files (5GB+)
- **Dashboard Query Optimization**: PostgreSQL functions for faster aggregations
- **Performance Indexes**: Optimized indexes for common query patterns
- **Date-based Filtering**: Filter emails by date range in UI

### Production Infrastructure
- **Railway Deployment**: Auto-scaling backend
- **Supabase Database**: PostgreSQL with RLS and functions
- **Redis Caching**: Job progress and queue management
- **Environment Management**: Separate dev/prod configurations
- **Error Handling**: Retry logic, graceful failures, logging

---

## Stage 2 Plan: Business Intelligence Layer

### Sprint 1: Foundation
**Goal**: Establish secure multi-tenant infrastructure with OAuth-based email synchronization

| Epic | Description | Status |
|------|-------------|--------|
| Account Manager & Client Hierarchy | Admin creates AMs, assigns clients, tenant isolation | **Complete** |
| Role-Based Access Control | Admin, Client Manager, Account Manager roles with RLS and Supabase Auth | **Complete** |
| Gmail LIVE Sync | Connect Gmail via OAuth, automatic sync every 15 min (configurable), link to mailboxes | **Complete** |
| Outlook LIVE Sync | Connect Outlook/O365 via Azure AD OAuth, automatic sync, link to mailboxes | **Complete** |
| Date Range Processing | Fetch historical emails by date range from Gmail & Outlook | **Complete** |

### Sprint 2: Customer Data Extraction
**Goal**: Automatic customer recognition, contact database, engagement analytics
**Status**: **COMPLETE** (February 26, 2026)

| Epic | Description | Status |
|------|-------------|--------|
| 13-Step Extraction Pipeline | Validate, extract contacts, resolve companies, classify roles, link emails, score engagement | **Complete** |
| Contact Database | Auto-extract from headers, parse names, classify contact types, deduplicate | **Complete** |
| Company Resolution | Domain grouping, free provider handling, email_domains JSONB | **Complete** |
| Role Classification | Title parsing into seniority + functional role + decision-maker flag | **Complete** |
| Email Linking | Batch link emails to contacts/companies with 100% link rate | **Complete** |
| Engagement Analytics | Response times, thread tracking, communication patterns, 8-factor scoring | **Complete** |
| Analytics API | 30 REST endpoints across 7 categories (extraction, contacts, companies, threads, etc.) | **Complete** |
| Incremental Extraction | Full + incremental modes with configurable lookback (1-365 days) | **Complete** |
| Production Fixes | Pagination (26K+ emails), NULL handling, retry logic, batch processing | **Complete** |
| Analytics Frontend | 6 pages: Dashboard, Contacts, Companies, Threads, Errors, Email Rules | **Complete** |

### Sprint 3: AI Semantic Intelligence
**Goal**: AI-powered semantic analysis, intent classification, and proactive relationship intelligence
**Status**: **Week 1 + Frontend COMPLETE** (March 3, 2026)

| Session | Description | Status |
|---------|-------------|--------|
| 1-2 | AI Client + Privacy Filter + Usage Tracker + DB Schema | **Complete** |
| 3 | Per-Email AI Analyzer (multi-axis classification, entity extraction) | **Complete** |
| 4 | Action Signal Engine (6 AM-centric signals, v3) | **Complete** |
| 5 | Entity Aggregator + Daily Digest Generator | **Complete** |
| 6 | Email Rules Engine (auto-tag, auto-forward, priority escalation) | **Complete** |
| 6b | Frontend: Smart Inbox, Digest, Opportunities, Usage pages | **Complete** |
| 7-19 | QB Integration + LangChain Strategic Digest + AM Rehaul | **Complete** |

**AI Architecture**: Three-layer design — Per-Email AI (Claude Haiku ~$0.001/email) → Action Bucket Engine (pure Python) → Aggregation Layer (pure Python). Admin usage tracking with cost control.

---

## Quick Start

### Prerequisites
- Python 3.8+ with pip
- Node.js 16+ with npm
- Redis Server (required)
- Supabase Account

### 1. Clone & Setup
```bash
git clone <repository-url>
cd email-intelligence-platform

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install
```

### 2. Environment Configuration
Create `.env.development` in backend and frontend directories:

**Backend (`backend/.env.development`)**:
```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_role_key
SUPABASE_JWT_SECRET=your_jwt_secret  # For RBAC token verification
REDIS_URL=redis://localhost:6379
REDIS_TTL_DAYS=7
# Google OAuth (Gmail LIVE + Google Drive)
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
# Microsoft OAuth (Outlook LIVE)
MICROSOFT_CLIENT_ID=your-azure-app-client-id
MICROSOFT_CLIENT_SECRET=your-azure-client-secret
MICROSOFT_TENANT_ID=common
API_HOST=0.0.0.0
API_PORT=8000
```

**Frontend (`frontend/.env.development`)**:
```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_SUPABASE_URL=https://xxx.supabase.co  # For RBAC authentication
VITE_SUPABASE_ANON_KEY=your_anon_key  # For RBAC authentication
VITE_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
VITE_MICROSOFT_CLIENT_ID=your-azure-app-client-id
VITE_MICROSOFT_REDIRECT_URI=http://localhost:3000/auth/microsoft/callback
```

### 3. Database Setup
Run in Supabase SQL Editor:

**Stage 1 Migrations:**
1. `scripts/create_tables.sql` (main schema)
2. `scripts/migrations/001a_add_error_columns.sql`
3. `scripts/migrations/001b_add_error_functions.sql`
4. `scripts/migrations/001c_add_error_indexes.sql`
5. `scripts/migrations/002_add_business_hierarchy.sql`
6. `scripts/migrations/010_create_user_profiles.sql` (RBAC with Supabase Auth)

**Sprint 2 Migrations (run in order):**
7. `scripts/sprint2/sprint2_migration_001_supporting_tables.sql`
8. `scripts/sprint2/sprint2_migration_002_unified_email_rules.sql`
9. `scripts/sprint2/sprint2_migration_003_unique_constraints.sql`
10. `scripts/sprint2/sprint2_migration_004_contact_classification.sql`
11. `scripts/sprint2/sprint2_migration_005_fix_analytics_tables.sql`
12. `scripts/sprint2/sprint2_migration_006_analytics_batch_ops.sql`
13. `scripts/sprint2/sprint2_migration_008_fix_thread_status.sql` (run BEFORE 007)
14. `scripts/sprint2/sprint2_migration_007_analytics_calculations.sql`
15. `scripts/sprint2/sprint2_migration_009_comm_pattern_calcs.sql`
16. `scripts/sprint2/sprint2_migration_010_incremental_mode.sql`

**Sprint 3 Migrations (AI + QB + AM):**
17. `scripts/sprint3/sprint3_migration_013_ai_layer.sql` (AI tables + enums + indexes)
18. `scripts/sprint3/sprint3_migration_014_add_skipped_status.sql` (skipped status for pre-filtered emails)
19. `scripts/sprint3/sprint3_migration_021_strategic_digest.sql` (9 QB + strategic tables)
20. `scripts/migrations/021a_add_qb_enrichment_columns.sql` (QB enrichment on companies/contacts)
21. `scripts/migrations/026_am_lifecycle_rehaul.sql` (timezone, lifecycle tiers, has_response_urgency)

See `scripts/sprint2/README_MIGRATIONS.md` for detailed migration guide.

After running migrations, create initial admin user:
```sql
-- Create user profile for your Supabase auth user
INSERT INTO user_profiles (id, email, name, role, is_active)
SELECT
  id, email,
  COALESCE(raw_user_meta_data->>'full_name', split_part(email, '@', 1)),
  'admin',  -- Set as admin
  true
FROM auth.users
WHERE email = 'your-email@example.com'
ON CONFLICT (id) DO NOTHING;
```

### 4. Start Services
```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Backend (port 8000)
cd backend
python main.py

# Terminal 3: Frontend (port 3000)
cd frontend
npm run dev
```

### 5. Access Application
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## Documentation

- [Claude Code Instructions](docs/CLAUDE.md) - Development guidelines and best practices
- [Sprint 2 Implementation](docs/SPRINT2_IMPLEMENTATION.md) - Complete extraction pipeline guide
- [Sprint 3 AI MVP Plan](docs/AI_MVP_PLAN.md) - Full AI layer design (13 sessions, 3-layer architecture)
- [Sprint 3 Implementation Plan](docs/SPRINT3_IMPLEMENTATION_PLAN.md) - Sprint 3 session-by-session plan
- [Invite User System](docs/INVITE_USER_SMTPLESS.md) - Admin-controlled user onboarding (planned)
- [Sprint 2 Migrations](scripts/sprint2/README_MIGRATIONS.md) - Database migration guide (10 migrations)
- [Continuation Guide](docs/CONTINUATION_GUIDE.md) - Session handoff and next steps
- [Google OAuth Setup](docs/GOOGLE_OAUTH_SETUP.md) - Gmail LIVE sync and Google Drive setup
- [Azure AD OAuth Setup](docs/AZURE_OAUTH_SETUP.md) - Outlook LIVE sync and Microsoft login
- [Google Drive Integration](docs/GOOGLE_DRIVE_INTEGRATION.md) - OAuth setup and file access
- [Architecture Overview](docs/ARCHITECTURE.md) - System design and components
- [Email Tagging System](docs/EMAIL_TAGGING.md) - Rule-based classification
- [Deployment Guide](docs/DEPLOYMENT.md) - Production deployment steps

---

## Tech Stack

### Backend
- **Framework**: FastAPI 0.104+
- **Database**: Supabase (PostgreSQL) with 10 Sprint 2 + 5 Sprint 3 migrations
- **Authentication**: Supabase Auth + PyJWT
- **Cache**: Redis 7.0+
- **AI**: Claude API (Haiku/Sonnet) + LangChain/LangGraph + Gemini 2.0 Flash with PII filter + cost tracking
- **Business Data**: QuickBase API integration
- **Cloud Storage**: Google Drive API
- **Processing**: ThreadPoolExecutor (20 workers)
- **Extraction Pipeline**: 13-step orchestrator with 8 specialized services
- **Analytics**: 30 REST endpoints with pagination, filtering, and batch operations
- **AI Services**: 7 services (client, privacy filter, usage tracker, analyzer, bucket engine, aggregator, digest)
- **AI API**: 19 AI endpoints + 4 rules endpoints

### Frontend
- **Framework**: React 18 + TypeScript
- **UI Library**: Ant Design 5.x
- **Authentication**: @supabase/supabase-js
- **State Management**: React Context + Hooks
- **API Client**: Centralized apiClient with retry/timeout
- **Build Tool**: Vite

### Infrastructure
- **Hosting**: Railway (backend + Redis)
- **Database**: Supabase Cloud
- **Storage**: Google Drive (user files)
- **Monitoring**: Application logs + Redis metrics

---

## Troubleshooting

### Common Issues

#### Backend Won't Start
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG

# Check port 8000 is free
netstat -an | grep 8000
```

#### Frontend Connection Issues
The frontend will show a yellow banner when disconnected from backend. Wait for auto-reconnect or restart the backend.

#### Migration Timeout on Railway
Use the split migration files (001a, 001b, 001c) instead of the combined 001_add_error_handling.sql.

#### Email Count Shows 0
Run folder counts update:
```sql
SELECT update_folder_counts();
```

---

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

---

## License

MIT License - see LICENSE file for details

---

## Support

- **Documentation**: Check `/docs` folder
- **Issues**: GitHub Issues
- **API Docs**: http://localhost:8000/docs

---

**Stage 1 Complete | Stage 2 Complete | Stage 3 (AI + QB + AM Rehaul) Complete**

*Last Updated: March 15, 2026*

*Built with Python, TypeScript, React, Supabase Auth, Claude AI, Google Cloud APIs, and Microsoft Graph API*
