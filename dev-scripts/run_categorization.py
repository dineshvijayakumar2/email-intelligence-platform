#!/usr/bin/env python3

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import logging
from tqdm import tqdm

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.processors.industry_categorizer import categorize_with_industry_standards
from src.database.operations import EmailOperations
from src.database.mailbox_operations import MailboxOperations

# Load environment variables
load_dotenv()

def setup_logging(log_level: str = 'INFO'):
    """Configure logging"""
    level = getattr(logging, log_level.upper())
    
    # Create logs directory if it doesn't exist
    log_dir = project_root / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'categorization_{timestamp}.log'
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Categorization logging initialized. Log file: {log_file}")
    return logger

class CategoryOperations:
    """Database operations for email categories"""
    
    def __init__(self, use_service_key: bool = True):
        """Initialize with database client"""
        from src.database.supabase_client import SupabaseClient
        self.client = SupabaseClient.get_client(use_service_key=use_service_key)
        
    def assign_categories(self, email_id: str, categories: dict):
        """
        Assign categories to an email
        
        Args:
            email_id: Email UUID
            categories: Category assignment dict
        """
        try:
            # Clear existing categories for this email
            self.client.table('email_categories')\
                .delete()\
                .eq('email_id', email_id)\
                .execute()
            
            # Insert new category
            category_data = {
                'email_id': email_id,
                'category': categories['category'],
                'confidence': categories.get('confidence', 0.8),
                'detection_method': f"system:{categories.get('system', 'unknown')}",
                'created_at': datetime.now().isoformat()
            }
            
            self.client.table('email_categories')\
                .insert(category_data)\
                .execute()
                
            logging.debug(f"Assigned category '{categories['category']}' to email {email_id}")
        
        except Exception as e:
            logging.error(f"Failed to assign categories to email {email_id}: {e}")
            raise

def run_categorization(
    mailbox_id: str = None,
    mailbox_email: str = None,
    categorization_style: str = 'automation',
    max_emails: int = None,
    recategorize: bool = False,
    batch_size: int = 100
):
    """
    Run email categorization on existing emails
    
    Args:
        mailbox_id: Specific mailbox ID to categorize
        mailbox_email: Specific mailbox email to categorize
        categorization_style: Style of categorization (gmail, outlook, apple, automation)
        max_emails: Maximum number of emails to categorize
        recategorize: Whether to recategorize already categorized emails
        batch_size: Number of emails to process per batch
    """
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting email categorization: style={categorization_style}")
    
    # Initialize components
    email_ops = EmailOperations()
    mailbox_ops = MailboxOperations()
    category_ops = CategoryOperations()
    
    try:
        # Test database connection
        from src.database.supabase_client import SupabaseClient
        if not SupabaseClient.test_connection():
            raise RuntimeError("Database connection failed")
        
        # Determine target mailbox
        target_mailbox_id = mailbox_id
        if mailbox_email and not mailbox_id:
            mailbox = mailbox_ops.get_mailbox_by_email(mailbox_email)
            if not mailbox:
                raise ValueError(f"Mailbox not found: {mailbox_email}")
            target_mailbox_id = mailbox['id']
            logger.info(f"Found mailbox: {mailbox['name']} ({mailbox_email})")
        
        # Build query for emails to categorize
        query = email_ops.client.table('emails').select('id,message_id,sender_email,subject,body_text,folder_path,raw_headers')
        
        if target_mailbox_id:
            query = query.eq('mailbox_id', target_mailbox_id)
        
        # If not recategorizing, only get uncategorized emails
        if not recategorize:
            # Get emails that don't have categories
            categorized_email_ids = email_ops.client.table('email_categories')\
                .select('email_id')\
                .execute()
            
            if categorized_email_ids.data:
                categorized_ids = [row['email_id'] for row in categorized_email_ids.data]
                # Filter out already categorized emails
                query = query.not_.in_('id', categorized_ids)
        
        # Apply limit if specified
        if max_emails:
            query = query.limit(max_emails)
        
        # Execute query
        logger.info("Fetching emails for categorization...")
        result = query.execute()
        emails = result.data or []
        
        if not emails:
            logger.info("No emails found for categorization")
            return {
                'success': True,
                'total_processed': 0,
                'total_categorized': 0,
                'errors': []
            }
        
        logger.info(f"Found {len(emails)} emails to categorize")
        
        # Process emails in batches
        total_processed = 0
        total_categorized = 0
        errors = []
        
        with tqdm(desc="Categorizing emails", total=len(emails), unit="emails") as pbar:
            for i in range(0, len(emails), batch_size):
                batch = emails[i:i + batch_size]
                batch_num = i // batch_size + 1
                
                logger.info(f"Processing batch {batch_num}: {len(batch)} emails")
                
                for email in batch:
                    try:
                        # Categorize email
                        categories = categorize_with_industry_standards(email, categorization_style)
                        
                        # Store category in database
                        category_ops.assign_categories(email['id'], categories)
                        
                        total_categorized += 1
                        total_processed += 1
                        
                    except Exception as e:
                        error_msg = f"Failed to categorize email {email.get('message_id', 'unknown')}: {e}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        total_processed += 1
                    
                    pbar.update(1)
                    pbar.set_postfix({
                        'categorized': total_categorized,
                        'errors': len(errors)
                    })
        
        # Final statistics
        logger.info("="*60)
        logger.info("CATEGORIZATION COMPLETED")
        logger.info("="*60)
        logger.info(f"Categorization style: {categorization_style}")
        logger.info(f"Total emails processed: {total_processed}")
        logger.info(f"Total emails categorized: {total_categorized}")
        logger.info(f"Total errors: {len(errors)}")
        if target_mailbox_id:
            logger.info(f"Mailbox: {target_mailbox_id}")
        logger.info("="*60)
        
        return {
            'success': True,
            'total_processed': total_processed,
            'total_categorized': total_categorized,
            'errors': errors
        }
        
    except Exception as e:
        logger.error(f"Categorization pipeline failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def run_recategorization(
    mailbox_id: str = None,
    mailbox_email: str = None,
    old_style: str = None,
    new_style: str = 'automation',
    max_emails: int = None
):
    """
    Recategorize emails with a different categorization style
    
    Args:
        mailbox_id: Specific mailbox ID to recategorize
        mailbox_email: Specific mailbox email to recategorize  
        old_style: Previous categorization style to replace (optional filter)
        new_style: New categorization style to apply
        max_emails: Maximum number of emails to recategorize
    """
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting email recategorization: {old_style} → {new_style}")
    
    return run_categorization(
        mailbox_id=mailbox_id,
        mailbox_email=mailbox_email,
        categorization_style=new_style,
        max_emails=max_emails,
        recategorize=True
    )

def show_categorization_stats(mailbox_id: str = None, mailbox_email: str = None):
    """Show categorization statistics"""
    
    logger = logging.getLogger(__name__)
    
    try:
        from src.database.supabase_client import SupabaseClient
        client = SupabaseClient.get_client()
        
        # Determine target mailbox
        target_mailbox_id = mailbox_id
        if mailbox_email and not mailbox_id:
            mailbox_ops = MailboxOperations()
            mailbox = mailbox_ops.get_mailbox_by_email(mailbox_email)
            if mailbox:
                target_mailbox_id = mailbox['id']
        
        # Get category statistics
        query = """
        SELECT 
            ec.category,
            COUNT(*) as email_count,
            AVG(ec.confidence) as avg_confidence,
            ec.detection_method
        FROM email_categories ec
        JOIN emails e ON ec.email_id = e.id
        """
        
        if target_mailbox_id:
            query += f" WHERE e.mailbox_id = '{target_mailbox_id}'"
        
        query += """
        GROUP BY ec.category, ec.detection_method
        ORDER BY email_count DESC
        """
        
        # This is a conceptual example - adapt to your Supabase client
        result = client.rpc('execute_raw_sql', {'sql': query}).execute()
        
        print("\n" + "="*60)
        print("CATEGORIZATION STATISTICS")
        print("="*60)
        print(f"{'Category':<20} {'Count':<10} {'Confidence':<12} {'Method':<15}")
        print("-"*60)
        
        for row in result.data:
            print(f"{row['category']:<20} {row['email_count']:<10} {row['avg_confidence']:<12.2f} {row['detection_method']:<15}")
        
        print("="*60)
        
    except Exception as e:
        logger.error(f"Failed to get categorization stats: {e}")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Categorize emails using industry standards')
    
    # Action selection
    parser.add_argument('action', choices=['categorize', 'recategorize', 'stats'],
                       help='Action to perform')
    
    # Mailbox identification
    parser.add_argument('--mailbox-id', help='Specific mailbox ID to process')
    parser.add_argument('--mailbox-email', help='Specific mailbox email to process')
    
    # Categorization options
    parser.add_argument('--style', default='automation',
                       choices=['gmail', 'outlook', 'apple', 'automation'],
                       help='Categorization style (default: automation)')
    parser.add_argument('--old-style', 
                       choices=['gmail', 'outlook', 'apple', 'automation'],
                       help='Previous style to replace (for recategorization)')
    
    # Processing options
    parser.add_argument('--max-emails', type=int,
                       help='Maximum number of emails to process')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Batch size for processing (default: 100)')
    parser.add_argument('--recategorize', action='store_true',
                       help='Recategorize already categorized emails')
    
    # Logging
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level (default: INFO)')
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    try:
        if args.action == 'categorize':
            result = run_categorization(
                mailbox_id=args.mailbox_id,
                mailbox_email=args.mailbox_email,
                categorization_style=args.style,
                max_emails=args.max_emails,
                recategorize=args.recategorize,
                batch_size=args.batch_size
            )
            
        elif args.action == 'recategorize':
            result = run_recategorization(
                mailbox_id=args.mailbox_id,
                mailbox_email=args.mailbox_email,
                old_style=args.old_style,
                new_style=args.style,
                max_emails=args.max_emails
            )
            
        elif args.action == 'stats':
            show_categorization_stats(
                mailbox_id=args.mailbox_id,
                mailbox_email=args.mailbox_email
            )
            return
        
        if result['success']:
            logger.info("Categorization completed successfully!")
            if 'total_categorized' in result:
                print(f"\nSUCCESS: Categorized {result['total_categorized']} emails")
        else:
            logger.error("Categorization failed")
            print(f"\nFAILED: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Categorization interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Categorization failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()