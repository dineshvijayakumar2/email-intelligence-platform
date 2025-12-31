-- Check what job_type values exist
SELECT id, job_type, status, mailbox_id, total_records, processed_records
FROM processing_jobs
ORDER BY created_at DESC
LIMIT 10;
