# QB-Anchored Company Cleanup Plan

**Goal:** Make QB the sole source of truth for company identity. Fix contaminated SB companies, move contacts to correct rows, stop pipeline from creating junk companies.

**Date:** 2026-05-11

## Status

| Step | Script | Status |
|------|--------|--------|
| 1 Pre-flight | `step1_preflight_name_collisions.py` | PASS (4.5% < 5%) |
| 1 Execute | `step1_execute_create_sb_from_qb.py --execute` | RUNNING |
| 2 Pre-flight | `step2_preflight_contact_moves.py` | READY |
| 2 Execute | `step2_execute_contact_moves.py --execute` | READY (needs Step 1 done) |
| 3 Pre-flight | `step3_preflight_contamination.py` | READY |
| 3 Execute | `step3_execute_decontaminate.py --execute` | READY |
| 4 Pre-flight | `step4_preflight_orphan_sb.py` | READY (bucket list) |
| 5 Code change | `company_resolver.py` | DONE (Phase 2 locked to existing-only) |

## Key Numbers (diagnosis baseline)

- **15,152** QB customers ($46.8M total revenue)
- **14,898** SB companies (before cleanup)
- **20,894** contacts
- **2,207** contaminated SB companies (>1 QB customer matched)
- **8,925** unmatched QB customers (no SB company)

## Step 1: Create SB from QB (315 links + 8,519 creates + 91 review)

- Pre-flight: 406 name collisions (4.5%), 315 easy-link, 91 need review
- Execution: batch-50 insert + individual QB update
- Review cases: `step1_review_cases.json`

## Step 2: Move contacts to correct SB

- ~3,258 contacts to move (1,294 wrong SB + 1,964 pending SB from Step 1)
- Dry-run first, then `--execute`
- Unique constraint guard: (customer_company_id, email_address)

## Step 3: Decontaminate 2,207 SB companies

- Auto-resolve: 1 real QB + N junk $0 → unlink junk
- All-junk: every QB is $0 → unlink all
- Multi-real: manual review → `step3_review_cases.json`

## Step 4: Soft-delete orphan SB rows (bucket list)

- SB companies with no QB match AND no contacts
- Check FK references (emails, quotes) before delete

## Step 5: Lock down CompanyResolver

- Phase 2 (domain fallback): only match to EXISTING companies
- Never call `domain_to_company_name()` for new domains
- Never call `_create_individual_company()` for free providers
- Contacts without match → stay unlinked (NULL company_id)
- `_link_orphan_contacts()` is safe (only links to existing by domain)

## All scripts in `scripts/db/`

All execution scripts default to **dry-run**. Pass `--execute` to write.
