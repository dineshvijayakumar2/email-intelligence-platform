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

from src.extractors.outlook_live_extractor import OutlookLiveExtractor
from src.extractors.mbox_extractor import MBOXExtractor
from src.processors.normalizer import EmailNormalizer
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
    log_file = log_dir / f'extraction_{timestamp}.log'
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger

def create_outlook_extractor(config: dict) -> OutlookLiveExtractor:
    """Create and configure Outlook Live extractor"""
    return OutlookLiveExtractor(config)

def create_mbox_extractor(file_path: str) -> MBOXExtractor:
    """Create and configure MBOX extractor"""
    return MBOXExtractor({'file_path': file_path})

def run_outlook_extraction(
    folder_name: str = 'Inbox',
    date_from: datetime = None,
    date_to: datetime = None,
    max_emails: int = None,
    user_domains: list = None,
    user_emails: list = None,
    batch_size: int = 100
):
    """Run email extraction from Outlook Live"""
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Outlook Live extraction pipeline")
    
    # Initialize components
    extractor = create_outlook_extractor({})
    normalizer = EmailNormalizer(user_domains=user_domains, user_emails=user_emails)
    db_ops = EmailOperations()
    
    try:
        # Test database connection
        from src.database.supabase_client import SupabaseClient
        if not SupabaseClient.test_connection():
            raise RuntimeError("Database connection failed")
        
        # Connect to Outlook
        logger.info("Connecting to Outlook Live...")
        if not extractor.connect():
            raise RuntimeError("Failed to connect to Outlook Live")
        
        # Get available folders
        folders = extractor.get_folders()
        logger.info(f"Available folders: {[f['name'] for f in folders]}")
        
        # Create processing job
        job_id = db_ops.create_processing_job('outlook_extraction', max_emails or 0)
        
        # Process emails in batches
        batch = []
        total_processed = 0
        total_inserted = 0
        total_skipped = 0
        
        logger.info(f"Starting extraction from folder: {folder_name}")
        
        # Extract emails with progress bar
        email_iterator = extractor.extract_emails(
            folder_name=folder_name,
            date_from=date_from,
            date_to=date_to,
            max_emails=max_emails
        )
        
        with tqdm(desc="Processing emails", unit="emails") as pbar:
            for email_data in email_iterator:
                # Check if email already exists
                if db_ops.email_exists(email_data.get('message_id', '')):
                    total_skipped += 1
                    pbar.set_postfix({
                        'processed': total_processed,
                        'inserted': total_inserted,
                        'skipped': total_skipped
                    })
                    continue
                
                # Normalize email
                try:
                    normalized = normalizer.normalize(email_data)
                    
                    # Validate normalized email
                    if normalizer.validate_normalized_email(normalized):
                        batch.append(normalized)
                        total_processed += 1
                    else:
                        logger.warning(f"Invalid email data: {email_data.get('message_id', 'unknown')}")
                        continue
                        
                except Exception as e:
                    logger.error(f"Failed to normalize email: {e}")
                    continue
                
                # Insert batch when full
                if len(batch) >= batch_size:
                    result = db_ops.batch_insert_emails(batch, mailbox_id)
                    total_inserted += result['success']
                    
                    # Update job progress
                    db_ops.update_job_progress(job_id, total_inserted, result['failed'])
                    
                    pbar.set_postfix({
                        'processed': total_processed,
                        'inserted': total_inserted,
                        'skipped': total_skipped,
                        'batch_success': result['success'],
                        'batch_failed': result['failed']
                    })
                    
                    batch = []
                
                pbar.update(1)
        
        # Insert remaining emails
        if batch:
            result = db_ops.batch_insert_emails(batch, mailbox_id)
            total_inserted += result['success']
        
        # Complete job
        db_ops.update_job_progress(job_id, total_inserted, 0, 'completed')
        
        # Print final statistics
        extractor_stats = extractor.get_stats()
        
        logger.info("="*60)
        logger.info("EXTRACTION COMPLETED")
        logger.info("="*60)
        logger.info(f"Extracted from folder: {folder_name}")
        logger.info(f"Date range: {date_from} to {date_to}")
        logger.info(f"Total emails processed: {total_processed}")
        logger.info(f"Total emails inserted: {total_inserted}")
        logger.info(f"Total emails skipped: {total_skipped}")
        logger.info(f"Extractor success: {extractor_stats['success']}")
        logger.info(f"Extractor failed: {extractor_stats['failed']}")
        logger.info(f"Processing time: {extractor_stats.get('end_time', datetime.now()) - extractor_stats.get('start_time', datetime.now())}")
        logger.info("="*60)
        
        return {
            'success': True,
            'total_processed': total_processed,
            'total_inserted': total_inserted,
            'total_skipped': total_skipped,
            'job_id': job_id
        }
        
    except Exception as e:
        logger.error(f"Extraction pipeline failed: {e}")
        # Update job status to failed
        try:
            db_ops.update_job_progress(job_id, total_inserted, 0, 'failed', [str(e)])
        except:
            pass
        raise
    finally:
        extractor.disconnect()

def run_mbox_extraction(
    file_path: str,
    mailbox_email: str,
    mailbox_name: str = None,
    date_from: datetime = None,
    date_to: datetime = None,
    max_emails: int = None,
    user_domains: list = None,
    user_emails: list = None,
    batch_size: int = 100
):
    """Run email extraction from MBOX file"""
    
    logger = logging.getLogger(__name__)
    logger.info(f"Starting MBOX extraction pipeline: {file_path}")
    
    # Validate file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"MBOX file not found: {file_path}")
    
    # Initialize components
    mailbox_ops = MailboxOperations()
    
    # Get or create mailbox
    display_name = mailbox_name or f"MBOX - {mailbox_email}"
    mailbox_id = mailbox_ops.get_or_create_mailbox(
        email_address=mailbox_email,
        mailbox_type='mbox',
        name=display_name,
        connection_config={'file_path': file_path}
    )
    
    extractor = create_mbox_extractor(file_path)
    normalizer = EmailNormalizer(user_domains=user_domains, user_emails=user_emails)
    db_ops = EmailOperations(mailbox_id=mailbox_id)
    
    try:
        # Test database connection
        from src.database.supabase_client import SupabaseClient
        if not SupabaseClient.test_connection():
            raise RuntimeError("Database connection failed")
        
        # Connect to MBOX
        logger.info("Opening MBOX file...")
        if not extractor.connect():
            raise RuntimeError("Failed to open MBOX file")
        
        # Create processing job
        job_id = db_ops.create_processing_job('mbox_extraction', mailbox_id, max_emails or 0)
        
        # Process emails
        batch = []
        total_processed = 0
        total_inserted = 0
        total_skipped = 0
        
        logger.info("Starting MBOX extraction...")
        
        # Extract emails with progress bar
        email_iterator = extractor.extract_emails(
            date_from=date_from,
            date_to=date_to,
            max_emails=max_emails
        )
        
        with tqdm(desc="Processing emails", unit="emails") as pbar:
            for email_data in email_iterator:
                # Check if email already exists
                if db_ops.email_exists(email_data.get('message_id', '')):
                    total_skipped += 1
                    pbar.set_postfix({
                        'processed': total_processed,
                        'inserted': total_inserted,
                        'skipped': total_skipped
                    })
                    continue
                
                # Normalize email
                try:
                    normalized = normalizer.normalize(email_data)
                    
                    # Validate normalized email
                    if normalizer.validate_normalized_email(normalized):
                        batch.append(normalized)
                        total_processed += 1
                    else:
                        logger.warning(f"Invalid email data: {email_data.get('message_id', 'unknown')}")
                        continue
                        
                except Exception as e:
                    logger.error(f"Failed to normalize email: {e}")
                    continue
                
                # Insert batch when full
                if len(batch) >= batch_size:
                    result = db_ops.batch_insert_emails(batch, mailbox_id)
                    total_inserted += result['success']
                    
                    # Update job progress
                    db_ops.update_job_progress(job_id, total_inserted, result['failed'])
                    
                    pbar.set_postfix({
                        'processed': total_processed,
                        'inserted': total_inserted,
                        'skipped': total_skipped,
                        'batch_success': result['success'],
                        'batch_failed': result['failed']
                    })
                    
                    batch = []
                
                pbar.update(1)
        
        # Insert remaining emails
        if batch:
            result = db_ops.batch_insert_emails(batch, mailbox_id)
            total_inserted += result['success']
        
        # Complete job
        db_ops.update_job_progress(job_id, total_inserted, 0, 'completed')
        
        # Print final statistics
        extractor_stats = extractor.get_stats()
        
        logger.info("="*60)
        logger.info("EXTRACTION COMPLETED")
        logger.info("="*60)
        logger.info(f"MBOX file: {file_path}")
        logger.info(f"Date range: {date_from} to {date_to}")
        logger.info(f"Total emails processed: {total_processed}")
        logger.info(f"Total emails inserted: {total_inserted}")
        logger.info(f"Total emails skipped: {total_skipped}")
        logger.info(f"Extractor success: {extractor_stats['success']}")
        logger.info(f"Extractor failed: {extractor_stats['failed']}")
        logger.info(f"Processing time: {extractor_stats.get('end_time', datetime.now()) - extractor_stats.get('start_time', datetime.now())}")
        logger.info("="*60)
        
        return {
            'success': True,
            'total_processed': total_processed,
            'total_inserted': total_inserted,
            'total_skipped': total_skipped,
            'job_id': job_id
        }
        
    except Exception as e:
        logger.error(f"MBOX extraction pipeline failed: {e}")
        raise
    finally:
        extractor.disconnect()

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Extract and process emails')
    
    # Source type
    parser.add_argument('--source', choices=['outlook', 'mbox'], required=True,
                       help='Email source type')
    
    # Mailbox identification
    parser.add_argument('--mailbox-email', required=True,
                       help='Email address for the mailbox')
    parser.add_argument('--mailbox-name', 
                       help='Display name for the mailbox')
    
    # Source-specific arguments
    parser.add_argument('--file', help='Path to MBOX file (for MBOX source)')
    parser.add_argument('--folder', default='Inbox', 
                       help='Folder name for Outlook (default: Inbox)')
    
    # Date filters
    parser.add_argument('--date-from', type=str,
                       help='Start date (YYYY-MM-DD)')
    parser.add_argument('--date-to', type=str,
                       help='End date (YYYY-MM-DD)')
    parser.add_argument('--max-emails', type=int,
                       help='Maximum number of emails to process')
    
    # User identification
    parser.add_argument('--user-domains', nargs='+',
                       help='User domains for outbound email detection')
    parser.add_argument('--user-emails', nargs='+',
                       help='User email addresses for outbound email detection')
    
    # Processing options
    parser.add_argument('--batch-size', type=int, default=100,
                       help='Batch size for database inserts (default: 100)')
    parser.add_argument('--log-level', default='INFO',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level (default: INFO)')
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    # Parse dates
    date_from = None
    date_to = None
    
    if args.date_from:
        try:
            date_from = datetime.strptime(args.date_from, '%Y-%m-%d')
            logger.info(f"Date from: {date_from}")
        except ValueError:
            logger.error(f"Invalid date format: {args.date_from}. Use YYYY-MM-DD")
            sys.exit(1)
    
    if args.date_to:
        try:
            date_to = datetime.strptime(args.date_to, '%Y-%m-%d')
            logger.info(f"Date to: {date_to}")
        except ValueError:
            logger.error(f"Invalid date format: {args.date_to}. Use YYYY-MM-DD")
            sys.exit(1)
    
    try:
        if args.source == 'outlook':
            result = run_outlook_extraction(
                folder_name=args.folder,
                date_from=date_from,
                date_to=date_to,
                max_emails=args.max_emails,
                user_domains=args.user_domains,
                user_emails=args.user_emails,
                batch_size=args.batch_size
            )
        elif args.source == 'mbox':
            if not args.file:
                logger.error("--file is required for MBOX source")
                sys.exit(1)
            
            result = run_mbox_extraction(
                file_path=args.file,
                mailbox_email=args.mailbox_email,
                mailbox_name=args.mailbox_name,
                date_from=date_from,
                date_to=date_to,
                max_emails=args.max_emails,
                user_domains=args.user_domains,
                user_emails=args.user_emails,
                batch_size=args.batch_size
            )
        
        if result['success']:
            logger.info("Extraction completed successfully!")
            print(f"\nSUCCESS: Processed {result['total_processed']} emails, inserted {result['total_inserted']}")
            sys.exit(0)
        else:
            logger.error("Extraction failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Extraction interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()