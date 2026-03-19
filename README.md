# Email Intelligence Platform

**Commercial Intelligence Platform for B2B Account Management Teams**

Syncs email from Gmail and Outlook, runs AI analysis on every email, and surfaces actionable insights about customers, deals, and relationship health — enriched with QuickBase CRM data.

---

## Project Status

| Sprint | Scope | Status |
|--------|-------|--------|
| Stage 1 | Email extraction (MBOX/PST/OLM), rule-based tagging, Redis, Railway | ✅ Complete (Jan 2026) |
| Sprint 1 | Auth, RBAC, Gmail/Outlook LIVE sync | ✅ Complete (Feb 2026) |
| Sprint 2 | 13-step extraction pipeline, 30 analytics endpoints, analytics frontend | ✅ Complete (Feb 2026) |
| Sprint 3 | QB integration, AI pipeline, strategic digest, prompt system | ✅ Complete (Mar 2026) |
| Sprint 4 | Sales Intelligence: QB Operations, Customer Profile, Recommendation Engine, Vector AI + Chat Agent | 🔲 In Progress (Mar 2026) |
| Invite User System | Admin-controlled onboarding, restrict open sign-up | 🔲 Planned |

**Production:** Railway · **Backend:** FastAPI (Python 3.13), ~150+ API endpoints · **Frontend:** React/TypeScript, 30+ pages · **Database:** Supabase PostgreSQL, ~34 tables

---

## Quick Start

### Prerequisites
- Python 3.8+ with pip
- Node.js 16+ with npm
- Redis Server (required for job tracking)
- Supabase account

### Setup

```bash
# Clone repository
git clone <repository-url>
cd email-intelligence-platform

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # Edit with your credentials

# Frontend setup
cd ../frontend
npm install
```

### Environment Variables

**Backend (`backend/.env.development`):**
```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_role_key
SUPABASE_JWT_SECRET=your_jwt_secret
REDIS_URL=redis://localhost:6379
REDIS_TTL_DAYS=7
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
MICROSOFT_CLIENT_ID=your-azure-app-client-id
MICROSOFT_CLIENT_SECRET=your-azure-client-secret
MICROSOFT_TENANT_ID=common
ANTHROPIC_API_KEY=your_anthropic_api_key
GOOGLE_AI_API_KEY=your_google_ai_api_key
QUICKBASE_USER_TOKEN=your_qb_token
API_HOST=0.0.0.0
API_PORT=8000
```

**Frontend (`frontend/.env.development`):**
```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_SUPABASE_URL=https://xxx.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_key
VITE_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
VITE_MICROSOFT_CLIENT_ID=your-azure-app-client-id
VITE_MICROSOFT_REDIRECT_URI=http://localhost:3001/auth/microsoft/callback
```

### Start Services

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Backend (port 8000)
cd backend && ./run.sh         # or: uvicorn main:app --reload

# Terminal 3: Frontend (port 3001)
cd frontend && npm start
```

Access:
- Frontend: http://localhost:3001
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

### Database Migrations

Run in order in the Supabase SQL Editor:

**Stage 1:**
1. `scripts/create_tables.sql`
2. `scripts/migrations/001a_add_error_columns.sql`
3. `scripts/migrations/001b_add_error_functions.sql`
4. `scripts/migrations/001c_add_error_indexes.sql`
5. `scripts/migrations/002_add_business_hierarchy.sql`
6. `scripts/migrations/010_create_user_profiles.sql`

**Sprint 2:**
7. `scripts/sprint2/sprint2_migration_001_supporting_tables.sql`
8–16. (see `scripts/sprint2/README_MIGRATIONS.md` for full list)

**Sprint 3:**
17. `scripts/sprint3/sprint3_migration_013_ai_layer.sql`
18. `scripts/sprint3/sprint3_migration_014_add_skipped_status.sql`
19. `scripts/sprint3/sprint3_migration_021_strategic_digest.sql`
20. `scripts/migrations/021a_add_qb_enrichment_columns.sql`
21. `scripts/migrations/026_am_lifecycle_rehaul.sql`

**Sprint 4 (in progress):**
22. `scripts/migrations/032_qb_operations.sql` — QB Operations table
23. `scripts/migrations/033_product_intelligence.sql` — Recommendations + affinities cache
24. `scripts/migrations/034_pgvector_embeddings.sql` — Vector extension + embedding columns

---

## Architecture

### System Overview

```
Email Sources (Gmail / Outlook / MBOX / PST / OLM)
        ↓
FastAPI Backend (14 routers, ~150 endpoints)
        ↓
13-Step Extraction Pipeline → Supabase PostgreSQL (~34 tables)
        ↓
AI Analysis Layer (Claude Haiku/Sonnet + Gemini 2.0 Flash)
        ↓
QuickBase CRM Sync (6 tables: customers, contacts, quotes, jobs, line items, operations)
        ↓
Vector Intelligence (pgvector embeddings — emails + companies + operations)
        ↓
React Frontend (30+ pages)
```

### Backend Structure

```
backend/
├── main.py                          # FastAPI app, router registration
├── src/
│   ├── routers/                     # 14 API routers
│   │   ├── auth.py                  # Auth + user management
│   │   ├── analytics.py             # 30 analytics endpoints
│   │   ├── ai.py                    # 25+ AI endpoints
│   │   ├── quickbase.py             # 6 QB endpoints
│   │   ├── customers.py             # Customer profile endpoints
│   │   ├── gmail.py / outlook.py    # LIVE sync
│   │   └── ...
│   ├── services/                    # Business logic
│   │   ├── extraction_orchestrator.py      # 13-step pipeline
│   │   ├── ai_email_analyzer.py            # Per-email AI classification
│   │   ├── ai_digest_generator.py          # Daily/weekly digest
│   │   ├── strategic_digest_pipeline.py    # LangGraph ReAct agent
│   │   ├── quickbase_sync.py               # QB 6-table sync
│   │   ├── recommendation_engine.py        # Level 1+2 recommendations (Sprint 4)
│   │   ├── vector_service.py               # pgvector embeddings (Sprint 4)
│   │   └── ai_agent_service.py             # AI Chat Agent (Sprint 4)
│   ├── extractors/                  # Email format extractors
│   ├── processors/                  # Email normalizer + tagger
│   ├── models/                      # Pydantic models
│   ├── utils/                       # Domain, name, title parsers
│   └── dependencies/                # Auth (JWT/RBAC)
└── requirements.txt
```

### Frontend Structure

```
frontend/src/
├── pages/
│   ├── analytics/                   # Dashboard, Contacts, Companies, Threads, Detail pages
│   └── intelligence/                # Inbox, Digest, Opportunities, Strategic Digest, QB Config, Agent
├── components/                      # Shared: ActionBucketTag, LifecycleBadge, AIInsightsCard, etc.
├── services/                        # API wrappers: analyticsService, aiService, strategicDigestService
└── contexts/                        # AuthContext, etc.
```

---

## Feature Overview

### Email Ingestion
- **Multi-format:** MBOX, PST, OLM archives
- **LIVE sync:** Gmail (historyId incremental) + Outlook (deltaLink incremental)
- **Google Drive:** OAuth2 streaming for large files (65GB+) without download
- **Incremental:** Full + incremental extraction modes with configurable lookback

### AI Intelligence Layer (Sprint 3)
- **Per-email classification:** Intent, action type, business signal, sentiment, urgency (Claude Haiku ~$0.001/email)
- **6 AM-centric signals:** response_urgency, deal_at_risk, retention_risk, revenue_opportunity, new_relationship, account_neglect
- **Customer lifecycle tiers:** prospect → new_customer → active_customer → at_risk → dormant → champion
- **Daily/weekly digest:** AI-generated summaries (Claude Sonnet)
- **Strategic digest:** LangGraph ReAct agent with 4 lookup tools, 8-section executive output
- **Per-entity AI insights:** On-demand company/contact/thread analysis (cached 24h)
- **AI Chat Agent (Sprint 4):** Conversational portfolio Q&A with 6 tools + semantic search

### QuickBase CRM Integration (Sprint 3 + Sprint 4)
- **5 synced tables:** Customers, Contacts, Quotes, Jobs, Sales Line Items
- **6th table (Sprint 4):** Operations (`bvqsudnif`) — granular product/service detail per job
- **4-tier company matching:** QB customers → `customer_companies`
- **Data propagation:** Revenue, tier, AM data flows into engagement scoring and AI prompts
- **Config:** App ID `buzfemk4f`, Realm `dc.quickbase.com`

### Sales Intelligence (Sprint 4)
- **Customer Profile redesign:** 6-section full profile — product breakdown, order history, contacts, recommendations, timeline
- **Recommendation Engine (Level 1):** Cross-contact gaps — products the company uses that a specific contact hasn't been involved in
- **Recommendation Engine (Level 2):** Related product affinities — market basket analysis across portfolio ("68% of customers using X also use Y")
- **Recommendations surface:** Customer Profile · Smart Inbox drawer · Daily/Weekly Digest
- **Vector embeddings:** `ai_email_intelligence`, `customer_companies`, `qb_operations` via Google `text-embedding-004` (768 dims)
- **Semantic search:** HNSW indexes on Supabase pgvector, `search_email_intelligence()` RPC

### Auth & Access Control
- **Supabase Auth:** Email/password + Google OAuth + Microsoft OAuth
- **3 roles:** `admin` (full access), `client_manager` (oversight), `account_manager` (own mailboxes)
- **Multi-role:** Users can hold multiple roles simultaneously
- **JWT:** Supports ES256/RS256 (JWKS) and HS256 (shared secret)

---

## Gmail LIVE Sync

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/gmail/mailbox/{id}/connect` | Connect Gmail to mailbox |
| POST | `/api/gmail/mailbox/{id}/sync` | Trigger sync |
| DELETE | `/api/gmail/mailbox/{id}/disconnect` | Disconnect |

**Scopes:** `gmail.readonly`, `gmail.labels` · **Incremental:** historyId · **Interval:** configurable (default 15 min)

**Google OAuth Setup:** [Google Cloud Console](https://console.cloud.google.com) → Enable Gmail API → Create OAuth 2.0 credentials → Add redirect URI `http://localhost:3001/auth/google/callback`

---

## Outlook LIVE Sync

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/outlook/mailbox/{id}/connect` | Connect Outlook to mailbox |
| POST | `/api/outlook/mailbox/{id}/sync` | Trigger sync |
| POST | `/api/outlook/fetch-date-range` | Fetch emails by date range |

**Scopes:** `Mail.Read`, `User.Read`, `MailboxSettings.Read` · **Incremental:** deltaLink · Supports O365 + personal accounts

**Azure Setup:** [Azure Portal](https://portal.azure.com) → App registrations → SPA platform → Redirect URI `http://localhost:3001/auth/microsoft/callback` → Permissions: `Mail.Read`, `User.Read`

---

## Cost Model

| Component | Monthly Cost |
|-----------|-------------|
| Email analysis (Claude Haiku) | ~$8–12 |
| Daily/weekly digests (Claude Sonnet) | ~$3–4 |
| Strategic digest (Claude Sonnet + Gemini) | ~$2–5 |
| Per-page AI insights | ~$1–3 |
| QuickBase sync | $0 |
| Sprint 4: vector embeddings + AI Chat Agent | ~$3–8 |
| **Total** | **~$17–32/month** |
| **Budget cap** | **$50/month** |

---

## Troubleshooting

**Port 8000 in use:**
```bash
lsof -ti:8000 | xargs kill -9
```

**Supabase connection errors:** Verify `.env` credentials and that the DB schema is applied.

**Gmail/Outlook sync not working:** Check OAuth credentials, verify redirect URIs match exactly, check token expiry.

**Migration timeout on Railway:** Split large migrations, avoid `CREATE INDEX CONCURRENTLY`.

**Email count shows 0:**
```sql
SELECT update_folder_counts();
```

---

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/CLAUDE.md](docs/CLAUDE.md) | Development guidelines for Claude Code |
| [docs/PLATFORM_PROGRESS.md](docs/PLATFORM_PROGRESS.md) | Full DB schema, API routers, all features with columns |
| [docs/TODO.md](docs/TODO.md) | Active task list + Sprint 4 implementation checklist |
| [docs/UPDATE_CONTEXT.md](docs/UPDATE_CONTEXT.md) | Session handoff + current sprint status |
| [docs/INVITE_USER_SMTPLESS.md](docs/INVITE_USER_SMTPLESS.md) | Invite user system design (planned) |
| [scripts/sprint2/README_MIGRATIONS.md](scripts/sprint2/README_MIGRATIONS.md) | Sprint 2 migration guide |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.13), Uvicorn, Pydantic |
| Database | Supabase PostgreSQL (pgvector for Sprint 4), ~34 tables |
| Auth | Supabase Auth, PyJWT (ES256/HS256) |
| Cache | Redis 7.0+ (required) |
| AI | Claude Haiku/Sonnet (Anthropic) + Gemini 2.0 Flash (Google) |
| Orchestration | LangChain, LangGraph (ReAct agent) |
| Embeddings | Google `text-embedding-004` via `langchain-google-genai` (Sprint 4) |
| CRM | QuickBase API (6 tables) |
| Cloud Storage | Google Drive API (OAuth2 streaming) |
| Frontend | React 18 + TypeScript, Vite, Ant Design 5.x, Recharts |
| Production | Railway (backend + Redis), Supabase Cloud |

---

**Stage 1–3 Complete · Sprint 4 In Progress**

*Last Updated: March 19, 2026*
