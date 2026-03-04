# Invite User Feature — SMTP-Less Implementation
## Uses Supabase Built-in Email Delivery (No SMTP Setup Required)

---

## How It Works (No SMTP, No Edge Functions)

```
Admin clicks "Invite User"
       │
       ▼
POST /api/v1/users/invite
  1. Creates pending_invites record (email, role, client, mailboxes)
  2. Returns invite_token
       │
       ▼
Frontend receives success → shows modal with TWO options:

  Option A: "Copy Invite Link" → admin shares link manually
            (link: /invite/accept?token=xxx)

  Option B: "Send Magic Link" → frontend calls:
            supabase.auth.signInWithOtp({
              email: invitedEmail,
              options: { shouldCreateUser: true,
                         emailRedirectTo: SITE_URL + '/auth/callback' }
            })
            Supabase sends its standard magic link email to the user.
            The user clicks it → gets auto-logged in → callback checks
            for pending invite → auto-sets up account.

Either way, the user ends up authenticated with a pending invite
matched to their email → roles, client, mailboxes assigned → done.
```

**Why this works:** Supabase already sends emails for magic links.
We just trigger a magic link for the invited email address. When
the user clicks it, Supabase creates their auth account AND logs
them in. Our auth callback then detects the pending invite and
completes the setup. Zero SMTP configuration needed.

---

## The Complete User Experience

### Admin Invites Someone:

```
┌──────────────────────────────────────────┐
│  Invite New User                      ✕  │
│                                          │
│  Email *          [john@acme.com       ] │
│  Display Name *   [John Smith          ] │
│                                          │
│  Role *           (•) Account Manager    │
│                   ( ) Client Manager     │
│                   ( ) Admin              │
│                                          │
│  Client *         [▾ Test 1            ] │
│  Mailboxes        [▾ Dinesh Gmail, ... ] │
│                                          │
│            [Cancel]  [Send Invite →]     │
└──────────────────────────────────────────┘

After clicking "Send Invite":

┌──────────────────────────────────────────┐
│  ✅ Invite Created!                      │
│                                          │
│  How should John receive the invite?     │
│                                          │
│  [ 📧 Send Login Email ]                │
│    Sends a magic link to john@acme.com   │
│    via Supabase (no SMTP needed)         │
│                                          │
│  [ 🔗 Copy Invite Link ]                │
│    Share the link yourself via Slack,     │
│    WhatsApp, or any channel              │
│                                          │
│  [ Done ]                                │
└──────────────────────────────────────────┘
```

### What the Invited User Experiences:

**Path A — Magic Link Email (Supabase sends it):**
```
1. Gets Supabase magic link email: "Your Magic Link"
2. Clicks the link → auto-logged in
3. Auth callback detects pending invite → sets up account
4. Lands on dashboard, fully configured
```

**Path B — Shared Invite Link:**
```
1. Admin shares link: https://app.example.com/invite/accept?token=xxx
2. User clicks link → sees accept page:

   ┌──────────────────────────────────────┐
   │                                      │
   │  🎉 You've been invited!            │
   │                                      │
   │  Role: Account Manager               │
   │  Invited by: Dinesh Vijayakumar      │
   │                                      │
   │  Sign in to get started:             │
   │                                      │
   │  [ 🔵 Continue with Google    ]      │
   │  [ 🟦 Continue with Microsoft ]      │
   │  [ 📧 Sign in with Email     ]      │
   │                                      │
   └──────────────────────────────────────┘

3. Clicks Google/Microsoft → OAuth → callback → invite detected → done
   OR clicks Email → enters email → gets Supabase magic link → clicks → done
```

**Path C — User ignores invite, just goes to normal login page:**
```
1. User goes to your login page directly
2. Signs in with Google/Microsoft (their invited email)
3. Auth callback checks: "pending invite for this email?" → YES
4. Auto-assigns roles, client, mailboxes
5. Normal dashboard, fully set up
```

All three paths converge at the same point: the auth callback.

---

## Architecture

```
                    ┌─────────────────────────┐
                    │   pending_invites table  │
                    │   email, roles, client,  │
                    │   mailboxes, token,      │
                    │   status: 'pending'      │
                    └──────────┬──────────────┘
                               │
    ┌──────────────────────────┼──────────────────────────┐
    │                          │                          │
    ▼                          ▼                          ▼
Path A: Magic Link        Path B: Invite Link        Path C: Direct Login
Supabase sends email      Admin shares URL           User goes to /login
User clicks → logged in   User clicks → accept page  Signs in via OAuth
    │                      User picks OAuth/email         │
    │                          │                          │
    └──────────────┬───────────┘──────────────────────────┘
                   │
                   ▼
          Auth Callback / Post-Login Hook
          Calls: POST /api/v1/invites/accept
          "Any pending invite for my email?"
                   │
            ┌──────┴──────┐
            │ YES         │ NO
            ▼             ▼
    Create user record    Normal login
    Assign roles          (existing user)
    Assign client
    Assign mailboxes
    Mark invite accepted
            │
            ▼
        /dashboard
```

---

## Database Schema

```sql
-- Migration 014: Invite User System (SMTP-less)

CREATE TABLE IF NOT EXISTS pending_invites (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Who is being invited
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,

    -- What they're being assigned
    roles TEXT[] NOT NULL DEFAULT '{}',
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    mailbox_ids UUID[] DEFAULT '{}',

    -- Invite link token (for Path B — shared link)
    invite_token TEXT NOT NULL UNIQUE,

    -- Tracking
    invited_by UUID REFERENCES users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'expired', 'revoked')),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,    -- 7 days from creation
    accepted_at TIMESTAMPTZ
);

-- Only one pending invite per email at a time
CREATE UNIQUE INDEX idx_invites_unique_pending
    ON pending_invites(email) WHERE (status = 'pending');

CREATE INDEX idx_invites_token ON pending_invites(invite_token)
    WHERE status = 'pending';
CREATE INDEX idx_invites_email ON pending_invites(email)
    WHERE status = 'pending';

GRANT SELECT, INSERT, UPDATE ON pending_invites TO anon, authenticated;

-- Add invite tracking to existing users table
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS invited_by UUID,
    ADD COLUMN IF NOT EXISTS invited_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS invite_accepted_at TIMESTAMPTZ;
```

---

## Backend Endpoints

### Router: `backend/src/routers/invites.py`

```
POST /api/v1/users/invite              — Create invite (admin/CM only)
GET  /api/v1/invites/validate/{token}  — Validate invite token (public)
POST /api/v1/invites/accept            — Accept invite (authenticated user)
GET  /api/v1/invites/pending           — List pending invites (admin/CM)
POST /api/v1/invites/{invite_id}/resend   — Trigger new magic link
POST /api/v1/invites/{invite_id}/revoke   — Cancel invite
```

**POST /api/v1/users/invite** — The core endpoint:
```python
import secrets
from datetime import datetime, timedelta

def create_invite(request, current_user):
    # 1. Permission: admin or client_manager only
    if current_user.role not in ('admin', 'client_manager'):
        raise HTTPException(403)

    email = request.email.lower().strip()

    # 2. Check email not already a user
    existing_user = supabase.table('users').select('id') \
        .eq('email', email).execute()
    if existing_user.data:
        raise HTTPException(409, "A user with this email already exists")

    # 3. Check no existing pending invite
    existing_invite = supabase.table('pending_invites').select('id') \
        .eq('email', email).eq('status', 'pending').execute()
    if existing_invite.data:
        raise HTTPException(409, "A pending invite already exists for this email")

    # 4. Create invite
    invite_token = secrets.token_urlsafe(32)
    invite = {
        "email": email,
        "display_name": request.display_name,
        "roles": request.roles,
        "client_id": str(request.client_id) if request.client_id else None,
        "mailbox_ids": [str(m) for m in (request.mailbox_ids or [])],
        "invite_token": invite_token,
        "invited_by": str(current_user.id),
        "status": "pending",
        "expires_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
    }
    supabase.table('pending_invites').insert(invite).execute()

    # 5. Return token — frontend decides how to deliver it
    invite_url = f"{FRONTEND_URL}/invite/accept?token={invite_token}"

    return {
        "success": True,
        "invite_url": invite_url,
        "invite_token": invite_token,
        "email": email,
        "message": f"Invite created for {email}",
    }
```

**POST /api/v1/invites/accept** — Called after login:
```python
def accept_invite(current_auth_user):
    """
    Called after any login (OAuth or magic link).
    Checks if the authenticated email has a pending invite.
    If yes, creates the full user record with assignments.
    """
    email = current_auth_user.email.lower().strip()

    # 1. Find pending invite
    result = supabase.table('pending_invites').select('*') \
        .eq('email', email).eq('status', 'pending').execute()

    if not result.data:
        return {"accepted": False, "reason": "no_pending_invite"}

    invite = result.data[0]

    # 2. Check expiry
    if datetime.fromisoformat(invite['expires_at'].replace('Z', '+00:00')) < datetime.now(timezone.utc):
        supabase.table('pending_invites').update({"status": "expired"}) \
            .eq('id', invite['id']).execute()
        raise HTTPException(410, "This invite has expired. Ask your admin to resend.")

    # 3. Check user doesn't already exist (race condition guard)
    existing = supabase.table('users').select('id').eq('email', email).execute()
    if existing.data:
        # User already set up (maybe from a previous attempt)
        supabase.table('pending_invites').update({"status": "accepted"}) \
            .eq('id', invite['id']).execute()
        return {"accepted": True, "user_id": existing.data[0]['id'], "already_existed": True}

    # 4. Create user record
    from uuid import uuid4
    user_id = str(uuid4())
    supabase.table('users').insert({
        "id": user_id,
        "auth_user_id": str(current_auth_user.id),
        "email": email,
        "display_name": invite['display_name'],
        "status": "active",
        "invited_by": invite['invited_by'],
        "invited_at": invite['created_at'],
        "invite_accepted_at": datetime.utcnow().isoformat(),
    }).execute()

    # 5. Assign roles
    for role in invite['roles']:
        supabase.table('user_roles').insert({
            "user_id": user_id, "role": role,
        }).execute()

    # 6. Assign client
    if invite.get('client_id'):
        supabase.table('user_clients').insert({
            "user_id": user_id, "client_id": invite['client_id'],
        }).execute()

    # 7. Assign mailboxes
    for mb_id in (invite.get('mailbox_ids') or []):
        supabase.table('user_mailboxes').insert({
            "user_id": user_id, "mailbox_id": mb_id,
        }).execute()

    # 8. Mark invite accepted
    supabase.table('pending_invites').update({
        "status": "accepted",
        "accepted_at": datetime.utcnow().isoformat(),
    }).eq('id', invite['id']).execute()

    return {"accepted": True, "user_id": user_id}
```

**POST /api/v1/invites/{invite_id}/resend:**
```python
def resend_invite(invite_id, current_user):
    """Regenerate token, reset expiry. Frontend triggers the magic link."""
    invite = supabase.table('pending_invites').select('*') \
        .eq('id', invite_id).eq('status', 'pending').execute()

    if not invite.data:
        raise HTTPException(404, "Invite not found")

    new_token = secrets.token_urlsafe(32)
    new_expiry = (datetime.utcnow() + timedelta(days=7)).isoformat()

    supabase.table('pending_invites').update({
        "invite_token": new_token,
        "expires_at": new_expiry,
    }).eq('id', invite_id).execute()

    invite_url = f"{FRONTEND_URL}/invite/accept?token={new_token}"
    return {"success": True, "invite_url": invite_url, "email": invite.data[0]['email']}
```

---

## Frontend Implementation

### 1. Invite Modal — `frontend/src/components/users/InviteUserModal.tsx`

Two-step modal:

**Step 1: Fill form**
```
Fields:
- Email (Input, required, email validation)
- Display Name (Input, required)
- Role (Radio.Group: Account Manager / Client Manager / Admin)
- Client (Select, searchable, loads from /api/v1/clients)
  - Required for Account Manager / Client Manager
  - Hidden for Admin
- Mailboxes (Select, mode='multiple')
  - Loads mailboxes filtered by selected client
  - Shows after client is selected

Submit → POST /api/v1/users/invite
```

**Step 2: Delivery options (after invite created successfully)**
```typescript
// After successful invite creation:
const [step, setStep] = useState<'form' | 'deliver'>('form');
const [inviteData, setInviteData] = useState(null);

// Step 2 renders:
<Result
  status="success"
  title={`Invite created for ${inviteData.email}`}
  subTitle="Choose how to send the invite:"
/>

<Space direction="vertical" style={{ width: '100%' }}>
  <Button
    type="primary"
    icon={<MailOutlined />}
    block
    onClick={async () => {
      // Use Supabase to send a magic link — THIS IS THE SMTP-LESS TRICK
      const { error } = await supabase.auth.signInWithOtp({
        email: inviteData.email,
        options: {
          shouldCreateUser: true,
          emailRedirectTo: `${window.location.origin}/auth/callback`,
        },
      });
      if (!error) {
        notification.success({ message: `Login email sent to ${inviteData.email}` });
      }
    }}
  >
    Send Login Email (via Supabase)
  </Button>

  <Button
    icon={<CopyOutlined />}
    block
    onClick={() => {
      navigator.clipboard.writeText(inviteData.invite_url);
      notification.success({ message: 'Invite link copied!' });
    }}
  >
    Copy Invite Link
  </Button>
</Space>
```

### 2. Accept Invite Page — `frontend/src/pages/InviteAccept.tsx`

**Route:** `/invite/accept?token=xxx` (public, no auth required)

```typescript
const InviteAccept = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [invite, setInvite] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Validate the token
    apiClient.get(`/api/v1/invites/validate/${token}`)
      .then(res => setInvite(res.data))
      .catch(err => setError(err.response?.status === 410
        ? 'This invite has expired.'
        : 'Invalid invite link.'))
      .finally(() => setLoading(false));
  }, [token]);

  const handleGoogleLogin = () => {
    supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
  };

  const handleMicrosoftLogin = () => {
    supabase.auth.signInWithOAuth({
      provider: 'azure',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    });
  };

  const handleEmailLogin = () => {
    supabase.auth.signInWithOtp({
      email: invite.email,
      options: {
        shouldCreateUser: true,
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    });
    notification.info({ message: 'Check your email for a login link!' });
  };

  if (loading) return <Spin />;
  if (error) return <Result status="error" title={error} />;

  return (
    <div style={/* centered card layout */}>
      <Title level={2}>You've been invited!</Title>
      <Text>Role: {invite.roles[0]}</Text>

      <Space direction="vertical" style={{ width: '100%', marginTop: 24 }}>
        <Button size="large" block icon={<GoogleOutlined />}
          onClick={handleGoogleLogin}>
          Continue with Google
        </Button>
        <Button size="large" block icon={<WindowsOutlined />}
          onClick={handleMicrosoftLogin}>
          Continue with Microsoft
        </Button>
        <Divider>or</Divider>
        <Button size="large" block icon={<MailOutlined />}
          onClick={handleEmailLogin}>
          Sign in with Email Link
        </Button>
      </Space>
    </div>
  );
};
```

### 3. Auth Callback Update — The Critical Piece

**In your existing auth callback** (the page where Google/Microsoft redirects
after login), add the invite acceptance check:

```typescript
// In your existing auth callback (e.g., /auth/callback):

useEffect(() => {
  const handleAuthCallback = async () => {
    // Wait for Supabase session to be established
    const { data: { session } } = await supabase.auth.getSession();

    if (session) {
      // KEY: Check for pending invite EVERY time someone logs in
      try {
        const response = await apiClient.post('/api/v1/invites/accept');
        if (response.data.accepted) {
          notification.success({
            message: 'Welcome!',
            description: 'Your account has been set up.',
          });
        }
      } catch (e) {
        // No pending invite — that's fine, normal login
      }

      // Continue to dashboard
      navigate('/dashboard');
    }
  };

  handleAuthCallback();
}, []);
```

**This is the entire magic.** Every login — whether from the invite link,
from a magic link, or from the normal login page — checks for a pending invite.
No special routing needed. The invite is matched by email, not by token.

### 4. Users Page Updates — `frontend/src/pages/Users.tsx`

```
Changes to existing Users page:

HEADER:
- Add "+ Invite User" button (primary, blue) next to Refresh
- Only visible if current user role is admin or client_manager

TABLE DATA:
- Update the API call to ALSO return pending invites:
  GET /api/v1/invites/pending (merge into same table)
- Pending invites show as rows with:
  - User column: display_name + email (same as active users)
  - Roles column: assigned role tags (same as active users)
  - Status: 🟡 "Invited" badge (yellow) instead of 🟢 "Active"
  - If expired: 🔴 "Expired" badge

ACTIONS for invited users:
- 📩 Resend: POST /api/v1/invites/{id}/resend → then send magic link
- 🚫 Revoke: POST /api/v1/invites/{id}/revoke with confirmation
- No edit/link/email/disable icons for invited users (not active yet)
```

---

## Route Updates

Add to your React Router:

```typescript
// Public routes (no auth required):
<Route path="/invite/accept" element={<InviteAccept />} />

// The auth callback route already exists — just update the component
// to include the invite acceptance logic
```

---

## Claude Code Session Prompt

```
Read CLAUDE.md and docs/CONTINUATION_GUIDE.md for project context.

I need to add "Invite User" to the Users page. The platform uses Google,
Microsoft, and email-based auth via Supabase. There is NO SMTP configured —
all emails go through Supabase's built-in email delivery.

ARCHITECTURE: We use a pending_invites table. Admin creates invite → user
signs in via OAuth or magic link → auth callback checks for pending invite
by email → auto-assigns roles, client, mailboxes. Three paths all converge
at the auth callback.

BACKEND:

1. Create migration `scripts/sprint2/sprint2_migration_014_invite_user.sql`:
   
   CREATE TABLE pending_invites:
   - id UUID PRIMARY KEY DEFAULT uuid_generate_v4()
   - email TEXT NOT NULL
   - display_name TEXT NOT NULL
   - roles TEXT[] NOT NULL DEFAULT '{}'
   - client_id UUID REFERENCES clients(id) ON DELETE SET NULL
   - mailbox_ids UUID[] DEFAULT '{}'
   - invite_token TEXT NOT NULL UNIQUE
   - invited_by UUID REFERENCES users(id) ON DELETE SET NULL
   - status TEXT NOT NULL DEFAULT 'pending'
     CHECK (status IN ('pending', 'accepted', 'expired', 'revoked'))
   - created_at TIMESTAMPTZ DEFAULT NOW()
   - expires_at TIMESTAMPTZ NOT NULL
   - accepted_at TIMESTAMPTZ
   
   CREATE UNIQUE INDEX idx_invites_unique_pending
     ON pending_invites(email) WHERE (status = 'pending');
   CREATE INDEX idx_invites_token ON pending_invites(invite_token)
     WHERE status = 'pending';
   CREATE INDEX idx_invites_email ON pending_invites(email)
     WHERE status = 'pending';
   GRANT SELECT, INSERT, UPDATE ON pending_invites TO anon, authenticated;
   
   ALTER TABLE users
     ADD COLUMN IF NOT EXISTS invited_by UUID,
     ADD COLUMN IF NOT EXISTS invited_at TIMESTAMPTZ,
     ADD COLUMN IF NOT EXISTS invite_accepted_at TIMESTAMPTZ;

2. Create `backend/src/routers/invites.py`:

   POST /api/v1/users/invite
   - Body: {email, display_name, roles: string[], client_id?, mailbox_ids?}
   - Permission: admin or client_manager only
   - Validate: email not in users table, not in pending_invites (status=pending)
   - Generate: invite_token = secrets.token_urlsafe(32)
   - Insert pending_invites with expires_at = now + 7 days
   - Return: {success, invite_url, invite_token, email}
   - The invite_url = FRONTEND_URL + "/invite/accept?token=" + token

   GET /api/v1/invites/validate/{token}
   - PUBLIC endpoint (no auth required)
   - Find invite by token where status=pending
   - Check not expired (if expired, update status to 'expired')
   - Return: {valid, email, display_name, roles} or 404/410

   POST /api/v1/invites/accept
   - REQUIRES AUTH (user just logged in via OAuth or magic link)
   - Get authenticated user's email from Supabase JWT
   - Find pending invite matching that email (case-insensitive)
   - If no invite: return {accepted: false, reason: "no_pending_invite"}
   - If expired: update status, return 410
   - If found:
     a) Check user doesn't already exist in users table (race condition guard)
     b) Create users record: id, auth_user_id, email, display_name,
        status='active', invited_by, invited_at, invite_accepted_at
     c) Create user_roles records for each role in invite
     d) Create user_clients record if client_id present
     e) Create user_mailboxes records for each mailbox_id
     f) Update invite: status='accepted', accepted_at=now
     g) Return: {accepted: true, user_id}

   GET /api/v1/invites/pending
   - Admin/client_manager only
   - Return all pending_invites where status='pending'
   - Include invited_by user's display_name

   POST /api/v1/invites/{invite_id}/resend
   - Admin/client_manager only
   - Verify invite exists and status='pending'
   - Regenerate: new invite_token, reset expires_at to now + 7 days
   - Return: {success, invite_url, email}

   POST /api/v1/invites/{invite_id}/revoke
   - Admin/client_manager only
   - Update status to 'revoked'
   - Return: {success}

   Register router in main.py with prefix.

   Use existing patterns: _execute_with_retry for Supabase calls,
   proper error handling, logging module.

FRONTEND:

3. Create `frontend/src/pages/InviteAccept.tsx`:
   Route: /invite/accept?token=xxx (PUBLIC — no auth required)
   
   On mount:
   - Extract token from URL searchParams
   - GET /api/v1/invites/validate/{token}
   - If valid: show invite details + sign-in buttons
   - If 410: show "Invite expired, ask admin to resend"
   - If 404: show "Invalid invite link"

   Sign-in buttons (all redirect to /auth/callback after login):
   - "Continue with Google" → supabase.auth.signInWithOAuth({provider: 'google',
     options: {redirectTo: origin + '/auth/callback'}})
   - "Continue with Microsoft" → same with provider: 'azure'
   - "Sign in with Email" → supabase.auth.signInWithOtp({email: invite.email,
     options: {shouldCreateUser: true, emailRedirectTo: origin + '/auth/callback'}})
     → show message "Check your email for a login link"

   Layout: centered card, similar to login page.
   Use Ant Design: Card, Typography, Button, Space, Divider, Result, Spin.

4. Update your existing auth callback page/component:
   After Supabase session is established, add:
   - try { await apiClient.post('/api/v1/invites/accept') }
   - If response.accepted === true: show welcome notification
   - Then navigate to /dashboard as normal
   This makes invite acceptance automatic — works for ALL login paths.

5. Create `frontend/src/components/users/InviteUserModal.tsx`:
   Two-step Ant Design Modal:
   
   Step 1 "Invite Details": Form with fields:
   - email: Input (required, email validation)
   - display_name: Input (required)
   - role: Radio.Group (Account Manager / Client Manager / Admin)
   - client_id: Select (searchable, loads from /api/v1/clients)
     Required for Account Manager and Client Manager, hidden for Admin
   - mailbox_ids: Select mode='multiple' (loads mailboxes filtered by client_id,
     only shows after client is selected)
   Submit → POST /api/v1/users/invite

   Step 2 "Send Invite" (shown after successful creation):
   - Result component: "Invite created for {email}"
   - Button: "Send Login Email" → calls supabase.auth.signInWithOtp({
     email: invitedEmail, options: {shouldCreateUser: true,
     emailRedirectTo: origin + '/auth/callback'}})
     Shows success notification after
   - Button: "Copy Invite Link" → copies invite_url to clipboard
   - Button: "Done" → closes modal

6. Update `frontend/src/pages/Users.tsx` (or wherever Users page is):
   - Add "+ Invite User" button next to Refresh (only for admin/client_manager)
   - Button opens InviteUserModal
   - Merge pending invites into the users table:
     Call GET /api/v1/invites/pending alongside users fetch
     Pending invites show as rows with status "Invited" (yellow badge)
   - For invited user rows, action icons:
     📩 Resend (POST resend, then trigger signInWithOtp from frontend)
     🚫 Revoke (POST revoke with Popconfirm)
   - On modal close/success: refresh the table

7. Add route in React Router:
   <Route path="/invite/accept" element={<InviteAccept />} />
   (This is a public route, no auth wrapper)

REMINDERS:
- Supabase NULL: Python-side filtering, NOT .neq() on nullable columns
- Supabase booleans: lowercase strings 'true'/'false'
- Frontend: use apiClient.ts, no nested retries
- Ant Design v5 patterns only
- Ports: backend 8000, frontend 3001
- Email matching: always .lower().strip() for case-insensitive comparison
- DO NOT use supabase.auth.admin.inviteUserByEmail() — conflicts with OAuth
- signInWithOtp shouldCreateUser:true ensures Supabase creates the auth user
  if they don't exist yet
```

---

## Security Checklist

```
✅ Invite tokens: cryptographically random (secrets.token_urlsafe(32))
✅ Tokens expire: 7 days, checked on both validate and accept
✅ Single-use: once accepted, can't be reused (status changes)
✅ Email matching: case-insensitive, trimmed
✅ Permission: only admin/client_manager can create invites
✅ No duplicate invites: partial unique index on email where status=pending
✅ Race condition guard: accept checks if user already exists
✅ No service_role key needed: everything uses standard Supabase client
✅ OAuth email must match invite email: prevents wrong account acceptance
✅ Revocable: admin can cancel pending invites
```

## Supabase Configuration

```
Only needed if not already done:

□ Authentication → URL Configuration:
  - Add /invite/accept to Redirect URLs (for OAuth redirect)
  - Add /auth/callback to Redirect URLs (if not already)

□ Authentication → Email Templates:
  - Optionally customize the Magic Link template to be more branded
  - This is the email users get when "Send Login Email" is clicked
  
□ Authentication → Providers:
  - Google: already enabled ✅
  - Microsoft (Azure): already enabled ✅
  - Email (magic link): already enabled ✅
```
