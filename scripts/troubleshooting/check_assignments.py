import os
import sys
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database.supabase_client import SupabaseClient

# Initialize Supabase client with service key
client = SupabaseClient.get_client(use_service_key=True)

user_id = 'b52a7a74-98d0-4696-92c1-ef47d4c53627'

print(f"Checking assignments for user {user_id} (dinwin1989@gmail.com)")
print("=" * 80)

# Check user_client_assignments
print("\n1. user_client_assignments:")
result = client.table('user_client_assignments').select('*').eq('user_id', user_id).execute()
print(json.dumps(result.data, indent=2, default=str))

# Check client_manager_assignments
print("\n2. client_manager_assignments:")
result = client.table('client_manager_assignments').select('*').eq('user_id', user_id).execute()
print(json.dumps(result.data, indent=2, default=str))

# Call the database function directly
print("\n3. get_user_accessible_mailboxes function result:")
result = client.rpc('get_user_accessible_mailboxes', {'p_user_id': user_id}).execute()
print(f"Returned {len(result.data)} mailboxes:")
for item in result.data:
    print(f"  - {item}")

# Get details of those mailboxes
if result.data:
    mailbox_ids = [item['mailbox_id'] for item in result.data]
    print("\n4. Mailbox details:")
    result = client.table('mailboxes').select('id, name, email_address, client_id, user_id').in_('id', mailbox_ids).execute()
    print(json.dumps(result.data, indent=2, default=str))