# Ant Design → shadcn/ui Migration Tracker

## Status: COMPLETE ✅ — 35+ files migrated, zero antd imports (8 Apr 2026)

---

### Pages — All Migrated ✅

#### Customers
- [x] `src/pages/analytics/companies.tsx`
- [x] `src/pages/analytics/company-detail.tsx`
- [x] `src/pages/analytics/contacts.tsx`
- [x] `src/pages/analytics/contact-detail.tsx`
- [x] `src/pages/analytics/threads.tsx`

#### Insights
- [x] `src/pages/intelligence/inbox.tsx`
- [x] `src/pages/intelligence/digest.tsx`
- [x] `src/pages/intelligence/opportunities.tsx`
- [x] `src/pages/intelligence/strategic-digest.tsx`
- [x] `src/pages/intelligence/vector-search.tsx`
- [x] `src/pages/intelligence/agent.tsx` (SSE streaming preserved)
- [x] `src/pages/analytics/email-rules.tsx`

#### Manage
- [x] `src/pages/analytics/response-times.tsx`
- [x] `src/pages/analytics/patterns.tsx`
- [x] `src/pages/analytics/data-health.tsx` (Thread Health card + Recompute + mailbox errors added)
- [x] `src/pages/processing.tsx`
- [x] `src/pages/errors.tsx`
- [x] `src/pages/manage/intelligence-config.tsx`

#### Admin
- [x] `src/pages/users.tsx`
- [x] `src/pages/clients.tsx`
- [x] `src/pages/settings.tsx`
- [x] `src/pages/extraction.tsx`
- [x] `src/pages/admin-data.tsx`
- [x] `src/pages/audit-logs.tsx`
- [x] `src/pages/manage/log-monitor.tsx`

#### QuickBase
- [x] `src/pages/intelligence/quickbase-config.tsx`
- [x] `src/pages/intelligence/quickbase-data.tsx`
- [x] `src/pages/intelligence/quickbase-matches.tsx`

#### Mailbox
- [x] `src/pages/mailboxes.tsx` (1107 lines — split during migration)
- [x] `src/pages/mailbox-process.tsx`
- [x] `src/components/MailboxCreateForm.tsx`
- [x] `src/components/MailboxEditForm.tsx`

#### AI Usage
- [x] `src/pages/intelligence/usage.tsx`
- [x] `src/pages/intelligence/playground.tsx`

#### Auth
- [x] `src/pages/login.tsx`
- [x] `src/pages/reset-password.tsx`
- [x] `src/pages/oauth-callback.tsx`

#### Dashboard
- [x] `src/pages/dashboard.tsx`
- [x] `src/pages/analytics/dashboard.tsx`

---

### Shared Components — All Migrated ✅

- [x] `src/components/layout.tsx`
- [x] `src/components/ProtectedRoute.tsx`
- [x] `src/components/EmailDetailPanel.tsx`
- [x] `src/components/DataTable.tsx`
- [x] `src/components/MailboxSelector.tsx`
- [x] `src/components/QBLinkWidget.tsx`
- [x] `src/components/SyncStatusBar.tsx`
- [x] `src/components/ProcessingStatusBadge.tsx`
- [x] `src/components/ErrorDisplay.tsx`
- [x] `src/components/GmailConnection.tsx`
- [x] `src/components/OutlookConnection.tsx`
- [x] `src/components/GoogleDriveConnection.tsx`
- [x] `src/components/GoogleDrivePicker.tsx`
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
- [x] `src/components/analytics/ChartCard.tsx`
- [x] `src/components/analytics/MetricCard.tsx`
- [x] `src/components/analytics/AnalyticsTable.tsx` — **deleted** (unused after TanStack Table migration)
- [x] `src/components/ai/ActionBucketTag.tsx`
- [x] `src/components/ai/FeedbackButtons.tsx`

---

### Infrastructure — Complete ✅

- [x] `src/App.tsx` — removed `ConfigProvider`, antd theme, `glass.css` import
- [x] `src/theme/glassTheme.ts` — **deleted** (114 lines)
- [x] `src/styles/glass.css` — **deleted** (1,855 lines)
- [x] `src/contexts/ClientContext.tsx` — new global client selector (`useClient()` hook)
- [x] `src/lib/risk-variants.ts` — new global risk pattern (`getRiskClass()`)

---

### New Primitives Added

| Component | Purpose |
|-----------|---------|
| `StatusBadge` | CVA variants using semantic token colors |
| `KPICard` | Metric display with trend |
| `PageShell` | Consistent page wrapper |
| `PageHeader` | Title + actions header |
| `ContentSkeleton` | Loading skeleton for page content |
| `EmptyState` | Zero-data placeholder |

---

## Design Decisions (locked in)

- **Component library:** shadcn/ui (new-york style) — Button, Card, Badge, Dialog, Sheet, DropdownMenu, Tabs, Tooltip, Avatar, Skeleton, Table, Select, Popover
- **Chart library:** Recharts (stays). Tremor for BarList only.
- **Semantic tokens:** `destructive` / `warning` / `success` / `risk` with `subtle` bg variants
- **Risk pattern:** `getRiskClass()` from `lib/risk-variants.ts` — single source of truth
- **cn():** Used in every component for Tailwind class merging
- **StatusBadge:** CVA variants using semantic token colors, not raw Tailwind
- **Global client:** `useClient()` context replaces per-page ClientSelector
- **Toast:** Sonner via `lib/toast.ts` — replaced 263 `message.*` calls
- **Icons:** Lucide React via `lib/icons.ts` — 37 mappings from `@ant-design/icons`
- **Number formatting:** `formatNumber()` utility with `'en-AU'` locale — zero bare `.toLocaleString()` calls remain
- **Typography:** Inter via Google Fonts preconnect

## Migration Rules (for any future components)

- Zero `from 'antd'` imports — hard rule
- Never use raw Tailwind colors (`bg-red-500`) — use semantic tokens (`bg-destructive`)
- All forms: react-hook-form + zod
- Preserve all business logic, SSE streaming, TanStack Query hooks — only swap UI layer
