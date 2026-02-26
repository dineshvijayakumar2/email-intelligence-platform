"""
Debug Email Linking Issue

Usage:
    python scripts/sprint2/debug_email_linking.py <mailbox_id>
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent / 'backend'
sys.path.insert(0, str(backend_path))

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_file = backend_path / '.env'
    env_dev_file = backend_path / '.env.development'

    if env_file.exists():
        load_dotenv(env_file)
    elif env_dev_file.exists():
        load_dotenv(env_dev_file)
except ImportError:
    pass

try:
    from backend.src.database.supabase_client import SupabaseClient
except ImportError as e:
    print(f"Error: {e}")
    sys.exit(1)


def debug_email_linking(mailbox_id: str):
    """Debug why emails are not linking to contacts"""
    print("\n" + "=" * 80)
    print("EMAIL LINKING DIAGNOSTIC".center(80))
    print("=" * 80 + "\n")

    try:
        client = SupabaseClient.get_client(use_service_key=True)

        # Get mailbox info
        mailbox_response = client.table('mailboxes').select('id, email_address, client_id').eq('id', mailbox_id).execute()

        if not mailbox_response.data:
            print(f"❌ Mailbox {mailbox_id} not found")
            return

        mailbox = mailbox_response.data[0]
        client_id = mailbox.get('client_id')

        print(f"📧 Mailbox: {mailbox.get('email_address')}")
        print(f"   Client ID: {client_id}\n")

        if not client_id:
            print("❌ No client_id assigned to mailbox!")
            return

        # Count contacts for this client
        contacts_response = client.table('customer_contacts').select('id, email_address', count='exact').eq('client_id', client_id).execute()

        print(f"📊 Total Contacts: {contacts_response.count}")

        if contacts_response.count > 0:
            print(f"\n   Sample Contacts (first 5):")
            for i, contact in enumerate(contacts_response.data[:5], 1):
                print(f"   {i}. {contact['email_address']}")

        print("\n" + "-" * 80)

        # Get sample emails to link
        emails_response = (
            client.table('emails')
            .select('id, sender_email, recipients, is_outbound, customer_contact_id')
            .eq('mailbox_id', mailbox_id)
            .eq('processing_status', 'success')
            .limit(10)
            .execute()
        )

        print(f"\n📧 Sample Emails (first 10):\n")

        linked_count = 0
        unlinked_count = 0

        for i, email in enumerate(emails_response.data, 1):
            is_outbound = email.get('is_outbound', False)
            linked = email.get('customer_contact_id') is not None

            if linked:
                linked_count += 1
            else:
                unlinked_count += 1

            # Determine which email to check
            if is_outbound:
                recipients = email.get('recipients', [])
                if recipients and len(recipients) > 0:
                    if isinstance(recipients[0], dict):
                        check_email = recipients[0].get('email', 'Unknown')
                    else:
                        check_email = recipients[0]
                else:
                    check_email = 'No recipients'
                direction = "OUT"
            else:
                check_email = email.get('sender_email', 'Unknown')
                direction = "IN "

            # Check if this email exists in contacts
            if check_email != 'Unknown' and check_email != 'No recipients':
                contact_check = (
                    client.table('customer_contacts')
                    .select('id, email_address')
                    .eq('client_id', client_id)
                    .eq('email_address', check_email)
                    .execute()
                )
                contact_exists = len(contact_check.data) > 0
            else:
                contact_exists = False

            status = "✅ LINKED" if linked else ("📧 CONTACT EXISTS" if contact_exists else "❌ NO CONTACT")

            print(f"   {i}. [{direction}] {check_email[:50]}")
            print(f"      Status: {status}")
            if linked:
                print(f"      Linked to: {email['customer_contact_id'][:8]}...")
            print()

        print("-" * 80)
        print(f"\n📊 Summary:")
        print(f"   Linked emails: {linked_count}/10")
        print(f"   Unlinked emails: {unlinked_count}/10")

        # Get overall stats
        total_emails = client.table('emails').select('id', count='exact').eq('mailbox_id', mailbox_id).eq('processing_status', 'success').execute().count

        linked_emails = (
            client.table('emails')
            .select('id', count='exact')
            .eq('mailbox_id', mailbox_id)
            .eq('processing_status', 'success')
            .not_.is_('customer_contact_id', 'null')
            .execute().count
        )

        link_rate = (linked_emails / total_emails * 100) if total_emails > 0 else 0

        print(f"\n📈 Overall Stats:")
        print(f"   Total emails: {total_emails}")
        print(f"   Linked emails: {linked_emails}")
        print(f"   Link rate: {link_rate:.2f}%")

        print("\n" + "=" * 80)
        print("💡 DIAGNOSIS:\n")

        if link_rate < 10:
            print("   ❌ CRITICAL: Very low link rate (<10%)")
            print("   → Email linker may not be running correctly")
            print("   → Check that Step 9 completes without errors")
        elif link_rate < 50:
            print("   ⚠️  WARNING: Low link rate (<50%)")
            print("   → Many contacts not matching email addresses")
            print("   → Check for email address format mismatches")
        else:
            print("   ✅ Link rate looks acceptable")

        if contacts_response.count == 0:
            print("\n   ❌ No contacts found for this client!")
            print("   → Run extraction pipeline first to create contacts")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/sprint2/debug_email_linking.py <mailbox_id>")
        sys.exit(1)

    mailbox_id = sys.argv[1]
    debug_email_linking(mailbox_id)


if __name__ == '__main__':
    main()
