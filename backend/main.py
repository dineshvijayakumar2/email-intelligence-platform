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
from concurrent.futures import ThreadPoolExecutor
from google_auth_oauthlib.flow import Flow

# Version: 1.2.0 - Email count estimation + folder/tag separation + Redis
# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.processors.email_processor import EmailProcessor
from src.database.redis_client import JobProgressManager, JobQueueManager, RedisClient

# Configure logging to both file and console
import logging.handlers

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # File handler - rotates when file reaches 10MB, keeps 5 backup files
        logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'backend.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        ),
        # Console handler - also output to terminal
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables from parent directory
# Check for environment-specific files first, then fallback to .env
parent_dir = os.path.join(os.path.dirname(__file__), '..')
python_env = os.getenv('PYTHON_ENV', 'development')  # default to development

# Try environment-specific file first
env_file = os.path.join(parent_dir, f'.env.{python_env}')
if os.path.exists(env_file):
    load_dotenv(dotenv_path=env_file)
    logger.info(f"Loading {python_env} environment variables from: {env_file}")
else:
    # Fallback to generic .env file
    fallback_env = os.path.join(parent_dir, '.env')
    if os.path.exists(fallback_env):
        load_dotenv(dotenv_path=fallback_env)
        logger.info(f"Loading environment variables from: {fallback_env}")
    else:
        logger.warning("No .env file found! Please create .env.development or .env file")

logger.info(f"Running in {python_env} mode")

app = FastAPI(title="Email Intelligence API", version="1.0.0")

# Configure thread pool for concurrent job processing
# Allows up to 20 concurrent background jobs (file processing is I/O bound)
# This ensures multiple mailboxes can be processed simultaneously
executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="email_processor")

# Initialize Redis managers (REQUIRED for job processing)
try:
    progress_manager = JobProgressManager()
    queue_manager = JobQueueManager()
    logger.info("Redis managers initialized successfully")
    
    # Test Redis connection
    if not RedisClient.test_connection():
        raise Exception("Redis connection test failed")
        
except Exception as e:
    logger.error(f"Failed to initialize Redis managers: {e}")
    logger.error("Redis is REQUIRED for job processing. Please ensure Redis is running.")
    logger.error("Install Redis: brew install redis (macOS) or sudo apt install redis-server (Ubuntu)")
    logger.error("Start Redis: redis-server")
    raise RuntimeError("Redis is required but not available. Cannot start application.")

# Initialize shared progress tracker (used by email processor)
# Force backend restart
try:
    import sys
    src_path = os.path.join(os.path.dirname(__file__), '..', 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from utils.progress_tracker import initialize_progress_managers
    initialize_progress_managers(progress_manager, queue_manager)
    logger.info("Shared progress tracker initialized")
except Exception as e:
    logger.error(f"Failed to initialize shared progress tracker: {e}")

def sync_redis_to_database():
    """Sync all Redis progress to database before shutdown"""
    if not progress_manager:
        return

    try:
        active_jobs = progress_manager.get_all_active_jobs()
        logger.info(f"Syncing {len(active_jobs)} jobs from Redis to database...")

        for job_id in active_jobs:
            try:
                progress = progress_manager.get_progress(job_id)
                if progress:
                    get_supabase().table('processing_jobs').update({
                        'processed_records': progress['processed'],
                        'failed_records': progress['failed']
                    }).eq('id', job_id).execute()
                    logger.info(f"Synced job {job_id}: {progress['processed']} processed")
            except Exception as e:
                logger.error(f"Failed to sync job {job_id} to database: {e}")
    except Exception as e:
        logger.error(f"Failed to sync Redis to database: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on server shutdown"""
    logger.info("Syncing all Redis progress to database...")
    sync_redis_to_database()
    logger.info("Shutting down thread pool executor...")
    executor.shutdown(wait=True)
    logger.info("Thread pool executor shut down successfully")

def get_job_progress(job_id: str) -> dict:
    """Get progress from Redis (fast) or database (fallback)"""
    if progress_manager:
        progress = progress_manager.get_progress(job_id)
        if progress:
            return progress

    # Fallback to database
    return {"processed": 0, "failed": 0}

def update_job_progress_redis(job_id: str, processed: int, failed: int = 0, sync_to_db: bool = False):
    """
    Update job progress in Redis

    Args:
        job_id: Job ID
        processed: Number of emails processed
        failed: Number of failed emails
        sync_to_db: If True, also sync to database immediately

    Returns:
        True if should sync to database (every 100 emails or 30 seconds)
    """
    if not progress_manager:
        # Redis not available, always sync to DB
        return True

    # Update Redis
    progress_manager.update_progress(job_id, processed, failed)

    # Determine if we should sync to database
    # Sync every 100 emails to reduce DB load but ensure persistence
    should_sync = sync_to_db or (processed > 0 and processed % 100 == 0)

    return should_sync

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

class OAuth2ExchangeRequest(BaseModel):
    code: str  # OAuth2 authorization code from frontend
    user_id: str  # User identifier

class GoogleDriveConnection(BaseModel):
    user_id: str
    status: str  # 'connected' or 'disconnected'

# In-memory job storage for POC (use Redis in production)
active_jobs = {}

# Helper functions for Google Drive token management
def store_user_google_tokens(user_id: str, access_token: str, refresh_token: str) -> bool:
    """Store user's Google Drive tokens in database"""
    try:
        # Check if integration already exists
        existing = get_supabase().table('user_integrations').select('id').eq('user_id', user_id).eq('provider', 'google_drive').execute()
        
        token_data = {
            'user_id': user_id,
            'provider': 'google_drive',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        if existing.data:
            # Update existing integration
            result = get_supabase().table('user_integrations').update(token_data).eq('user_id', user_id).eq('provider', 'google_drive').execute()
        else:
            # Create new integration
            token_data['created_at'] = datetime.now(timezone.utc).isoformat()
            result = get_supabase().table('user_integrations').insert(token_data).execute()
        
        logger.info(f"Stored Google Drive tokens for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to store Google Drive tokens for user {user_id}: {e}")
        return False

def get_user_google_tokens(user_id: str) -> Optional[Dict]:
    """Get user's Google Drive tokens from database"""
    try:
        result = get_supabase().table('user_integrations').select('access_token,refresh_token').eq('user_id', user_id).eq('provider', 'google_drive').execute()
        
        if result.data:
            return result.data[0]
        return None
        
    except Exception as e:
        logger.error(f"Failed to get Google Drive tokens for user {user_id}: {e}")
        return None

def update_user_access_token(user_id: str, new_access_token: str) -> bool:
    """Update user's access token after refresh"""
    try:
        get_supabase().table('user_integrations').update({
            'access_token': new_access_token,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('user_id', user_id).eq('provider', 'google_drive').execute()
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to update access token for user {user_id}: {e}")
        return False

# =========================================================================
# Google Drive OAuth2 Integration Endpoints
# =========================================================================

@app.post("/api/auth/google/exchange")
async def exchange_oauth_code(request: OAuth2ExchangeRequest):
    """Exchange OAuth2 authorization code for tokens and store securely"""
    try:
        # Create OAuth2 flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI")]
                }
            },
            scopes=[
                'https://www.googleapis.com/auth/drive.readonly',
                'https://www.googleapis.com/auth/userinfo.email',
                'openid',
                'https://www.googleapis.com/auth/userinfo.profile'
            ]
        )
        
        flow.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
        
        # Exchange authorization code for tokens
        flow.fetch_token(code=request.code)
        
        # Store tokens securely in database
        success = store_user_google_tokens(
            user_id=request.user_id,
            access_token=flow.credentials.token,
            refresh_token=flow.credentials.refresh_token
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to store Google Drive tokens")
        
        return {
            "status": "success",
            "message": "Google Drive connected successfully",
            "user_id": request.user_id
        }
        
    except Exception as e:
        logger.error(f"OAuth2 token exchange failed: {e}")
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {str(e)}")

@app.get("/api/auth/google/status/{user_id}")
async def get_google_drive_status(user_id: str):
    """Check if user has connected their Google Drive"""
    try:
        tokens = get_user_google_tokens(user_id)
        
        return {
            "user_id": user_id,
            "connected": tokens is not None,
            "provider": "google_drive"
        }
        
    except Exception as e:
        logger.error(f"Failed to check Google Drive status for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to check connection status")

@app.delete("/api/auth/google/disconnect/{user_id}")
async def disconnect_google_drive(user_id: str):
    """Disconnect user's Google Drive integration"""
    try:
        # Remove tokens from database
        get_supabase().table('user_integrations').delete().eq('user_id', user_id).eq('provider', 'google_drive').execute()
        
        logger.info(f"Disconnected Google Drive for user {user_id}")
        
        return {
            "status": "success",
            "message": "Google Drive disconnected successfully",
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Failed to disconnect Google Drive for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect Google Drive")

@app.get("/")
async def root():
    return {"message": "Email Intelligence API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Mailbox endpoints
@app.get("/api/mailboxes")
async def get_mailboxes():
    """Get all mailboxes with email counts"""
    try:
        sb = get_supabase()
        
        # Get mailboxes
        mailboxes_result = sb.table('mailboxes').select('*').order('created_at', desc=True).execute()
        
        if not mailboxes_result.data:
            return []
        
        # Get email counts for each mailbox
        mailboxes_with_counts = []
        for mailbox in mailboxes_result.data:
            try:
                count_result = sb.table('emails').select('*', count='exact', head=True).eq('mailbox_id', mailbox['id']).execute()
                email_count = count_result.count or 0
                
                mailboxes_with_counts.append({
                    **mailbox,
                    'total_emails': email_count
                })
            except Exception as e:
                logger.warning(f"Failed to get email count for mailbox {mailbox['id']}: {e}")
                mailboxes_with_counts.append({
                    **mailbox,
                    'total_emails': 0
                })
        
        return mailboxes_with_counts
        
    except Exception as e:
        logger.error(f"Error fetching mailboxes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch mailboxes: {str(e)}")

@app.get("/api/mailboxes/{mailbox_id}")
async def get_mailbox(mailbox_id: str):
    """Get a single mailbox by ID"""
    try:
        sb = get_supabase()
        result = sb.table('mailboxes').select('*').eq('id', mailbox_id).single().execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        
        return result.data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch mailbox: {str(e)}")

@app.post("/api/mailboxes")
async def create_mailbox(mailbox_data: MailboxConfig):
    """Create a new mailbox"""
    try:
        sb = get_supabase()
        
        # Prepare data for insertion
        insert_data = {
            "name": mailbox_data.name,
            "mailbox_type": mailbox_data.mailbox_type,
            "is_active": mailbox_data.is_active,
            "connection_config": mailbox_data.connection_config,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total_emails": 0
        }
        
        # Add email_address if provided
        if mailbox_data.email_address:
            insert_data["email_address"] = mailbox_data.email_address
        
        # Insert the mailbox
        result = sb.table('mailboxes').insert(insert_data).execute()
        
        # Fetch the created mailbox
        if result.data and len(result.data) > 0:
            mailbox_id = result.data[0]['id']
            created_result = sb.table('mailboxes').select('*').eq('id', mailbox_id).single().execute()
            return created_result.data
        else:
            raise HTTPException(status_code=500, detail="Failed to create mailbox")
        
    except Exception as e:
        logger.error(f"Error creating mailbox: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create mailbox: {str(e)}")

@app.put("/api/mailboxes/{mailbox_id}")
async def update_mailbox(mailbox_id: str, mailbox_data: MailboxConfig):
    """Update an existing mailbox"""
    try:
        sb = get_supabase()
        
        # Prepare update data
        update_data = {
            "name": mailbox_data.name,
            "mailbox_type": mailbox_data.mailbox_type,
            "is_active": mailbox_data.is_active,
            "connection_config": mailbox_data.connection_config,
        }
        
        # Add email_address if provided
        if mailbox_data.email_address:
            update_data["email_address"] = mailbox_data.email_address
        
        # Update the mailbox
        result = sb.table('mailboxes').update(update_data).eq('id', mailbox_id).execute()
        
        # Fetch the updated mailbox
        updated_result = sb.table('mailboxes').select('*').eq('id', mailbox_id).single().execute()
        
        if not updated_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        
        return updated_result.data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update mailbox: {str(e)}")

@app.delete("/api/mailboxes/{mailbox_id}")
async def delete_mailbox(mailbox_id: str):
    """Delete a mailbox"""
    try:
        sb = get_supabase()
        
        # Check if mailbox exists
        check_result = sb.table('mailboxes').select('id').eq('id', mailbox_id).execute()
        if not check_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        
        # Delete the mailbox
        sb.table('mailboxes').delete().eq('id', mailbox_id).execute()
        
        return {"message": "Mailbox deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete mailbox: {str(e)}")

@app.post("/api/mailboxes/{mailbox_id}/sync")
async def sync_mailbox(mailbox_id: str):
    """Trigger sync for a mailbox"""
    try:
        sb = get_supabase()
        
        # Update last_sync_at timestamp
        update_data = {
            "last_sync_at": datetime.now(timezone.utc).isoformat()
        }
        
        result = sb.table('mailboxes').update(update_data).eq('id', mailbox_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")
        
        return {"message": "Mailbox sync triggered successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync mailbox: {str(e)}")

@app.post("/api/mailboxes/test/test-connection")
async def test_connection_generic(connection_test: ConnectionTest):
    """Test mailbox connection based on type"""
    
    mailbox_type = connection_test.mailbox_type
    config = connection_test.connection_config
    
    try:
        # Use EmailProcessor to validate configuration
        processor = EmailProcessor(
            mailbox_id="test_connection",  # Temporary ID for validation
            connection_config=config
        )
        
        # For local files, use the validation method
        if config.get('file_source', 'local') == 'local':
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
        else:
            # For Google Drive files, test extractor initialization with service account
            try:
                if not processor.initialize_extractor(mailbox_type):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to initialize {mailbox_type.upper()} extractor for Google Drive file"
                    )
                
                # Test successful - cleanup and return
                processor.disconnect()
                
                google_file_name = config.get('google_drive_file_name', 'Unknown file')
                return {
                    "success": True,
                    "message": f"{mailbox_type.upper()} Google Drive connection test successful",
                    "details": {
                        "file_name": google_file_name,
                        "file_source": "google_drive",
                        "mailbox_type": mailbox_type
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Google Drive connection test failed: {str(e)}"
                )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")

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

        # For local files, use the validation method
        if config.get('file_source', 'local') == 'local':
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
        else:
            # For Google Drive files, test extractor initialization with service account
            try:
                if not processor.initialize_extractor(mailbox_type):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to initialize {mailbox_type.upper()} extractor for Google Drive file"
                    )
                
                # Test successful - cleanup and return
                processor.disconnect()
                
                google_file_name = config.get('google_drive_file_name', 'Unknown file')
                return {
                    "success": True,
                    "message": f"{mailbox_type.upper()} Google Drive connection test successful",
                    "details": {
                        "file_name": google_file_name,
                        "file_source": "google_drive",
                        "mailbox_type": mailbox_type
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Google Drive connection test failed: {str(e)}"
                )

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

        # Immediately update status to 'running' so user sees it's active
        await update_job_status(job_id, "running", {
            "started_at": datetime.now(timezone.utc).isoformat()
        })

        # Initialize processor with actual configuration
        processor = EmailProcessor(
            mailbox_id=config.mailbox_id,
            connection_config=config.connection_config
        )

        # Initialize the extractor
        logger.info(f"Initializing {config.mailbox_type} extractor for job {job_id}...")
        if not processor.initialize_extractor(config.mailbox_type):
            error_msg = f"Failed to initialize {config.mailbox_type} extractor"
            logger.error(error_msg)

            # Check if job was already stopped (don't override stopped status)
            job_result = get_supabase().table('processing_jobs').select('status').eq('id', job_id).execute()
            if job_result.data and job_result.data[0].get('status') not in ['stopped', 'cancelled']:
                await update_job_status(job_id, "failed", {
                    "error_log": [error_msg],
                    "completed_at": datetime.now(timezone.utc).isoformat()
                })
            else:
                logger.warning(f"Extractor initialization failed after job was stopped: {error_msg}")

            return

        # Get total email count for progress estimation (fast, doesn't process emails)
        try:
            total_emails = processor.extractor.get_email_count()
            if total_emails:
                logger.info(f"Estimated total emails in mailbox: {total_emails}")
                # Update job with accurate total_records
                get_supabase().table('processing_jobs').update({
                    'total_records': total_emails
                }).eq('id', job_id).execute()
                # Update Redis cache too
                if progress_manager:
                    progress_manager.update_progress(job_id, 0, 0, total_records=total_emails)
            else:
                logger.warning("Could not estimate total email count - using config value or None")
        except Exception as e:
            logger.warning(f"Failed to get email count (will proceed without estimate): {e}")

        # Process emails with streaming
        # Run in dedicated thread pool to avoid blocking event loop
        # Using custom executor allows multiple concurrent jobs
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,  # Custom thread pool with 20 workers
            lambda: processor.process_emails(
                job_id=job_id,
                max_emails=config.total_records,  # max_emails (None for all)
                batch_size=config.batch_size or 5000,  # batch_size
                skip_duplicates=True,  # skip_duplicates
                enable_categorization=config.enable_categorization  # enable_categorization
            )
        )

        logger.info(f"Processing completed for job {job_id}: {result}")

        # Cleanup
        processor.disconnect()

    except Exception as e:
        error_msg = f"Processing error: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Check if job was already stopped (don't override stopped status)
        job_result = get_supabase().table('processing_jobs').select('status').eq('id', job_id).execute()
        if job_result.data and job_result.data[0].get('status') in ['stopped', 'cancelled']:
            logger.warning(f"Exception occurred after job was stopped: {error_msg}")
        else:
            # Not stopped - genuine failure
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
            # Get real-time progress from Redis (faster than database)
            redis_progress = get_job_progress(job['id'])
            if redis_progress['processed'] > job.get('processed_records', 0):
                # Redis has more recent data than database
                job['processed_records'] = redis_progress['processed']
                job['failed_records'] = redis_progress['failed']

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

@app.post("/api/processing-jobs/{job_id}/pause")
async def pause_job(job_id: str):
    """Pause a processing job"""
    return await control_job_action(job_id, "pause")

@app.post("/api/processing-jobs/{job_id}/resume")
async def resume_job(job_id: str):
    """Resume a processing job"""
    return await control_job_action(job_id, "resume")

@app.post("/api/processing-jobs/{job_id}/stop")
async def stop_job(job_id: str):
    """Stop a processing job"""
    return await control_job_action(job_id, "stop")

async def control_job_action(job_id: str, action: str):
    """Control processing job (pause, resume, stop)"""
    
    valid_actions = ["pause", "resume", "stop"]
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {valid_actions}")
    
    try:
        status_map = {
            "pause": "paused",
            "resume": "running",
            "stop": "stopped"
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
            # Check if job should be stopped or paused
            job_status_result = sb.table('processing_jobs').select('status').eq('id', job_id).execute()
            if job_status_result.data:
                current_status = job_status_result.data[0]['status']

                if current_status in ['stopped', 'cancelled', 'failed']:
                    logger.info(f"Reprocessing job {job_id} stopped at offset {offset}")
                    break

                if current_status == 'paused':
                    logger.info(f"Reprocessing job {job_id} paused at offset {offset}, waiting...")
                    # Wait for resume or stop
                    from src.database.operations import DatabaseOperations
                    db_ops = DatabaseOperations(mailbox_id=mailbox_id)
                    if not db_ops.wait_while_paused(job_id):
                        logger.info(f"Reprocessing job {job_id} stopped while paused")
                        break
                    logger.info(f"Reprocessing job {job_id} resumed")

            # Fetch one batch at a time from database
            logger.info(f"Fetching batch: offset={offset}, limit={batch_size}")
            result = sb.table('emails').select('*').eq('mailbox_id', mailbox_id).range(offset, offset + batch_size - 1).execute()
            batch = result.data

            if not batch:
                break  # No more emails

            # OPTIMIZED: Process entire batch with bulk operations instead of individual queries
            batch_folder_updates = []
            batch_email_ids = []
            all_category_inserts = []

            for email in batch:
                try:
                    # Step 1: Re-normalize email with new folder inference
                    inferred_folder = normalizer._infer_folder_path(
                        provided_folder=None,  # Force inference
                        is_outbound=email.get('is_outbound', False),
                        sender_email=email.get('sender_email', ''),
                        recipients=email.get('recipients', []),
                        subject=email.get('subject', ''),
                        body_text=email.get('body_text', '')
                    )

                    # Collect folder updates for bulk operation
                    old_folder = email.get('folder_path', '')
                    if inferred_folder != old_folder:
                        batch_folder_updates.append({
                            'id': email['id'],
                            'folder_path': inferred_folder
                        })
                        email['folder_path'] = inferred_folder  # Update for tagging

                    # Track folders that need to exist
                    folders_to_create.add(inferred_folder)

                    # Step 2: Tag the email (with updated folder_path)
                    tag_result = tagger.tag_email(email)

                    # Collect email ID for bulk delete
                    batch_email_ids.append(email['id'])

                    # Collect all category inserts for bulk operation
                    # Add regular tags
                    for tag in tag_result.get('tags', []):
                        all_category_inserts.append({
                            'email_id': email['id'],
                            'category': tag,
                            'confidence': 1.0,
                            'detection_method': 'rule_based',
                            'tag_type': _classify_tag_type(tag),
                        })

                    # Add metadata tags
                    if tag_result.get('is_spam'):
                        all_category_inserts.append({
                            'email_id': email['id'],
                            'category': '_meta_spam',
                            'confidence': 1.0,
                            'detection_method': 'rule_based',
                            'tag_type': 'metadata',
                        })

                    if tag_result.get('is_marketing'):
                        all_category_inserts.append({
                            'email_id': email['id'],
                            'category': '_meta_marketing',
                            'confidence': 1.0,
                            'detection_method': 'rule_based',
                            'tag_type': 'metadata',
                        })

                    # Add priority
                    priority_score = tag_result.get('priority_score', 5)
                    all_category_inserts.append({
                        'email_id': email['id'],
                        'category': f'_meta_priority_{priority_score}',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                        'tag_type': 'metadata',
                    })

                    # Add sender type
                    sender_type = tag_result.get('sender_type', 'unknown')
                    all_category_inserts.append({
                        'email_id': email['id'],
                        'category': f'_meta_sender_{sender_type}',
                        'confidence': 1.0,
                        'detection_method': 'rule_based',
                        'tag_type': 'metadata',
                    })

                    processed += 1

                except Exception as e:
                    logger.error(f"Failed to reprocess email {email.get('id', 'unknown')}: {str(e)}")
                    failed += 1

            # Perform bulk database operations for the entire batch
            try:
                # Bulk update folder paths (if any changed)
                if batch_folder_updates:
                    for update in batch_folder_updates:
                        sb.table('emails').update({
                            'folder_path': update['folder_path']
                        }).eq('id', update['id']).execute()
                    logger.info(f"Updated {len(batch_folder_updates)} folder paths")

                # Bulk delete old categories for all emails in batch
                if batch_email_ids:
                    sb.table('email_categories').delete().in_('email_id', batch_email_ids).execute()
                    logger.info(f"Deleted old categories for {len(batch_email_ids)} emails")

                # Bulk insert new categories in chunks (Supabase has limits)
                if all_category_inserts:
                    chunk_size = 1000
                    for i in range(0, len(all_category_inserts), chunk_size):
                        chunk = all_category_inserts[i:i + chunk_size]
                        sb.table('email_categories').insert(chunk).execute()
                    logger.info(f"Inserted {len(all_category_inserts)} new categories")

            except Exception as e:
                logger.error(f"Bulk operation failed for batch at offset {offset}: {str(e)}")
                # Don't fail the whole job, just log and continue

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

        # Check if job was already stopped (don't override stopped status)
        job_result = get_supabase().table('processing_jobs').select('status').eq('id', job_id).execute()
        if job_result.data and job_result.data[0].get('status') in ['stopped', 'cancelled']:
            logger.warning(f"Reprocessing exception occurred after job was stopped: {error_msg}")
        else:
            # Not stopped - genuine failure
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

@app.get("/api/emails/folders")
async def get_folder_names():
    """Get distinct folder names from emails for filter dropdown"""

    try:
        sb = get_supabase()

        logger.info("Fetching distinct folder names...")

        # First, get total count to verify data
        count_result = sb.table('emails').select('id', count='exact').execute()
        total_emails = count_result.count or 0
        logger.info(f"Total emails in database: {total_emails}")

        # Fetch all emails in batches
        # IMPORTANT: Supabase may have varying limits, so we loop until we get all emails
        all_folders = set()
        page = 0
        page_size = 1000  # Request size
        total_fetched = 0

        while total_fetched < total_emails:
            from_idx = page * page_size
            to_idx = from_idx + page_size - 1

            logger.info(f"Fetching page {page} (rows {from_idx}-{to_idx})")

            # Supabase range() is INCLUSIVE on both ends
            result = sb.table('emails').select('folder_path').range(from_idx, to_idx).execute()

            if not result.data or len(result.data) == 0:
                logger.warning(f"No data returned for page {page}, stopping")
                break

            batch_size = len(result.data)
            total_fetched += batch_size
            logger.info(f"Page {page}: Got {batch_size} rows, total fetched: {total_fetched}/{total_emails}")

            # Add to set
            for row in result.data:
                folder = row.get('folder_path')
                if folder:
                    all_folders.add(folder)

            logger.info(f"Unique folders so far: {len(all_folders)} - {sorted(all_folders)}")

            # Continue to next page
            page += 1

            # Safety limit
            if page > 100:
                logger.warning(f"Hit safety limit of 100 pages (100k emails)")
                break

        folders_list = sorted(list(all_folders))
        logger.info(f"✓ Found {len(folders_list)} unique folders from {total_fetched} emails: {folders_list}")

        return folders_list

    except Exception as e:
        logger.error(f"Error fetching folder names: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch folders: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)