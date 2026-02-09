# Azure AD OAuth Setup Guide

This guide walks through setting up Microsoft Azure AD for OAuth authentication in the Email Intelligence Platform. Azure AD is used for:

1. **Supabase Login** - "Sign in with Microsoft" on the login page
2. **Outlook LIVE Sync** - Connecting Outlook accounts to mailboxes for email sync

## Prerequisites

- Microsoft Azure account (free tier works)
- Access to [Azure Portal](https://portal.azure.com)

## Step 1: Create an App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **+ New registration**
4. Fill in the details:
   - **Name**: `Email Intelligence Platform` (or your preferred name)
   - **Supported account types**: Select **"Accounts in any organizational directory and personal Microsoft accounts"**
     - This allows both work/school (O365) and personal Microsoft accounts
   - **Redirect URI**: Leave blank for now (we'll add them in the next step)
5. Click **Register**

## Step 2: Note Your Application IDs

After registration, note these values from the **Overview** page:

| Field | Description | Environment Variable |
|-------|-------------|---------------------|
| Application (client) ID | Your app's unique identifier | `MICROSOFT_CLIENT_ID` / `VITE_MICROSOFT_CLIENT_ID` |
| Directory (tenant) ID | Usually use `common` for multi-tenant | `MICROSOFT_TENANT_ID` |

## Step 3: Create a Client Secret

1. Go to **Certificates & secrets** in the left menu
2. Click **+ New client secret**
3. Add a description (e.g., "Production Secret")
4. Choose an expiration (24 months recommended)
5. Click **Add**
6. **IMPORTANT**: Copy the secret **Value** immediately (it won't be shown again)
   - This goes in `MICROSOFT_CLIENT_SECRET`

## Step 4: Configure Redirect URIs

Go to **Authentication** in the left menu and configure:

### Web Platform (Required)

Click **+ Add a platform** → **Web**

Add these redirect URIs:

#### For Supabase Authentication (Login with Microsoft)
```
https://YOUR_SUPABASE_PROJECT.supabase.co/auth/v1/callback
```

#### For Outlook LIVE Sync (Frontend callbacks)
```
# Development
http://localhost:3000/auth/microsoft/callback

# Production
https://your-frontend-domain.com/auth/microsoft/callback
```

### Platform Settings

Under the Web platform configuration:
- **Front-channel logout URL**: Leave blank
- **Implicit grant and hybrid flows**: Leave unchecked (we use authorization code flow)

### Allow Public Client Flows

At the bottom of the Authentication page:
- Set **"Allow public client flows"** to **Yes**
  - Required for PKCE flow used by Supabase

Click **Save**.

## Step 5: Configure API Permissions

Go to **API permissions** in the left menu:

1. Click **+ Add a permission**
2. Select **Microsoft Graph**
3. Choose **Delegated permissions**
4. Add these permissions:

| Permission | Description |
|------------|-------------|
| `openid` | Sign users in |
| `profile` | View users' basic profile |
| `email` | View users' email address |
| `offline_access` | Maintain access to data (refresh tokens) |
| `User.Read` | Sign in and read user profile |
| `Mail.Read` | Read user mail |
| `MailboxSettings.Read` | Read user mailbox settings |

5. Click **Add permissions**
6. Click **Grant admin consent** (if you have admin rights, otherwise ask your admin)

## Step 6: Configure Supabase

In your Supabase Dashboard:

1. Go to **Authentication** → **Providers**
2. Find **Azure** and enable it
3. Fill in:
   - **Azure Client ID**: Your Application (client) ID
   - **Azure Secret**: Your client secret
   - **Azure Tenant URL**: `https://login.microsoftonline.com/common` (for multi-tenant)

## Step 7: Environment Variables

### Backend (.env)
```env
# Microsoft OAuth (Outlook LIVE)
MICROSOFT_CLIENT_ID=your-application-client-id
MICROSOFT_CLIENT_SECRET=your-client-secret-value
MICROSOFT_TENANT_ID=common
```

### Frontend (.env)
```env
# Microsoft OAuth (Outlook)
VITE_MICROSOFT_CLIENT_ID=your-application-client-id
VITE_MICROSOFT_REDIRECT_URI=http://localhost:3000/auth/microsoft/callback
```

### Production Frontend
```env
VITE_MICROSOFT_CLIENT_ID=your-application-client-id
VITE_MICROSOFT_REDIRECT_URI=https://your-frontend-domain.com/auth/microsoft/callback
```

## Complete Redirect URIs Checklist

Your Azure AD app should have these redirect URIs under the **Web** platform:

| Environment | URI | Purpose |
|-------------|-----|---------|
| Supabase | `https://YOUR_PROJECT.supabase.co/auth/v1/callback` | Login with Microsoft |
| Local Dev | `http://localhost:3000/auth/microsoft/callback` | Outlook LIVE sync |
| Production | `https://your-frontend-domain.com/auth/microsoft/callback` | Outlook LIVE sync |

## Troubleshooting

### "AADSTS50011: The redirect URI is not valid"
- Ensure the redirect URI in your app exactly matches what's registered in Azure
- Check for trailing slashes - they must match exactly
- URIs are case-sensitive

### "AADSTS7000218: The request body must contain: client_assertion or client_secret"
- You're using a flow that requires a client secret
- Ensure `MICROSOFT_CLIENT_SECRET` is set in your backend

### "PKCE is required for this application"
- Enable **"Allow public client flows"** in Azure AD → Authentication
- This error occurs when Supabase tries to authenticate

### "Admin consent required"
- Some permissions require admin consent
- Ask your Azure AD admin to grant consent, or
- Use the **Grant admin consent** button if you have admin rights

### OAuth popup closes but nothing happens
- Check browser console for errors
- Verify the callback route exists in your frontend (`/auth/microsoft/callback`)
- Ensure the redirect URI is registered in Azure AD

## Security Notes

1. **Never commit secrets** - Use environment variables
2. **Rotate secrets** - Set calendar reminders before expiration
3. **Minimal permissions** - Only request what you need
4. **Monitor sign-ins** - Check Azure AD sign-in logs for suspicious activity

## Related Documentation

- [Microsoft Identity Platform Documentation](https://docs.microsoft.com/en-us/azure/active-directory/develop/)
- [Microsoft Graph API Reference](https://docs.microsoft.com/en-us/graph/api/overview)
- [Supabase Auth with Azure](https://supabase.com/docs/guides/auth/social-login/auth-azure)
