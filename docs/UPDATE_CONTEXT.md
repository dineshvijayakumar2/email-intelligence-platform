# Update Context - March 15, 2026

## Session Summary

This document captures the current state of the Email Intelligence Platform. Sprint 3 (AI Semantic Intelligence + QuickBase Integration + AM-Centric Rehaul) is COMPLETE. Sprint 4 (Power Mode) is planned but not started.

---

## Stage 2 Scope (Revised)

Based on updated user stories, Stage 2 is now organized into 3 sprints:

### Sprint 1: Foundation (Weeks 1-3)
**Goal**: Secure multi-tenant infrastructure with OAuth-based email synchronization

| Epic | Status |
|------|--------|
| Account Manager & Client Hierarchy | Backend Complete |
| Role-Based Access Control | **Complete** - Production Deployed |
| Gmail OAuth Integration | **Complete** |
| Outlook OAuth Integration | Pending |
| Date Range Processing | Complete |

### Sprint 2: Customer Data Extraction (Weeks 4-6)
**Status**: ✅ COMPLETE (February 26, 2026)

| Epic | Status |
|------|--------|
| 13-Step Extraction Pipeline | **Complete** |
| Contact Database + Deduplication | **Complete** |
| Company Resolution + Domain Grouping | **Complete** |
| Engagement Analytics (8-factor scoring) | **Complete** |
| 30 REST API Analytics Endpoints | **Complete** |
| Analytics Frontend (6 pages) | **Complete** |

### Sprint 3: AI Semantic Intelligence + QB Integration
**Status**: ✅ COMPLETE (March 15, 2026)

| Epic | Status |
|------|--------|
| AI Email Classification (Claude Haiku) | **Complete** |
| Business Entity Extraction | **Complete** |
| Action Signal Engine (6 AM-centric signals) | **Complete** |
| QuickBase CRM Integration | **Complete** |
| LangChain Strategic Digest | **Complete** |
| AM Efficiency Analyzer | **Complete** |
| Customer Lifecycle Tiers | **Complete** |
| Frontend (Inbox, Digest, Opportunities, Usage, Strategic Digest) | **Complete** |
| AM-Centric Rehaul (migration 026) | **Complete** |

### Next: Sprint 4 — Power Mode (Planned)
7 features: Deal Radar, Ghost Writer, Heatmap, War Room, Alerts, Scoreboard, Executive Report.
Plan: `docs/SPRINT3_4_IMPLEMENTATION_PLAN.md`

---

## Completed Work

### Stage 1 (Complete)
- Multi-format email extraction (MBOX, PST, OLM)
- Google Drive streaming for large files
- Rule-based tagging system (20+ tags)
- Real-time processing with Redis
- Production deployment on Railway

### Stage 2 Progress (Jan 19-27, 2026)

#### 1. Error Handling System (Complete)
- Added `processing_status`, `processing_error`, `processing_attempts` columns to emails
- Created error tracking functions in PostgreSQL
- Split migrations for Railway (001a, 001b, 001c)
- Job error log endpoint with batch error analysis

#### 2. Business Hierarchy (Backend Complete)
- Database tables: `account_managers`, `clients`, `customer_companies`, `customer_contacts`, `customer_recognition_rules`
- Backend routers with CRUD endpoints
- Foreign key relationships to emails table

#### 3. Parallel Download (Complete)
- `backend/src/storage/parallel_downloader.py` - multi-threaded byte-range downloads
- Optional "Download Before Processing" in Advanced Settings
- Progress tracking with speed display

#### 4. Frontend Resilience (Complete)
- `frontend/src/services/apiClient.ts` - centralized API client with timeout/retry
- `frontend/src/hooks/useConnectionStatus.ts` - connection tracking hook
- Auto-reconnect when backend restarts
- Connection status banner in UI

#### 5. Gmail LIVE Integration (Complete - Jan 27, 2026)
- **OAuth Authentication**: Google OAuth2 flow with consent screen
- **Gmail Extractor**: `backend/src/extractors/gmail_extractor.py` following BaseExtractor pattern
- **Sync Service**: `backend/src/services/gmail_sync_service.py` with background polling
- **API Endpoints**: `backend/src/routers/gmail.py` with auth, sync, and config routes
- **Frontend Components**:
  - `GmailConnection.tsx` - Connection status and sync controls (legacy)
  - `gmailService.ts` - Frontend API service
  - Sync settings in `MailboxEditForm.tsx`
- **Features**:
  - Connect Gmail via OAuth popup
  - Link Gmail to existing archive mailboxes for continuous sync
  - Automatic 15-minute sync (configurable 1-1440 minutes)
  - Incremental sync using Gmail historyId
  - Manual "Sync Now" button
  - Frontend UI for configuring sync interval
  - Persistent config in `app_config` database table

#### 5b. Per-Mailbox Gmail Integration (Complete - Jan 28, 2026)
- **Architecture Change**: Each mailbox now stores its own Gmail tokens directly in `connection_config`
- **Benefits**:
  - Multiple Gmail accounts can be connected (one per mailbox)
  - No global account management needed
  - Each mailbox independent - simpler mental model
- **New Endpoints** (`backend/src/routers/gmail.py`):
  - `POST /api/gmail/mailbox/{mailbox_id}/connect` - Connect Gmail directly to mailbox
  - `DELETE /api/gmail/mailbox/{mailbox_id}/disconnect` - Disconnect Gmail from mailbox
  - `GET /api/gmail/mailbox/{mailbox_id}/status` - Get mailbox Gmail sync status
  - `POST /api/gmail/mailbox/{mailbox_id}/sync` - Trigger manual sync for mailbox
- **Sync Service Updates** (`backend/src/services/gmail_sync_service.py`):
  - Added `_sync_all_mailboxes()` - loops through mailboxes with Gmail tokens
  - Added `_sync_mailbox()` - syncs individual mailbox using its tokens
  - Added `_update_mailbox_sync_status()` - updates status in connection_config
  - Backward compatible: still syncs legacy `user_integrations` based connections
- **Frontend Updates**:
  - `gmailService.ts` - Added `connectToMailbox()`, `disconnectFromMailbox()`, `getMailboxGmailStatus()`, `triggerMailboxSync()`
  - `MailboxEditForm.tsx` - Direct Gmail connect/disconnect per mailbox
  - `dashboard.tsx` - Removed global Gmail connection, shows per-mailbox summary
- **Migration**: `scripts/migrations/007_migrate_gmail_to_mailbox.sql` for existing connections

#### 6. Role-Based Access Control (Complete - Jan 30, 2026)
- **Architecture**: Supabase Auth for authentication with custom user profiles
- **3 User Roles**:
  - **Admin**: Access to all mailboxes and user management
  - **Client Manager**: Access to mailboxes of assigned clients only
  - **Account Manager**: Access to own mailboxes only (default for new users)
- **Authentication Flow**:
  - Supabase Auth supports Google OAuth, Microsoft OAuth, email/password
  - Frontend uses `@supabase/supabase-js` for OAuth flows and token management
  - Backend verifies JWT tokens using PyJWT with dual algorithm support:
    - **ES256/RS256**: JWKS-based verification (primary, for newer Supabase projects)
    - **HS256**: Shared secret verification (fallback, for legacy tokens)
  - Automatic algorithm detection from JWT header with graceful fallback
- **Production Deployment**:
  - ✅ Deployed to Railway and fully operational
  - ✅ ES256 JWT verification working with JWKS endpoint
  - ✅ User profiles loading correctly
  - ✅ OAuth redirects configured for production domain
  - ✅ All authentication flows tested and verified
- **Database Schema** (`scripts/migrations/010_create_user_profiles.sql`):
  - `user_profiles` table extending Supabase `auth.users`
  - `user_client_assignments` table for client manager role assignments
  - `get_user_accessible_mailboxes()` function for role-based mailbox filtering
  - Row Level Security (RLS) policies for data isolation
  - Auto-create user profile trigger on signup
- **Backend Implementation**:
  - `backend/src/dependencies/auth.py` - JWT verification and user profile fetching
    - **ES256 Support**: Uses PyJWKClient to fetch public keys from `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`
    - **Algorithm Detection**: Inspects JWT header to determine algorithm (ES256/RS256/HS256)
    - **Graceful Fallback**: Falls back to HS256 with shared secret if JWKS fails
    - **Lazy Loading**: JWKS client initialized on first ES256 token
  - `backend/src/routers/auth.py` - Auth endpoints:
    - `GET /api/auth/me` - Get current user profile with accessible mailboxes
    - `GET /api/auth/users` - List all users (admin only)
    - `PATCH /api/auth/users/{user_id}/role` - Update user role (admin only)
    - `PATCH /api/auth/users/{user_id}/status` - Activate/deactivate user (admin only)
    - `PUT /api/auth/users/{user_id}/client-assignments` - Assign clients to user (admin only)
  - Added `PyJWT` and `cryptography` to requirements.txt
- **Frontend Implementation**:
  - `frontend/src/lib/supabase.ts` - Supabase client configuration
  - `frontend/src/contexts/AuthContext.tsx` - Global auth state with user profile
  - `frontend/src/pages/login.tsx` - Login page with Google/Microsoft OAuth + email/password
  - `frontend/src/components/ProtectedRoute.tsx` - Route guards (authenticated, admin-only, client-manager+)
  - `frontend/src/components/layout.tsx` - User profile display with logout in header
  - `frontend/src/pages/users.tsx` - Admin user management page
  - `frontend/src/pages/emails.tsx` - Updated to use accessible mailboxes only, auto-select first mailbox
  - `frontend/src/components/MailboxSelector.tsx` - Dropdown for mailbox selection (replaces "All Mailboxes")
  - Added `@supabase/supabase-js` to package.json
- **Environment Configuration**:
  - Frontend: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
  - Backend: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_JWT_SECRET`
  - Updated `.env.example` files with Supabase configuration
- **UI Updates**:
  - Removed "All Mailboxes" view - users see only their accessible mailboxes
  - Role-based badges in user management (Admin, Client Manager, Account Manager)
  - User status toggle (Active/Inactive)
  - Client assignment interface for Client Managers

#### 7. Error Tracking Page (Complete - Jan 27, 2026)
- New dedicated errors page: `frontend/src/pages/errors.tsx`
- View errors by processing job with filtering by phase and type
- Job errors summary with error type breakdown (categories, counts)
- Batch error log display from `processing_jobs.error_log`
- Error analysis: timeout, duplicate_in_batch, constraint_violation
- Failed message IDs tracking with sample display
- Retry failed emails functionality

#### 8. Dashboard Redesign (Complete)
- Gmail LIVE sync status card with connection controls
- Processing job status with real-time progress
- Email statistics with count by mailbox
- Optimized database queries using PostgreSQL functions:
  - `get_dashboard_stats()` - aggregated dashboard metrics
  - `get_email_counts_by_mailbox()` - per-mailbox counts
- Performance indexes for faster queries

#### 9. Date-Based Filtering (Complete)
- Date range picker in emails page for filtering
- Gmail date-range fetch endpoint for historical imports
- Start/end date parameters in email extraction

#### 10. Bug Fixes (Complete)
- Removed faulty `DaemonThreadPoolExecutor` (was trying to set daemon on active threads)
- Split migration scripts for Railway timeout issues
- Fixed Gmail OAuth scope validation error
- Fixed Supabase client initialization errors

#### 11. Mailbox Switching & Filtering UX Improvements (Complete - Feb 6, 2026)
- **Problem**: Mailbox switching showed stale data briefly before loading new content, causing user confusion
- **Solution Implemented**:
  1. **Route-Based Navigation** - Each mailbox has its own URL (`/emails/:mailboxId`, `/processing/:mailboxId`)
  2. **Instant Skeleton Feedback** - Clear old content immediately and show loading skeleton
  3. **Removed "All Mailboxes" View** - Always require mailbox selection in Emails page
  4. **React Strict Mode Fix** - Handle double-mounting gracefully in MailboxSelector
  5. **Processing Page Filtering** - Filter jobs by mailbox with instant feedback
- **Key Files Modified**:
  - `frontend/src/App.tsx` - Added mailbox routes (`/emails/:mailboxId`, `/processing/:mailboxId`)
  - `frontend/src/pages/emails.tsx` - Route-based navigation, instant skeleton display, strict guards
  - `frontend/src/pages/processing.tsx` - Added mailbox filtering with MailboxSelector dropdown
  - `frontend/src/components/MailboxSelector.tsx` - Fixed React Strict Mode issue, supports single/multiple modes
  - `scripts/troubleshooting/fix_accessible_mailboxes.sql` - Fixed RPC function for roles array support
- **Technical Details**:
  - **Mailbox Switching Flow**: Select mailbox → clear data → navigate to URL → load fresh data
  - **Folder Switching Flow**: Select folder → clear emails/count → show skeleton → load data
  - **Processing Page Filtering**: Select mailbox → clear jobs → navigate → filter by mailbox_id
  - **Guards**: Prevent loading without valid mailbox selection
  - **Optimistic UI**: Clear old data immediately before navigation for instant perceived performance

---

## Code Locations

### Gmail LIVE Integration (Per-Mailbox Architecture)
- **Extractor**: `backend/src/extractors/gmail_extractor.py`
- **Sync Service**: `backend/src/services/gmail_sync_service.py` (updated for per-mailbox)
- **API Router**: `backend/src/routers/gmail.py` (includes mailbox-specific endpoints)
- **Frontend Service**: `frontend/src/services/gmailService.ts` (mailbox methods added)
- **Frontend Form**: `frontend/src/components/MailboxEditForm.tsx` (direct Gmail connect)
- **Legacy Component**: `frontend/src/components/GmailConnection.tsx` (for backward compatibility)
- **Database Storage**: Gmail tokens stored in `mailboxes.connection_config` JSONB
- **Legacy Tables**: `user_integrations`, `gmail_filters`, `app_config`
- **Migration**: `scripts/migrations/007_migrate_gmail_to_mailbox.sql`

### Role-Based Access Control (RBAC)
- **Backend**:
  - Auth dependency: `backend/src/dependencies/auth.py`
  - Auth router: `backend/src/routers/auth.py`
  - Requirements: PyJWT, cryptography
- **Frontend**:
  - Supabase client: `frontend/src/lib/supabase.ts`
  - Auth context: `frontend/src/contexts/AuthContext.tsx`
  - Login page: `frontend/src/pages/login.tsx`
  - Protected routes: `frontend/src/components/ProtectedRoute.tsx`
  - User management: `frontend/src/pages/users.tsx`
  - Mailbox selector: `frontend/src/components/MailboxSelector.tsx`
- **Database**:
  - Migration: `scripts/migrations/010_create_user_profiles.sql`
  - Tables: `user_profiles`, `user_client_assignments`
  - Function: `get_user_accessible_mailboxes(user_id)`
- **Configuration**:
  - Frontend: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
  - Backend: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, `SUPABASE_JWT_SECRET`

### Business Hierarchy (Stage 2)
- Backend routers: `backend/src/routers/` (account_managers.py, clients.py, customers.py, contacts.py)
- Database migration: `scripts/migrations/002_add_business_hierarchy.sql`

### Error Handling
- Migration: `scripts/migrations/001a_add_error_columns.sql`, `001b_add_error_functions.sql`, `001c_add_error_indexes.sql`
- Backend: `backend/src/routers/errors.py`

### Frontend Resilience
- API Client: `frontend/src/services/apiClient.ts`
- Hook: `frontend/src/hooks/useConnectionStatus.ts`

### Parallel Download
- Backend: `backend/src/storage/parallel_downloader.py`

---

## Next Steps

### Immediate (Sprint 1 Continuation)
1. **Outlook OAuth Integration** (Final Sprint 1 Epic)
   - Implement Microsoft Graph OAuth
   - Import Outlook rules
   - Handle token refresh

2. **Gmail Filter Import** (Optional Enhancement)
   - Import Gmail filters to platform rules
   - Display imported filters in UI

### Sprint 2 (After Sprint 1 Complete)
1. Customer Recognition System with domain/keyword rules
2. Visual Rules Management Interface
3. Contact Database with signature parsing

### Sprint 3 (After Sprint 2 Complete)
1. AI Email Classification (Claude API)
2. Business Entity Extraction
3. Accuracy Testing (85% target)

---

## Environment Notes

- Platform: Windows 11
- Python: 3.13
- Backend port: 8000
- Frontend port: 3000
- Redis: Required for job tracking
- Database: Supabase PostgreSQL
- Production: Railway deployment
