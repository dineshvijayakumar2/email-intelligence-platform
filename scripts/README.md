# Scripts Directory

This directory contains utility scripts for testing, troubleshooting, and maintenance.

## Structure

- **troubleshooting/** - Scripts for diagnosing issues and checking system status
- **tests/** - Test scripts for validating functionality

## Troubleshooting Scripts

### `check_categories.py`
Check email categories and processing job status in the database.

```bash
source venv/bin/activate
python3 scripts/troubleshooting/check_categories.py
```

### `check_reprocess_status.py`
Monitor reprocessing job progress and email categorization status.

```bash
source venv/bin/activate
python3 scripts/troubleshooting/check_reprocess_status.py
```

### `test_supabase_query.py`
Test Supabase queries to verify category filtering and data retrieval.

```bash
source venv/bin/activate
python3 scripts/troubleshooting/test_supabase_query.py
```

### `test_tagger.py`
Verify EmailTagger functionality with sample emails.

```bash
source venv/bin/activate
python3 scripts/troubleshooting/test_tagger.py
```

### `check_jobs.sql`
SQL query to check processing jobs status. Run in Supabase SQL Editor.

## Notes

- All Python scripts require the virtual environment to be activated
- Scripts use `.env` or `frontend/.env.local` for Supabase credentials
- SQL scripts should be run directly in Supabase SQL Editor
