# Bucket List: May 29 – June 2026

**Purpose:** Tracking all planned work items for the June sprint.
**Status convention:** [ ] not started / [~] in progress / [x] done + verified / [D] deferred next sprint

---

## Carryover from May sprint

### QB Match Review fixes

- [ ] **Candidates count mismatch** — tab badge shows 228 vs browse total 240. Different query definitions (tab counts unreviewed, browse shows all pending+unreviewed). Align queries
- [ ] **Method filter dropdown fix** — dropdown values stale (`exact_name`, `domain_root` don't match actual DB values `qb_create`, `qb_link`). Also 2 "unknown" method records to investigate
- [ ] **Fix email count sorting in matched view** — sorting by email count in QB matched companies view doesn't work correctly

### QB Data Quality

- [ ] **Contact creation from QB data** — 1,344 unmatched QB customers have emails in `qb_unique_emails` but no corresponding SB contacts. Need to create contacts from QB unique emails to enable matching
- [ ] **Email-method SB name correction** — ~4,250 email-matched QB customers have wrong SB company names (Carbon8 staff emails create false links). Needs: name-similarity guard on email_lookup + batch correction script
- [ ] **Manual-only unmatched cleanup** — 942 "No link (manual)" unmatched QB customers with $0 revenue. Decide: auto-dismiss or leave for review
- [ ] **Automate candidate review** — 972 staged candidates could be auto-promoted where confidence is high (exact name + same domain = auto-accept)

### Known-issue cleanup (carried from Week 1)

- [x] `hello@carbon8.com.au` mailbox extraction coverage — resolved (was 5.4%, now complete)
- [ ] 14 Carbon8 domain variant cleanup
- [ ] 21 weekdays with no email data investigation

---

## Feature work

### Invite User System

- [ ] Migration 014: `pending_invites` + user table columns + RLS policies
- [ ] RLS policy design: anon-readable by token only, admin-listable via backend auth
- [ ] Backend: 6 endpoints per design doc (`invites.py`)
- [ ] Frontend: InviteUserModal (two-step)
- [ ] Frontend: InviteAcceptPage (Paths A/B/C)
- [ ] Auth callback: invite detection hook
- [ ] Frontend: Users.tsx integration (pending invites merged into table, resend/revoke actions)
- [ ] Supabase config: `/invite/accept` and `/auth/callback` redirect URLs
- [ ] OAuth email-mismatch UX
- [ ] Test matrix: 3 paths x 3 providers x 4 states

### Insights Review page

- [ ] Migration: `insight_validations` table
- [ ] Backend endpoint: list insights per contact / per company
- [ ] Backend endpoint: record validation (correct / partial / incorrect + notes)
- [ ] Frontend page: list view with NL summary + source data link per insight
- [ ] Frontend: validation buttons + optional notes field
- [ ] Source data link wiring: traceback to emails / quotes / jobs

### Top-N page

- [ ] Frontend page listing top customers with NL insight summaries + source data links
- [ ] Ship validation buttons on insight cards (correct / partial / incorrect + notes)
- [ ] Manual spot-check 5-10 customer profile pages for data accuracy

---

## Architectural gaps

- [ ] **Email vectorisation during extraction** — new emails not automatically vectorised. Integrate into extraction pipeline post-Step 9
- [ ] **Embedding model not configurable** — hardcoded to Google `gemini-embedding-001`. UI selector planned
- [ ] **QB tag data -> analytics/AI** — capabilities, processes, embellishments synced on unique emails; wire into customer profiling, AI agent tools, digest generation

---

## Infrastructure & stabilization

### Staged worker rollout

- [ ] Staged rollout: analytics -> QB sync -> reembed -> remaining job types
- [ ] Verify all Tier 2 BackgroundTasks callsites work correctly alongside workers

### Operations Center UI consolidation

- [ ] Final merge plan: which features stay, which retire, which consolidate
- [ ] Move operational triggers from AI Usage into Data Health
- [ ] Move extraction features from Extraction page into Data Health
- [ ] Retire standalone Extraction page (redirect to Data Health)
- [ ] "Run Full Pipeline" button (creates `email_pipeline` job for selected mailbox)

### Supabase Data API grant enforcement

- [ ] **Backfill explicit GRANTs in migration templates** — Supabase will remove auto-grants on new `public` tables. Existing 55 tables verified safe (May 2026 audit). Ensure all future `CREATE TABLE` migrations include `GRANT ... TO anon, authenticated, service_role`. Docs updated (BEST_PRACTICES §1, DATABASE_DESIGN §10)

### Stabilization

- [ ] Smoke test checklist for daily partner use
- [ ] Confirm cron-based sync runs autonomously
- [ ] Confirm two-worker Railway Pro setup handles peak load unattended

---

## Deferred (not scheduled)

- [D] Industry Gap Analysis (Insight 2)
- [D] Real-time action signal alerts / Action Signal Engine
- [D] Role change notifications
- [D] Smart inbox revival
- [D] Vector search revival as user-facing feature
- [D] LinkedIn prospect replication
- [D] Daily/Strategic digest as user-facing features
- [D] AU seasonal calendar integration
- [D] Classification/digest model audit columns
- [D] Seasonality patterns query design + integration
- [D] Due for Reorder (reorder cycle, approaching-window flag)
- [D] Status Transition Analytics (C3) — blocked until ~July 2026
- [D] Operations embedding (615K rows)
- [D] Quotes embedding (~19K matched)
- [D] I/O budget fix (shared_buffers tuning, Redis caching for dashboard)
- [D] Dropped threads cleanup (thread recompute post-migration-080 verification)

---

## Flags / risks

- Invite User realistic estimate (8-9d) — may not fit in a single sprint depending on hours allocated
- 1,344 unmatched QB customers with emails is the biggest fixable revenue coverage gap
- Contact creation from QB data is a prerequisite for improving match coverage beyond 95.5%
