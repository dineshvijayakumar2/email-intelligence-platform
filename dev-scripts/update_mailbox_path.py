#!/usr/bin/env python3
"""
Update mailbox file paths in database
Useful for fixing paths after moving files or migrating to cloud storage
"""
import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
    sys.exit(1)

# Create Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def list_mailboxes():
    """List all mailboxes and their file paths"""
    result = supabase.table('mailboxes').select('id, name, mailbox_type, connection_config').execute()

    if not result.data:
        print("No mailboxes found")
        return

    print("\n=== Current Mailboxes ===\n")
    for mailbox in result.data:
        file_path = mailbox['connection_config'].get('file_path', 'N/A')
        print(f"ID: {mailbox['id']}")
        print(f"Name: {mailbox['name']}")
        print(f"Type: {mailbox['mailbox_type']}")
        print(f"File Path: {file_path}")
        print("-" * 80)


def update_mailbox_path(mailbox_id: str, new_path: str):
    """Update the file path for a mailbox"""
    # Get current mailbox
    result = supabase.table('mailboxes').select('*').eq('id', mailbox_id).execute()

    if not result.data:
        print(f"Error: Mailbox {mailbox_id} not found")
        return False

    mailbox = result.data[0]
    old_path = mailbox['connection_config'].get('file_path', 'N/A')

    # Update connection_config with new path
    new_config = mailbox['connection_config'].copy()
    new_config['file_path'] = new_path

    # Update in database
    update_result = supabase.table('mailboxes').update({
        'connection_config': new_config
    }).eq('id', mailbox_id).execute()

    if update_result.data:
        print(f"\nSuccessfully updated mailbox: {mailbox['name']}")
        print(f"Old path: {old_path}")
        print(f"New path: {new_path}")
        return True
    else:
        print(f"Error updating mailbox")
        return False


def update_all_paths(old_prefix: str, new_prefix: str):
    """Replace path prefix for all mailboxes"""
    result = supabase.table('mailboxes').select('*').execute()

    if not result.data:
        print("No mailboxes found")
        return

    updated_count = 0
    for mailbox in result.data:
        old_path = mailbox['connection_config'].get('file_path', '')

        if old_path.startswith(old_prefix):
            new_path = old_path.replace(old_prefix, new_prefix, 1)

            new_config = mailbox['connection_config'].copy()
            new_config['file_path'] = new_path

            supabase.table('mailboxes').update({
                'connection_config': new_config
            }).eq('id', mailbox['id']).execute()

            print(f"Updated: {mailbox['name']}")
            print(f"  {old_path} -> {new_path}")
            updated_count += 1

    print(f"\nUpdated {updated_count} mailboxes")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Manage mailbox file paths')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # List command
    subparsers.add_parser('list', help='List all mailboxes')

    # Update command
    update_parser = subparsers.add_parser('update', help='Update single mailbox path')
    update_parser.add_argument('mailbox_id', help='Mailbox ID')
    update_parser.add_argument('new_path', help='New file path or URI')

    # Batch update command
    batch_parser = subparsers.add_parser('batch', help='Batch update paths')
    batch_parser.add_argument('old_prefix', help='Old path prefix to replace')
    batch_parser.add_argument('new_prefix', help='New path prefix')

    args = parser.parse_args()

    if args.command == 'list':
        list_mailboxes()
    elif args.command == 'update':
        update_mailbox_path(args.mailbox_id, args.new_path)
    elif args.command == 'batch':
        update_all_paths(args.old_prefix, args.new_prefix)
    else:
        parser.print_help()
