#!/usr/bin/env python3
"""Check reprocessing job status"""

import os
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

client = create_client(supabase_url, supabase_key)

# Check processing jobs
print("=== Processing Jobs ===")
jobs = client.table('processing_jobs').select('*').order('created_at', desc=True).limit(10).execute()
for job in jobs.data:
    print(f"ID: {job['id']}")
    print(f"  Type: {job['job_type']}")
    print(f"  Status: {job['status']}")
    print(f"  Total: {job['total_records']}, Processed: {job['processed_records']}, Failed: {job['failed_records']}")
    print(f"  Started: {job.get('started_at', 'Not started')}")
    print(f"  Error: {job.get('error_log', 'None')}")
    print()

# Check emails count
emails = client.table('emails').select('id', count='exact').execute()
print(f"=== Total Emails: {emails.count} ===")

# Check email_categories count
categories = client.table('email_categories').select('*', count='exact').execute()
print(f"=== Total Email Categories: {categories.count} ===")

if categories.count > 0:
    print("\nSample categories:")
    for cat in categories.data[:10]:
        print(f"  Email: {cat['email_id']}, Category: {cat['category']}, Type: {cat.get('tag_type', 'N/A')}")
