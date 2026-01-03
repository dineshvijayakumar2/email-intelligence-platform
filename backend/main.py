from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client
import asyncio
import json
from datetime import datetime, timedelta, timezone
import random
import logging

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.processors.email_processor import EmailProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from parent directory
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)
logger.info(f"Loading environment variables from: {dotenv_path}")

app = FastAPI(title="Email Intelligence API", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Supabase client - lazy initialization to ensure env vars are loaded
_supabase_client = None

def get_supabase() -> Client:
    """Get or create Supabase client"""
    global _supabase_client
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        # Use SUPABASE_SERVICE_KEY (from root .env)
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

        if not supabase_url or not supabase_key:
            logger.error(f"Missing env - URL: {bool(supabase_url)}, KEY: {bool(supabase_key)}")
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment")

        _supabase_client = create_client(supabase_url, supabase_key)
        logger.info("Supabase client initialized successfully")

    return _supabase_client

# For backwards compatibility
supabase = None

# Pydantic models
class MailboxConfig(BaseModel):
    name: str
    email_address: Optional[str] = None
    mailbox_type: str
    is_active: bool = True
    connection_config: Optional[Dict[str, Any]] = {}

class ProcessingJobConfig(BaseModel):
    job_type: str
    total_records: Optional[int] = None  # None = process all emails
    batch_size: Optional[int] = 5000  # Increased for large files
    enable_categorization: Optional[bool] = True
    enable_enrichment: Optional[bool] = False
    # These will be populated from mailbox data
    mailbox_id: Optional[str] = None
    mailbox_type: Optional[str] = None
    connection_config: Optional[Dict[str, Any]] = {}

class ConnectionTest(BaseModel):
    mailbox_type: str
    connection_config: Dict[str, Any]

# In-memory job storage for POC (use Redis in production)
active_jobs = {}

@app.get("/")
async def root():
    return {"message": "Email Intelligence API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Mailbox endpoints
@app.post("/api/mailboxes/{mailbox_id}/test-connection")
async def test_connection(mailbox_id: str, connection_test: ConnectionTest):
    """Test mailbox connection based on type"""

    mailbox_type = connection_test.mailbox_type
    config = connection_test.connection_config

    try:
        # Use EmailProcessor to validate configuration
        processor = EmailProcessor(
            mailbox_id="test_connection",  # Temporary ID for validation
            connection_config=config
        )

        validation_result = processor.validate_configuration(mailbox_type)

        if not validation_result['valid']:
            raise HTTPException(
                status_code=400,
                detail=validation_result['error']
            )

        return {
            "success": True,
            "message": f"{mailbox_type.upper()} connection test successful",
            "details": validation_result['details'],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")

@app.post("/api/mailboxes/{mailbox_id}/process")
async def start_processing(mailbox_id: str, config: ProcessingJobConfig, background_tasks: BackgroundTasks):
    """Start email processing for a mailbox"""

    try:
        # Get mailbox info
        mailbox_result = get_supabase().table('mailboxes').select('*').eq('id', mailbox_id).execute()
        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        mailbox = mailbox_result.data[0]

        # Check for existing active jobs for this mailbox
        existing_jobs = get_supabase().table('processing_jobs').select('id, status').eq(
            'mailbox_id', mailbox_id
        ).in_('status', ['pending', 'running']).execute()

        if existing_jobs.data:
            active_job = existing_jobs.data[0]
            raise HTTPException(
                status_code=409,  # Conflict
                detail=f"A job is already {active_job['status']} for this mailbox. "
                       f"Please wait for it to complete or stop it first. "
                       f"Job ID: {active_job['id']}"
            )

        # Create processing job
        job_data = {
            "job_type": config.job_type,
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": config.total_records,
            "processed_records": 0,
            "failed_records": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_log": []
        }
        
        # Insert job into database
        result = get_supabase().table('processing_jobs').insert(job_data).execute()
        job = result.data[0]
        
        # Store job in memory for tracking
        active_jobs[job['id']] = {
            **job,
            "mailbox_name": mailbox['name'],
            "mailbox_type": mailbox['mailbox_type']
        }
        
        # Add mailbox connection config to processing config
        config.connection_config = mailbox['connection_config']
        config.mailbox_type = mailbox['mailbox_type']
        config.mailbox_id = mailbox_id

        # Start REAL background processing (not simulated)
        background_tasks.add_task(process_emails_real, job['id'], config)

        logger.info(f"Started processing job {job['id']} for mailbox {mailbox['name']}")

        return job
        
    except Exception as e:
        logger.error(f"Failed to start processing: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")

async def process_emails_real(job_id: str, config: ProcessingJobConfig):
    """
    REAL email processing (replaces simulate_processing)
    Processes actual emails from MBOX/IMAP/POP3/Outlook sources
    """

    try:
        logger.info(f"Starting REAL email processing for job {job_id}")

        # Initialize processor with actual configuration
        processor = EmailProcessor(
            mailbox_id=config.mailbox_id,
            connection_config=config.connection_config
        )

        # Initialize the extractor
        if not processor.initialize_extractor(config.mailbox_type):
            error_msg = f"Failed to initialize {config.mailbox_type} extractor"
            logger.error(error_msg)
            await update_job_status(job_id, "failed", {
                "error_log": [error_msg],
                "completed_at": datetime.now(timezone.utc).isoformat()
            })
            return

        # Process emails with streaming
        # Run in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            processor.process_emails,
            job_id,
            config.total_records,  # max_emails (None for all)
            config.batch_size or 5000,  # batch_size
            True,  # skip_duplicates
            config.enable_categorization  # enable_categorization
        )

        logger.info(f"Processing completed for job {job_id}: {result}")

        # Cleanup
        processor.disconnect()

    except Exception as e:
        error_msg = f"Processing error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await update_job_status(job_id, "failed", {
            "error_log": [error_msg],
            "completed_at": datetime.now(timezone.utc).isoformat()
        })

async def update_job_status(job_id: str, status: str, updates: Dict[str, Any]):
    """Update job status in database and memory"""
    
    update_data = {"status": status, **updates}
    
    # Update database
    get_supabase().table('processing_jobs').update(update_data).eq('id', job_id).execute()
    
    # Update in-memory job
    if job_id in active_jobs:
        active_jobs[job_id].update(update_data)

async def generate_sample_emails(job_id: str, count: int):
    """Generate sample email data for demonstration"""
    
    categories = ['promotional', 'transactional', 'conversation', 'system', 'spam']
    senders = [
        'noreply@amazon.com', 'support@github.com', 'team@slack.com',
        'notifications@linkedin.com', 'info@stripe.com', 'hello@discord.com'
    ]
    subjects = [
        'Your order has been shipped', 'Security alert for your account',
        'Welcome to our platform', 'Monthly report is ready',
        'Meeting reminder: Project sync', 'Invoice #12345 from Stripe'
    ]
    
    # Get mailbox for this job
    job_result = get_supabase().table('processing_jobs').select('mailbox_id').eq('id', job_id).execute()
    if not job_result.data:
        return
        
    mailbox_id = job_result.data[0]['mailbox_id']
    
    # Generate sample emails (limit to 50 for POC)
    sample_count = min(50, count // 20)
    
    for i in range(sample_count):
        email_data = {
            "mailbox_id": mailbox_id,
            "message_id": f"<sample-{job_id}-{i}@example.com>",
            "subject": random.choice(subjects),
            "sender_email": random.choice(senders),
            "sender_name": random.choice(senders).split('@')[0].title(),
            "sent_date": (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))).isoformat(),
            "received_date": datetime.now(timezone.utc).isoformat(),
            "is_outbound": random.choice([True, False]),
            "is_reply": random.choice([True, False]),
            "folder_path": "INBOX",
            "message_size": random.randint(1024, 50000),
            "body_text": f"This is a sample email body for email {i+1}. Generated for POC demonstration.",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Insert email
        email_result = get_supabase().table('emails').insert(email_data).execute()
        if email_result.data:
            email_id = email_result.data[0]['id']
            
            # Add category
            category_data = {
                "email_id": email_id,
                "category": random.choice(categories),
                "confidence": round(random.uniform(0.7, 1.0), 2),
                "detection_method": "ai_classifier",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            get_supabase().table('email_categories').insert(category_data).execute()

@app.get("/api/processing-jobs")
async def get_processing_jobs():
    """Get all processing jobs"""
    
    try:
        # Try to get from database with mailbox join
        result = get_supabase().table('processing_jobs').select(
            'id, job_type, mailbox_id, status, total_records, processed_records, failed_records, started_at, completed_at, created_at, error_log, mailboxes(name)'
        ).order('created_at', desc=True).execute()
        
        jobs = []
        for job in result.data:
            # Calculate progress safely, handling None and 0
            total = job.get('total_records') or 0
            processed = job.get('processed_records') or 0

            if total > 0:
                progress = round((processed / total) * 100)
            elif job.get('status') == 'completed':
                progress = 100  # If completed but no total_records, show 100%
            else:
                progress = 0  # Pending or running without total_records yet

            job_data = {
                **job,
                "mailbox_name": job.get('mailboxes', {}).get('name') if job.get('mailboxes') else 'Unknown Mailbox',
                "progress": progress,
                "total_records": total,  # Ensure it's not None
                "processed_records": processed  # Ensure it's not None
            }
            # Remove the nested mailboxes object
            if 'mailboxes' in job_data:
                del job_data['mailboxes']
            jobs.append(job_data)
            
        return jobs
        
    except Exception as e:
        logger.error(f"Failed to get processing jobs from database: {str(e)}", exc_info=True)
        # Fallback: return mock data
        return [
            {
                "id": "mock-1",
                "job_type": "extraction",
                "mailbox_id": "mb-1",
                "mailbox_name": "Sample Mailbox",
                "status": "completed",
                "total_records": 1000,
                "processed_records": 1000,
                "failed_records": 0,
                "started_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "created_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "error_log": [],
                "progress": 100
            }
        ]

@app.post("/api/processing-jobs/{job_id}/control")
async def control_job(job_id: str, action: str):
    """Control processing job (pause, resume, stop)"""
    
    valid_actions = ["pause", "resume", "stop"]
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {valid_actions}")
    
    try:
        status_map = {
            "pause": "paused",
            "resume": "running",
            "stop": "stopped"  # Fixed: was "failed"
        }

        new_status = status_map[action]
        update_data = {"status": new_status}

        if action == "stop":
            update_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            
        get_supabase().table('processing_jobs').update(update_data).eq('id', job_id).execute()
        
        return {"message": f"Job {action}d successfully", "status": new_status}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to {action} job: {str(e)}")

@app.delete("/api/processing-jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a processing job"""

    try:
        get_supabase().table('processing_jobs').delete().eq('id', job_id).execute()

        # Remove from memory if exists
        if job_id in active_jobs:
            del active_jobs[job_id]

        return {"message": "Job deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete job: {str(e)}")

@app.post("/api/processing-jobs/{job_id}/reprocess")
async def reprocess_emails(job_id: str, background_tasks: BackgroundTasks):
    """Reprocess existing emails to add categorization/tags"""

    try:
        # Get the job details
        job_result = get_supabase().table('processing_jobs').select('*').eq('id', job_id).execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = job_result.data[0]
        mailbox_id = job['mailbox_id']

        # Create a new reprocessing job
        reprocess_job_data = {
            "job_type": "reprocessing",
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": 0,  # Will be updated
            "processed_records": 0,
            "failed_records": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        result = get_supabase().table('processing_jobs').insert(reprocess_job_data).execute()
        new_job_id = result.data[0]['id']

        # Start reprocessing in background
        background_tasks.add_task(run_reprocessing, new_job_id, mailbox_id)

        return {
            "message": "Reprocessing started",
            "job_id": new_job_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start reprocessing: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start reprocessing: {str(e)}")

def _classify_tag_type(tag: str) -> str:
    """Classify tag into type categories"""
    if tag in ['inbound', 'outbound']:
        return 'direction'
    elif tag in ['new_thread', 'reply', 'forward']:
        return 'thread_type'
    elif tag in ['inbox', 'sent', 'spam', 'trash', 'archive', 'drafts']:
        return 'folder'
    elif tag in ['spam', 'marketing', 'system', 'automated']:
        return 'classification'
    elif tag.startswith('sender_'):
        return 'sender_type'
    elif tag in ['high_priority', 'low_priority', 'urgent']:
        return 'priority'
    else:
        return 'content'

async def run_reprocessing(job_id: str, mailbox_id: str):
    """
    Run reprocessing to:
    1. Re-normalize emails with new folder inference logic
    2. Update folder_path in emails table
    3. Re-tag emails with updated logic
    4. Update folders table
    """

    try:
        from src.processors.email_tagger import EmailTagger
        from src.processors.normalizer import EmailNormalizer

        logger.info(f"Starting reprocessing job {job_id} for mailbox {mailbox_id}")

        # Update status to running
        await update_job_status(job_id, "running", {
            "started_at": datetime.now(timezone.utc).isoformat()
        })

        # Initialize normalizer and tagger
        normalizer = EmailNormalizer()
        tagger = EmailTagger()

        sb = get_supabase()

        # Get total count first (lightweight query)
        count_result = sb.table('emails').select('id', count='exact').eq('mailbox_id', mailbox_id).execute()
        total_emails = count_result.count or 0
        logger.info(f"Found {total_emails} emails to reprocess")

        if total_emails == 0:
            logger.warning(f"No emails found for mailbox {mailbox_id}")
            await update_job_status(job_id, "completed", {
                "total_records": 0,
                "processed_records": 0,
                "failed_records": 0
            })
            return

        # Update total records
        await update_job_status(job_id, "running", {
            "total_records": total_emails
        })

        processed = 0
        failed = 0
        folders_to_create = set()

        # Process in batches using pagination (avoid loading all emails into memory)
        batch_size = 100
        offset = 0

        while offset < total_emails:
            # Fetch one batch at a time from database
            logger.info(f"Fetching batch: offset={offset}, limit={batch_size}")
            result = sb.table('emails').select('*').eq('mailbox_id', mailbox_id).range(offset, offset + batch_size - 1).execute()
            batch = result.data

            if not batch:
                break  # No more emails

            for email in batch:
                try:
                    # Step 1: Re-normalize email with new folder inference
                    # The email from DB already has all fields, we just need to infer folder
                    inferred_folder = normalizer._infer_folder_path(
                        provided_folder=None,  # Force inference
                        is_outbound=email.get('is_outbound', False),
                        sender_email=email.get('sender_email', ''),
                        recipients=email.get('recipients', []),
                        subject=email.get('subject', ''),
                        body_text=email.get('body_text', '')
                    )

                    # Update folder_path if it changed
                    old_folder = email.get('folder_path', '')
                    if inferred_folder != old_folder:
                        sb.table('emails').update({
                            'folder_path': inferred_folder
                        }).eq('id', email['id']).execute()
                        email['folder_path'] = inferred_folder  # Update for tagging
                        logger.debug(f"Updated folder: {old_folder} -> {inferred_folder}")

                    # Track folders that need to exist
                    folders_to_create.add(inferred_folder)

                    # Step 2: Tag the email (with updated folder_path)
                    tag_result = tagger.tag_email(email)

                    # Delete existing tags for this email
                    sb.table('email_categories').delete().eq('email_id', email['id']).execute()

                    # Insert new tags
                    category_inserts = []

                    # Add regular tags
                    for tag in tag_result.get('tags', []):
                        category_inserts.append({
                            'email_id': email['id'],
                            'category': tag,
                            'confidence': 1.0,
                            'detection_method': 'rule_based',
                            'tag_type': _classify_tag_type(tag),
                        })

                    # Add metadata tags
                    if tag_result.get('is_spam'):
                        category_inserts.append({
                            'email_id': email['id'],
                            'category': '_meta_spam',
                            'confidence': 1.0,
                            'detection_method': 'rule_based',
                            'tag_type': 'metadata',
                        })

                    if tag_result.get('is_marketing'):
                        category_inserts.append({
                            'email_id': email['id'],
                            'category': '_meta_marketing',
                            'confidence': 1.0,
                            'detection_method': 'rule_based',
                            'tag_type': 'metadata',
                        })

                    # Add priority
                    priority_score = tag_result.get('priority_score', 5)
                    category_inserts.append({
                        'email_id': email['id'],
                        'category': f'_meta_priority_{priority_score}',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                        'tag_type': 'metadata',
                    })

                    # Add sender type
                    sender_type = tag_result.get('sender_type', 'unknown')
                    category_inserts.append({
                        'email_id': email['id'],
                        'category': f'_meta_sender_{sender_type}',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                        'tag_type': 'metadata',
                    })

                    # Batch insert tags
                    if category_inserts:
                        sb.table('email_categories').insert(category_inserts).execute()

                    processed += 1

                except Exception as e:
                    logger.error(f"Failed to reprocess email {email['id']}: {str(e)}")
                    failed += 1

            # Update progress after each batch
            await update_job_status(job_id, "running", {
                "processed_records": processed,
                "failed_records": failed
            })

            logger.info(f"Reprocessing progress: {processed}/{total_emails} (batch offset: {offset})")

            # Move to next batch
            offset += batch_size

        # Step 3: Ensure all folders exist in folders table
        logger.info(f"Creating {len(folders_to_create)} folder entries...")
        folder_type_map = {
            'Inbox': 'inbox',
            'INBOX': 'inbox',
            'Sent': 'sent',
            'Sent Items': 'sent',
            'Spam': 'spam',
            'Junk': 'spam',
            'Trash': 'trash',
            'Deleted Items': 'trash',
            'Drafts': 'drafts',
            'Archive': 'archive',
            'Archived': 'archive'
        }

        # Check which folders already exist
        existing_folders = set()
        try:
            result = sb.table('folders').select('folder_path').eq('mailbox_id', mailbox_id).execute()
            if result.data:
                existing_folders = {f['folder_path'] for f in result.data}
        except Exception as e:
            logger.warning(f"Failed to check existing folders: {e}")

        # Create missing folders
        new_folders = []
        for folder_path in folders_to_create:
            if folder_path not in existing_folders:
                folder_type = folder_type_map.get(folder_path, 'user')
                new_folders.append({
                    'folder_path': folder_path,
                    'mailbox_id': mailbox_id,
                    'folder_type': folder_type,
                    'message_count': 0
                })

        if new_folders:
            try:
                sb.table('folders').insert(new_folders).execute()
                logger.info(f"Created {len(new_folders)} new folder entries")
            except Exception as e:
                logger.warning(f"Failed to create folders: {e}")

        # Step 4: Update folder counts
        try:
            sb.rpc('update_folder_counts', {}).execute()
            logger.info("Folder counts updated")
        except Exception as e:
            logger.warning(f"Failed to update folder counts: {e}")

        # Mark as completed
        await update_job_status(job_id, "completed", {
            "processed_records": processed,
            "failed_records": failed,
            "completed_at": datetime.now(timezone.utc).isoformat()
        })

        logger.info(f"Reprocessing job {job_id} completed. Processed: {processed}, Failed: {failed}")

    except Exception as e:
        error_msg = f"Reprocessing error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await update_job_status(job_id, "failed", {
            "error_log": [error_msg],
            "completed_at": datetime.now(timezone.utc).isoformat()
        })

# Email analysis endpoints for dashboard
@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """Get dashboard statistics"""
    
    try:
        # Get stats from database
        sb = get_supabase()
        emails_count = sb.table('emails').select('id', count='exact').execute()
        mailboxes_count = sb.table('mailboxes').select('id', count='exact').execute()

        today = datetime.now(timezone.utc).date().isoformat()
        today_emails = sb.table('emails').select('id', count='exact').gte('sent_date', today).execute()

        processing_jobs_count = sb.table('processing_jobs').select('id', count='exact').in_('status', ['pending', 'running']).execute()
        
        return {
            "totalEmails": emails_count.count or 0,
            "totalMailboxes": mailboxes_count.count or 0, 
            "todayEmails": today_emails.count or 0,
            "processingJobs": processing_jobs_count.count or 0
        }
        
    except Exception as e:
        # Return mock data if database unavailable
        return {
            "totalEmails": 1250,
            "totalMailboxes": 3,
            "todayEmails": 45,
            "processingJobs": 1
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)