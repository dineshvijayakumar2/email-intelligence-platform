# TODO List

## NEXT UP: Invite User System

### Invite User — Restrict Open Sign-Up (Planned)
Design: `docs/INVITE_USER_SMTPLESS.md`

- [ ] Migration 014: Create `pending_invites` table + user_profiles invite columns
- [ ] Backend: `invites.py` router — 6 endpoints (create, validate, accept, list, resend, revoke)
- [ ] Backend: Auto-create inactive mailbox on invite acceptance (detect gmail/outlook from email domain)
- [ ] Register invites router in `main.py`
- [ ] Frontend: Remove "Create Account" tab from login page (invite-only)
- [ ] Frontend: `InviteUserModal.tsx` — two-step modal (form → delivery options)
- [ ] Frontend: `invite-accept.tsx` — public invite acceptance page with OAuth/magic link sign-in
- [ ] Frontend: Update Users page — "Invite User" button + pending invites in table
- [ ] Frontend: Update AuthContext — invite acceptance check on login
- [ ] Frontend: Dashboard banner — "Connect your email" prompt for unconnected mailboxes

---

## PRIORITY FIXES: Sprint 3 AI Issues — ALL RESOLVED ✅

- [x] **Fix 1:** Date filtering — `date_from`/`date_to` params with 7-day default + frontend date range selector
- [x] **Fix 2:** Daily/Weekly digest — `digest_type` param, TZ-aware boundaries, migration 015
- [x] **Fix 3:** Cost reduction — batch 10→20, body 500→300, trivial skip (<50 chars), forward-only skip
- [x] **Fix 4:** Churn risk too sensitive — strict exit-intent-only classification, 0.6 confidence threshold (Mar 9)
- [x] **Fix 5:** Digest restates visible stats — prompt rewritten for non-obvious insights only (Mar 9)

---

## CURRENT FOCUS: Sprint 3 AI Layer

Full plan: `docs/AI_MVP_PLAN.md` (3-week session-by-session plan + implementation status)

### Week 1: Intelligence Engine + Buckets + Digest — ✅ COMPLETE
- [x] Session 1: DB migration + AI client + privacy filter + usage tracker
- [x] Session 2: Email analyzer (classify + extract entities + justify)
- [x] Session 3: Action bucket engine (zero AI cost)
- [x] Session 4: Entity aggregator + all API endpoints (19 endpoints in `ai.py`)
- [x] Session 5: Digest service (bucket-aware)

### Week 2: Dashboard Integration + Opportunities — PARTIAL (Frontend pages done, backend integration pending)
- [x] Session 6: Digest + Smart Inbox frontend (4 pages: inbox, digest, opportunities, usage)
- [ ] Session 7: Relationship summary service (`ai_relationship_summarizer.py`)
- [ ] Session 8: Company detail page AI cards
- [ ] Session 9: Opportunities page Tab 5 (Budget Discussions) — 4 of 5 tabs done
- [ ] Session 10: AM Comparison + Gap Alerts

### Week 3: Polish + Deploy — NOT STARTED
- [ ] Session 11: Navigation + usage page + cross-linking (sidebar done, Quick Insights not built)
- [ ] Session 12: Integration testing
- [ ] Session 13: Production deploy + docs

---

## Frontend Analytics Dashboard

**Status:** ✅ COMPLETE (Feb 2026)
**Tech Stack:** React + Vite + Ant Design + Recharts

### Analytics Pages — ALL COMPLETE
- [x] Analytics dashboard page (overview metrics, client selector, period selector, extraction trigger)
- [x] Contacts analytics (All/Top/At-Risk/DMs/By-Type tabs, sort, filter, score slider, search)
- [x] Companies analytics (All/Top/At-Risk/By-Engagement tabs, sort, filter, score slider, search)
- [x] Thread analytics (single table, status/search filters, URL param drilldown)
- [x] Contact detail drill-down (stats, threads table, patterns, clickable KPIs → emails/threads page)
- [x] Company detail drill-down (stats, threads table, clickable KPIs → emails/contacts/threads page)
- [x] Admin Data View (raw table browser, search, sort, pagination, CSV export)

### Analytics UX Overhaul — ✅ COMPLETE (Mar 10, 2026)
- [x] Cross-page drilldown: threads → emails, contacts → emails/threads, companies → emails/contacts/threads
- [x] Thread drilldown: click thread subject → emails page filtered by thread_id (iframe HTML rendering)
- [x] Emails page: supports thread_id, contact_id, company_id URL params for analytics mode
- [x] Threads page: supports contact_id, company_id, status URL params for drilldown
- [x] Clickable counts: Sent/Received on contacts, Emails/Contacts/DMs on companies → drilldown pages
- [x] Dashboard period selector (7d/30d/90d/6m/1y) — filters engagement, threads, response times
- [x] Dashboard client-scoped threads + response times (was fetching all clients)
- [x] ClientSelector: module-level cache + optimistic localStorage ID (instant page load)
- [x] Search on companies + threads pages (server-side ilike)
- [x] Smart Inbox: column filters (bucket/urgency/intent/sentiment) + sorting on all columns
- [x] Smart Inbox: email body preview in drawer (iframe HTML + plain text toggle)
- [x] Removed engagement trend chart from detail pages (micro-level noise)
- [x] Removed threads page tabs (single table with filters instead)

---

## High Priority

### Processing Page UX Improvements
- [ ] Add status filter dropdown (All, Running, Completed, Failed, etc.)

### Code Cleanup
- [x] ~~Remove debug console.logs from apiClient.ts~~ (cleaned up Feb 2026)
- [x] ~~Remove debug console.logs from mailboxService.ts~~ (cleaned up Feb 2026)
- [ ] Remove debug console.logs from MailboxSelector.tsx
- [ ] Remove debug console.logs from emails.tsx loading
- [ ] Remove unused handler `handleMailboxSelect` from emails.tsx
- [ ] Fix deprecated `dropdownRender` usage in emails.tsx

## Medium Priority

### Testing
- [ ] Add E2E tests for mailbox switching flow
  - [ ] Test route navigation
  - [ ] Test skeleton display
  - [ ] Test empty states
  - [ ] Test React Strict Mode compatibility
- [ ] Add unit tests for email loading guards
- [ ] Add integration tests for folder switching

### Performance
- [ ] Consider implementing virtual scrolling for large email lists
- [ ] Add request debouncing for search input
- [ ] Implement intelligent prefetching for next folder
- [ ] Cache folder lists per mailbox

### UX Enhancements
- [ ] Add keyboard shortcuts for folder navigation
- [ ] Add bulk actions for emails
- [ ] Implement email preview on hover
- [ ] Add "Mark as read/unread" functionality

## Low Priority

### Documentation
- [ ] Add JSDoc comments to key functions
- [ ] Create architecture diagrams
- [ ] Document state management patterns
- [ ] Add API documentation

### Monitoring
- [ ] Add analytics for user navigation patterns
- [ ] Track mailbox switch performance metrics
- [ ] Monitor API response times
- [ ] Add error tracking (Sentry integration?)

### Nice to Have
- [ ] Add dark mode support
- [x] ~~Implement email threading~~ (Threading overhaul: multi-priority thread ID, provider IDs, confidence scoring)
- [ ] Add email labels/tags
- [ ] Export email data (CSV, JSON)
- [ ] Advanced search with boolean operators
- [ ] Saved searches/filters

## Completed ✅

### Phase B: Operational Intelligence (Mar 9, 2026)
- [x] **B1: Business Hours Metrics** — timezone/BH config on user_profiles, BH response time calc (dateutil.tz), settings API + page, migration 016
- [x] **B2: Metric Versioning** — metric_history table, scoring_version tracking, EngagementTrendChart on contact/company detail, migration 017
- [x] **B3: Data Health Dashboard** — sync lag per mailbox, identity resolution coverage, thread distribution, missing weekday detection, extraction job health
- [x] **AI Churn Risk Tightened** — strict exit-intent-only, 0.6 confidence threshold, complaints no longer auto-churn
- [x] **AI Digest Rewritten** — insight-focused prompt (no stat regurgitation), fallback to is_outbound
- [x] **AI Credits Card** — daily/monthly remaining on Usage page
- [x] **B4: Audit Logging** — audit_log table (migration 018), `audit.py` utility, hooked into auth (settings, roles, user activate/deactivate, client assignments), gmail/outlook sync, AI analyze, extraction, mailbox create/delete

### Analytics Enhancements (Mar 6, 2026)
- [x] **Reusable EmailDetailPanel** — Extracted from emails.tsx into `frontend/src/components/EmailDetailPanel.tsx` with all helpers
- [x] **Contact search** — Backend `search` param on `GET /contacts` (name/email/company), frontend `Input.Search` on contacts page
- [x] **Contact detail: linked emails** — `GET /contacts/{id}/emails` endpoint + table + email preview Drawer
- [x] **Contact detail: Total Emails fix** — Use live count from linked emails instead of stale cached values
- [x] **Company detail: linked emails** — `GET /companies/{id}/emails` endpoint + table + email preview Drawer
- [x] **AI Summarise Email** — `POST /ai/summarize/{email_id}` (Haiku), "Summarise" button in EmailDetailPanel across all pages
- [x] **Sync improvements** — Per-folder sync limits (both Gmail/Outlook), recursive Outlook folder loading, folder filter aliases
- [x] **Post-sync extraction** — Auto-trigger Sprint 2 extraction pipeline after email sync completes
- [x] **RPC error fix** — Removed stale `get_job_errors_summary` RPC call, kept Python fallback aggregation

### Performance Optimizations (Mar 4, 2026)
- [x] **Email Rules page**: Combined `/analytics/{client_id}/full` endpoint (3 DB queries, down from 66-151), read-only load, manual "Sync Rules" button
- [x] **Email Rules backend**: Batch queries (`_batch_query_rules`), single-pass `get_full_analytics()`, extracted `_compute_insights()`
- [x] **AuthContext**: Deduplicated `/api/auth/me` calls — `onAuthStateChange` as single source, `mounted` guard (was 4-5x per load)
- [x] **apiClient timeout**: Increased default 5s → 15s, rules analytics 30s (fixed empty data from AbortError)
- [x] **Inbox page**: Parallelized `loadData` + `loadBucketSummary` with `Promise.all()`
- [x] **Opportunities page**: Parallelized 4 API calls with `Promise.all()`, removed wasteful client_id resolution call

### Documentation Cleanup (Mar 3, 2026)
- [x] Consolidated AI MVP plans (v2, v3, v3.1, v3.2) into single `AI_MVP_PLAN.md` (final)
- [x] Updated CLAUDE.md with invite system plan + current status
- [x] Updated CONTINUATION_GUIDE.md with invite system + AI MVP references
- [x] Updated TODO.md with structured Sprint 3 session plan
- [x] Documented invite user system requirements in `INVITE_USER_SMTPLESS.md`

### Post-Production Fixes (Feb 26-27, 2026)
- [x] **Fix uniform engagement scores** — comm_pattern_analyzer missing 3 fields + wrong field name, company scorer had hardcoded values
- [x] **Migration 011** — Fix RPC functions for email counts, contact dates, thread data
- [x] **Migration 012** — Backfill scoring input fields (last_inbound/outbound, emails_per_month_avg, initiation_ratio, reply_rate, frequency_trend)
- [x] **Fix 'unknown' seniority label** — Hide seniority tag when value is 'unknown' on contact detail page
- [x] **Fix min score 500 error** — Cast float to int before Supabase `.gte()` on INTEGER columns
- [x] **Engagement label display** — Show "High"/"Medium"/"Low"/"Very Low" labels alongside numeric scores
- [x] **Slider UX fix** — Use `onChangeComplete` instead of `onChange` for API triggers (contacts + companies pages)

### Analytics Frontend — COMPLETE (Feb 26-27, 2026)
- [x] Dashboard page (client selector, overview metrics, extraction trigger)
- [x] Contacts page (All/Top/At-Risk/DMs/By-Type tabs, sort, filter, engagement score slider)
- [x] Companies page (All/Top/At-Risk/By-Engagement tabs, sort, filter, score slider)
- [x] Threads page (All/Overdue/By-Status tabs, status chart, sort, filter)
- [x] Contact detail page (stats, threads, communication patterns, engagement badge)
- [x] Company detail page (stats, top contacts, threads)
- [x] Admin Data View (raw table browser with search, sort, pagination, CSV export)

### Sprint 2 Backend — ALL PHASES COMPLETE (Feb 2026)
- [x] **Phase 1-2:** 13-step extraction pipeline (orchestrator + 8 services + 3 utilities)
- [x] **Phase 4:** Engagement analytics (response times, thread tracking, comm patterns, 8-factor scoring)
- [x] **Phase 5A:** 30 REST API analytics endpoints (2,886 lines, 41 Pydantic models)
- [x] **Phase 5B:** Incremental extraction mode (Migration 010, configurable lookback)
- [x] **Phase 6:** Production deployment + 5 critical fixes:
  - NULL processing_status exclusion → Python-side filtering
  - Supabase .or_() compatibility → removed server-side filter
  - Pagination off-by-one → len==0 break condition
  - Transient SSL errors → retry with exponential backoff
  - Count visibility → upfront COUNT + page X/Y logging
- [x] **Production verified:** 26,654 emails across 54 pages processed successfully
- [x] **12 database migrations** run and verified (v1.8+ master schema)

### Performance & Stability Fixes (Feb 23-24, 2026)
- [x] **CRITICAL**: Remove `error_log` from `/processing-jobs` SELECT (620KB → ~20KB response)
- [x] Add `.limit(100)` to processing-jobs query
- [x] Simplify mailboxService retry logic (removed nested 3x retry amplification)
- [x] Simplify dashboardService retry logic (removed nested 3x retry amplification)
- [x] Clean up debug logging from apiClient.ts and backend/main.py
- [x] Remove unused `JSONResponse` import and `response_model=list` from mailboxes endpoint

### WebSocket Fixes (Feb 23, 2026)
- [x] Fix "WebSocket is not connected. Need to call 'accept' first" errors
- [x] Accept WebSocket before closing/sending in routes.py exception handlers
- [x] Add RuntimeError-specific handling in manager.py send_personal

### Email Address Guardrails (Feb 23, 2026)
- [x] Auto-populate email_address after Gmail/Outlook OAuth linking
- [x] Post-OAuth email validation to prevent mismatched account linking
- [x] Backend validation in update_mailbox to prevent email address changes when connection exists
- [x] Make email_address field read-only in MailboxCreateForm and MailboxEditForm

### LIVE Sync Fixes (Feb 23-24, 2026)
- [x] Dashboard shows "Sync" button for MBOX/OLM mailboxes with live sync linked
- [x] Fix `last_sync_at` not updating on mailboxes table after Gmail/Outlook sync
- [x] Fix date-range fetch navigation to include mailbox ID (`/processing/{mailboxId}`)
- [x] Fix "View Sync History" navigation to include mailbox ID

### Port & Environment (Feb 23, 2026)
- [x] Change frontend port from 3000 to 3001 (avoid conflicts)
- [x] Update CORS ALLOWED_ORIGINS to port 3001
- [x] Update Google/Microsoft redirect URIs to port 3001

### Emails Page
- [x] Route-based navigation for emails (`/emails/:mailboxId`)
- [x] Move mailbox selector to top-right dropdown
- [x] Instant skeleton feedback for mailbox switching
- [x] Remove "all mailboxes" view
- [x] Fix React Strict Mode mailbox dropdown issue
- [x] Clear totalCount when switching folders
- [x] Add proper empty states
- [x] Fix initial loadEmails() call
- [x] Add strict mailbox guards

### Processing Page
- [x] Route-based filtering (`/processing/:mailboxId`)
- [x] Add MailboxSelector to top-right header
- [x] Instant loading feedback when switching mailboxes
- [x] Filter jobs by selected mailbox
- [x] Optimistic UI updates for filter switching

### General
- [x] Organize troubleshooting scripts into `scripts/troubleshooting/`
- [x] Move documentation to `docs/` folder

## Blocked/Waiting

None currently

## Notes

### Performance Considerations
- React Strict Mode causes double mounting in development - handled gracefully
- API response caching could improve perceived performance
- Consider implementing optimistic updates for more actions

### Architecture Decisions
- URL as source of truth for mailbox selection (enables deep linking, browser back/forward)
- Optimistic UI updates for instant feedback (better UX than waiting for server)
- Strict guards prevent invalid states (defensive programming)

### Future Considerations
- Consider using React Query or SWR for data fetching
- Evaluate moving to Zustand or Redux for complex state management
- Consider implementing command pattern for undo/redo