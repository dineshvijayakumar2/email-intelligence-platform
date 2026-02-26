"""
Diagnose mailbox email status

Usage:
    python scripts/sprint2/diagnose_mailbox.py <mailbox_id>
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent / 'backend'
sys.path.insert(0, str(backend_path))

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_file = backend_path / '.env'
    env_dev_file = backend_path / '.env.development'

    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded environment from {env_file}")
    elif env_dev_file.exists():
        load_dotenv(env_dev_file)
        print(f"✓ Loaded environment from {env_dev_file}")
except ImportError:
    print("⚠ Warning: python-dotenv not installed")

try:
    from backend.src.database.supabase_client import SupabaseClient
except ImportError as e:
    print(f"❌ Error: {e}")
    print("Please install dependencies: pip install supabase")
    sys.exit(1)


def diagnose_mailbox(mailbox_id: str):
    """Diagnose mailbox email processing status"""
    print("\n" + "=" * 80)
    print("MAILBOX DIAGNOSTIC".center(80))
    print("=" * 80 + "\n")

    try:
        client = SupabaseClient.get_client(use_service_key=True)

        # Get mailbox info
        mailbox_response = (
            client.table('mailboxes')
            .select('id, email_address, mailbox_type')
            .eq('id', mailbox_id)
            .execute()
        )

        if not mailbox_response.data:
            print(f"❌ Mailbox {mailbox_id} not found")
            return

        mailbox = mailbox_response.data[0]
        print(f"📧 Mailbox: {mailbox['email_address']}")
        print(f"   Type: {mailbox['mailbox_type']}")
        print(f"   ID: {mailbox_id}\n")

        # Count total emails
        total_response = (
            client.table('emails')
            .select('id', count='exact')
            .eq('mailbox_id', mailbox_id)
            .execute()
        )

        total_count = total_response.count
        print(f"📊 Total Emails: {total_count}\n")

        if total_count == 0:
            print("❌ No emails found in this mailbox")
            print("\n💡 You need to sync emails first using the email sync functionality")
            return

        # Count by processing_status
        print("📈 Breakdown by processing_status:\n")

        # Get all possible statuses
        status_response = (
            client.table('emails')
            .select('processing_status')
            .eq('mailbox_id', mailbox_id)
            .execute()
        )

        # Count statuses
        status_counts = {}
        for email in status_response.data:
            status = email.get('processing_status') or 'null'
            status_counts[status] = status_counts.get(status, 0) + 1

        for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_count) * 100
            print(f"   {status:20s}: {count:6d} ({percentage:5.1f}%)")

        print()

        # Check if any are success
        success_count = status_counts.get('success', 0)

        if success_count == 0:
            print("❌ PROBLEM: No emails with processing_status='success'")
            print("\n💡 Solutions:")
            print("   1. If emails were recently synced, they may still be processing")
            print("   2. Check processing_jobs table for failed jobs")
            print("   3. Re-run email processing on this mailbox")
            print("   4. Update processing_status manually for testing:")
            print(f"\n      UPDATE emails SET processing_status = 'success'")
            print(f"      WHERE mailbox_id = '{mailbox_id}'")
            print(f"      AND processing_status IS NULL OR processing_status = 'pending';")
        else:
            print(f"✅ Found {success_count} successfully processed emails")
            print(f"\n💡 You can now run extraction:")
            print(f"   python scripts/sprint2/test_extraction_pipeline.py full {mailbox_id} --limit 100")

        # Sample a few emails
        print("\n" + "-" * 80)
        print("📧 Sample Emails (first 5):\n")

        sample_response = (
            client.table('emails')
            .select('id, subject, sent_date, processing_status, sender_email')
            .eq('mailbox_id', mailbox_id)
            .order('sent_date', desc=True)
            .limit(5)
            .execute()
        )

        for i, email in enumerate(sample_response.data, 1):
            print(f"{i}. {email.get('subject', 'No subject')[:60]}")
            print(f"   From: {email.get('sender_email', 'Unknown')}")
            print(f"   Date: {email.get('sent_date', 'Unknown')}")
            print(f"   Status: {email.get('processing_status', 'null')}")
            print()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/sprint2/diagnose_mailbox.py <mailbox_id>")
        print("\nGet mailbox ID by running:")
        print("  python scripts/sprint2/get_ids.py")
        sys.exit(1)

    mailbox_id = sys.argv[1]
    diagnose_mailbox(mailbox_id)


if __name__ == '__main__':
    main()
