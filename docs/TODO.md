# TODO List

## CURRENT FOCUS: Frontend Analytics Dashboard (Phase 6)

**Timeline:** 2-3 weeks | **Tech Stack:** Next.js 14 + TypeScript + TailwindCSS + Recharts
**Goal:** Build analytics dashboard consuming all 30 backend endpoints

### Week 1: Core Infrastructure + Dashboard (5 days)

#### Day 1-2: Project Setup
- [ ] Initialize Next.js 14 project with TypeScript
- [ ] Setup TailwindCSS + shadcn/ui component library
- [ ] Create base layout with navigation
- [ ] Setup Axios API client (apiClient.ts)
- [ ] Define TypeScript types (mirror Pydantic models from backend)
- [ ] Create api/analytics.ts with all 30 endpoint wrappers
- [ ] Create api/extraction.ts for extraction endpoints
- [ ] Setup environment variables (.env.local)
- [ ] Configure CORS if needed

#### Day 3-4: Main Dashboard Page
- [ ] Create dashboard page layout
- [ ] Implement 4 metric cards (contacts, companies, threads, avg response time)
- [ ] Add engagement overview chart (6-month line chart)
- [ ] Create thread status breakdown (pie chart)
- [ ] Build top engaged contacts table (top 10)
- [ ] Build top engaged companies table (top 10)
- [ ] Add at-risk alerts section
- [ ] Integrate GET /api/v1/analytics/dashboard endpoint

#### Day 5: Shared Components
- [ ] Create MetricCard component (reusable)
- [ ] Create LoadingState/Skeleton components
- [ ] Create ErrorBoundary component
- [ ] Create Pagination component (reusable)
- [ ] Create FilterPanel component
- [ ] Create EmptyState component
- [ ] Create usePagination hook
- [ ] Create useAnalytics hook

### Week 2: Analytics Pages (5 days)

#### Day 6-7: Contacts Analytics
- [ ] Create contacts list page (/analytics/contacts)
- [ ] Implement contacts data table with sorting
- [ ] Add pagination controls (limit: 100, max: 500)
- [ ] Add filters (contact_type, engagement_score, is_decision_maker)
- [ ] Create contact detail modal/page
- [ ] Build top engaged contacts page (/analytics/contacts/top-engaged)
- [ ] Build at-risk contacts page (/analytics/contacts/at-risk)
- [ ] Build decision makers page (/analytics/contacts/decision-makers)
- [ ] Add export to CSV functionality
- [ ] Integrate 6 contact endpoints

#### Day 8-9: Companies Analytics
- [ ] Create companies list page (/analytics/companies)
- [ ] Implement companies cards/table view
- [ ] Add pagination + filters (engagement_status)
- [ ] Create company detail page (/analytics/companies/{id})
- [ ] Show company contacts in detail page
- [ ] Build top engaged companies page
- [ ] Build at-risk companies page
- [ ] Add companies by engagement status view
- [ ] Integrate 5 company endpoints

#### Day 10: Thread Analytics
- [ ] Create all threads page (/analytics/threads)
- [ ] Add thread status filters (complete, overdue, dropped, etc.)
- [ ] Create overdue threads page (critical view)
- [ ] Build thread status breakdown visualization
- [ ] Create thread detail view
- [ ] Add threads by contact view
- [ ] Integrate 4 thread endpoints

### Week 3: Advanced Features + Polish (5 days)

#### Day 11-12: Response Times & Patterns
- [ ] Create response time analytics page
- [ ] Build response time stats cards (avg, median, min, max)
- [ ] Create slowest responders table
- [ ] Add response time chart (bar/line)
- [ ] Create communication patterns page
- [ ] Build initiation ratio visualization (donut chart)
- [ ] Create frequency patterns heatmap
- [ ] Add engagement trends chart (line chart over time)
- [ ] Integrate 8 endpoints (4 response + 4 pattern)

#### Day 13-14: Extraction Job Management
- [ ] Create extraction trigger page (/extraction)
- [ ] Build extraction form (mailbox selector, mode, options)
- [ ] Add mode selector radio (Full vs Incremental)
- [ ] Create lookback days slider (1-365 days)
- [ ] Add extraction options checkboxes
- [ ] Build job history table with pagination
- [ ] Create real-time progress bar with polling (usePolling hook)
- [ ] Build job detail modal
- [ ] Add cancel job functionality
- [ ] Integrate 5 extraction endpoints

#### Day 15: Polish & Testing
- [ ] Add loading states to all pages
- [ ] Implement error handling for all API calls
- [ ] Make responsive design (mobile, tablet, desktop)
- [ ] Add accessibility features (ARIA labels, keyboard nav)
- [ ] Optimize performance (lazy loading, code splitting)
- [ ] Create end-to-end tests with Playwright/Cypress
- [ ] Final UX polish and bug fixes

---

## High Priority (After Frontend Dashboard)

### Processing Page UX Improvements
- [ ] Add status filter dropdown (All, Running, Completed, Failed, etc.)
  - Currently filtering by mailbox only
  - Could add additional status filtering in dropdown

### Code Cleanup
- [x] ~~Remove debug console.logs from apiClient.ts~~ (cleaned up Feb 2026)
- [x] ~~Remove debug console.logs from mailboxService.ts~~ (cleaned up Feb 2026)
- [ ] Remove debug console.logs from MailboxSelector.tsx
- [ ] Remove debug console.logs from emails.tsx loading
- [ ] Remove unused handler `handleMailboxSelect` from emails.tsx
- [ ] Fix deprecated `dropdownRender` usage in emails.tsx (use `dropdownRender` prop properly)

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