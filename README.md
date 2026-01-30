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

### Stage 2: In Progress - Business Intelligence Layer
**Status**: Sprint 1 In Progress (January 30, 2026)

**Sprint 1 - Foundation (Weeks 1-3)**:
- Account Manager & Client Hierarchy (Backend Complete)
- Role-Based Access Control (**Complete** - Migration Required)
- Gmail LIVE Sync Integration (**Complete**)
- Outlook OAuth Integration (Pending)
- Date Range Processing (Complete)

**Sprint 2 - Intelligence (Weeks 4-6)**:
- Customer Recognition System (domain/keyword rules)
- Rules Management Interface (visual rule builder)
- Contact Database (auto-extract from email headers)
- Email Signature Parsing
- Communication History

**Sprint 3 - AI Layer (Weeks 7-9)**:
- AI Email Classification (type, priority, sentiment)
- Business Entity Extraction (quote numbers, PO numbers, amounts)
- Manual Correction UI (trust building)
- Accuracy Testing & Metrics (85% target)

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

### Gmail LIVE Sync (Stage 2)
- **OAuth2 Authentication**: Google consent screen with proper scopes
- **Automatic Sync**: Background service syncs new emails every 15 minutes (configurable 1-1440 min)
- **Incremental Sync**: Uses Gmail historyId to fetch only new emails
- **Mailbox Linking**: Link existing archive mailboxes to Gmail for continuous updates
- **Frontend Controls**: Connect/disconnect, sync now, configure interval
- **Persistent Config**: Sync settings stored in database, changes apply immediately

### Role-Based Access Control (Stage 2)
- **Supabase Authentication**: Google OAuth, Microsoft OAuth, email/password login
- **3 User Roles**:
  - **Admin**: Full access to all mailboxes and user management
  - **Client Manager**: Access to assigned client mailboxes only
  - **Account Manager**: Access to own mailboxes only
- **Row Level Security**: Database-level access control with RLS policies
- **User Management**: Admin interface for role assignment and client assignments
- **Protected Routes**: Frontend route guards based on user role
- **JWT Verification**: Secure token-based authentication

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
| Account Manager & Client Hierarchy | Admin creates AMs, assigns clients, tenant isolation | Backend Complete |
| Role-Based Access Control | Admin, Client Manager, Account Manager roles with RLS and Supabase Auth | **Complete** |
| Gmail LIVE Sync | Connect Gmail via OAuth, automatic sync every 15 min (configurable), link to mailboxes | **Complete** |
| Outlook OAuth Integration | Connect Outlook, import rules, token refresh | Pending |
| Date Range Processing | Select date range for initial sync, re-process historical | Complete |

### Sprint 2: Intelligence
**Goal**: Automatic customer recognition and comprehensive contact database

| Epic | Description | Status |
|------|-------------|--------|
| Customer Recognition | Domain patterns, keyword rules, apply to historical emails | Pending |
| Rules Management | Form-based rule creation, priority ordering, test before apply | Pending |
| Contact Database | Auto-extract from headers, parse signatures, deduplicate | Pending |
| Communication History | Per-contact email timeline, company overview | Pending |
| Shared Inbox Handling | Detect info@, support@, don't treat as individuals | Pending |

### Sprint 3: AI Layer
**Goal**: AI-powered email classification with trust mechanisms and accuracy metrics

| Epic | Description | Status |
|------|-------------|--------|
| AI Classification | Type, priority, sentiment with confidence scores | Pending |
| Entity Extraction | Quote numbers, PO numbers, dollar amounts, deadlines | Pending |
| Manual Correction | Override buttons, "Needs Review" queue, track corrections | Pending |
| Cost & Performance | Track API costs, batch processing, prompt versioning | Pending |
| Accuracy Testing | Gold-standard test dataset, precision/recall metrics, drift detection | Pending |

### Go/No-Go Criteria for Sprint 3
| Metric | Target |
|--------|--------|
| Accuracy | ≥85% overall |
| Confidence | Scores on all outputs |
| Cost | < $X per 1,000 emails |
| Human Trust | Correction UI working |
| Volume | 10k emails no degradation |

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
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
API_HOST=0.0.0.0
API_PORT=8000
```

**Frontend (`frontend/.env.development`)**:
```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_SUPABASE_URL=https://xxx.supabase.co  # For RBAC authentication
VITE_SUPABASE_ANON_KEY=your_anon_key  # For RBAC authentication
VITE_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
```

### 3. Database Setup
Run in Supabase SQL Editor:
1. `scripts/create_tables.sql` (main schema)
2. `scripts/migrations/001a_add_error_columns.sql`
3. `scripts/migrations/001b_add_error_functions.sql`
4. `scripts/migrations/001c_add_error_indexes.sql`
5. `scripts/migrations/002_add_business_hierarchy.sql`
6. `scripts/migrations/010_create_user_profiles.sql` (RBAC with Supabase Auth)

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
- [Update Context](docs/UPDATE_CONTEXT.md) - Current session state and progress
- [Google Drive Integration](docs/GOOGLE_DRIVE_INTEGRATION.md) - OAuth setup and file access
- [Architecture Overview](docs/ARCHITECTURE.md) - System design and components
- [Email Tagging System](docs/EMAIL_TAGGING.md) - Rule-based classification
- [Deployment Guide](docs/DEPLOYMENT.md) - Production deployment steps

---

## Tech Stack

### Backend
- **Framework**: FastAPI 0.104+
- **Database**: Supabase (PostgreSQL)
- **Authentication**: Supabase Auth + PyJWT
- **Cache**: Redis 7.0+
- **AI**: Claude 3.5 Sonnet API (Stage 2 Sprint 3)
- **Cloud Storage**: Google Drive API
- **Processing**: ThreadPoolExecutor (20 workers)

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

**Stage 1 Complete | Stage 2 Sprint 1 In Progress (Gmail LIVE + RBAC Complete)**

*Last Updated: January 30, 2026*

*Built with Python, TypeScript, React, Supabase Auth, Claude AI, and Google Cloud APIs*
