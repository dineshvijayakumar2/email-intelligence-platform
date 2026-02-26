"""
Helper script to get Mailbox and Client IDs

Usage:
    python scripts/sprint2/get_ids.py
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

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Try .env first, then .env.development
    env_file = backend_path / '.env'
    env_dev_file = backend_path / '.env.development'

    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded environment from {env_file}")
    elif env_dev_file.exists():
        load_dotenv(env_dev_file)
        print(f"✓ Loaded environment from {env_dev_file}")
    else:
        print("⚠ Warning: No .env file found")
except ImportError:
    print("⚠ Warning: python-dotenv not installed, using system environment variables")

try:
    from backend.src.database.supabase_client import SupabaseClient
except ImportError as e:
    print("=" * 80)
    print("ERROR: Required dependencies not installed")
    print("=" * 80)
    print(f"\nImport error: {e}\n")
    print("Please install dependencies first:")
    print("\n  cd backend")
    print("  pip install -r requirements.txt")
    print("\nOr if using Poetry:")
    print("\n  cd backend")
    print("  poetry install")
    print("\n" + "=" * 80)
    sys.exit(1)


def print_banner(text: str):
    """Print a nice banner"""
    width = 80
    print("\n" + "=" * width)
    print(text.center(width))
    print("=" * width + "\n")


def get_mailboxes():
    """Get all mailboxes"""
    print_banner("AVAILABLE MAILBOXES")

    try:
        client = SupabaseClient.get_client(use_service_key=True)

        response = client.table('mailboxes').select('id, email_address, mailbox_type, client_id').execute()

        if not response.data:
            print("❌ No mailboxes found")
            return

        print(f"Found {len(response.data)} mailbox(es):\n")

        for i, mailbox in enumerate(response.data, 1):
            print(f"{i}. Email: {mailbox['email_address']}")
            print(f"   Type: {mailbox['mailbox_type']}")
            print(f"   Mailbox ID: {mailbox['id']}")
            print(f"   Client ID: {mailbox['client_id']}")

            # Count emails
            email_count = client.table('emails').select('id', count='exact').eq('mailbox_id', mailbox['id']).execute()
            print(f"   Total Emails: {email_count.count}")

            # Count successful emails
            success_count = client.table('emails').select('id', count='exact').eq('mailbox_id', mailbox['id']).eq('processing_status', 'success').execute()
            print(f"   Successful Emails: {success_count.count}")

            print()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def get_clients():
    """Get all clients"""
    print_banner("AVAILABLE CLIENTS")

    try:
        client = SupabaseClient.get_client(use_service_key=True)

        # Try to get all columns - handle different schema versions
        try:
            response = client.table('clients').select('*').execute()
        except Exception as e:
            print(f"❌ Error accessing clients table: {e}")
            return

        if not response.data:
            print("❌ No clients found")
            return

        print(f"Found {len(response.data)} client(s):\n")

        for i, client_data in enumerate(response.data, 1):
            # Try different possible column names for company/name
            name = (
                client_data.get('company_name') or
                client_data.get('name') or
                client_data.get('client_name') or
                'Unknown'
            )

            print(f"{i}. Company: {name}")
            print(f"   Client ID: {client_data['id']}")

            if 'created_at' in client_data:
                print(f"   Created: {client_data['created_at']}")

            # Show email if available
            if 'email' in client_data:
                print(f"   Email: {client_data['email']}")

            print()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def get_extraction_jobs():
    """Get recent extraction jobs"""
    print_banner("RECENT EXTRACTION JOBS")

    try:
        client = SupabaseClient.get_client(use_service_key=True)

        response = (
            client.table('extraction_jobs')
            .select('id, status, mailbox_id, current_step, current_step_number, total_steps, started_at, completed_at')
            .order('started_at', desc=True)
            .limit(10)
            .execute()
        )

        if not response.data:
            print("ℹ️  No extraction jobs found (run your first extraction!)")
            return

        print(f"Found {len(response.data)} recent job(s):\n")

        for i, job in enumerate(response.data, 1):
            status_emoji = {
                'running': '🔄',
                'completed': '✅',
                'failed': '❌',
                'pending': '⏳'
            }.get(job['status'], '❓')

            print(f"{i}. {status_emoji} {job['status'].upper()}")
            print(f"   Job ID: {job['id']}")
            print(f"   Mailbox: {job['mailbox_id']}")

            if job['status'] == 'running':
                print(f"   Progress: {job['current_step_number']}/{job['total_steps']} - {job['current_step']}")
            elif job['status'] == 'completed':
                print(f"   Completed: {job['completed_at']}")
            elif job['status'] == 'failed':
                print(f"   Failed at step: {job['current_step_number']}/{job['total_steps']}")

            print(f"   Started: {job['started_at']}")
            print()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main entry point"""
    try:
        # Get mailboxes
        get_mailboxes()

        # Get clients
        get_clients()

        # Get recent extraction jobs
        get_extraction_jobs()

        # Print example commands
        print_banner("EXAMPLE TEST COMMANDS")

        try:
            client = SupabaseClient.get_client(use_service_key=True)
            mailbox = client.table('mailboxes').select('id, client_id').limit(1).execute()

            if mailbox.data:
                mailbox_id = mailbox.data[0]['id']
                client_id = mailbox.data[0]['client_id']

                print("# Test full pipeline:")
                print(f"python scripts/sprint2/test_extraction_pipeline.py full {mailbox_id}")
                print()

                print("# Test with 100 emails (faster):")
                print(f"python scripts/sprint2/test_extraction_pipeline.py full {mailbox_id} --limit 100")
                print()

                print("# Test contacts only:")
                print(f"python scripts/sprint2/test_extraction_pipeline.py contacts {mailbox_id}")
                print()

                print("# Test companies:")
                print(f"python scripts/sprint2/test_extraction_pipeline.py companies {mailbox_id} {client_id}")
                print()

                print("# Test roles:")
                print(f"python scripts/sprint2/test_extraction_pipeline.py roles {mailbox_id}")
                print()

                print("# Test email linker:")
                print(f"python scripts/sprint2/test_extraction_pipeline.py linker {mailbox_id}")
                print()

        except Exception as e:
            print(f"ℹ️  Could not generate example commands: {e}")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
