# TODO List

## CURRENT FOCUS: Sprint 3 AI Layer

### Sprint 3 Phase 1: Semantic Intent & Sentiment Engine
- [ ] Create `AIIntentProcessor` service — classify emails into strategic categories
  - Categories: Pricing Inquiry, Feature Request, Expansion Signal, Churn Risk
  - Use Claude API (latest model, cost-optimized)
- [ ] Add `sentiment_score` field to customer_contacts and emails
- [ ] Build sentiment drift detection — track tone shifts across email threads
- [ ] Create urgency detection — identify hidden urgency from email body context
- [ ] Update `normalizer.py` to include `body_summary` and `detected_sentiment` fields
- [ ] Modify `email_tagger.py` to call Claude API for intent classification on emails >100 chars
- [ ] Build AI usage tracking table and admin dashboard for cost control

### Sprint 3 Phase 2: Entity & Opportunity Extraction
- [ ] Automate detection of competitors, product names, budget mentions in emails
- [ ] Modify `engagement_scorer.py` to weight buying signals (procurement, legal review, implementation timeline)
- [ ] Use Claude to infer job functions from email signatures when `title_parser.py` fails
- [ ] Create `business_entities` table for extracted entities

### Sprint 3 Phase 3: Hidden Network & Relationship Insights
- [ ] Implement influence mapping — track high-seniority CC entries as "Stakeholder Entry" insights
- [ ] Build communication gap analysis — flag single-contact-dependency risk
- [ ] Add relationship summarization — Claude-generated 3-sentence executive summaries
- [ ] Add summary to contact-detail page

### Sprint 3 Phase 4: Proactive "Next Best Action"
- [ ] Build suggested responses — AI-drafted replies based on thread history and intent
- [ ] Create proactive churn alerts — auto-flag accounts with >30% engagement velocity drop
- [ ] Build marketing trigger exports — identify champions, export to CSV/CRM
- [ ] Update dashboard with "Top Opportunities" card based on AI-detected buying signals

---

## Frontend Analytics Dashboard

**Status:** ✅ COMPLETE (Feb 2026)
**Tech Stack:** React + Vite + Ant Design + Recharts

### Analytics Pages — ALL COMPLETE
- [x] Analytics dashboard page (overview metrics, client selector, extraction trigger)
- [x] Contacts analytics (All/Top/At-Risk/DMs/By-Type tabs, sort, filter, score slider)
- [x] Companies analytics (All/Top/At-Risk/By-Engagement tabs, sort, filter, score slider)
- [x] Thread analytics (All/Overdue/By-Status tabs, status chart, sort, filter)
- [x] Contact detail drill-down (stats, threads, communication patterns)
- [x] Company detail drill-down (stats, top contacts, threads)
- [x] Admin Data View (raw table browser, search, sort, pagination, CSV export)

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
- [ ] Implement email threading
- [ ] Add email labels/tags
- [ ] Export email data (CSV, JSON)
- [ ] Advanced search with boolean operators
- [ ] Saved searches/filters

## Completed ✅

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