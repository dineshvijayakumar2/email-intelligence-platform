# Changelog

All notable changes to the Email Intelligence Platform will be documented in this file.

## [2026-03-06] Analytics UX & Navigation Overhaul

### Added
- **Analytics mode on Emails page**: Navigate from contact/company detail → emails page with cross-mailbox filter (`?contact_id`, `?company_id` URL params), banner with back button
- **Clickable KPIs**: Total Emails → emails page, Contacts/Decision Makers → filtered contacts page
- **Live email counts**: Backend endpoints return `total`, `total_sent`, `total_received` for contacts and companies (replaces stale stored values)
- **Contacts drilldown back button**: "Back to {company}" when navigated from company detail page

### Changed
- **Navigation menu reorganized**: Consolidated 11 top-level items into 5 (Dashboard, Emails, Intelligence, Analytics, Manage) following frequency-of-use UX principles
- **Contact detail simplified**: Removed inline email table and drawer, uses clickable KPI → emails page
- **Company detail simplified**: Removed inline email table and drawer, uses clickable KPI → emails page
- Email Rules moved from Analytics submenu to Manage submenu (it's configuration, not analysis)
- AI Usage moved from Intelligence submenu to Manage submenu (admin-only, monitoring)

### Fixed
- Emails Sent/Received showing stale values on contact and company detail pages (now live from DB)
- Company emails endpoint pagination bug (incorrect per-batch range calculation)

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