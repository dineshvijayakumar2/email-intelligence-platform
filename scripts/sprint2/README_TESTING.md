# Sprint 2 Extraction Pipeline - Testing Guide

## Quick Start

### Prerequisites

1. **Get your Mailbox ID** from Supabase:
```sql
SELECT id, email_address, mailbox_type
FROM mailboxes
WHERE email_address = 'your-email@example.com';
```

2. **Get your Client ID** from Supabase:
```sql
SELECT id, company_name
FROM clients;
```

3. **Ensure migrations are applied**:
```bash
# Check if Sprint 2 tables exist
psql -h your-db-host -d your-db -c "SELECT table_name FROM information_schema.tables WHERE table_name IN ('extraction_jobs', 'internal_domains', 'free_email_providers');"
```

4. **Set environment variables** (optional):
```bash
# For Redis (if using)
export REDIS_URL=redis://localhost:6379
# or
export REDIS_HOST=localhost
export REDIS_PORT=6379

# For Supabase (if not using .env file)
export SUPABASE_URL=your-url
export SUPABASE_SERVICE_KEY=your-key
```

---

## Test Commands

### 1. Test Full Pipeline (Recommended First Run)

**Test with a small subset first:**
```bash
python scripts/sprint2/test_extraction_pipeline.py full <mailbox_id> --limit 100
```

**Full extraction (all emails):**
```bash
python scripts/sprint2/test_extraction_pipeline.py full <mailbox_id>
```

**Skip role classification (faster):**
```bash
python scripts/sprint2/test_extraction_pipeline.py full <mailbox_id> --skip-roles
```

**Expected output:**
```
================================================================================
            FULL EXTRACTION PIPELINE TEST
================================================================================

Mailbox ID: abc-123-def
Skip roles: False
Limit: None (process all)

--------------------------------------------------------------------------------
  Initializing Orchestrator
--------------------------------------------------------------------------------
Redis progress tracking enabled

--------------------------------------------------------------------------------
  Running Extraction Pipeline
--------------------------------------------------------------------------------
================================================================================
STEP 1/13: Validate prerequisites
================================================================================
Mailbox validated: test@example.com (GMAIL)
Total emails to process: 4009

================================================================================
STEP 2/13: Extract contacts from emails
================================================================================
Processing 4009 emails for contact extraction
Extracted 387 contacts

...

================================================================================
                        EXTRACTION RESULTS
================================================================================

✓ SUCCESS - Completed in 123.45s

Job ID: 550e8400-e29b-41d4-a716-446655440000

📊 Pipeline Summary:
  emails_processed: 4009
  contacts_extracted: 387
  contacts_created: 312
  contacts_updated: 75
  companies_resolved: 127
  companies_created: 89
  companies_updated: 38
  emails_linked: 3487
  link_rate: 87.0%
  roles_classified: 271
  decision_makers: 34

💾 Full results saved to: extraction_results_550e8400-e29b-41d4-a716-446655440000.json
```

---

### 2. Test Individual Services

#### A. Contact Extractor Only

```bash
# Test with all emails
python scripts/sprint2/test_extraction_pipeline.py contacts <mailbox_id>

# Test with first 100 emails
python scripts/sprint2/test_extraction_pipeline.py contacts <mailbox_id> --limit 100
```

**Expected output:**
```
📊 Contact Extraction Summary:
  total_contacts: 387
  sender_contacts: 348
  recipient_contacts: 387
  mailing_list_contacts: 12
  noreply_contacts: 23
  shared_contacts: 8
  distribution_contacts: 15
  personal_contacts: 341

📋 Top 10 Most Active Contacts:
 1. john.doe@acme.com                          (John Doe                 ) -  45 emails
     Domain: acme.com                        Type: personal
 2. jane.smith@techcorp.com                    (Jane Smith               ) -  38 emails
     Domain: techcorp.com                    Type: personal
...

💾 Contacts saved to: contacts_abc-123-.json
```

#### B. Company Resolver

```bash
python scripts/sprint2/test_extraction_pipeline.py companies <mailbox_id> <client_id>
```

**Expected output:**
```
📊 Company Resolution Summary:
  total_companies: 127
  new_companies: 89
  existing_companies: 38
  by_classification: {'customer': 115, 'free_provider': 12}
  total_contacts: 387
  total_emails: 4009

🏢 Top 10 Companies by Email Volume:
 1. [NEW     ] Acme Corporation                   (acme.com)
     Contacts:  12  Emails:  456  Classification: customer
 2. [EXISTING] TechCorp Inc                       (techcorp.com)
     Contacts:   8  Emails:  342  Classification: customer
...
```

#### C. Role Classifier

```bash
python scripts/sprint2/test_extraction_pipeline.py roles <mailbox_id>
```

**Expected output:**
```
📊 Role Classification Summary:
  total_contacts: 387
  with_extracted_title: 271
  title_extraction_rate: 70.03
  decision_makers: 34
  decision_maker_rate: 8.78
  avg_confidence: 0.72
  by_seniority: {'c_level': 12, 'vp': 8, 'director': 15, 'manager': 48, ...}
  by_role: {'executive': 12, 'sales': 89, 'marketing': 42, ...}

👔 Decision Makers Found (34):
 1. john.doe@acme.com
     CEO & Founder                                      [c_level, executive]
 2. jane.smith@techcorp.com
     VP of Sales                                        [vp, sales]
...

📊 Distribution by Seniority Level:
  c_level   :  12 ██████
  vp        :   8 ████
  director  :  15 ███████
  manager   :  48 ████████████████████████
...
```

#### D. Email Linker

```bash
python scripts/sprint2/test_extraction_pipeline.py linker <mailbox_id>
```

**Expected output:**
```
📊 Before Linking:
  total_emails: 4009
  linked_emails: 0
  company_linked_emails: 0
  unlinked_emails: 4009
  contact_link_rate: 0.0
  company_link_rate: 0.0

✓ Completed in 18.23s
  Linked: 3487
  Skipped: 522
  Errors: 0

📊 Updated Stats:
  total_emails: 4009
  linked_emails: 3487
  company_linked_emails: 3204
  unlinked_emails: 522
  contact_link_rate: 87.0
  company_link_rate: 79.9

📈 Improvement: +87.0% link rate
```

---

### 3. Check Job Progress (While Running)

While an extraction job is running, check progress from another terminal:

```bash
python scripts/sprint2/test_extraction_pipeline.py progress <job_id>
```

**Expected output:**
```
================================================================================
                    JOB PROGRESS CHECK
================================================================================

Job ID: 550e8400-e29b-41d4-a716-446655440000

--------------------------------------------------------------------------------
  Progress
--------------------------------------------------------------------------------
  Status: running
  Current step: 7/13
  Description: Classify roles from signatures

  [███████████████████████████░░░░░░░░░░░░░░░░░░░░░░░] 53.8%

  Mailbox ID: abc-123-def
  Client ID: xyz-789-ghi
```

---

## Troubleshooting

### Error: "Mailbox not found"
```bash
# Verify mailbox exists
psql -h your-db-host -d your-db -c "SELECT id, email_address FROM mailboxes WHERE id = 'your-mailbox-id';"
```

### Error: "Failed to connect to Redis"
This is not critical - the pipeline will still work, but progress tracking will only be in the database.

To fix:
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG

# Or disable Redis tracking (it will fallback to database only)
# Modify orchestrator initialization in the script
```

### Error: "Table extraction_jobs does not exist"
```bash
# Run Sprint 2 migrations
psql -h your-db-host -d your-db -f scripts/sprint2/sprint2_migration_001_new_tables.sql
psql -h your-db-host -d your-db -f scripts/sprint2/sprint2_migration_002_column_additions.sql
```

### Low Link Rate (< 70%)
This means many emails couldn't be linked to contacts. Possible causes:
1. Run contact extractor first: `python scripts/sprint2/test_extraction_pipeline.py contacts <mailbox_id>`
2. Run company resolver: `python scripts/sprint2/test_extraction_pipeline.py companies <mailbox_id> <client_id>`
3. Then run linker again

### Slow Performance
For large mailboxes (10k+ emails):
1. Test with `--limit 1000` first
2. Ensure database has proper indexes
3. Consider increasing batch sizes in service code
4. Monitor database connection pool

---

## Understanding the Results

### Contact Link Rate
Percentage of emails successfully linked to a customer_contact record.
- **Good**: 80%+
- **Fair**: 60-80%
- **Low**: < 60% (investigate why contacts weren't created)

### Title Extraction Rate
Percentage of contacts with job titles extracted from email signatures.
- **Good**: 60%+
- **Fair**: 40-60%
- **Low**: < 40% (emails may not have signatures or signatures are poorly formatted)

### Decision Maker Rate
Percentage of contacts classified as decision makers (C-level, VP, Director).
- Typically: 5-15% depending on your customer base
- B2B enterprise: 10-20%
- SMB: 5-10%

---

## Next Steps After Testing

1. **Review the extraction results JSON file** to understand what was extracted
2. **Query the database** to see the new data:
   ```sql
   -- Check contacts
   SELECT COUNT(*) FROM customer_contacts WHERE mailbox_id = 'your-mailbox-id';

   -- Check companies
   SELECT company_name, contact_count FROM customer_companies WHERE client_id = 'your-client-id' ORDER BY contact_count DESC LIMIT 10;

   -- Check linked emails
   SELECT COUNT(*) FROM emails WHERE customer_contact_id IS NOT NULL;

   -- Check decision makers
   SELECT email, title, seniority_level, functional_role FROM customer_contacts WHERE is_decision_maker = true;
   ```

3. **Run full extraction on production mailboxes** when satisfied with test results

4. **Set up scheduled extraction jobs** (Phase 5) to keep data fresh

---

## Performance Benchmarks

Based on 4000 emails:

| Step | Expected Time | Notes |
|------|--------------|-------|
| Contact extraction | 10-15s | Depends on email complexity |
| Company resolution | 5-10s | Depends on domain lookups |
| Role classification | 30-60s | Signature parsing is CPU intensive |
| Email linking | 15-25s | Depends on contact count |
| **Total** | **~2-3 minutes** | For 4000 emails |

Scale estimate: **~30-45 emails per second** end-to-end.

---

## Support

If you encounter issues:
1. Check the logs (they're very detailed)
2. Review the error messages
3. Verify migrations are applied correctly
4. Check the generated JSON result files for detailed error information
