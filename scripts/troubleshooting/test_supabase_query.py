#!/usr/bin/env python3
"""Test what Supabase query returns for categories"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(dotenv_path="frontend/.env.local")

# Use anon key like frontend does
client = create_client(
    os.getenv("REACT_APP_SUPABASE_URL"),
    os.getenv("REACT_APP_SUPABASE_ANON_KEY")
)

print("Testing Supabase query like frontend does...")
print(f"URL: {os.getenv('REACT_APP_SUPABASE_URL')}")

# Exact same query as frontend
result = client.table('email_categories')\
    .select('category')\
    .execute()

print(f"\nTotal rows returned: {len(result.data)}")

# Get unique categories
categories = set()
for item in result.data:
    if item['category']:
        categories.add(item['category'])

print(f"Unique categories: {len(categories)}")
print("\nCategories (sorted):")
for cat in sorted(categories):
    if not cat.startswith('_meta_'):
        print(f"  - {cat}")

print("\n Metadata categories:")
for cat in sorted(categories):
    if cat.startswith('_meta_'):
        print(f"  - {cat}")
