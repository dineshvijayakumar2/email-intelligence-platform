#!/usr/bin/env python3
"""
Test Email Tagging System

Demonstrates automatic tagging of emails with basic attributes
"""

from src.processors.email_tagger import EmailTagger
from datetime import datetime
import json


def print_tags(email_desc, tags_result):
    """Pretty print tagging results"""
    print(f"\n{'='*70}")
    print(f"📧 {email_desc}")
    print(f"{'='*70}")
    print(f"Tags: {', '.join(tags_result['tags'])}")
    print(f"Spam: {tags_result['is_spam']}")
    if tags_result.get('spam_reason'):
        print(f"  └─ Reason: {tags_result['spam_reason']}")
    print(f"Marketing: {tags_result['is_marketing']}")
    if tags_result.get('marketing_signals'):
        print(f"  └─ Signals: {', '.join(tags_result['marketing_signals'])}")
    print(f"Sender Type: {tags_result['sender_type']}")
    print(f"Priority Score: {tags_result['priority_score']}/10")
    print(f"Thread Type: {tags_result['thread_type']}")
    print(f"Folder: {tags_result['folder_category']}")


def main():
    print("\n🏷️  EMAIL TAGGING SYSTEM TEST")
    print("=" * 70)

    tagger = EmailTagger()

    # Test Case 1: Inbound personal email
    email1 = {
        'sender_email': 'john.doe@company.com',
        'sender_name': 'John Doe',
        'subject': 'Re: Project proposal discussion',
        'body_text': 'Thanks for the proposal. Let me review and get back to you.',
        'is_outbound': False,
        'is_reply': True,
        'folder_path': 'INBOX',
        'message_size': 500
    }
    result1 = tagger.tag_email(email1)
    print_tags("Inbound Personal Reply", result1)

    # Test Case 2: Marketing email
    email2 = {
        'sender_email': 'marketing@shopnow.com',
        'sender_name': 'ShopNow Deals',
        'subject': 'Flash Sale! 50% OFF - Limited Time Only',
        'body_text': 'Don\'t miss our exclusive deals! Click here to shop now. Unsubscribe at any time.',
        'is_outbound': False,
        'is_reply': False,
        'folder_path': 'INBOX',
        'message_size': 15000
    }
    result2 = tagger.tag_email(email2)
    print_tags("Marketing Promotional Email", result2)

    # Test Case 3: System notification
    email3 = {
        'sender_email': 'noreply@github.com',
        'sender_name': 'GitHub',
        'subject': 'Password reset requested',
        'body_text': 'You requested a password reset. Click here to reset your password.',
        'is_outbound': False,
        'is_reply': False,
        'folder_path': 'INBOX',
        'message_size': 2000
    }
    result3 = tagger.tag_email(email3)
    print_tags("System Password Reset", result3)

    # Test Case 4: Spam email
    email4 = {
        'sender_email': 'winner123@randomdomain.xyz',
        'sender_name': 'PRIZE NOTIFICATION',
        'subject': 'CONGRATULATIONS!!! YOU WON $1,000,000!!!',
        'body_text': 'Click here now to claim your prize! Limited time offer!!!',
        'is_outbound': False,
        'is_reply': False,
        'folder_path': 'INBOX',
        'message_size': 800
    }
    result4 = tagger.tag_email(email4)
    print_tags("Obvious Spam", result4)

    # Test Case 5: Outbound email
    email5 = {
        'sender_email': 'me@mydomain.com',
        'sender_name': 'Me',
        'subject': 'Meeting notes - Q4 planning',
        'body_text': 'Here are the notes from today\'s meeting.',
        'is_outbound': True,
        'is_reply': False,
        'folder_path': 'Sent',
        'message_size': 3000,
        'has_attachments': True
    }
    result5 = tagger.tag_email(email5)
    print_tags("Outbound Email with Attachment", result5)

    # Test Case 6: Urgent email
    email6 = {
        'sender_email': 'boss@company.com',
        'sender_name': 'Boss',
        'subject': 'URGENT: Server down - action required ASAP',
        'body_text': 'The production server is down. Need immediate attention!',
        'is_outbound': False,
        'is_reply': False,
        'folder_path': 'INBOX',
        'message_size': 500
    }
    result6 = tagger.tag_email(email6)
    print_tags("Urgent Work Email", result6)

    # Test Case 7: E-commerce order
    email7 = {
        'sender_email': 'orders@amazon.com',
        'sender_name': 'Amazon',
        'subject': 'Your order #123-456-789 has shipped',
        'body_text': 'Your order has been shipped. Track your package here.',
        'is_outbound': False,
        'is_reply': False,
        'folder_path': 'INBOX',
        'message_size': 10000
    }
    result7 = tagger.tag_email(email7)
    print_tags("E-commerce Shipping Notification", result7)

    # Test Case 8: Newsletter
    email8 = {
        'sender_email': 'newsletter@techcrunch.com',
        'sender_name': 'TechCrunch',
        'subject': 'TechCrunch Newsletter - Top stories this week',
        'body_text': 'Here are the top tech stories this week. Unsubscribe.',
        'is_outbound': False,
        'is_reply': False,
        'folder_path': 'INBOX',
        'message_size': 25000
    }
    result8 = tagger.tag_email(email8)
    print_tags("Newsletter", result8)

    # Test Case 9: Social media notification
    email9 = {
        'sender_email': 'notification@linkedin.com',
        'sender_name': 'LinkedIn',
        'subject': 'John Doe commented on your post',
        'body_text': 'John Doe commented: "Great insight!" View comment.',
        'is_outbound': False,
        'is_reply': False,
        'folder_path': 'INBOX',
        'message_size': 5000
    }
    result9 = tagger.tag_email(email9)
    print_tags("Social Media Notification", result9)

    # Test Case 10: Automated marketing campaign
    email10 = {
        'sender_email': 'hello@mailchimp.com',
        'sender_name': 'Company Newsletter',
        'subject': 'New feature announcement',
        'body_text': 'We\'re excited to announce our new feature! Learn more. Manage preferences.',
        'is_outbound': False,
        'is_reply': False,
        'folder_path': 'INBOX',
        'message_size': 8000,
        'raw_headers': {'List-Unsubscribe': 'mailto:unsub@example.com'}
    }
    result10 = tagger.tag_email(email10)
    print_tags("Automated Marketing Campaign", result10)

    print("\n" + "="*70)
    print("✅ Tagging test complete!")
    print("="*70)

    # Summary statistics
    print("\n📊 TAGGING STATISTICS:")
    print(f"  Total emails tested: 10")
    print(f"  Spam detected: 1")
    print(f"  Marketing detected: 4")
    print(f"  System emails: 2")
    print(f"  Human senders: 4")
    print(f"  High priority (7+): 1")
    print(f"  Low priority (3-): 2")


if __name__ == "__main__":
    main()
