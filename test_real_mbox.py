#!/usr/bin/env python3
"""
Test script for processing real MBOX file from Google Drive
Tests with a small subset first before processing the full 54GB file
"""
import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from src.processors.email_processor import EmailProcessor
from src.database.operations import EmailOperations

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('email_processing.log')
    ]
)
logger = logging.getLogger(__name__)


def test_mbox_processing(file_path: str, max_emails: int = 100, mailbox_id: str = None):
    """
    Test MBOX processing with a limited number of emails

    Args:
        file_path: Path to MBOX file
        max_emails: Maximum number of emails to process (for testing)
        mailbox_id: Existing mailbox ID (will create test mailbox if None)
    """
    logger.info("="*80)
    logger.info(f"MBOX Processing Test Started")
    logger.info(f"File: {file_path}")
    logger.info(f"Max emails: {max_emails}")
    logger.info("="*80)

    try:
        # Step 1: Validate file exists
        logger.info("Step 1: Validating file...")
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False

        file_size_gb = os.path.getsize(file_path) / (1024**3)
        logger.info(f"✓ File found: {file_size_gb:.2f} GB")

        # Step 2: Find or create mailbox
        from src.database.supabase_client import SupabaseClient
        supabase = SupabaseClient.get_client(use_service_key=True)

        if not mailbox_id:
            logger.info("Step 2: Checking for existing mailbox with this file...")

            # Try to find existing mailbox with same file path
            result = supabase.table('mailboxes')\
                .select('*')\
                .eq('mailbox_type', 'mbox')\
                .execute()

            existing_mailbox = None
            if result.data:
                for mb in result.data:
                    # Check if connection_config matches
                    if mb.get('connection_config', {}).get('file_path') == file_path:
                        existing_mailbox = mb
                        break

            if existing_mailbox:
                mailbox_id = existing_mailbox['id']
                logger.info(f"✓ Found existing mailbox: {mailbox_id}")
                logger.info(f"  Name: {existing_mailbox['name']}")
                logger.info(f"  Created: {existing_mailbox.get('created_at', 'Unknown')}")
            else:
                logger.info("  No existing mailbox found, creating new one...")

                mailbox_data = {
                    'name': f'MBOX: Jeff Newbound Archive',
                    'email_address': 'jeff@newbound.com',
                    'mailbox_type': 'mbox',
                    'is_active': True,
                    'connection_config': {
                        'file_path': file_path
                    }
                }

                result = supabase.table('mailboxes').insert(mailbox_data).execute()
                mailbox_id = result.data[0]['id']
                logger.info(f"✓ New mailbox created: {mailbox_id}")
        else:
            logger.info(f"Step 2: Using specified mailbox: {mailbox_id}")
            # Verify it exists
            result = supabase.table('mailboxes')\
                .select('*')\
                .eq('id', mailbox_id)\
                .single()\
                .execute()
            if result.data:
                logger.info(f"  Name: {result.data['name']}")
            else:
                logger.error(f"  Mailbox {mailbox_id} not found!")
                return False

        # Step 3: Initialize processor
        logger.info("Step 3: Initializing email processor...")
        processor = EmailProcessor(
            mailbox_id=mailbox_id,
            connection_config={'file_path': file_path}
        )

        # Validate configuration
        validation_result = processor.validate_configuration('mbox')
        if not validation_result['valid']:
            logger.error(f"Validation failed: {validation_result['error']}")
            return False

        logger.info(f"✓ Configuration validated")
        logger.info(f"  Details: {validation_result['details']}")

        # Step 4: Initialize extractor
        logger.info("Step 4: Initializing MBOX extractor...")
        if not processor.initialize_extractor('mbox'):
            logger.error("Failed to initialize extractor")
            return False
        logger.info("✓ Extractor initialized")

        # Step 5: Create processing job
        logger.info("Step 5: Creating processing job...")
        db_ops = EmailOperations(mailbox_id=mailbox_id)
        job_id = db_ops.create_processing_job(
            job_type='extraction',
            mailbox_id=mailbox_id,
            total_records=max_emails
        )
        logger.info(f"✓ Job created: {job_id}")

        # Step 6: Process emails
        logger.info(f"Step 6: Processing up to {max_emails} emails...")
        logger.info("This may take a few minutes...")

        result = processor.process_emails(
            job_id=job_id,
            max_emails=max_emails,
            batch_size=1000,  # Use smaller batches for testing
            skip_duplicates=True,
            enable_categorization=False  # Disable for now
        )

        logger.info("="*80)
        logger.info("PROCESSING COMPLETED!")
        logger.info("="*80)
        logger.info(f"Total processed: {result['total']}")
        logger.info(f"Successfully inserted: {result['success']}")
        logger.info(f"Failed: {result['failed']}")
        logger.info(f"Skipped (duplicates): {result.get('skipped', 0)}")

        if result['errors']:
            logger.warning(f"Errors encountered: {len(result['errors'])}")
            for error in result['errors'][:5]:  # Show first 5 errors
                logger.warning(f"  - {error}")

        # Step 7: Verify data in database
        logger.info("Step 7: Verifying data in database...")
        stats = db_ops.get_database_stats()
        logger.info(f"✓ Total emails in database: {stats.get('total_emails', 0)}")

        # Cleanup
        processor.disconnect()
        logger.info("✓ Processor disconnected")

        return True

    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        return False


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Test MBOX file processing')
    parser.add_argument(
        '--file',
        type=str,
        default='/home/ubuntu/GDrive/EmailProcessing/Archives/Jeff_Newbound_All mail Including Spam and Trash.mbox',
        help='Path to MBOX file'
    )
    parser.add_argument(
        '--max-emails',
        type=int,
        default=100,
        help='Maximum number of emails to process (default: 100)'
    )
    parser.add_argument(
        '--mailbox-id',
        type=str,
        default=None,
        help='Existing mailbox ID (optional)'
    )

    args = parser.parse_args()

    # Expand file path
    file_path = os.path.expanduser(args.file)

    logger.info(f"Starting test with parameters:")
    logger.info(f"  File: {file_path}")
    logger.info(f"  Max emails: {args.max_emails}")
    logger.info(f"  Mailbox ID: {args.mailbox_id or 'Will create new'}")
    logger.info("")

    success = test_mbox_processing(
        file_path=file_path,
        max_emails=args.max_emails,
        mailbox_id=args.mailbox_id
    )

    if success:
        logger.info("\n✅ TEST PASSED - System is ready for large-scale processing!")
        logger.info("\nNext steps:")
        logger.info("1. Review the processed emails in the database")
        logger.info("2. If satisfied, increase --max-emails gradually (1000, 10000, etc.)")
        logger.info("3. For full file processing, set --max-emails to 0 or remove the parameter")
        return 0
    else:
        logger.error("\n❌ TEST FAILED - Please review errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
