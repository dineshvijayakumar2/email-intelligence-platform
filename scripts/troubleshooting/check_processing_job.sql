-- Check the most recent processing job
SELECT 
    id,
    mailbox_id,
    status,
    processed_records,
    failed_records,
    error_log,
    created_at,
    completed_at
FROM processing_jobs
WHERE mailbox_id = '12452d9f-9524-4cc7-9c85-0d703b5650b7'
ORDER BY created_at DESC
LIMIT 1;
