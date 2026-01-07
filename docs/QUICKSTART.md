# Email Tagging System - Quick Start Guide

## Summary

**Email tagging system is implemented and ready to use!** 🏷️

- ✅ Backend automatically tags emails during processing
- ✅ Tags stored in `email_categories` table (normalized)
- ✅ Frontend UI ready for tag-based filtering
- ✅ 20+ automatic tags (spam, marketing, urgent, etc.)

---

## Prerequisites

### Redis (REQUIRED)
```bash
# Install Redis
brew install redis          # macOS
sudo apt install redis-server  # Ubuntu

# Start Redis
redis-server
```

### Environment Setup
Create `.env` file in root directory:
```bash
# Required
SUPABASE_URL=your_url
SUPABASE_ANON_KEY=your_key
SUPABASE_SERVICE_KEY=your_service_key
REDIS_URL=redis://localhost:6379

# Google Drive Integration (Industry Standard OAuth2)
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
```

## Setup (5 minutes)

### Step 1: Database Setup

Run the complete schema in Supabase SQL Editor:
```sql
\i scripts/create_tables.sql
```

**Note**: The complete schema includes all tables, indexes, and Google Drive OAuth2 support.

### Step 1.5: Google Drive OAuth2 Setup (Optional but Recommended)

For seamless Google Drive integration, set up OAuth2 credentials:

1. **Create Google Cloud Project**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing
   - Enable Google Drive API

2. **Create OAuth2 Credentials**:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth 2.0 Client ID"
   - Application type: "Web application"
   - Authorized redirect URIs: `http://localhost:3000/auth/google/callback`
   - Copy the Client ID and Client Secret to your `.env` file

3. **Update Frontend Scopes** (in `frontend/src/services/googleDriveService.ts`):
   ```javascript
   const SCOPES = [
     'https://www.googleapis.com/auth/drive.readonly',
     'https://www.googleapis.com/auth/userinfo.email'
   ];
   ```

**Benefits**: Users connect Google Drive once, then access any file without manual sharing!

**New Backend Endpoints**:
- `POST /api/auth/google/exchange` - Exchange OAuth2 code for tokens
- `GET /api/auth/google/status/{user_id}` - Check connection status
- `DELETE /api/auth/google/disconnect/{user_id}` - Disconnect account

### Step 2: Process Emails

**Option A: New Processing from Local File**
1. Go to **Mailboxes** page
2. Click **Add Mailbox**
3. Select file source: "Local File" or "Google Drive"
4. Choose file and save mailbox
5. Click **Process** button
6. Start processing (tags are automatically applied)

**Option A2: New Processing from Google Drive (OAuth2 - Recommended)**
1. Go to **Mailboxes** page
2. Click **Add Mailbox**
3. Select "Google Drive" as file source
4. Click "Connect Google Drive" (OAuth2 popup)
5. Grant permission to your Google Drive
6. Browse and select your email archive from anywhere in your Drive
7. Save and process (backend handles authentication automatically)

**Benefits**: No file sharing needed, access to entire Google Drive, seamless UX!

**Option B: Reprocess Existing Emails**
1. Go to **Processing Jobs** page
2. Find a completed extraction job
3. Click the **Reprocess** button (sync icon)
4. This will add categorization tags to all existing emails

### Step 3: View Tagged Emails

Go to **Emails** page to see tags on each email.

---

## What Tags Are Created

### Automatic Tags (20+)

**Direction**: `inbound`, `outbound`
**Thread**: `new_thread`, `reply`, `forward`
**Folder**: `inbox`, `sent`, `spam`, `trash`, `archive`
**Classification**: `spam`, `marketing`, `system`, `automated`
**Sender**: `sender_human`, `sender_system`, `sender_automated`, `sender_marketing`
**Priority**: `high_priority`, `low_priority`, `urgent`
**Content**: `financial`, `meeting`, `account_action`, `ecommerce`, `newsletter`, `notification`, `has_attachments`

Plus metadata: `is_spam`, `is_marketing`, `priority_score` (0-10), `sender_type`

---

## How It Works

### Backend (Automatic)
```
Email → Normalize → Tag → Insert → Store tags in email_categories
```

**Files Changed**:
- `src/processors/email_tagger.py` - Tagging rules ✅
- `src/processors/email_processor.py` - Calls tagger ✅
- `src/database/operations.py` - Stores in email_categories ✅

### Frontend (Ready to Use)

Update these files to show tags in UI:

**`frontend/src/services/emailService.ts`** - Query tags from email_categories
**`frontend/src/pages/emails.tsx`** - Display tags with filtering

---

## Database Queries

### Get tags for an email
```sql
SELECT category, tag_type
FROM email_categories
WHERE email_id = 'email-uuid'
AND category NOT LIKE '_meta_%';
```

### Get emails with tag
```sql
SELECT DISTINCT e.*
FROM emails e
JOIN email_categories ec ON e.id = ec.email_id
WHERE ec.category = 'urgent';
```

### Tag distribution
```sql
SELECT category, COUNT(*) as count
FROM email_categories
WHERE category NOT LIKE '_meta_%'
GROUP BY category
ORDER BY count DESC;
```

---

## Next Steps

1. ✅ **Database migrated** - `tag_type` column added
2. ✅ **Backend ready** - Tags inserted automatically
3. ✅ **Frontend updated** - `emailService.ts` queries email_categories
4. ✅ **Reprocessing available** - Use sync button to tag existing emails
5. ✅ **Auto-refresh** - Processing jobs refresh every 5 seconds
6. ⚠️ **UI enhancement needed** - Add tag filtering UI to emails.tsx

**Full details**: See `EMAIL_TAGGING_IMPLEMENTATION.md`
