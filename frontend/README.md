# Email Intelligence Frontend

React/TypeScript frontend for the Email Intelligence Platform with Ant Design UI, Supabase authentication, and Gmail/Outlook LIVE sync integrations.

## Quick Start

### Prerequisites
- Node.js 18+
- npm or yarn

### Setup & Run

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env.development
# Edit .env.development with your credentials

# Start development server
npm start
```

The app will be running at `http://localhost:3000`

## Environment Variables

Create `.env.development` (for local) or `.env.production` (for deployment):

```env
# API Configuration
VITE_API_BASE_URL=http://localhost:8000/api

# Supabase (Required for Authentication)
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_key_here

# Google OAuth (Gmail & Drive)
VITE_GOOGLE_CLIENT_ID=your_google_client_id
VITE_GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback

# Microsoft OAuth (Outlook)
VITE_MICROSOFT_CLIENT_ID=your_microsoft_client_id
VITE_MICROSOFT_REDIRECT_URI=http://localhost:3000/auth/microsoft/callback
```

---

## Authentication

The platform uses Supabase Auth with multiple sign-in methods:

- **Email/Password** - Standard email authentication
- **Google OAuth** - Sign in with Google
- **Microsoft OAuth** - Sign in with Microsoft (Azure AD)

### Auth Context

```typescript
import { useAuth } from '../contexts/AuthContext';

const MyComponent = () => {
  const {
    user,           // Supabase user object
    profile,        // User profile with roles
    isAuthenticated,
    isAdmin,        // Check admin role
    isClientManager,
    isAccountManager,
    signInWithEmail,
    signInWithGoogle,
    signInWithMicrosoft,
    signOut
  } = useAuth();

  return <div>{profile?.name}</div>;
};
```

### Role-Based Access

The frontend respects backend RBAC. User profile includes:

```typescript
interface UserProfile {
  id: string;
  email: string;
  name: string;
  roles: Array<'admin' | 'client_manager' | 'account_manager'>;
  isActive: boolean;
  accessibleMailboxIds: string[];
}
```

---

## Gmail LIVE Sync

Connect Gmail accounts for automatic email synchronization.

### Components

- **`GmailConnection.tsx`** - Connection status and controls
- **Dashboard Gmail Section** - Overview with sync status

### Service

```typescript
import gmailService from '../services/gmailService';

// Connect Gmail via OAuth popup
const result = await gmailService.connect(userId);

// Connect Gmail to specific mailbox
const result = await gmailService.connectToMailbox(mailboxId);

// Trigger manual sync
await gmailService.triggerSync(userId);

// Get connection status
const status = await gmailService.getConnectionStatus(userId);
```

### OAuth Flow

1. User clicks "Connect Gmail"
2. Google OAuth popup opens
3. User grants permissions
4. Authorization code sent to backend
5. Backend exchanges for tokens and stores them
6. Frontend polls for connection status

---

## Outlook LIVE Sync

Connect Outlook accounts (O365 and personal) for automatic email synchronization.

### Components

- **`OutlookConnection.tsx`** - Connection status and controls
- **Dashboard Outlook Section** - Overview with sync status
- **MailboxEditForm** - Per-mailbox Outlook connection

### Service

```typescript
import outlookService from '../services/outlookService';

// Connect Outlook via MSAL popup
const result = await outlookService.connect(userId);

// Connect Outlook to specific mailbox
const result = await outlookService.connectToMailbox(mailboxId);

// Trigger manual sync
await outlookService.triggerSync(userId);

// Get mailbox-specific status
const status = await outlookService.getMailboxOutlookStatus(mailboxId);
```

### Supported Account Types

- **O365 (Work/School)** - Microsoft 365 accounts
- **Personal** - outlook.com, hotmail.com, live.com

---

## Pages

### Dashboard (`/dashboard`)
- Email statistics overview
- Gmail LIVE sync section
- Outlook LIVE sync section
- Quick actions

### Mailboxes (`/mailboxes`)
- List all mailboxes with status
- Create new mailboxes
- Link Gmail/Outlook for LIVE sync
- Process mailbox files

### Mailbox Edit (`/mailboxes/:id/edit`)
- Configure mailbox settings
- Gmail LIVE sync controls
- Outlook LIVE sync controls
- Google Drive file selection

### Emails (`/emails`)
- Browse extracted emails
- Filter by folder, sender, date
- Full-text search
- View email details

### Clients (`/clients`)
- Manage consulting clients
- View client mailboxes
- Assign account managers

### Users (`/users`)
- User management (admin only)
- Role assignments
- Client assignments

---

## Services

### API Services

| Service | Purpose |
|---------|---------|
| `mailboxService.ts` | Mailbox CRUD operations |
| `gmailService.ts` | Gmail OAuth & sync |
| `outlookService.ts` | Outlook OAuth & sync |
| `clientService.ts` | Client management |
| `userService.ts` | User management |

### Common Patterns

```typescript
// All services use the configured API base URL
import config from '../config';

const response = await fetch(`${config.apiBaseUrl}/endpoint`, {
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
});
```

---

## Components

### Connection Components

| Component | Purpose |
|-----------|---------|
| `GoogleDriveConnection.tsx` | Google Drive OAuth & status |
| `GoogleDrivePicker.tsx` | File picker for Google Drive |
| `GmailConnection.tsx` | Gmail OAuth & sync controls |
| `OutlookConnection.tsx` | Outlook OAuth & sync controls |

### Form Components

| Component | Purpose |
|-----------|---------|
| `MailboxEditForm.tsx` | Full mailbox configuration |
| `ClientForm.tsx` | Client create/edit form |
| `UserForm.tsx` | User create/edit form |

---

## Styling

- **Ant Design** - UI component library
- **CSS-in-JS** - Inline styles for customization
- **Brand Colors:**
  - Google: `#4285f4`
  - Microsoft: `#0078d4`
  - Success: `#52c41a`

---

## Scripts

```bash
# Development server
npm start

# Production build
npm run build

# Run tests
npm test

# Type checking
npm run type-check

# Linting
npm run lint
```

---

## Project Structure

```
frontend/
├── src/
│   ├── components/          # Reusable UI components
│   │   ├── GoogleDriveConnection.tsx
│   │   ├── GoogleDrivePicker.tsx
│   │   ├── GmailConnection.tsx
│   │   ├── OutlookConnection.tsx
│   │   └── MailboxEditForm.tsx
│   ├── contexts/            # React contexts
│   │   └── AuthContext.tsx  # Authentication state
│   ├── lib/                 # Library configurations
│   │   └── supabase.ts      # Supabase client
│   ├── pages/               # Route pages
│   │   ├── dashboard.tsx
│   │   ├── mailboxes.tsx
│   │   ├── emails.tsx
│   │   ├── clients.tsx
│   │   └── users.tsx
│   ├── services/            # API service functions
│   │   ├── mailboxService.ts
│   │   ├── gmailService.ts
│   │   ├── outlookService.ts
│   │   └── clientService.ts
│   ├── config.ts            # Environment configuration
│   └── App.tsx              # Root component with routing
├── public/                  # Static assets
├── .env.example             # Environment template
└── package.json
```

---

## OAuth Setup

### Google OAuth

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create project and enable APIs:
   - Gmail API
   - Google Drive API
   - Google Picker API
3. Configure OAuth consent screen
4. Create OAuth 2.0 credentials (Web application)
5. Add authorized JavaScript origins:
   - `http://localhost:3000`
6. Add authorized redirect URIs:
   - `http://localhost:3000/auth/google/callback`
7. Copy Client ID to `VITE_GOOGLE_CLIENT_ID`

### Microsoft OAuth

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to App registrations > New registration
3. Configure:
   - Name: "Email Intelligence Platform"
   - Account types: "Accounts in any organizational directory and personal Microsoft accounts"
   - Redirect URI (SPA): `http://localhost:3000/auth/microsoft/callback`
4. Add API permissions:
   - Microsoft Graph: `Mail.Read`, `User.Read`, `MailboxSettings.Read`
5. Copy Application (client) ID to `VITE_MICROSOFT_CLIENT_ID`

---

## Troubleshooting

### OAuth popup blocked
- Ensure popups are allowed for localhost
- Use browser's popup blocker settings

### Gmail/Outlook connection fails
- Verify OAuth credentials in `.env`
- Check redirect URIs match exactly (including trailing slashes)
- Ensure backend is running and accessible

### Auth token expired
- Tokens auto-refresh via Supabase
- If issues persist, sign out and sign in again

### CORS errors
- Verify `VITE_API_BASE_URL` is correct
- Check backend CORS configuration

---

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
