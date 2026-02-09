# Google Cloud Console OAuth Setup Guide

This guide walks through setting up Google Cloud Console for OAuth authentication in the Email Intelligence Platform. Google OAuth is used for:

1. **Supabase Login** - "Sign in with Google" on the login page
2. **Gmail LIVE Sync** - Connecting Gmail accounts to mailboxes for email sync
3. **Google Drive Integration** - Accessing MBOX/PST/OLM files stored in Google Drive

## Prerequisites

- Google account
- Access to [Google Cloud Console](https://console.cloud.google.com)

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Click the project dropdown at the top → **New Project**
3. Enter a project name (e.g., "Email Intelligence Platform")
4. Click **Create**
5. Wait for the project to be created, then select it

## Step 2: Enable Required APIs

Navigate to **APIs & Services** → **Library** and enable these APIs:

| API | Purpose |
|-----|---------|
| **Gmail API** | Read emails for LIVE sync |
| **Google Drive API** | Access MBOX/PST files in Drive |
| **Google People API** | Get user profile info (optional) |

To enable each:
1. Search for the API name
2. Click on it
3. Click **Enable**

## Step 3: Configure OAuth Consent Screen

Navigate to **APIs & Services** → **OAuth consent screen**

### User Type
- Select **External** (unless you're in a Google Workspace org and want internal only)
- Click **Create**

### App Information
Fill in the required fields:

| Field | Value |
|-------|-------|
| App name | Email Intelligence Platform |
| User support email | Your email address |
| App logo | (Optional) Upload your logo |

### App Domain (Optional for testing)
- Application home page: Your app URL
- Privacy policy link: Your privacy policy URL
- Terms of service: Your ToS URL

### Developer Contact Information
- Add your email address

Click **Save and Continue**

### Scopes
Click **Add or Remove Scopes** and add:

| Scope | Description |
|-------|-------------|
| `openid` | Associate you with your personal info |
| `email` | View your email address |
| `profile` | View your basic profile info |
| `https://www.googleapis.com/auth/gmail.readonly` | View your email messages and settings |
| `https://www.googleapis.com/auth/drive.readonly` | View files in Google Drive |

Click **Update** then **Save and Continue**

### Test Users (Required for "Testing" status)
While your app is in "Testing" mode:
1. Click **+ Add Users**
2. Add email addresses of users who need to test
3. Only these users can authenticate until you publish the app

Click **Save and Continue** → **Back to Dashboard**

## Step 4: Create OAuth 2.0 Credentials

Navigate to **APIs & Services** → **Credentials**

1. Click **+ Create Credentials** → **OAuth client ID**
2. Select **Web application**
3. Name it (e.g., "Email Intelligence Web Client")

### Authorized JavaScript Origins
Add origins where your app runs:

```
# Development
http://localhost:3000
http://localhost:5173

# Production
https://your-frontend-domain.com
```

### Authorized Redirect URIs
Add callback URLs:

```
# For Supabase Authentication (Login with Google)
https://YOUR_SUPABASE_PROJECT.supabase.co/auth/v1/callback

# For Gmail/Drive OAuth (Frontend callbacks)
# Development
http://localhost:3000/auth/google/callback

# Production
https://your-frontend-domain.com/auth/google/callback
```

4. Click **Create**
5. Note your **Client ID** and **Client Secret**

## Step 5: Configure Supabase

In your Supabase Dashboard:

1. Go to **Authentication** → **Providers**
2. Find **Google** and enable it
3. Fill in:
   - **Client ID**: Your OAuth client ID
   - **Client Secret**: Your OAuth client secret

## Step 6: Environment Variables

### Backend (.env)
```env
# Google OAuth (Gmail & Drive)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
```

### Frontend (.env)
```env
# Google OAuth (Gmail & Drive)
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
VITE_GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
```

### Production Frontend
```env
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
VITE_GOOGLE_REDIRECT_URI=https://your-frontend-domain.com/auth/google/callback
```

## Complete Redirect URIs Checklist

Your Google OAuth client should have these redirect URIs:

| Environment | URI | Purpose |
|-------------|-----|---------|
| Supabase | `https://YOUR_PROJECT.supabase.co/auth/v1/callback` | Login with Google |
| Local Dev | `http://localhost:3000/auth/google/callback` | Gmail/Drive OAuth |
| Production | `https://your-frontend-domain.com/auth/google/callback` | Gmail/Drive OAuth |

## Step 7: Publishing Your App (Optional)

While in "Testing" mode:
- Only test users can authenticate
- Users see a warning screen during OAuth

To remove restrictions:

1. Go to **OAuth consent screen**
2. Click **Publish App**
3. Your app will be reviewed by Google
4. Once approved, any Google user can authenticate

### Verification Requirements
If you use sensitive scopes (like Gmail access), Google may require:
- Privacy policy
- Terms of service
- Video demonstration of your app
- Security assessment (for certain scopes)

For development/internal use, staying in "Testing" mode is fine.

## Troubleshooting

### "Access blocked: This app's request is invalid"
- Check that redirect URIs exactly match what's configured
- Ensure JavaScript origins include your domain
- No trailing slashes in URIs

### "Error 400: redirect_uri_mismatch"
- The redirect URI in your request doesn't match what's registered
- Copy the exact URI from the error message and add it to your credentials

### "This app isn't verified"
- Your app is in "Testing" mode
- Either add the user as a test user, or publish your app
- Users can click "Advanced" → "Go to [App Name] (unsafe)" to proceed

### "Access denied" or "Insufficient scopes"
- Check that all required scopes are added to the consent screen
- User must re-authenticate if you add new scopes

### OAuth popup closes immediately
- Check browser console for errors
- Verify the callback route exists in your frontend
- Ensure popup blockers aren't interfering

### "403 Forbidden" on Gmail/Drive API
- Verify the API is enabled in your project
- Check that the correct scopes were granted during OAuth
- Token might have expired - try re-authenticating

## API Quotas

Google APIs have usage quotas. Check **APIs & Services** → **Quotas** if you hit limits:

| API | Default Quota |
|-----|---------------|
| Gmail API | 1,000,000,000 quota units/day |
| Drive API | 1,000,000,000 quota units/day |

Most operations use 1-100 quota units. You're unlikely to hit limits in normal use.

## Security Best Practices

1. **Never commit credentials** - Use environment variables
2. **Restrict API key usage** - Add HTTP referrer restrictions
3. **Request minimal scopes** - Only ask for what you need
4. **Monitor usage** - Check Cloud Console for unusual activity
5. **Rotate secrets periodically** - Regenerate client secrets occasionally

## Multiple Environments

For staging/production, you can either:

### Option A: Single OAuth Client (Recommended)
- Add all redirect URIs to one OAuth client
- Same Client ID across environments
- Simpler to manage

### Option B: Separate OAuth Clients
- Create different credentials for dev/staging/prod
- Different Client IDs per environment
- Better isolation but more to manage

## Related Documentation

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Gmail API Reference](https://developers.google.com/gmail/api/reference/rest)
- [Google Drive API Reference](https://developers.google.com/drive/api/reference/rest/v3)
- [Supabase Auth with Google](https://supabase.com/docs/guides/auth/social-login/auth-google)
- [OAuth Consent Screen Configuration](https://support.google.com/cloud/answer/10311615)
