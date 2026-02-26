# Sprint 2 Database Migrations - Usage Guide

## Files Overview

### For Existing Databases (Recommended)
✅ **Run these in Supabase SQL Editor in order:**

1. **sprint2_migration_001_new_tables.sql** (3 min)
   - Creates 6 new tables
   - Seeds 29 free email providers
   - Adds indexes, RLS, permissions
   - Self-verifying (check console for ✅)

2. **sprint2_migration_002_column_additions.sql** (2 min)
   - Adds 18+ columns to `customer_contacts`
   - Adds 11+ columns to `customer_companies`
   - Creates 5 SQL helper functions
   - Self-verifying (check console for ✅)

3. **sprint2_migration_003_batch_operations.sql** (1 min)
   - Adds unique constraint for batch upsert
   - Creates 2 batch update functions
   - **CRITICAL:** Run this AFTER testing extraction pipeline
   - Enables production-ready batch operations

4. **sprint2_migration_004_contact_classification.sql** (<1 min)
   - Adds `contact_type` column to `customer_contacts`
   - Classifies existing contacts (person/automated/shared/mailing_list)
   - Updates batch_update function to handle contact_type
   - Enables tag-instead-of-filter pattern

5. **sprint2_migration_005_fix_analytics_tables.sql** (2 min) ✨ **NEW**
   - Fixes `email_response_metrics` table schema for Phase 4
   - Matches response_time_tracker service requirements
   - Adds `is_auto_reply` column and proper indexes
   - **REQUIRED** before running Phase 4 analytics pipeline

### For Reference/Documentation
📖 **SPRINT2_MASTER_SCHEMA.sql** (v1.3)
   - Complete consolidated schema
   - Updated whenever Sprint 2 changes
   - Use for: documentation, fresh installs, review
   - **DO NOT** run on existing databases (use migrations above)
   - **Version 1.3** includes all 5 migrations

---

## Quick Start

### Option 1: Existing Database (Your Case)

```bash
# 1. Open Supabase SQL Editor
# 2. Copy-paste contents of sprint2_migration_001_new_tables.sql
# 3. Execute → Check for ✅ "All 6 tables created successfully"
# 4. Copy-paste contents of sprint2_migration_002_column_additions.sql
# 5. Execute → Check for ✅ "customer_contacts: X columns added"
# 6. Test extraction pipeline on 100-500 emails
# 7. Copy-paste contents of sprint2_migration_003_batch_operations.sql
# 8. Execute → Check for ✅ "Migration 003 completed successfully"
# 9. Copy-paste contents of sprint2_migration_004_contact_classification.sql
# 10. Execute → Check for ✅ "Migration 004 completed successfully"
# 11. Copy-paste contents of sprint2_migration_005_fix_analytics_tables.sql
# 12. Execute → Check for ✅ "Migration 005 completed successfully"
```

Expected output:
```
✅ All 6 tables created successfully
✅ Free email providers seeded: 29 domains
✅ customer_contacts: 18 new columns added
✅ customer_companies: 11 new columns added
✅ All 5 SQL helper functions created
✅ Unique constraint verified
✅ batch_update_contact_roles function created
✅ batch_update_contact_companies function created
✅ Migration 003 completed successfully
✅ contact_type column added
✅ X existing contacts classified
✅ Migration 004 completed successfully
✅ email_response_metrics table recreated with correct schema
✅ All required columns present in email_response_metrics
✅ Migration 005 completed successfully
```

### Option 2: Fresh Database (New Installation)

```bash
# 1. Run Sprint 1 schema first (create_tables.sql or migrations)
# 2. Run SPRINT2_MASTER_SCHEMA.sql (all-in-one)
```

---

## What Gets Created

### New Tables (6)

1. **internal_domains** - Exclude own org domains from extraction
2. **free_email_providers** - Gmail, Yahoo, etc. (29 seeded)
3. **extraction_jobs** - Track 13-step pipeline progress
4. **unified_email_rules** - Gmail/Outlook rules normalized
5. **email_response_metrics** - Response time tracking
6. **thread_status** - Thread completeness (open/overdue/dropped)

### New Columns on customer_contacts (19+)

**Role Classification:**
- seniority_level, functional_role, is_decision_maker
- is_primary_contact, role_source, role_confidence
- department

**Engagement Analytics:**
- engagement_score (0-100)
- avg_response_time_seconds, their_avg_response_time
- initiation_ratio, reply_rate
- emails_per_month_avg, frequency_trend
- avg_thread_depth
- last_inbound_at, last_outbound_at
- open_thread_count, dropped_thread_count
- is_shared_address

**Contact Classification:** ✨ **NEW in Migration 004**
- contact_type (person/automated/shared/mailing_list/internal/unknown)

### New Columns on customer_companies (11+)

**Aggregates:**
- contact_count, decision_maker_count
- primary_contact_id, highest_seniority
- engagement_score (0-100)

**Communication Health:**
- relationship_status (active/cooling/dormant/new)
- avg_response_time_seconds
- sla_compliance_rate (0.0-1.0)
- open_thread_count, dropped_thread_count
- avg_emails_per_month, frequency_trend
- communication_health (excellent/good/needs_attention/critical)

### SQL Helper Functions (7)

**Analytics Functions (5):**
1. `get_unlinked_emails_count(mailbox_id)` - Returns link coverage %
2. `get_domain_summary(mailbox_id, client_id)` - Domain classification
3. `link_emails_by_domain(client_id, domain, company_id)` - Batch link
4. `update_contact_engagement_metrics(contact_id)` - Refresh contact stats
5. `update_company_engagement_metrics(company_id)` - Refresh company stats

**Batch Operations (2):** ✨ **NEW in Migration 003**
6. `batch_update_contact_roles(updates JSONB)` - Batch update roles (Step 8)
7. `batch_update_contact_companies(updates JSONB)` - Batch update companies (Step 5)

---

## Verification

### After Migration 001:

```sql
SELECT * FROM free_email_providers LIMIT 5;
-- Should show gmail.com, yahoo.com, etc.

SELECT COUNT(*) FROM information_schema.tables
WHERE table_name IN ('internal_domains', 'free_email_providers', 'extraction_jobs',
                     'unified_email_rules', 'email_response_metrics', 'thread_status');
-- Should return: 6
```

### After Migration 002:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'customer_contacts'
  AND column_name IN ('seniority_level', 'engagement_score', 'is_decision_maker');
-- Should return all 3 columns

SELECT column_name FROM information_schema.columns
WHERE table_name = 'customer_companies'
  AND column_name IN ('relationship_status', 'communication_health', 'engagement_score');
-- Should return all 3 columns

SELECT proname FROM pg_proc WHERE proname LIKE '%engagement%';
-- Should show update_contact_engagement_metrics, update_company_engagement_metrics
```

### After Migration 003:

```sql
-- Verify unique constraint exists
SELECT conname FROM pg_constraint
WHERE conname = 'customer_contacts_client_email_unique';
-- Should return: customer_contacts_client_email_unique

-- Verify batch update functions exist
SELECT proname FROM pg_proc
WHERE proname IN ('batch_update_contact_roles', 'batch_update_contact_companies');
-- Should return both function names

-- Test batch update (safe - updates 0 rows with empty array)
SELECT * FROM batch_update_contact_roles('[]'::JSONB);
-- Should return: updated_count=0, error_count=0
```

### After Migration 004:

```sql
-- Verify contact_type column exists
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'customer_contacts' AND column_name = 'contact_type';
-- Should return: contact_type | text | 'person'::text

-- View contact type distribution
SELECT contact_type, COUNT(*) as count
FROM customer_contacts
GROUP BY contact_type
ORDER BY count DESC;
-- Should show breakdown: person, automated, shared, mailing_list, etc.

-- Verify contact_type constraint
SELECT conname, consrc
FROM pg_constraint
WHERE conname LIKE '%contact_type%';
-- Should show CHECK constraint with allowed values
```

---

## Troubleshooting

### "Table already exists" Error
✅ **Expected behavior** - migrations use `CREATE TABLE IF NOT EXISTS`
- Safe to re-run migrations
- No data loss

### "Column already exists" Error
✅ **Expected behavior** - migrations use `ADD COLUMN IF NOT EXISTS`
- Safe to re-run migrations
- No data loss

### "FILTER is not a known variable" Error
❌ **Fixed in latest version** - Updated to use `CASE WHEN` syntax
- Re-download latest migration files
- Should not occur in current version

### Migration 001 passes but Migration 002 fails
- Check PostgreSQL version (requires 12+)
- Verify `customer_contacts` and `customer_companies` tables exist
- These tables should have been created in Sprint 1

---

## Rollback (If Needed)

### To Rollback Migration 004 (Contact Classification):

```sql
-- Remove contact_type column
ALTER TABLE customer_contacts DROP COLUMN IF EXISTS contact_type;

-- Note: This will revert batch_update_contact_companies to v1.1
-- You'll need to re-run Migration 003 to restore the original function
```

### To Rollback Migration 003 (Batch Operations):

```sql
-- Remove unique constraint
ALTER TABLE customer_contacts DROP CONSTRAINT IF EXISTS customer_contacts_client_email_unique;

-- Drop batch update functions
DROP FUNCTION IF EXISTS batch_update_contact_roles(JSONB);
DROP FUNCTION IF EXISTS batch_update_contact_companies(JSONB);

-- Drop index
DROP INDEX IF EXISTS idx_customer_contacts_client_email;
```

### To Rollback Migration 002 (Column Additions):

```sql
-- Remove columns from customer_contacts
ALTER TABLE customer_contacts DROP COLUMN IF EXISTS seniority_level;
ALTER TABLE customer_contacts DROP COLUMN IF EXISTS functional_role;
-- ... (repeat for all added columns)

-- Remove columns from customer_companies
ALTER TABLE customer_companies DROP COLUMN IF EXISTS contact_count;
-- ... (repeat for all added columns)

-- Drop functions
DROP FUNCTION IF EXISTS get_unlinked_emails_count(UUID);
DROP FUNCTION IF EXISTS get_domain_summary(UUID, UUID);
DROP FUNCTION IF EXISTS link_emails_by_domain(UUID, TEXT, UUID);
DROP FUNCTION IF EXISTS update_contact_engagement_metrics(UUID);
DROP FUNCTION IF EXISTS update_company_engagement_metrics(UUID);
```

### To Rollback Migration 001 (New Tables):

```sql
-- WARNING: This deletes all data in these tables
DROP TABLE IF EXISTS thread_status CASCADE;
DROP TABLE IF EXISTS email_response_metrics CASCADE;
DROP TABLE IF EXISTS unified_email_rules CASCADE;
DROP TABLE IF EXISTS extraction_jobs CASCADE;
DROP TABLE IF EXISTS internal_domains CASCADE;
DROP TABLE IF EXISTS free_email_providers CASCADE;
```

---

## Updating Master Schema

When making changes to Sprint 2 schema:

1. Update the relevant migration file (001 or 002)
2. Update `SPRINT2_MASTER_SCHEMA.sql` to match
3. Update the CHANGE LOG at the bottom of master schema
4. Update this README if structure changes

---

## Performance Notes

### Migration 003 Impact

**Before Migration 003:**
- Contact updates: 500+ individual PATCH requests (~2-3 minutes)
- Role updates: Skipped for testing (not persisted to database)

**After Migration 003:**
- Contact updates: 1-2 batch RPC calls (~1 second)
- Role updates: 1-2 batch RPC calls (~1 second)
- **Overall improvement:** 25x faster extraction pipeline
- **Tested on:** 500+ emails, ~26 seconds total pipeline time

### When to Run Migration 003

⚠️ **IMPORTANT:** Run Migration 003 AFTER you've tested the extraction pipeline:

1. ✅ Run Migrations 001 & 002 first
2. ✅ Test extraction pipeline on 100-500 emails
3. ✅ Verify contacts/companies created correctly
4. ✅ Then run Migration 003 for production performance

**Why this order?**
- Migration 003 adds a unique constraint
- Testing first ensures no duplicate (client_id, email) combinations exist
- If duplicates exist, constraint will fail
- Pipeline testing helps identify and fix duplicates first

---

## Next Steps After Migration

1. ✅ Verify all tables/columns created (run verification queries above)
2. ✅ Test extraction pipeline: `python scripts/sprint2/test_extraction_pipeline.py full <mailbox_id> --limit 100`
3. ✅ Run Migration 003 after successful test
4. → Proceed to Phase 3: Email Rules Intelligence (Gmail/Outlook sync)
5. → Proceed to Phase 4: Engagement Analytics (response times, thread tracking)

---

## Support

- See `docs/SPRINT2_IMPLEMENTATION.md` for complete implementation plan
- See `~/.claude/plans/splendid-wondering-hinton.md` for strategic review
- Check migration SQL files for inline comments and documentation
