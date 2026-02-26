"""
Diagnose contact extraction for a mailbox

Usage:
    python scripts/sprint2/diagnose_contacts.py <mailbox_id>
"""

import sys
import os
from pathlib import Path
from collections import Counter

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


def diagnose_contacts(mailbox_id: str):
    """Diagnose why contact extraction is finding so few contacts"""
    print("\n" + "=" * 80)
    print("CONTACT EXTRACTION DIAGNOSTIC".center(80))
    print("=" * 80 + "\n")

    try:
        client = SupabaseClient.get_client(use_service_key=True)

        # Get mailbox info
        mailbox_response = (
            client.table('mailboxes')
            .select('id, email_address, mailbox_type, client_id')
            .eq('id', mailbox_id)
            .execute()
        )

        if not mailbox_response.data:
            print(f"❌ Mailbox {mailbox_id} not found")
            return

        mailbox = mailbox_response.data[0]
        mailbox_email = mailbox.get('email_address')
        client_id = mailbox.get('client_id')

        print(f"📧 Mailbox: {mailbox_email or 'No email address'}")
        print(f"   Type: {mailbox['mailbox_type']}")
        print(f"   ID: {mailbox_id}")
        print(f"   Client ID: {client_id or 'No client_id'}\n")

        if not client_id:
            print("⚠️  WARNING: This mailbox has no client_id assigned!")
            print("   Cannot query customer_contacts or customer_companies.")
            print("   Please assign a client_id to this mailbox first.\n")

        # Count total emails
        total_response = (
            client.table('emails')
            .select('id', count='exact')
            .eq('mailbox_id', mailbox_id)
            .eq('processing_status', 'success')
            .execute()
        )
        total_emails = total_response.count
        print(f"📊 Total Emails (processing_status=success): {total_emails}\n")

        # Get email direction breakdown
        print("📈 Email Direction Breakdown:\n")

        # Inbound emails
        inbound_response = (
            client.table('emails')
            .select('id', count='exact')
            .eq('mailbox_id', mailbox_id)
            .eq('processing_status', 'success')
            .eq('is_outbound', False)
            .execute()
        )
        inbound_count = inbound_response.count

        # Outbound emails
        outbound_response = (
            client.table('emails')
            .select('id', count='exact')
            .eq('mailbox_id', mailbox_id)
            .eq('processing_status', 'success')
            .eq('is_outbound', True)
            .execute()
        )
        outbound_count = outbound_response.count

        print(f"   Inbound (customer → you):  {inbound_count:5d} ({inbound_count/total_emails*100:5.1f}%)")
        print(f"   Outbound (you → customer): {outbound_count:5d} ({outbound_count/total_emails*100:5.1f}%)")
        print()

        # Sample emails to understand structure
        print("📧 Sample Emails (5 inbound, 5 outbound):\n")

        # Get sample inbound
        sample_inbound = (
            client.table('emails')
            .select('id, subject, sender_email, sender_name, is_outbound')
            .eq('mailbox_id', mailbox_id)
            .eq('processing_status', 'success')
            .eq('is_outbound', False)
            .order('sent_date', desc=True)
            .limit(5)
            .execute()
        )

        print("  Inbound Emails:")
        if sample_inbound.data:
            for i, email in enumerate(sample_inbound.data, 1):
                sender = email.get('sender_email', 'Unknown')
                name = email.get('sender_name', '')
                subject = email.get('subject', 'No subject')[:50]
                print(f"    {i}. From: {sender} ({name})")
                print(f"       Subject: {subject}")
        else:
            print("    No inbound emails found")

        print()

        # Get sample outbound
        sample_outbound = (
            client.table('emails')
            .select('id, subject, sender_email, recipients, is_outbound')
            .eq('mailbox_id', mailbox_id)
            .eq('processing_status', 'success')
            .eq('is_outbound', True)
            .order('sent_date', desc=True)
            .limit(5)
            .execute()
        )

        print("  Outbound Emails:")
        if sample_outbound.data:
            for i, email in enumerate(sample_outbound.data, 1):
                sender = email.get('sender_email', 'Unknown')
                recipients = email.get('recipients', [])
                subject = email.get('subject', 'No subject')[:50]

                # Extract first recipient
                if recipients and len(recipients) > 0:
                    first_recipient = recipients[0]
                    if isinstance(first_recipient, dict):
                        to_email = first_recipient.get('email', 'Unknown')
                    else:
                        to_email = first_recipient
                else:
                    to_email = 'No recipients'

                print(f"    {i}. From: {sender}")
                print(f"       To: {to_email}")
                print(f"       Subject: {subject}")
        else:
            print("    No outbound emails found")

        print("\n" + "-" * 80)

        # Count unique email addresses
        print("\n📋 Unique Email Addresses Analysis:\n")

        # Get all emails and count unique addresses
        all_emails = (
            client.table('emails')
            .select('sender_email, recipients, cc_list, is_outbound')
            .eq('mailbox_id', mailbox_id)
            .eq('processing_status', 'success')
            .execute()
        )

        sender_emails = set()
        recipient_emails = set()

        for email in all_emails.data:
            sender = email.get('sender_email')
            is_outbound = email.get('is_outbound', False)

            # Track senders
            if sender:
                sender_emails.add(sender.lower())

            # Track recipients
            for recipient_list in [email.get('recipients', []), email.get('cc_list', [])]:
                if recipient_list:
                    for recipient in recipient_list:
                        if isinstance(recipient, dict):
                            r_email = recipient.get('email')
                        else:
                            r_email = recipient
                        if r_email:
                            recipient_emails.add(r_email.lower())

        print(f"   Unique sender addresses:    {len(sender_emails)}")
        print(f"   Unique recipient addresses: {len(recipient_emails)}")
        print(f"   All unique addresses:       {len(sender_emails | recipient_emails)}")

        # Check if mailbox email is in the list
        if mailbox_email and mailbox_email.lower() in sender_emails:
            print(f"\n   ⚠️  Mailbox email ({mailbox_email}) appears as sender")
        if mailbox_email and mailbox_email.lower() in recipient_emails:
            print(f"   ⚠️  Mailbox email ({mailbox_email}) appears as recipient")

        print("\n" + "-" * 80)

        # Check extracted contacts
        print("\n👥 Extracted Contacts:\n")

        if not client_id:
            print("   ⚠️  Cannot query contacts (no client_id)")
        else:
            contacts_response = (
                client.table('customer_contacts')
                .select('id, email_address, full_name, customer_company_id')
                .eq('client_id', client_id)
                .execute()
            )

            print(f"   Total contacts in database: {len(contacts_response.data)}")

            if contacts_response.data:
                print("\n   Contact List:")
                for i, contact in enumerate(contacts_response.data, 1):
                    email = contact.get('email_address', 'Unknown')
                    name = contact.get('full_name', 'No name')
                    company_id = contact.get('customer_company_id')
                    print(f"    {i}. {email} - {name} (Company: {company_id[:8] if company_id else 'None'}...)")

        print("\n" + "-" * 80)

        # Check email linking
        print("\n🔗 Email Linking Status:\n")

        linked_response = (
            client.table('emails')
            .select('id', count='exact')
            .eq('mailbox_id', mailbox_id)
            .eq('processing_status', 'success')
            .not_.is_('customer_contact_id', 'null')
            .execute()
        )

        linked_count = linked_response.count
        link_rate = (linked_count / total_emails * 100) if total_emails > 0 else 0

        print(f"   Linked emails:   {linked_count}")
        print(f"   Unlinked emails: {total_emails - linked_count}")
        print(f"   Link rate:       {link_rate:.2f}%")

        # Get sample linked emails
        if linked_count > 0:
            linked_sample = (
                client.table('emails')
                .select('id, sender_email, customer_contact_id, is_outbound')
                .eq('mailbox_id', mailbox_id)
                .eq('processing_status', 'success')
                .not_.is_('customer_contact_id', 'null')
                .limit(5)
                .execute()
            )

            print("\n   Sample Linked Emails:")
            for i, email in enumerate(linked_sample.data, 1):
                sender = email.get('sender_email', 'Unknown')
                contact_id = email.get('customer_contact_id', 'None')
                direction = "OUT" if email.get('is_outbound') else "IN "
                print(f"    {i}. [{direction}] {sender} → Contact {contact_id[:8]}...")

        print("\n" + "-" * 80)
        print("\n💡 Diagnosis:\n")

        # Provide recommendations
        if not client_id:
            print("   ⚠️  CRITICAL: Mailbox has no client_id!")
            print("   → This mailbox is not assigned to any client")
            print("   → Cannot extract or link contacts without client_id")
            print()
            print("   FIX: Assign a client_id to this mailbox:")
            print(f"   UPDATE mailboxes SET client_id = '<your-client-id>'")
            print(f"   WHERE id = '{mailbox_id}';")

        elif inbound_count == 0:
            print("   ⚠️  ISSUE: No inbound emails found!")
            print("   → All emails are marked as outbound (is_outbound=true)")
            print("   → Contact extractor only extracts sender from INBOUND emails")
            print("   → Only extracting recipients from outbound emails")
            print()
            print("   FIX: Check is_outbound logic in email sync")
            print("   → Emails received by this mailbox should be is_outbound=false")
            print("   → Emails sent by this mailbox should be is_outbound=true")

        elif len(recipient_emails) < 20:
            print("   ⚠️  ISSUE: Very few unique recipients!")
            print(f"   → Only {len(recipient_emails)} unique recipient addresses found")
            print("   → Suggests mailbox owner emails the same few people repeatedly")
            print()
            print("   EXPECTED: Business mailboxes typically have 100+ unique contacts")

        elif linked_count < (total_emails * 0.1):
            print("   ⚠️  ISSUE: Very low link rate!")
            print(f"   → Only {link_rate:.1f}% of emails are linked to contacts")
            print("   → Suggests contacts were not created properly")
            print()
            print("   FIX: Check contact extraction logs for errors")

        else:
            print("   ✅ Email distribution looks normal")
            print("   → Check contact extraction filters (noreply, shared addresses, etc.)")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/sprint2/diagnose_contacts.py <mailbox_id>")
        print("\nGet mailbox ID by running:")
        print("  python scripts/sprint2/get_ids.py")
        sys.exit(1)

    mailbox_id = sys.argv[1]
    diagnose_contacts(mailbox_id)


if __name__ == '__main__':
    main()
