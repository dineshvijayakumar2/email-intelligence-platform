# Sprint 2 Testing - Setup Guide

## Quick Setup

### Step 1: Install Python Dependencies

```bash
# Navigate to backend directory
cd c:\Users\Dinesh Vijayakumar\Documents\Projects\Newbound\email-intelligence-platform\backend

# Install dependencies
pip install -r requirements.txt
```

**Or if using Poetry:**
```bash
cd c:\Users\Dinesh Vijayakumar\Documents\Projects\Newbound\email-intelligence-platform\backend
poetry install
```

### Step 2: Set Environment Variables

Create or update your `.env` file in the backend directory:

```env
# Supabase (Required)
SUPABASE_URL=your-supabase-url
SUPABASE_SERVICE_KEY=your-service-key

# Redis (Optional - for progress tracking)
REDIS_URL=redis://localhost:6379
# Or individual settings:
# REDIS_HOST=localhost
# REDIS_PORT=6379
# REDIS_DB=0
```

**Get your Supabase credentials:**
1. Go to your Supabase project dashboard
2. Settings → API
3. Copy:
   - Project URL → `SUPABASE_URL`
   - service_role key (secret) → `SUPABASE_SERVICE_KEY`

### Step 3: Verify Setup

```bash
cd c:\Users\Dinesh Vijayakumar\Documents\Projects\Newbound\email-intelligence-platform

# Run the ID helper (this will verify your setup)
python scripts/sprint2/get_ids.py
```

If you see your mailboxes and clients, you're ready! ✅

---

## Troubleshooting

### Error: "No module named 'supabase'"

**Solution:**
```bash
cd backend
pip install supabase
```

### Error: "No module named 'redis'"

**Solution:**
```bash
cd backend
pip install redis
```

Or install all dependencies:
```bash
cd backend
pip install -r requirements.txt
```

### Error: "Failed to connect to Supabase"

**Check your .env file:**
1. Ensure `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` are set
2. Verify the values are correct (copy from Supabase dashboard)
3. Make sure .env file is in the `backend/` directory

**Test connection:**
```bash
cd backend
python -c "from src.database.supabase_client import SupabaseClient; print('✓ Connection successful' if SupabaseClient.get_client() else '✗ Connection failed')"
```

### Error: "Failed to connect to Redis"

**Redis is optional** - the pipeline will still work without it (progress tracking will use database only).

**To use Redis:**

**Option 1: Install Redis locally (Windows)**
- Download: https://github.com/microsoftarchive/redis/releases
- Or use WSL: `sudo apt install redis-server && redis-server`

**Option 2: Use a cloud Redis service**
- Upstash (free tier): https://upstash.com
- Redis Cloud: https://redis.com
- Update `REDIS_URL` in .env with your connection string

**Option 3: Disable Redis**
The scripts will automatically fall back to database-only tracking if Redis is unavailable.

### Error: "Table extraction_jobs does not exist"

**You need to run the Sprint 2 migrations first:**

```bash
# From your database client or Supabase SQL editor
# Run these files in order:

# 1. Create new tables
scripts/sprint2/sprint2_migration_001_new_tables.sql

# 2. Add columns to existing tables
scripts/sprint2/sprint2_migration_002_column_additions.sql
```

**Or use the master schema for fresh installs:**
```bash
scripts/sprint2/SPRINT2_MASTER_SCHEMA.sql
```

---

## Verification Checklist

Before running tests, verify:

- [ ] Python dependencies installed (`pip list | grep supabase`)
- [ ] `.env` file exists with Supabase credentials
- [ ] Supabase connection works
- [ ] Sprint 2 migrations executed
- [ ] At least one mailbox exists with processed emails

**Quick verification:**
```bash
cd c:\Users\Dinesh Vijayakumar\Documents\Projects\Newbound\email-intelligence-platform

# This should show your mailboxes
python scripts/sprint2/get_ids.py
```

---

## Ready to Test!

Once setup is complete:

```bash
# Get your mailbox ID
python scripts/sprint2/get_ids.py

# Run a quick test (100 emails)
python scripts/sprint2/test_extraction_pipeline.py full <mailbox-id> --limit 100

# Run full extraction
python scripts/sprint2/test_extraction_pipeline.py full <mailbox-id>
```

See [README_TESTING.md](README_TESTING.md) for complete testing documentation.
