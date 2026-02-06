# Troubleshooting Scripts

This directory contains diagnostic and fix scripts for debugging and resolving issues.

## Diagnostic Scripts

### Database Checks

- **`check_assignments.py`** - Verify user-client and client-mailbox assignments
- **`check_gmail_user_id.sql`** - Check Gmail user ID mappings for mailboxes
- **`check_processing_job.sql`** - Query processing job status and details
- **`check_rbac.sql`** - Verify RBAC (Role-Based Access Control) configuration

### Code Checks

- **`test_imports.py`** - Test Python module imports and dependencies

## Fix Scripts

### Database Fixes

- **`fix_accessible_mailboxes.sql`** - Update `get_user_accessible_mailboxes` RPC function to handle roles array
  - **Issue**: Function expected single `role TEXT` but schema uses `roles TEXT[]`
  - **Fix**: Updated to use `'admin' = ANY(v_roles)` pattern
  - **When to use**: If users can't see their assigned mailboxes

## Usage

### Running SQL Scripts

```bash
# Connect to Supabase SQL Editor or use psql
psql -h your-host -U your-user -d your-db -f check_rbac.sql
```

Or copy-paste into Supabase SQL Editor.

### Running Python Scripts

```bash
cd backend
python ../scripts/troubleshooting/check_assignments.py
```

## When to Use These Scripts

1. **User can't see assigned mailboxes** → Run `check_rbac.sql` and `fix_accessible_mailboxes.sql`
2. **Gmail sync not working** → Run `check_gmail_user_id.sql`
3. **Processing jobs stuck** → Run `check_processing_job.sql`
4. **Assignment issues** → Run `check_assignments.py`
5. **Import errors** → Run `test_imports.py`

## Notes

- These scripts are for development and debugging only
- Do not run in production without understanding what they do
- Fix scripts modify the database - back up first!
- Check scripts are read-only and safe to run anytime