#!/usr/bin/env python3
"""Test script to verify EmailTagger works"""

import sys
sys.path.insert(0, '.')

from src.processors.email_tagger import EmailTagger

# Create test email
test_email = {
    'sender_email': 'test@example.com',
    'sender_name': 'Test User',
    'subject': 'Test email',
    'body_text': 'This is a test email body',
    'is_outbound': False,
    'is_reply': False,
    'folder_path': 'INBOX',
}

# Tag it
tagger = EmailTagger()
result = tagger.tag_email(test_email)

print("✅ EmailTagger works!")
print(f"Tags: {result.get('tags', [])}")
print(f"Is Spam: {result.get('is_spam', False)}")
print(f"Is Marketing: {result.get('is_marketing', False)}")
print(f"Priority: {result.get('priority_score', 5)}")
print(f"Sender Type: {result.get('sender_type', 'unknown')}")
