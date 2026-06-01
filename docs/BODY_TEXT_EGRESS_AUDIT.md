# body_text & SELECT * on emails — Egress Audit

**Date:** June 1, 2026
**Purpose:** Identify every callsite that fetches `body_text` or uses `SELECT *` on the emails table, to inform vertical partition and egress reduction.

---

## Critical Findings

- **2 `SELECT *` callsites** on the emails table (both in `operations.py`)
- **19 backend callsites** explicitly fetch `body_text`
- **3 frontend references** use `body_text` for display
- **6 SQL RPCs/migrations** reference `body_text` in `FROM emails` queries (mostly for full-text search / vector embedding)

---

## Category A: SELECT * (Highest Priority)

| # | File | Line | Context | Verdict |
|---|------|------|---------|---------|
| A1 | `backend/src/database/operations.py` | 1000 | `select('*', count='exact')` — `search_emails()` method. Dead code (no production callers — superseded by vector_service RPC search), but fixed to explicit column list excluding body_text, body_html, raw_headers, embedding, search_text | **FIXED** |
| A2 | `backend/src/database/supabase_client.py` | 177 | `select('*')` — docstring example only, not runtime code | **Ignore** — documentation example |

---

## Category B: Fetches body_text for AI / LLM Processing (Legitimate)

These need body_text to feed into AI classifiers, embedders, or context builders. Body content is the input data.

| # | File | Line | Select Columns | Purpose | Notes |
|---|------|------|---------------|---------|-------|
| B1 | `services/ai_email_analyzer.py` | 691 | Explicit column list incl `body_text` | Batch AI classification — reads email body to classify intent/sentiment | **Legitimate** — core pipeline |
| B2 | `services/ai_email_analyzer.py` | 898 | Explicit list incl `body_text` | Thread history context for AI classification (prior messages) | **Legitimate** — truncated to MAX_BODY_CHARS |
| B3 | `services/ai_email_analyzer.py` | 940 | Uses `email.get("body_text")` | Single email AI analysis input | **Legitimate** — from B1 fetch |
| B4 | `services/ai_email_analyzer.py` | 1681 | Explicit list incl `body_text,body_html` | Single email on-demand analysis (get_intelligence) | **Legitimate** — single row |
| B5 | `routers/ai.py` | 1038 | `body_text, body_html` | On-demand AI summary for single email | **Legitimate** — single row, needs body |
| B6 | `services/ai_digest_generator.py` | 681 | Explicit list incl `body_text` | Thread emails for digest generation | **Legitimate** — truncated to MAX_SNIPPET |
| B7 | `services/ai_insights_engine.py` | 383 | Explicit list incl `body_text` | Thread context for company insight generation | **Legitimate** — truncated to 200 chars |
| B8 | `services/vector_service.py` | 309 | `id, subject, body_text, sender_email, sender_name, is_outbound` | Email embedding — builds embed text from body | **Legitimate** — core vectorization |
| B9 | `services/reference_extractor.py` | 146–188 | `body_text, body_html` | QB reference extraction (quote/job numbers from body) | **Legitimate** — needs body content |
| B10 | `services/role_classifier.py` | 242 | `id, body_text` | Signature extraction from last 1000 chars | **Optimize** — only needs last 1KB, fetches entire body |

---

## Category C: Fetches body_text for Display (Review for Optimization)

| # | File | Line | Select Columns | Purpose | Notes |
|---|------|------|---------------|---------|-------|
| C1 | `routers/emails.py` | 736–752 | Explicit list incl `body_text, body_html` | Single email detail view (by ID) | **Legitimate** — user clicked to read email |
| C2 | `routers/analytics.py` | 2492 | `COLS` incl `body_text` | Thread detail view — all emails in a thread | **Review** — fetches full body for up to `limit` emails; used for thread display |
| C3 | `routers/analytics.py` | 2553–2565 | Truncates body_text to preview | Thread emails — truncates after fetch | **Optimize** — fetches full body then truncates in Python. Could use SQL `LEFT(body_text, 300)` or partition |

---

## Category D: Fetches body_text During Extraction Pipeline (Write Path)

These run during email ingestion — body_text is being processed for storage, not queried for reads.

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| D1 | `database/operations.py` | 667 | `_ensure_utf8(email.get('body_text'))` | Email INSERT — writing body_text to DB | **N/A** — write path |
| D2 | `processors/normalizer.py` | 51–98 | Cleans and normalizes body_text | Email processing pipeline | **N/A** — write path |
| D3 | `processors/email_tagger.py` | 177–369 | `email.get('body_text').lower()` | Rule-based tagging (reads from in-memory dict) | **N/A** — in-memory processing |
| D4 | `processors/industry_categorizer.py` | 79–220 | `email.get('body_text').lower()` | Industry categorization from body keywords | **N/A** — in-memory processing |
| D5 | `processors/automation_categorizer.py` | 91–175 | `email.get('body_text').lower()` | Auto-reply detection from body patterns | **N/A** — in-memory processing |
| D6 | `extractors/*.py` | Various | body_text extraction from MBOX/PST/OLM/Gmail/Outlook | Raw email extraction | **N/A** — write path |

---

## Category E: Explicitly Excludes body_text (Good Patterns)

| # | File | Line | Pattern | Notes |
|---|------|------|---------|-------|
| E1 | `routers/admin.py` | 64 | `exclude_columns: ["body_html", "body_text", "raw_headers"]` | Admin data browser excludes heavy columns | **Good** |
| E2 | `routers/emails.py` | 442 | `body_text=None` | Email list view — explicitly nulls body | **Good** |
| E3 | `routers/emails.py` | 619 | `body_text=None` | Email search results — nulls body | **Good** |
| E4 | `routers/dashboard.py` | 249 | Select omits body_text entirely | Recent emails widget — no body fetched | **Good** |

---

## Category F: Frontend body_text Usage

| # | File | Line | Context | Notes |
|---|------|------|---------|-------|
| F1 | `components/EmailDetailPanel.tsx` | 250–280 | Renders body_text or body_html | Single email detail — user is reading the email | **Legitimate** |
| F2 | `pages/intelligence/opportunities.tsx` | 327 | `previewEmail.body_text` | Email preview in opportunities page | **Review** — could use truncated preview |
| F3 | `types/analytics.ts` | 289 | Type definition: `body_text?: string \| null` | Thread email type includes body_text | Schema definition |
| F4 | `services/emailService.ts` | 25 | Type definition: `body_text?: string` | Email type | Schema definition |
| F5 | `hooks/queries/use-emails.ts` | 79 | `body_text: e.body_text \|\| ''` | Email query hook | Maps body_text from API response |

---

## Category G: SQL RPCs That Read body_text

| # | File | Lines | Context | Notes |
|---|------|-------|---------|-------|
| G1 | `migrations/037_vector_embeddings.sql` | 79 | `FROM emails e` — vector embed RPC reads body | **Legitimate** — embedding needs body |
| G2 | `migrations/057_fulltext_search_emails.sql` | 83 | Full-text search tsvector on body | **Legitimate** — FTS index build |
| G3 | `migrations/064_io_budget_rpc_functions.sql` | 216 | Email stats RPC | **Check** — may read body for size calc |

---

## Category H: Scripts / Dev Tools (Non-Production)

| # | File | Line | Context |
|---|------|------|---------|
| H1 | `dev-scripts/run_categorization.py` | 134 | Dev script fetches body_text for batch categorization |
| H2 | `scripts/db/backfill_ai_for_active_threads.py` | 72 | One-off backfill script |
| H3 | `scripts/db/_diagnose_classification_gap.py` | 83 | Diagnostic script (LENGTH only, not full body) |

---

## Remediation Priority

### P0 — SELECT * Elimination

| Callsite | Action |
|----------|--------|
| **A1** `operations.py:1000` | Replace `select('*', count='exact')` with explicit column list excluding `body_text`, `body_html`, `raw_headers` |

### P1 — Fetches Full Body Then Truncates

| Callsite | Action | Estimated Savings |
|----------|--------|-------------------|
| **C3** `analytics.py:2492` | Thread detail: fetches full body_text for N emails, then truncates to preview in Python (line 2554). Either: (a) don't fetch body_text here, fetch on click; or (b) use SQL `LEFT(body_text, 300)` if partition not in place | **High** — thread can have 10-50 emails |
| **B10** `role_classifier.py:242` | Fetches full body_text, uses only last 1000 chars for signature. Could use SQL `RIGHT(body_text, 1000)` or fetch from partition | **Medium** — batch of emails per contact |

### P2 — Batch AI Processing (Large Egress, Legitimate Need)

| Callsite | Action | Estimated Savings |
|----------|--------|-------------------|
| **B1** `ai_email_analyzer.py:691` | Batch classification fetches body_text for up to PAGE_SIZE emails. If body is partitioned, this becomes a JOIN. Could also truncate in SQL since classifier uses `MAX_BODY_CHARS` | **High** — biggest single source of body_text egress |
| **B8** `vector_service.py:309` | Embedding pipeline fetches body_text in batches. Same partition-JOIN approach | **High** — runs on all unembedded emails |

### P3 — Single-Row Lookups (Low Impact, Legitimate)

| Callsite | Action |
|----------|--------|
| **C1** `emails.py:752` | Single email detail — user reading email. Keep as-is or JOIN partition |
| **B5** `ai.py:1038` | Single email AI summary. Keep as-is |
| **B4** `ai_email_analyzer.py:1681` | Single email analysis. Keep as-is |

### P4 — Context Builders (Already Truncated)

| Callsite | Current Truncation | Action |
|----------|-------------------|--------|
| **B2** `ai_email_analyzer.py:898` | `[:MAX_BODY_CHARS]` | Already truncated — could truncate at SQL level |
| **B6** `ai_digest_generator.py:681` | `[:MAX_SNIPPET]` | Already truncated — could truncate at SQL level |
| **B7** `ai_insights_engine.py:383` | `[:200]` | Already truncated — could truncate at SQL level |

---

## Vertical Partition Impact Assessment

If `body_text` (and `body_html`) are moved to a separate `email_bodies` table:

### Must JOIN (need body content):
- B1: AI batch classification
- B2: Thread context for AI
- B4: Single email analysis
- B5: Single email summary
- B6: Digest generation
- B7: Insight thread context
- B8: Vector embedding
- B9: Reference extraction
- B10: Signature extraction
- C1: Email detail view
- C2/C3: Thread detail view

### Unaffected (don't fetch body):
- All count-only queries (`select('id', count='exact')`)
- Email list views (E2, E3 already null body)
- Dashboard queries (E4)
- Admin data browser (E1)
- All `analytics.py` email queries for metadata (direction, dates, etc.)
- Thread tracking, engagement scoring, response time — none read body

### Total callsites needing JOIN after partition: **~13 in production code**
### Total callsites unaffected: **~40+ email queries that never touch body**

---

## Quick Win: SQL-Side Truncation

Before full partition, these truncations could be pushed to SQL to reduce egress immediately:

```python
# Instead of fetching full body then truncating in Python:
.select("id, subject, LEFT(body_text, 300) as body_preview")

# For signature extraction (only need tail):
.select("id, RIGHT(body_text, 1000) as signature_block")
```

**Limitation:** Supabase REST API (PostgREST) does not support SQL functions in `.select()`. These would need RPC wrappers or computed columns.

Alternative: Add a `body_preview` generated column (first 300 chars) to the emails table — instant for reads, maintained automatically.
