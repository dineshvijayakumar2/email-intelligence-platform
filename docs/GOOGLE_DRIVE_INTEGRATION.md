# Google Drive Integration Guide

## Overview

The email intelligence platform supports seamless Google Drive integration using industry-standard OAuth2 flow. Users connect their Google Drive once and can access any email archive file without manual sharing.

## Features

✅ **One-click setup** - Users connect Google Drive once  
✅ **Full Drive access** - Browse and select any file from entire Google Drive  
✅ **Secure token storage** - Backend manages refresh tokens securely  
✅ **Auto token refresh** - No expiration issues during processing  
✅ **No file sharing required** - Access user's own files directly  

---

## Setup Instructions

### 1. Database Migration

Run the user integrations migration in Supabase SQL Editor:
```sql
\i migrations/add_user_integrations.sql
```

**For new deployments**, the table is included in the main schema:
```sql
\i scripts/create_tables.sql
```

### 2. Google Cloud Configuration

#### Create OAuth2 Credentials:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Google Drive API**:
   - APIs & Services → Library
   - Search "Google Drive API" → Enable

4. Create OAuth2 credentials:
   - APIs & Services → Credentials
   - Create Credentials → OAuth 2.0 Client ID
   - Application type: **Web application**
   - Authorized JavaScript origins: `http://localhost:3000`
   - Authorized redirect URIs: `http://localhost:3000` (for Google Identity Services)
   - Copy Client ID and Client Secret

### 3. Environment Configuration

Update your `.env` file:
```bash
# Google Drive Integration
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:3000
```

---

## How It Works

### User Experience:
1. **Connect Google Drive** (one-time setup)
   - User clicks "Connect Google Drive" 
   - OAuth2 popup for permission grant
   - Backend securely stores refresh token

2. **Select Files** (seamless)
   - Browse entire Google Drive 
   - Select any email archive (.mbox, .pst, .olm)
   - No manual file sharing required

3. **Process Files** (automatic)
   - Backend uses stored tokens to download file
   - Processes email archive normally
   - Auto-refreshes tokens if needed

### Technical Flow:
```
Frontend OAuth2 → Authorization Code → Backend Token Exchange → Token Storage → File Processing
```

### Backend Endpoints:
- `POST /api/auth/google/exchange` - Store user tokens
- `GET /api/auth/google/status/{user_id}` - Check connection
- `DELETE /api/auth/google/disconnect/{user_id}` - Revoke tokens

---

## Frontend Implementation

### GoogleDriveService Methods:

```javascript
// Connect user's Google Drive (OAuth2 authorization code flow)
await googleDriveService.authenticateForBackend(userId);

// Check if user has connected their Google Drive
const isConnected = await googleDriveService.isConnectedToBackend(userId);

// Disconnect user's Google Drive
await googleDriveService.disconnectFromBackend(userId);
```

### Required UI Components:

1. **Connect Google Drive Button**
   ```jsx
   <Button onClick={() => handleConnectGoogleDrive()}>
     Connect Google Drive
   </Button>
   ```

2. **Connection Status Display**
   ```jsx
   {isConnected ? (
     <Tag color="green">Google Drive Connected</Tag>
   ) : (
     <Tag color="orange">Not Connected</Tag>
   )}
   ```

3. **File Picker Integration**
   - GoogleDrivePicker component already exists
   - Update to use backend-stored tokens
   - Add user_id to mailbox connection_config

---

## Backend Implementation

### Token Management:
- **Storage**: `user_integrations` table
- **Auto-refresh**: Handled by Google API client
- **Scope**: `drive.readonly` + `userinfo.email`

### File Processing:
1. Check for user tokens in database
2. Authenticate with user's stored tokens
3. Download file to temporary location
4. Process normally with existing extractors
5. Clean up temporary files

### Authentication Fallback:
- Primary: User OAuth2 tokens (recommended)
- Fallback: Service account (if configured)

---

## Security Features

- 🔒 **Secure token storage** - Refresh tokens in database
- 🔄 **Automatic refresh** - No manual intervention needed  
- 👤 **User data isolation** - Access only user's own files
- 🚪 **Easy revocation** - Users can disconnect anytime
- 📊 **Audit trail** - All API calls logged

---

## Benefits Over Alternatives

| Approach | User Experience | Setup Complexity | Scalability |
|----------|-----------------|------------------|-------------|
| **OAuth2 + Backend Storage** ⭐ | Excellent | Medium | High |
| Service Account + File Sharing | Poor | Low | Low |
| Manual Download | Poor | None | None |

---

## Troubleshooting

### "Authentication failed"
- Verify Google Client ID/Secret in `.env`
- Check OAuth2 redirect URI configuration
- Ensure Google Drive API is enabled

### "Permission denied"
- User tokens may have expired - should auto-refresh
- Check `user_integrations` table for stored tokens
- Verify backend endpoints are working

### "File not found"
- Check Google Drive file still exists
- Ensure file hasn't been moved or deleted
- Verify file permissions haven't changed

---

## Migration Notes

**For existing installations:**
1. Run `migrations/add_user_integrations.sql`
2. Update `.env` with Google OAuth2 credentials
3. Frontend already supports both modes
4. No breaking changes to existing functionality

**For new deployments:**
- Complete schema includes all necessary tables
- Follow setup instructions above
- OAuth2 flow ready out of the box

This is the same approach used by **Slack, Notion, Zapier, and other major platforms** for Google Drive integration.