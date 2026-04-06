# Ant Design → shadcn/ui Migration Tracker

## Status: In Progress — 24 migrated / 44 remaining

### Fully Migrated (zero antd) ✅
- [x] `src/components/layout.tsx` — Phase 2
- [x] `src/components/DataTable.tsx` — Phase 4
- [x] `src/components/AIInsightsCard.tsx` — Phase 4 (auto-trigger on load)
- [x] `src/components/StrikeRateCard.tsx` — Phase 4
- [x] `src/components/SeasonalityChart.tsx` — Phase 4
- [x] `src/components/CapabilityRhythmCard.tsx` — Phase 4
- [x] `src/components/ContactCapabilitiesCard.tsx` — Phase 4
- [x] `src/components/ProductProfileCard.tsx` — Phase 4
- [x] `src/components/RecommendationsPanel.tsx` — Phase 4
- [x] `src/components/OrderHistoryTable.tsx` — Phase 4
- [x] `src/components/analytics/EngagementBadge.tsx` — Phase 4
- [x] `src/components/analytics/LifecycleBadge.tsx` — Phase 4
- [x] `src/components/analytics/ClientSelector.tsx` — Phase 4
- [x] `src/pages/dashboard.tsx` — Phase 3
- [x] `src/pages/analytics/companies.tsx` — Phase 5
- [x] `src/pages/analytics/company-detail.tsx` — Phase 5
- [x] `src/pages/analytics/contacts.tsx` — Phase 5
- [x] `src/pages/analytics/contact-detail.tsx` — Phase 5
- [x] `src/pages/analytics/threads.tsx` — Phase 5
- [x] `src/pages/intelligence/vector-search.tsx` — Phase 5
- [x] `src/pages/oauth-callback.tsx` — Tier 1
- [x] `src/pages/extraction.tsx` — Tier 1
- [x] `src/contexts/ClientContext.tsx` — new (global client selector)
- [x] `src/lib/risk-variants.ts` — new (global risk pattern)

### Tier 1 — Form/settings pages (bulk migrate)
- [ ] `src/pages/settings.tsx`
- [ ] `src/pages/users.tsx`
- [ ] `src/pages/clients.tsx`
- [ ] `src/pages/login.tsx`
- [ ] `src/pages/reset-password.tsx`
- [ ] `src/pages/audit-logs.tsx`
- [ ] `src/pages/admin-data.tsx`
- [ ] `src/pages/manage/intelligence-config.tsx`
- [ ] `src/pages/manage/log-monitor.tsx`

### Tier 2 — Data views (DataTable already done)
- [ ] `src/pages/intelligence/quickbase-data.tsx`
- [ ] `src/pages/intelligence/quickbase-matches.tsx`
- [ ] `src/pages/intelligence/quickbase-config.tsx`
- [ ] `src/pages/intelligence/usage.tsx`
- [ ] `src/pages/intelligence/playground.tsx`
- [ ] `src/pages/processing.tsx`
- [ ] `src/pages/errors.tsx`
- [ ] `src/pages/analytics/dashboard.tsx`
- [ ] `src/pages/analytics/data-health.tsx`
- [ ] `src/pages/analytics/email-rules.tsx`
- [ ] `src/pages/analytics/patterns.tsx`
- [ ] `src/pages/analytics/response-times.tsx`

### Tier 3 — Complex interaction pages (careful migration)
- [ ] `src/pages/emails.tsx` (700+ lines — split first)
- [ ] `src/pages/intelligence/agent.tsx` (SSE streaming — preserve EventSource logic)
- [ ] `src/pages/intelligence/inbox.tsx`
- [ ] `src/pages/intelligence/digest.tsx`
- [ ] `src/pages/intelligence/strategic-digest.tsx`
- [ ] `src/pages/intelligence/opportunities.tsx`
- [ ] `src/pages/mailboxes.tsx` (1107 lines — split first)
- [ ] `src/pages/mailbox-process.tsx`

### Shared components still using antd
- [ ] `src/components/EmailDetailPanel.tsx`
- [ ] `src/components/MailboxSelector.tsx`
- [ ] `src/components/QBLinkWidget.tsx`
- [ ] `src/components/SyncStatusBar.tsx`
- [ ] `src/components/ProcessingStatusBadge.tsx`
- [ ] `src/components/ErrorDisplay.tsx`
- [ ] `src/components/GmailConnection.tsx`
- [ ] `src/components/OutlookConnection.tsx`
- [ ] `src/components/GoogleDriveConnection.tsx`
- [ ] `src/components/GoogleDrivePicker.tsx`
- [ ] `src/components/ai/ActionBucketTag.tsx`
- [ ] `src/components/ai/FeedbackButtons.tsx`
- [ ] `src/components/analytics/AnalyticsTable.tsx`
- [ ] `src/components/analytics/ChartCard.tsx`
- [ ] `src/components/analytics/EngagementTrendChart.tsx`
- [ ] `src/components/analytics/MetricCard.tsx`

### Config/theme (delete in Phase 9)
- [ ] `src/App.tsx` — remove ConfigProvider + antTheme
- [ ] `src/theme/glassTheme.ts` — delete
- [ ] `src/styles/glass.css` — delete

---

## Design Decisions (locked in)
- **Chart library:** Recharts (4 files, stays). No Nivo. Tremor for BarList only.
- **Semantic tokens:** `destructive`/`warning`/`success`/`risk` with `subtle` bg variants
- **Risk pattern:** `getRiskClass()` from `lib/risk-variants.ts` — single source of truth
- **cn():** Used in every component for Tailwind class merging
- **StatusBadge:** CVA variants using semantic token colors, not raw Tailwind
- **Global client:** `useClient()` context replaces per-page ClientSelector
- **Toast:** Sonner via `lib/toast.ts` replaces antd `message.*`
- **Icons:** Lucide React via `lib/icons.ts` replaces `@ant-design/icons`

## Migration Rules
- Every migrated page: **zero** `from 'antd'` imports — confirm before committing
- Never use raw Tailwind colors (`bg-red-500`) — use semantic tokens (`bg-destructive`)
- All forms: native HTML inputs during migration, react-hook-form + zod post-cleanup
- Preserve all business logic, SSE streaming, TanStack Query hooks — only swap UI layer
