# Changelog

All notable changes to the Email Intelligence Platform will be documented in this file.

## [2026-03-10] Analytics UX Overhaul & Cross-Page Drilldown

### Added
- **Thread drilldown**: Click thread subject on contact/company detail → emails page filtered by `thread_id` with HTML email rendering
- **Threads page drilldown**: URL params `contact_id`, `company_id`, `status` for filtered views from detail pages
- **Dashboard period selector**: Filter all metrics by time period (7d / 30d / 90d / 6m / 1y)
- **Company threads table**: Company detail page now shows thread list with clickable subjects
- **Contact threads clickable**: Thread subjects → emails page, thread header → threads page
- **Company search**: Server-side search by company name or industry on companies page
- **Thread search**: Server-side search by thread subject on threads page
- **Smart Inbox column filters**: Filter by bucket, urgency, intent, sentiment directly from column headers
- **Smart Inbox sorting**: All columns sortable (urgency, subject, sender, date, sentiment, intent)
- **Smart Inbox email preview**: Iframe HTML email body rendering in drawer with HTML/text toggle
- **Thread detail endpoint**: `GET /threads/{thread_id}/emails` returns full thread with all emails
- **Company threads endpoint**: `GET /threads/by-company/{company_id}` returns threads for a company
- **Live email counts**: Backend returns `total_sent`, `total_received` for contacts and companies
- **Clickable counts everywhere**: Sent/Received on contacts, Emails/Contacts/DMs on companies → drilldown pages
- **Analytics mode on Emails page**: `?contact_id`, `?company_id`, `?thread_id` URL params for cross-mailbox view

### Changed
- **Navigation menu reorganized**: 11 items → 5 top-level (Dashboard, Emails, Intelligence, Analytics, Manage)
- **Threads page simplified**: Removed tabs (All/Overdue/By-Status), single table with status + search filters
- **Dashboard scoped to client**: Thread counts and response times now filtered by client's mailboxes (was global)
- **ClientSelector optimized**: Module-level cache (single fetch across all pages) + optimistic localStorage ID
- **Thread status filter**: Maps frontend enum values to all possible DB values (e.g., "active" → ongoing + awaiting_our_response)
- **Contact/Company detail simplified**: Removed inline email tables/drawers, uses clickable KPIs → emails page
- Email Rules moved from Analytics to Manage submenu; AI Usage moved from Intelligence to Manage
- Removed engagement trend chart from detail pages (micro-level noise)

### Fixed
- Dashboard thread counts not filtered by client (was fetching all clients' threads)
- Dashboard response times not filtered by client
- Emails Sent/Received showing stale stored values (now live from DB)
- Thread status filter not matching DB enum variants (awaiting_reply vs awaiting_response)
- Overdue threads endpoint not filtered by client
- Company emails endpoint pagination bug

---

## [Unreleased]

### Added
- Route-based navigation for mailbox selection (`/emails/:mailboxId`)
- Route-based filtering for Processing page (`/processing/:mailboxId`)
- Mailbox selector dropdown on Processing page header
- Instant skeleton feedback when switching mailboxes, folders, or filters
- Empty states when no mailbox is selected
- Debug logging for mailbox loading and email fetching

### Changed
- Moved mailbox selector from left sidebar to top-right dropdown (Gmail-style UX)
- Processing page now filters jobs by selected mailbox (shows all when none selected)
- Removed "all mailboxes" view - always require mailbox selection in Emails page
- Optimized folder switching to show skeleton immediately
- Stats bar now updates only after new data loads (not during loading)

### Fixed
- Mailbox dropdown becoming empty on page refresh (React Strict Mode issue)
- Stale email data briefly showing when switching mailboxes
- Stale counts showing with new folder labels
- Initial page load attempting to load all emails from all mailboxes
- RPC function `get_user_accessible_mailboxes` to handle roles array

### Technical
- Improved state management with URL as source of truth
- Optimistic UI updates for instant perceived performance
- Strict guards to prevent loading emails without valid mailbox
- Better handling of React 18 Strict Mode double-mounting

## [Previous Changes]

### Authentication & Authorization
- Supabase Auth integration (email, Google, Microsoft OAuth)
- Role-based access control (admin, client_manager, account_manager)
- Row-level security (RLS) for mailbox access

### Gmail Live Sync
- Gmail LIVE sync via Pub/Sub
- Extended permission system for full Gmail access
- Real-time email syncing from Gmail accounts

### Processing
- Background job processing for email extraction
- Progress tracking with ETAs
- Job restart with cached downloads
- Reprocessing completed jobs with categorization

### Email Features
- Email list view with folders
- Email detail panel
- Category filtering
- Date range filtering
- Attachment support
- Search functionality

### Mailbox Management
- Multi-format support (MBOX, PST, OLM, Gmail, Outlook)
- Google Drive integration for mailbox files
- Client and user assignment
- Active/inactive status management

### Dashboard
- System metrics overview
- Recent processing jobs
- Quick actions for common tasks