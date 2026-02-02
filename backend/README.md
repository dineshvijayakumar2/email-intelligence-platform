# Email Intelligence Backend API

FastAPI backend for the Email Intelligence Platform with Gmail and Outlook LIVE sync, multi-tenant support, and role-based access control.

## Quick Start

### Prerequisites
- Python 3.8+
- Active Supabase project with the email intelligence schema
- Redis (optional, for caching)

### Setup & Run

1. **Navigate to backend directory:**
   ```bash
   cd backend
   ```

2. **Run the setup script:**
   ```bash
   ./run.sh
   ```

That's it! The API will be running at `http://localhost:8000`

## API Documentation

Once running, visit:
- **API Docs:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

## Manual Setup (Alternative)

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Environment Variables

### Core Configuration
```env
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_ANON_KEY=your_anon_key
```

### Google OAuth (Gmail & Drive)
```env
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
```

### Microsoft OAuth (Outlook LIVE)
```env
MICROSOFT_CLIENT_ID=your_microsoft_client_id
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret
MICROSOFT_TENANT_ID=common
OUTLOOK_SYNC_INTERVAL_MINUTES=15
```

---

## Gmail LIVE Sync Integration

Gmail LIVE sync allows automatic, continuous email synchronization from Gmail accounts to archive mailboxes.

### How It Works

1. **OAuth Connection:** Users authenticate via Google OAuth popup
2. **Token Storage:** Tokens stored securely in `user_integrations` table
3. **Incremental Sync:** Uses Gmail's `historyId` for efficient sync
4. **Background Service:** `GmailSyncService` polls at configurable intervals (default: 15 min)

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/gmail/auth/exchange` | Exchange OAuth code for tokens |
| GET | `/api/gmail/auth/status/{user_id}` | Check connection status |
| DELETE | `/api/gmail/auth/disconnect/{user_id}` | Disconnect Gmail |
| POST | `/api/gmail/{user_id}/sync` | Trigger manual sync |
| POST | `/api/gmail/mailbox/{mailbox_id}/connect` | Connect Gmail to mailbox |
| DELETE | `/api/gmail/mailbox/{mailbox_id}/disconnect` | Disconnect from mailbox |
| POST | `/api/gmail/mailbox/{mailbox_id}/sync` | Trigger mailbox sync |

### Gmail Scopes Required
```
openid, email, profile
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.labels
```

### Setup Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project and enable Gmail API
3. Configure OAuth consent screen
4. Create OAuth 2.0 credentials (Web application)
5. Add authorized redirect URI: `http://localhost:3000/auth/google/callback`
6. Copy Client ID and Secret to `.env`

---

## Outlook LIVE Sync Integration

Outlook LIVE sync supports both O365 (work/school) and personal Microsoft accounts.

### How It Works

1. **OAuth Connection:** Users authenticate via Microsoft OAuth popup (MSAL)
2. **Token Storage:** Tokens stored in `user_integrations` table
3. **Incremental Sync:** Uses Microsoft Graph's `deltaLink` for efficient sync
4. **Background Service:** `OutlookSyncService` polls at configurable intervals

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/outlook/auth/exchange` | Exchange OAuth code for tokens |
| GET | `/api/outlook/auth/status/{user_id}` | Check connection status |
| DELETE | `/api/outlook/auth/disconnect/{user_id}` | Disconnect Outlook |
| POST | `/api/outlook/{user_id}/sync` | Trigger manual sync |
| POST | `/api/outlook/mailbox/{mailbox_id}/connect` | Connect Outlook to mailbox |
| DELETE | `/api/outlook/mailbox/{mailbox_id}/disconnect` | Disconnect from mailbox |
| POST | `/api/outlook/mailbox/{mailbox_id}/sync` | Trigger mailbox sync |
| POST | `/api/outlook/fetch-date-range` | Fetch emails by date range |

### Outlook Scopes Required
```
openid, profile, email, offline_access
User.Read, Mail.Read, MailboxSettings.Read
```

### Setup Azure App Registration

1. Go to [Azure Portal](https://portal.azure.com) > App registrations
2. Create new registration with name "Email Intelligence Platform"
3. Supported account types: "Accounts in any organizational directory and personal Microsoft accounts"
4. Platform: Single-page application (SPA)
5. Redirect URI: `http://localhost:3000/auth/microsoft/callback`
6. Add API permissions: `Mail.Read`, `User.Read`, `MailboxSettings.Read`
7. Copy Application (client) ID to environment variables
8. Create client secret and copy to backend environment

### Gmail vs Outlook Comparison

| Aspect | Gmail | Outlook |
|--------|-------|---------|
| OAuth Library | Google Identity Services | MSAL.js |
| Token Endpoint | `oauth2.googleapis.com` | `login.microsoftonline.com` |
| Email API | Gmail API | Microsoft Graph API |
| Incremental Sync | historyId | deltaLink |
| Redirect URI | `postmessage` | Explicit URI required |

---

## User Roles & Access Control (RBAC)

The platform implements role-based access control with three user roles that can be combined.

### Roles

| Role | Access Level | Description |
|------|--------------|-------------|
| `admin` | Full access | All mailboxes, all clients, system settings |
| `client_manager` | Oversight access | View mailboxes of clients they manage |
| `account_manager` | Operational access | Mailboxes of assigned clients + own mailboxes |

### Multi-Role Support

Users can have multiple roles simultaneously. For example, an admin can also be an account_manager to monitor specific mailboxes while having full system access.

### Database Tables

```sql
-- User profiles with roles array
user_profiles (
  id UUID PRIMARY KEY,          -- Links to Supabase auth.users
  email TEXT NOT NULL,
  name TEXT NOT NULL,
  roles TEXT[] NOT NULL,        -- ['admin', 'account_manager']
  is_active BOOLEAN
)

-- Account manager assignments (operational)
user_client_assignments (
  user_id UUID REFERENCES user_profiles(id),
  client_id UUID REFERENCES clients(id)
)

-- Client manager assignments (oversight)
client_manager_assignments (
  user_id UUID REFERENCES user_profiles(id),
  client_id UUID REFERENCES clients(id)
)
```

### Access Control Functions

```sql
-- Get mailboxes accessible to a user
SELECT * FROM get_user_accessible_mailboxes(user_id);

-- Check if user has a specific role
SELECT user_has_role(user_id, 'admin');
```

### Auth Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/auth/me` | Get current user profile with roles |
| GET | `/api/auth/accessible-mailboxes` | Get mailboxes user can access |

---

## Client & Customer Management

### Business Hierarchy

```
Platform
  └── Clients (Consulting clients)
       └── Customer Companies (Client's customers)
            └── Customer Contacts (Individual contacts)
```

### Client Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/clients` | List all clients |
| POST | `/api/clients` | Create a client |
| GET | `/api/clients/{id}` | Get client details |
| PUT | `/api/clients/{id}` | Update client |
| DELETE | `/api/clients/{id}` | Delete client |
| GET | `/api/clients/{id}/mailboxes` | Get client's mailboxes |

### User Management Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/users` | List all users |
| POST | `/api/users` | Create a user |
| GET | `/api/users/{id}` | Get user details |
| PUT | `/api/users/{id}` | Update user |
| PUT | `/api/users/{id}/roles` | Update user roles |
| POST | `/api/users/{id}/assign-client` | Assign user to client |
| DELETE | `/api/users/{id}/unassign-client` | Remove client assignment |

---

## Mailbox Types

The platform supports multiple mailbox types:

| Type | Description | Source |
|------|-------------|--------|
| `mbox` | Universal email format | Gmail export, Thunderbird, Apple Mail |
| `pst` | Windows Outlook archive | Outlook for Windows |
| `olm` | Mac Outlook archive | Outlook for Mac |
| `gmail` | Gmail LIVE sync | Gmail API |
| `outlook_live` | Outlook LIVE sync | Microsoft Graph API |

### Mailbox Connection Config

The `connection_config` JSONB column stores type-specific configuration:

**For Gmail LIVE:**
```json
{
  "gmail_sync_enabled": true,
  "gmail_email": "user@gmail.com",
  "gmail_access_token": "...",
  "gmail_refresh_token": "...",
  "gmail_last_history_id": "12345",
  "gmail_sync_status": "idle"
}
```

**For Outlook LIVE:**
```json
{
  "outlook_sync_enabled": true,
  "outlook_email": "user@outlook.com",
  "outlook_access_token": "...",
  "outlook_refresh_token": "...",
  "outlook_delta_link": "...",
  "outlook_sync_status": "idle"
}
```

---

## Database Migrations

Migrations are located in `/migrations/`. Run them in order in the Supabase SQL Editor:

1. `scripts/create_tables.sql` - Full schema (for fresh installs)
2. `migrations/add_outlook_integration.sql` - Outlook support
3. Other migrations as needed

### Auto User Profile Creation

A trigger automatically creates `user_profiles` entries when users sign up via Supabase Auth:

```sql
-- Create trigger (run once in Supabase SQL Editor)
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();
```

---

## Processing Jobs

### Job Types
- `extraction` - Extract emails from mailbox files
- `enrichment` - AI enrichment of extracted emails

### Job Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/processing-jobs` | List all jobs |
| POST | `/api/mailboxes/{id}/process` | Start processing |
| POST | `/api/processing-jobs/{id}/control` | Pause/resume/stop |
| DELETE | `/api/processing-jobs/{id}` | Delete completed job |

---

## Troubleshooting

### Common Issues

**Port 8000 already in use:**
```bash
# Find and kill process using port 8000
lsof -ti:8000 | xargs kill -9
```

**Supabase connection errors:**
- Verify `.env` file has correct credentials
- Check Supabase project is active
- Ensure database schema is set up

**Gmail/Outlook sync not working:**
- Check OAuth credentials in `.env`
- Verify redirect URIs match exactly
- Check token expiration in `user_integrations`
- Review sync service logs

**Role-based access issues:**
- Check `user_profiles.roles` array
- Verify `user_client_assignments` entries
- Check `get_user_accessible_mailboxes` function output

### Debug Mode

Enable debug logging:
```env
DEBUG=true
LOG_LEVEL=debug
```

---

## Architecture

```
backend/
├── main.py                 # FastAPI app, startup/shutdown
├── src/
│   ├── routers/           # API endpoints
│   │   ├── auth.py        # Authentication & user management
│   │   ├── gmail.py       # Gmail LIVE sync
│   │   ├── outlook.py     # Outlook LIVE sync
│   │   ├── clients.py     # Client management
│   │   └── mailboxes.py   # Mailbox operations
│   ├── services/          # Business logic
│   │   ├── gmail_sync_service.py    # Gmail background sync
│   │   └── outlook_sync_service.py  # Outlook background sync
│   ├── extractors/        # Email extraction
│   │   ├── gmail_extractor.py       # Gmail API extractor
│   │   └── outlook_extractor.py     # Microsoft Graph extractor
│   └── dependencies/      # FastAPI dependencies
│       └── auth.py        # JWT validation, RBAC
└── requirements.txt
```
