# Changelog

All notable changes to the Email Intelligence Platform will be documented in this file.

## [Unreleased]

### Added
- Route-based navigation for mailbox selection (`/emails/:mailboxId`)
- Instant skeleton feedback when switching mailboxes, folders, or filters
- Empty states when no mailbox is selected
- Debug logging for mailbox loading and email fetching

### Changed
- Moved mailbox selector from left sidebar to top-right dropdown (Gmail-style UX)
- Removed "all mailboxes" view - always require mailbox selection
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