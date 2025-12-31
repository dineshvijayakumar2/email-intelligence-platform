#!/usr/bin/env python3
"""
List all mailboxes in the database
Useful for finding mailbox IDs to use with test_real_mbox.py
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from src.database.supabase_client import SupabaseClient


def list_mailboxes():
    """List all mailboxes with their details"""
    try:
        supabase = SupabaseClient.get_client(use_service_key=True)

        # Get all mailboxes
        result = supabase.table('mailboxes').select('*').execute()

        if not result.data:
            print("No mailboxes found in database.")
            return

        print(f"\n{'='*100}")
        print(f"Found {len(result.data)} mailbox(es):")
        print(f"{'='*100}\n")

        for i, mb in enumerate(result.data, 1):
            print(f"{i}. {mb['name']}")
            print(f"   ID: {mb['id']}")
            print(f"   Type: {mb['mailbox_type']}")
            print(f"   Email: {mb.get('email_address', 'N/A')}")
            print(f"   Active: {mb.get('is_active', False)}")
            print(f"   Created: {mb.get('created_at', 'Unknown')}")

            # Show file path for MBOX
            if mb['mailbox_type'] == 'mbox':
                file_path = mb.get('connection_config', {}).get('file_path', 'N/A')
                # Truncate long paths
                if len(file_path) > 80:
                    file_path = '...' + file_path[-77:]
                print(f"   File: {file_path}")

            # Get email count for this mailbox
            try:
                count_result = supabase.table('emails')\
                    .select('id', count='exact')\
                    .eq('mailbox_id', mb['id'])\
                    .execute()
                email_count = count_result.count or 0
                print(f"   Emails: {email_count:,}")
            except:
                print(f"   Emails: Unknown")

            print()

        print(f"{'='*100}")
        print("\nTo use an existing mailbox with test_real_mbox.py:")
        print("  python test_real_mbox.py --mailbox-id <ID> --max-emails 100")
        print()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    list_mailboxes()
