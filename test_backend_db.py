#!/usr/bin/env python3
"""
Test if backend can connect to Supabase
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

print(f"Loading .env from: {dotenv_path}")
print(f"SUPABASE_URL exists: {bool(os.getenv('SUPABASE_URL'))}")
print(f"SUPABASE_SERVICE_ROLE_KEY exists: {bool(os.getenv('SUPABASE_SERVICE_ROLE_KEY'))}")

# Try to import and use supabase
from supabase import create_client

try:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        print("ERROR: Environment variables not set!")
        sys.exit(1)

    print(f"\nSUPABASE_URL: {supabase_url[:30]}...")
    print(f"SUPABASE_SERVICE_ROLE_KEY: {supabase_key[:20]}...")

    print("\nCreating Supabase client...")
    client = create_client(supabase_url, supabase_key)
    print("✓ Supabase client created successfully")

    print("\nTesting database query...")
    result = client.table('mailboxes').select('id, name').limit(5).execute()
    print(f"✓ Query successful! Found {len(result.data)} mailboxes:")
    for mb in result.data:
        print(f"  - {mb['name']} ({mb['id']})")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓ All tests passed! Backend should be able to connect to database.")
