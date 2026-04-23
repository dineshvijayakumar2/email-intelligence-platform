# Bucket List: Actions Through May 14, 2026

**Purpose:** Tracking all planned work items for the pre-trip sprint.
**Not a schedule** — that's in SCOPE_LOCK_APR22_MAY14.md. This is a completeness checklist.
**Status convention:** [ ] not started / [~] in progress / [x] done + verified / [D] deferred post-trip

---

## Already shipped (Apr 22–23)

- [x] Migration 094: Pass 3 QB propagation (15,077 contacts updated)
- [x] Schema document (`DATABASE_DESIGN.md`)
- [x] Insight Engine Audit (`INSIGHT_ENGINE_AUDIT.md`)
- [x] Signature extraction code fix (`role_classifier.py:369-386`, 11 sign-off phrases added)
- [x] Shared-address pattern expansion (`contact_extractor.py:110-127`, 17 patterns added)
- [x] Pass 3 exclusion logic (`094_propagate_qb_from_company.sql:53-73`) — **FLAG:** confirm whether this file edit is safe given 094 already ran in prod
- [x] Migration 095 cleanup (internal/shared contact QB tier nulling)
- [x] AI backfill chunked loop (`ai_backfill.py:58-89`)
- [x] Auth state audit (verdict: 5-6d per breakdown, my read 8-9d — slotted into scope discussion)
- [x] I/O budget investigation (Postgres buffer pool pressure identified)
- [x] Dropped threads investigation (likely expected aging behaviour)

---

## Data hardening — Week 1 core

### Embedding re-embed (added Apr 23 — priority)

- [ ] Migration: add `embedding_model` + `embedded_at` to `emails`, `qb_operations`, `customer_companies`
- [ ] `vector_service.py` updated to populate both columns on every embed write
- [ ] Verify `reembed_all()` / `BulkIndexManager` handles drop-rebuild cleanly for 258K rows
- [ ] OpenAI rate-limit handling: confirm runner respects `retry-after` headers with backoff
- [ ] Idempotency + resumability check on runner
- [ ] Scope query: null-out SQL for all non-OpenAI-768 rows (emails ~210K + operations ~6,800 from scratch since only 1% embedded anyway)
- [ ] Verification SQL written before kickoff (single-model count check)
- [ ] HNSW index drop, re-embed run, index rebuild
- [ ] Verification run: all rows have `embedding_model = 'text-embedding-3-small-768'`, no NULLs
- [ ] Spot-check semantic search quality on 20 known queries before/after

### Signature re-extraction (titles)

- [ ] Validation pass: 50-100 known-case emails through GPT-4o-mini, compare to expected
- [ ] Scope query: contacts with `title` matching 11 sign-off phrases (surgical, not full)
- [ ] Snapshot table: `(contact_id, old_title, snapshotted_at)` before overwrite
- [ ] Idempotent runner (completed_steps pattern)
- [ ] Verification SQL before kickoff
- [ ] Run + verify
- [ ] Consider: should signature re-extraction also populate a `title_extracted_model` column for future audits?

### Internal / shared contact propagation

- [~] Migration 095 applied? (confirm in prod, your standing rule)
- [ ] Verification SQL: zero internal contacts with Carbon8 QB tier, zero shared addresses with inherited QB data
- [ ] Spot-check: Carbon8 employees, `accounts@`, `hello@`, `noreply@` contacts

### AI classification coverage

- [ ] Run chunked backfill on AM mailboxes (Linda, Ehab, Kenneth, Nic, Jeff, Peter, Prince)
- [ ] Verify 80%+ coverage on last 90 days per mailbox
- [ ] Decide: does this run after or in parallel with re-embed? (Embeddings vs classifications are different API budgets, so parallel is fine)

### Known-issue cleanup (Week 1 fixes not yet done)

- [ ] `hello@carbon8.com.au` mailbox at 5.4% coverage — [D] deferred post-trip per scope doc
- [ ] 14 Carbon8 domain variants — [D] deferred post-trip per scope doc
- [ ] 21 weekdays with no email data investigation — [D] deferred post-trip

---

## AI config page hardening (added Apr 23)

- [ ] **Resolve dual-source-of-truth for embedding provider:** `EMBEDDING_PROVIDER` env var exists in Railway AND `system_settings` DB row exists — two mechanisms, can disagree silently
- [ ] Decision: env var is source of truth, remove embedding dropdown from UI (recommended — the dropdown is the root cause of today's rework)
- [ ] Remove embedding model dropdown from AI config page
- [ ] Keep LLM dropdowns (Email Analysis, Daily Digest, Strategic Digest, Entity Insights) — those are stateless, safe to toggle
- [ ] Audit code paths: confirm only env var is read at runtime after dropdown removal
- [ ] Consider storing model name on classification / digest / extraction rows for audit (post-trip if not core to MVP)

---

## Insight engine — Week 2 core

### Cross-Company Gaps

- [ ] Revive `cross_gap_intelligence.py`
- [ ] Fix data joins (specific fixes TBD from code review)
- [ ] Verify output on 5 known Carbon8 companies
- [ ] Natural-language summary via digest prompt templates
- [ ] Time-box the revival: if join fixes exceed 6h, explicit rewrite-vs-patch decision

### Insights Review page shell

- [ ] Migration: `insight_validations` table
- [ ] Backend endpoint: list insights per contact / per company
- [ ] Backend endpoint: record validation (correct / partial / incorrect + notes)
- [ ] Frontend page: list view with NL summary + source data link per insight
- [ ] Frontend: validation buttons + optional notes field
- [ ] Source data link wiring: traceback to emails / quotes / jobs

---

## Insight engine — Week 3 core

### Seasonality Patterns

- [ ] Query design: annual ordering cycle per customer from QB quotes/jobs (10yr history)
- [ ] Backend endpoint
- [ ] Integration into Insights Review page
- [ ] Spot-check on 5 known seasonal customers

### Due for Reorder

- [ ] Query design: per-customer typical reorder cycle, approaching-window flag
- [ ] Backend endpoint
- [ ] Integration into Insights Review page
- [ ] Per scope doc: **first to drop if Week 3 compresses**

---

## Invite User flow — Week 3

- [ ] Migration 014: `pending_invites` + user table columns + RLS policies
- [ ] **RLS policy design:** anon-readable by token only, admin-listable via backend auth (flagged in earlier audit)
- [ ] Backend: 6 endpoints per design doc (`invites.py`)
- [ ] Frontend: InviteUserModal (two-step)
- [ ] Frontend: InviteAcceptPage (Paths A/B/C)
- [ ] Auth callback: invite detection hook
- [ ] Frontend: Users.tsx integration (pending invites merged into table, resend/revoke actions)
- [ ] Supabase config: `/invite/accept` and `/auth/callback` redirect URLs
- [ ] Tailwind+shadcn vs Ant Design decision (design doc is Ant; migration is ongoing)
- [ ] OAuth email-mismatch UX: what does user see when they sign in with a different email than the invite?
- [ ] Test matrix: 3 paths × 3 providers × 4 states (valid/expired/revoked/already-accepted)

---

## Stabilization — Week 3 tail + Week 4

- [ ] Runbook: how partner adds a new mailbox/user without your involvement
- [ ] Runbook: common failure modes and recovery (pipeline jobs, sync issues)
- [ ] Smoke test checklist for daily partner use
- [ ] Confirm cron-based sync runs autonomously during trip window
- [ ] Confirm two-worker Railway Pro setup handles peak load unattended
- [ ] Pre-trip freeze: no deploys after May 13 EOD

---

## Deferred to post-trip (explicit)

- [D] Industry Gap Analysis (Insight 2) — including its Week 1 distribution query validation
- [D] Real-time action signal alerts / Action Signal Engine
- [D] Role change notifications
- [D] Smart inbox revival
- [D] Vector search revival as user-facing feature
- [D] LinkedIn prospect replication
- [D] Daily/Strategic digest as user-facing features
- [D] AU seasonal calendar integration
- [D] Embedding config UI: option 2 full migration-trigger flow
- [D] Classification/digest model audit columns
- [D] `hello@carbon8.com.au` classification coverage
- [D] 14 Carbon8 domain variant cleanup
- [D] 21-weekdays-no-data investigation
- [D] I/O budget fix (shared_buffers tuning, Redis caching for dashboard)
- [D] Dropped threads cleanup (thread recompute post-migration-080 verification)

---

## Open decisions (need answers before moving forward)

- [ ] Invite User UI: Ant Design (match design doc) or Tailwind+shadcn (match migration direction)
- [ ] Parent visit specific days — **still unresolved from scope lock doc**
- [ ] Re-embed run scheduling: during work hours (search degraded briefly) or overnight?

---

## Flags / risks being tracked

- Re-embed + title re-extraction + classification backfill = three big re-processing jobs stacked in Week 1 during a parent-visit week
- Cross-Gap revival may expand if join fixes reveal deeper schema issues
- Week 3 is doing 3 features + starting stabilization in 30h — tight
- Week 4 is 2 days of handoff only, not a full stabilization week
- Invite User realistic estimate (8-9d per my read) larger than Week 3 allocation can absorb; decision deferred per user
