# Ant Design → shadcn/ui Migration Tracker

## Status: In Progress

### Fully Migrated (zero antd)
- [x] `src/components/layout.tsx`
- [x] `src/components/DataTable.tsx`
- [x] `src/components/AIInsightsCard.tsx`
- [x] `src/components/StrikeRateCard.tsx`
- [x] `src/components/SeasonalityChart.tsx`
- [x] `src/components/CapabilityRhythmCard.tsx`
- [x] `src/components/ContactCapabilitiesCard.tsx`
- [x] `src/components/ProductProfileCard.tsx`
- [x] `src/components/RecommendationsPanel.tsx`
- [x] `src/components/OrderHistoryTable.tsx`
- [x] `src/components/analytics/EngagementBadge.tsx`
- [x] `src/components/analytics/LifecycleBadge.tsx`
- [x] `src/components/analytics/ClientSelector.tsx`
- [x] `src/pages/dashboard.tsx`
- [x] `src/pages/analytics/companies.tsx`
- [x] `src/pages/analytics/company-detail.tsx`
- [x] `src/pages/analytics/contacts.tsx`
- [x] `src/pages/analytics/contact-detail.tsx`
- [x] `src/pages/analytics/threads.tsx`
- [x] `src/pages/intelligence/vector-search.tsx`

### Still Using antd (46 files)

**Tier 1 — Form/settings pages (bulk migrate):**
- [ ] `src/pages/settings.tsx`
- [ ] `src/pages/users.tsx`
- [ ] `src/pages/clients.tsx`
- [ ] `src/pages/login.tsx`
- [ ] `src/pages/reset-password.tsx`
- [ ] `src/pages/oauth-callback.tsx`
- [ ] `src/pages/extraction.tsx`
- [ ] `src/pages/audit-logs.tsx`
- [ ] `src/pages/admin-data.tsx`
- [ ] `src/pages/manage/intelligence-config.tsx`
- [ ] `src/pages/manage/log-monitor.tsx`

**Tier 2 — Data views (DataTable already done):**
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

**Tier 3 — Complex interaction pages (careful migration):**
- [ ] `src/pages/emails.tsx` (700+ lines — split first)
- [ ] `src/pages/intelligence/agent.tsx` (SSE streaming)
- [ ] `src/pages/intelligence/inbox.tsx`
- [ ] `src/pages/intelligence/digest.tsx`
- [ ] `src/pages/intelligence/strategic-digest.tsx`
- [ ] `src/pages/intelligence/opportunities.tsx`
- [ ] `src/pages/mailboxes.tsx` (1107 lines)
- [ ] `src/pages/mailbox-process.tsx`

**Shared components still using antd:**
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

**Config/theme (delete in Phase 9):**
- [ ] `src/App.tsx` — remove ConfigProvider
- [ ] `src/theme/glassTheme.ts` — delete
- [ ] `src/styles/glass.css` — delete

## Design Decisions
- **Chart library:** Recharts (already in 4 files, stays)
- **Semantic tokens:** destructive/warning/success/risk with subtle variants
- **Risk pattern:** `getRiskClass()` from `lib/risk-variants.ts`
- **cn():** Used in every component for class merging
- **StatusBadge:** Customized with semantic token colors, not raw Tailwind
