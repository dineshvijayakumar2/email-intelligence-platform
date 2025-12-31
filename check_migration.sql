-- Check if tag_type column exists
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'email_categories'
ORDER BY ordinal_position;

-- Check if indexes exist
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'email_categories';

-- Check sample data
SELECT COUNT(*) as total_categories FROM email_categories;
SELECT COUNT(DISTINCT email_id) as emails_with_categories FROM email_categories;
