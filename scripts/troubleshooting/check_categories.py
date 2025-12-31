#!/usr/bin/env python3
"""Quick check of email categories"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

# Check categories
print("=== Email Categories (non-metadata) ===")
result = client.table('email_categories')\
    .select('category, tag_type')\
    .execute()

print(f"Total rows: {len(result.data)}")

if result.data:
    from collections import Counter
    categories = Counter(item['category'] for item in result.data)
    print("\nCategory counts:")
    for cat, count in categories.most_common(20):
        print(f"  {cat}: {count}")
else:
    print("No categories found!")

# Check processing jobs
print("\n=== Recent Processing Jobs ===")
jobs = client.table('processing_jobs')\
    .select('id, job_type, status, total_records, processed_records, error_log, created_at')\
    .order('created_at', desc=True)\
    .limit(5)\
    .execute()

for job in jobs.data:
    print(f"Job {job['id'][:8]}... - {job['job_type']} - {job['status']} - {job['processed_records']}/{job['total_records']}")
    if job.get('error_log'):
        print(f"  Error: {job['error_log']}")
