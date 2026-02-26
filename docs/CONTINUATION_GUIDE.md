# Continuation Guide — Sprint 3: AI Semantic Intelligence

**Last Updated:** 2026-02-26
**Current Status:** Sprint 2 FULLY COMPLETE ✅ | Ready for Sprint 3

---

## Quick Start (For New Conversation)

**Copy/paste this:**

> "Sprint 2 is FULLY COMPLETE. Check `docs/CONTINUATION_GUIDE.md` and `MEMORY.md` for full context.
>
> **What's complete (Sprint 2):**
> - 13-step extraction pipeline processing 26,000+ emails in production
> - 30 REST API analytics endpoints (all tested)
> - 10 database migrations (master schema v1.8)
> - Production fixes: pagination, NULL handling, retry logic, batch processing
> - 100% email link rate, ~1.5min full extraction, ~15-30s incremental
>
> **What to build next (in order):**
> 1. **Admin Data View** — Raw table browser for all Supabase tables (search, filter, sort, export)
> 2. **Sprint 3 AI Layer** — Semantic intent classification, sentiment tracking, entity extraction
>
> Start with the Admin Data View page."

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

### Database Schema (v1.8, 10 migrations)
| Table | Purpose | Key Columns |
|-------|---------|-------------|
| customer_contacts | Contact records | email_address, engagement_score, seniority_level, contact_type |
| customer_companies | Company records | company_name, email_domains[], engagement_score, relationship_status |
| extraction_jobs | Pipeline tracking | status, extraction_mode, emails_in_scope, current_step |
| email_response_metrics | Response pairs | response_time_seconds, is_auto_reply |
| thread_status | Thread evaluation | status (6 states), thread_depth, is_overdue |
| unified_email_rules | Email rules | source_type, conditions, actions, engagement_signal |

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

## Next Steps: What to Build

### Step 1: Admin Data View (Immediate)

Build a frontend page for admins to browse raw data from all Supabase tables.

**Requirements:**
- Table selector dropdown (all tables: emails, customer_contacts, customer_companies, extraction_jobs, thread_status, email_response_metrics, etc.)
- Data table with all columns visible
- Search across all columns
- Column-level filters (text, number ranges, date ranges, enum dropdowns)
- Sortable columns (click header to sort ASC/DESC)
- Pagination with configurable page size (25/50/100/250)
- Export to CSV
- Admin-only access (role check)

**Implementation approach:**
- Add a new route `/admin/data` in the existing React + Vite + Ant Design frontend
- Use Ant Design `Table` component with built-in sorting and filtering
- API: create a generic `/api/v1/admin/tables/{table_name}` endpoint that accepts query params for search, filters, sort, pagination
- Backend validates table name against allowed list (prevent SQL injection)

### Step 2: Sprint 3 — AI Semantic Intelligence

Transition from metadata tracking to **Semantic & Intent Intelligence** using Claude API.

**AI Model Strategy:**
- Use Claude API (latest model) in cost-optimized way
- Track usage per request in `ai_usage_log` table (model, tokens, cost, timestamp)
- Admin dashboard showing total cost, cost per mailbox, cost per operation type
- Batch processing to minimize API calls
- Cache results to avoid re-analyzing unchanged emails

**Phase 1: Semantic Intent & Sentiment Engine**

| Task | Service to Create/Modify | Description |
|------|--------------------------|-------------|
| Intent Classification | NEW: `ai_intent_processor.py` | Classify emails: Pricing Inquiry, Feature Request, Expansion Signal, Churn Risk |
| Sentiment Detection | MODIFY: `engagement_scorer.py` | Add `sentiment_score` using Claude body text analysis |
| Urgency Detection | NEW: `ai_intent_processor.py` | Detect hidden urgency from email body |
| Normalizer Update | MODIFY: `normalizer.py` | Add `body_summary` and `detected_sentiment` to normalized email |
| Tagger Enhancement | MODIFY: `email_tagger.py` | Call Claude API for intent classification on emails >100 chars |
| AI Usage Tracking | NEW: `ai_usage_tracker.py` | Track model, tokens, cost per API call |

**Phase 2: Entity & Opportunity Extraction**

| Task | Service to Modify | Description |
|------|-------------------|-------------|
| Entity Extraction | `extraction_orchestrator.py` | Detect competitors, product names, budget mentions |
| Lead Scoring 2.0 | `engagement_scorer.py` | Weight buying signals (procurement, legal review, timeline) |
| AI Enrichment | `title_parser.py` fallback | Infer job functions from email signatures via Claude |

**Phase 3: Hidden Network & Relationship Insights**

| Task | Service to Create | Description |
|------|-------------------|-------------|
| Influence Mapping | NEW: `influence_mapper.py` | Track high-seniority CC entries as "Stakeholder Entry" |
| Gap Analysis | NEW: `relationship_analyzer.py` | Flag single-contact dependency risk |
| Summarization | NEW: `relationship_summarizer.py` | 3-sentence executive summaries via Claude |

**Phase 4: Proactive "Next Best Action"**

| Task | Description |
|------|-------------|
| Suggested Responses | AI-drafted replies based on thread history + intent |
| Churn Alerts | Auto-flag accounts with >30% engagement velocity drop in 1 week |
| Marketing Exports | Identify champions for case study recruitment, CSV/CRM export |
| Dashboard Update | "Top Opportunities" card based on AI-detected buying signals |

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

backend/src/models/
└── analytics.py                — 41 Pydantic models + 5 enums

backend/src/routers/
└── analytics.py                — 30 REST API endpoints

backend/src/utils/
├── domain_parser.py            — Email → domain extraction
├── name_parser.py              — Display name → first/last
└── title_parser.py             — Job title → seniority + role

scripts/sprint2/
├── sprint2_migration_001-010   — 10 database migrations
├── SPRINT2_MASTER_SCHEMA.sql   — v1.8 consolidated schema
└── README_MIGRATIONS.md        — Migration guide
```

### Documentation
```
docs/
├── SPRINT2_IMPLEMENTATION.md   — Full implementation guide (pipeline, services, algorithms)
├── CONTINUATION_GUIDE.md       — This file (next conversation handoff)
├── TODO.md                     — Active task tracking
├── CLAUDE.md                   — Development guidelines
└── QUICK_START_PHASE5.md       — Phase 5 quick start (historical)
```
