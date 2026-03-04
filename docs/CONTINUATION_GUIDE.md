# Continuation Guide — Sprint 3: AI Semantic Intelligence

**Last Updated:** 2026-03-03
**Current Status:** Sprint 2 COMPLETE ✅ | Sprint 3 AI Week 1 COMPLETE ✅ | Sprint 3 Frontend (4 pages) COMPLETE ✅ | Invite User System PLANNED | AI Priority Fixes PENDING

---

## Quick Start (For New Conversation)

**Copy/paste this:**

> "Sprint 2 COMPLETE. Sprint 3 AI Layer partially built. Check `docs/CONTINUATION_GUIDE.md` and `MEMORY.md` for full context.
>
> **What's complete:**
> - Sprint 2: 13-step extraction pipeline, 30 analytics endpoints, 12 migrations, 6 analytics pages + Admin Data View
> - Sprint 3 Week 1: 7 AI backend services, 19 API endpoints, action bucket engine, digest service
> - Sprint 3 Frontend: 4 intelligence pages (Smart Inbox, Digest, Opportunities, Usage), 2 shared components, aiService.ts, types
>
> **What's planned (not yet implemented):**
> - **Invite User System** — Restrict open sign-up, admin-controlled onboarding. Design: `docs/INVITE_USER_SMTPLESS.md`
> - **AI Priority Fixes** — Date-range filtering, daily/weekly digest, 50% cost reduction
> - **Sprint 3 Sessions 7-13** — Relationship summaries, company AI cards, AM comparison, gap alerts, testing, deploy
>
> **What to build next:**
> 1. **AI Priority Fixes** — Fix 3 issues before continuing (see TODO.md)
> 2. **Sprint 3 Sessions 7-13** — See `docs/AI_MVP_PLAN.md` for plan + implementation status
> 3. **Invite User System** — See `docs/INVITE_USER_SMTPLESS.md` for full design
>
> Start with AI Priority Fixes, then continue Sprint 3 Sessions 7-13."

---

## Sprint 2 Complete Summary

### Architecture

```
Extraction Pipeline (13 steps):
  Validate → Extract Contacts → Deduplicate → Resolve Companies
  → Upsert Contacts → Upsert Companies → Classify Roles → Update Roles
  → Link Emails → Calculate Engagement → Update Company Stats
  → Generate Report → Mark Complete

Analytics API (30 endpoints at /api/v1/analytics/):
  Extraction Control (5) | Contact Analytics (6) | Company Analytics (5)
  Thread Analytics (4) | Response Times (4) | Comm Patterns (4) | Dashboard (2)
```

### Key Backend Services
| Service | File | Purpose |
|---------|------|---------|
| ExtractionOrchestrator | `backend/src/services/extraction_orchestrator.py` | 13-step pipeline coordinator |
| ContactExtractor | `backend/src/services/contact_extractor.py` | Email address extraction + deduplication |
| CompanyResolver | `backend/src/services/company_resolver.py` | Domain → company grouping |
| RoleClassifier | `backend/src/services/role_classifier.py` | Title → seniority + role parsing |
| EmailLinker | `backend/src/services/email_linker.py` | FK backfill (emails → contacts/companies) |
| EngagementScorer | `backend/src/services/engagement_scorer.py` | 8-factor scoring (0-100) |
| ResponseTimeTracker | `backend/src/services/response_time_tracker.py` | Response time calculations |
| ThreadTracker | `backend/src/services/thread_tracker.py` | Thread status evaluation (6 states) |
| CommunicationPatternAnalyzer | `backend/src/services/comm_pattern_analyzer.py` | Initiation ratio, reply rate, trends |
| Analytics Router | `backend/src/routers/analytics.py` | 30 REST endpoints (2,305 lines) |
| Analytics Models | `backend/src/models/analytics.py` | 41 Pydantic models + 5 enums |

### Key Utilities
| Utility | File | Purpose |
|---------|------|---------|
| DomainParser | `backend/src/utils/domain_parser.py` | Email → domain extraction |
| NameParser | `backend/src/utils/name_parser.py` | Display name → first/last |
| TitleParser | `backend/src/utils/title_parser.py` | Job title → seniority + role |

### Database Schema (v1.8+, 12 migrations)
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| customer_contacts | Contact records | email_address, engagement_score, seniority_level, contact_type |
| customer_companies | Company records | company_name, email_domains[], engagement_score, relationship_status |
| extraction_jobs | Pipeline tracking | status, extraction_mode, emails_in_scope, current_step |
| email_response_metrics | Response pairs | response_time_seconds, is_auto_reply |
| thread_status | Thread evaluation | status (6 states), thread_depth, is_overdue |
| unified_email_rules | Email rules | source_type, conditions, actions, engagement_signal |

### Analytics Frontend (Complete)
| Page | Route | Features |
|------|-------|----------|
| Dashboard | `/analytics` | Client selector, overview metrics, extraction trigger |
| Contacts | `/analytics/contacts` | All/Top/At-Risk/DMs/By-Type tabs, sort, filter, score slider |
| Companies | `/analytics/companies` | All/Top/At-Risk/By-Engagement tabs, sort, filter, score slider |
| Threads | `/analytics/threads` | All/Overdue/By-Status tabs, status chart, sort, filter |
| Contact Detail | `/analytics/contacts/:id` | Stats, threads, communication patterns |
| Company Detail | `/analytics/companies/:id` | Stats, top contacts, threads |
| Admin Data View | `/admin/data` | Raw table browser, search, sort, pagination, CSV export |

### Production Performance
- 26,654 emails across 54 pages processed successfully
- 100% email link rate maintained
- Full extraction: ~1.5 minutes | Incremental (7-day): ~15-30 seconds
- Batch operations: 25x faster (database RPC functions)
- Database-side calculations: ~250x faster (3 RPC calls vs 744+ queries)

### Critical Patterns Learned
1. **Supabase NULL handling:** `neq('col', 'val')` excludes NULLs — use Python-side filtering
2. **Supabase pagination:** `.range(0, 499)` returns 499 rows — use `len==0` break, not `< PAGE_SIZE`
3. **Supabase booleans:** Use lowercase strings `'true'`/`'false'`, not Python `True`/`False`
4. **Supabase .or_():** Not available in all versions — Python-side filtering is compatible
5. **Batch limits:** Max 100 items per Supabase batch update, 500 IDs per `.in_()` filter
6. **Retry logic:** Wrap Supabase queries in `_execute_with_retry()` for transient SSL/network errors

---

## Sprint 3 AI Implementation Status

### What's Built (Sessions 1-6) ✅

**Backend Services (7):** All in `backend/src/services/`
- `ai_client.py` — Claude Haiku + Sonnet, rate limiting, retry, budget caps ($2/day, $16/month)
- `ai_privacy_filter.py` — Strips PII, MAX_BODY_LENGTH=500
- `ai_usage_tracker.py` — Per-operation cost tracking
- `ai_email_analyzer.py` — BATCH_SIZE=10, 12 intent categories, entity extraction
- `ai_action_bucket_engine.py` — 8 bucket types (4 email-level + 4 relationship-level), zero cost
- `ai_entity_aggregator.py` — Entity rollup into `ai_business_entities`
- `ai_digest_generator.py` — Claude Sonnet, daily digest with bucket language

**API Endpoints (23):**
- `backend/src/routers/ai.py` — 19 endpoints (analyze, intelligence, action items, feedback, entities, digest, summaries, usage)
- `backend/src/routers/rules.py` — 4 endpoints (email rules CRUD)

**Frontend Pages (4):** All at `/intelligence/`
- Smart Inbox — filters, bucket chips, detail drawer, feedback buttons, analysis trigger
- Daily Digest — date picker, bucket summary bar, action items, highlights
- Opportunities — 4 tabs (Action Items, Opportunities, Competitors, Entities)
- Usage & Monitoring — admin controls, budget tracking, cost breakdown, health metrics

**Frontend Infrastructure:**
- `aiService.ts` (16 endpoints, TTL cache, dedup), `rulesService.ts`
- `ActionBucketTag.tsx`, `FeedbackButtons.tsx` shared components
- `ai.ts` types (13 enums, comprehensive interfaces)
- Email Rules page at `/analytics/email-rules`

---

## Next Steps: What to Build

### Step 1: AI Priority Fixes (3 Issues)

**Fix 1: Analysis processes age-old emails**
- `ai_email_analyzer.py` has no date filter — fetches ALL unanalyzed emails regardless of age
- Add `date_from`/`date_to` params, default to **last 7 days**
- Files: `ai_email_analyzer.py`, `ai.py` router, frontend analysis trigger

**Fix 2: Daily Digest considers old emails + add Weekly Digest**
- Digest should only process emails within its time window (1 day or 7 days)
- Add `digest_type` param (`daily` | `weekly`) to digest endpoint
- Daily = last 24h, Weekly = last 7 complete days
- Files: `ai_digest_generator.py`, `ai.py` router, frontend digest page

**Fix 3: Reduce AI cost by 50%+**
- Increase batch size: 10 → 20 emails per call (~40% cost reduction)
- Reduce body truncation: 500 → 300 chars (~40% fewer input tokens)
- Skip trivial emails: body < 50 chars, forwards-only with no added text
- Files: `ai_email_analyzer.py`, `ai_privacy_filter.py`

### Step 2: Sprint 3 Sessions 7-13 (Remaining)

Full plan + status in `docs/AI_MVP_PLAN.md`.

| Session | Deliverable | Status |
|---------|------------|--------|
| 7 | Relationship summary service (`ai_relationship_summarizer.py`) | Not started |
| 8 | Company detail page AI cards | Not started |
| 9 | Opportunities Tab 5 (Budget Discussions) | Not started |
| 10 | AM Comparison + Gap Alerts (bucket-enriched) | Not started |
| 11 | Main dashboard Quick Insights + cross-linking | Not started |
| 12 | Integration testing (`test_ai_pipeline.py`) | Not started |
| 13 | Production deployment + documentation | Not started |

### Step 3: Invite User System (Planned)

Restrict open sign-up with admin-controlled user onboarding. Full design in `docs/INVITE_USER_SMTPLESS.md`.

**Summary:**
- Admin creates invite (role + client assignment) → user accepts via magic link, shared URL, or direct OAuth
- On acceptance: `user_profiles` created, client assigned, inactive mailbox auto-created from email domain
- Dashboard banner prompts new user to authorize Gmail/Outlook OAuth to activate mailbox
- Login page "Create Account" tab removed — invite-only onboarding

**Implementation scope:**
- Migration 014: `pending_invites` table + user_profiles invite tracking columns
- Backend: `invites.py` router (6 endpoints: create, validate, accept, list, resend, revoke)
- Frontend: InviteUserModal, InviteAcceptPage, Users page update, AuthContext invite hook, dashboard connection banner

---

## File Reference

### Sprint 2 Backend (Complete)
```
backend/src/services/
├── extraction_orchestrator.py  — 13-step pipeline (full + incremental mode)
├── contact_extractor.py        — Email extraction + deduplication
├── company_resolver.py         — Domain → company resolution
├── role_classifier.py          — Title → seniority + role classification
├── email_linker.py             — FK backfill (emails → contacts/companies)
├── engagement_scorer.py        — 8-factor engagement scoring (0-100)
├── response_time_tracker.py    — Response time calculations
├── thread_tracker.py           — Thread status evaluation
└── comm_pattern_analyzer.py    — Communication pattern analysis
```

### Sprint 3 AI Backend (Sessions 1-5 Complete)
```
backend/src/services/
├── ai_client.py                — Claude API client (Haiku + Sonnet), rate limiting, retry, budgets
├── ai_privacy_filter.py        — Strip PII before AI (MAX_BODY_LENGTH=500)
├── ai_usage_tracker.py         — Per-operation cost tracking to ai_usage_log
├── ai_email_analyzer.py        — Unified classify + entities + justify (BATCH_SIZE=10)
├── ai_action_bucket_engine.py  — 8 action buckets (pure Python, $0)
├── ai_entity_aggregator.py     — Entity rollup into ai_business_entities
├── ai_digest_generator.py      — Daily digest (Claude Sonnet)
└── email_rules_service.py      — Email rules CRUD

backend/src/models/
├── analytics.py                — 41 Pydantic models + 5 enums (Sprint 2)
├── ai.py                       — AI request/response Pydantic models
└── rules.py                    — Email rules Pydantic models

backend/src/routers/
├── analytics.py                — 30 REST API endpoints (Sprint 2)
├── ai.py                       — 19 AI intelligence endpoints
└── rules.py                    — 4 email rules endpoints

backend/src/utils/
├── domain_parser.py            — Email → domain extraction
├── name_parser.py              — Display name → first/last
└── title_parser.py             — Job title → seniority + role

scripts/sprint2/
├── sprint2_migration_001-010   — 10 database migrations
├── SPRINT2_MASTER_SCHEMA.sql   — v1.8 consolidated schema
└── README_MIGRATIONS.md        — Migration guide
```

### Sprint 3 Frontend (Sessions 6 Complete)
```
frontend/src/pages/intelligence/
├── inbox.tsx                   — Smart Inbox (bucket filters, detail drawer, feedback)
├── digest.tsx                  — Daily Digest (date picker, bucket summary, action items)
├── opportunities.tsx           — Opportunities (4 tabs: actions, opps, competitors, entities)
└── usage.tsx                   — Usage & Monitoring (admin controls, cost breakdown)

frontend/src/components/ai/
├── ActionBucketTag.tsx         — Confidence-gated bucket display with justification tooltip
└── FeedbackButtons.tsx         — 👍/👎 with structured feedback + override

frontend/src/services/
├── aiService.ts                — 16 AI endpoint wrappers (TTL cache, dedup)
└── rulesService.ts             — Email rules CRUD service

frontend/src/types/
└── ai.ts                       — 13 enums, comprehensive AI interfaces

frontend/src/pages/analytics/
└── email-rules.tsx             — Email rules management page
```

### Documentation
```
docs/
├── CLAUDE.md                   — Development guidelines & architecture
├── CONTINUATION_GUIDE.md       — This file (next conversation handoff)
├── TODO.md                     — Active task tracking
├── AI_MVP_PLAN.md              — Sprint 3 AI MVP plan (final, 3-week session plan)
├── INVITE_USER_SMTPLESS.md     — Invite user system design (SMTP-less, planned)
├── SPRINT2_IMPLEMENTATION.md   — Sprint 2 implementation guide
├── SPRINT3_IMPLEMENTATION_PLAN.md — Sprint 3 technical architecture
└── QUICK_START_PHASE5.md       — Phase 5 quick start (historical)
```
