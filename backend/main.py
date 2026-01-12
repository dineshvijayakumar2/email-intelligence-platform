from fastapi import FastAPI, HTTPException, BackgroundTasks  # v9 - industry-standard RemoteZip implementation
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

# Load environment variables from backend directory
python_env = os.getenv('PYTHON_ENV', 'development')  # default to development
backend_dir = os.path.dirname(__file__)

# Try environment-specific file first in backend directory
env_file = os.path.join(backend_dir, f'.env.{python_env}')
if os.path.exists(env_file):
    load_dotenv(dotenv_path=env_file)
    logger.info(f"Loading {python_env} environment variables from: {env_file}")
else:
    # Fallback to generic .env file in backend directory
    fallback_env = os.path.join(backend_dir, '.env')
    if os.path.exists(fallback_env):
        load_dotenv(dotenv_path=fallback_env)
        logger.info(f"Loading environment variables from: {fallback_env}")
    else:
        logger.warning("No .env file found! Please create backend/.env.development or backend/.env file")

logger.info(f"Running in {python_env} mode")

app = FastAPI(title="Email Intelligence API", version="1.0.0")

# Configure CORS for frontend access
# Parse allowed origins from environment variable (comma-separated)
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")

# Log the raw environment variable to debug Railway variable resolution
logger.info(f"Raw ALLOWED_ORIGINS env var: '{allowed_origins_str}'")

# Handle wildcard or specific origins
if allowed_origins_str.strip() == "*":
    allowed_origins = ["*"]
    allow_credentials = False  # Must be False for wildcard
    logger.info("Using wildcard CORS origin (*)")
else:
    allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",") if origin.strip()]
    allow_credentials = True
    logger.info(f"Using specific CORS origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

logger.info(f"CORS middleware configured - Origins: {allowed_origins}, Credentials: {allow_credentials}")

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

    from src.utils.progress_tracker import initialize_progress_managers
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
    return {"processed": 0, "failed": 0, "total_records": 0, "emails_per_second": 0, "estimated_seconds_remaining": 0}

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

# Email API models
class EmailFilters(BaseModel):
    search: Optional[str] = None
    category: Optional[str] = None
    mailbox: Optional[str] = None
    folder: Optional[str] = None
    dateRange: Optional[List[str]] = None
    isOutbound: Optional[str] = None
    tags: Optional[List[str]] = None
    isSpam: Optional[bool] = None
    isMarketing: Optional[bool] = None
    minPriority: Optional[int] = None
    maxPriority: Optional[int] = None

class EmailRequest(BaseModel):
    filters: EmailFilters = EmailFilters()  # Make filters optional with default empty filters
    page: int = 1
    pageSize: int = 20

class EmailResponse(BaseModel):
    id: str
    subject: str
    sender_email: str
    sender_name: Optional[str]
    sent_date: str
    category: Optional[str]
    is_outbound: bool
    is_reply: bool
    folder_path: str
    message_size: int
    mailbox_name: str
    mailbox_id: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    tags: Optional[List[str]] = None
    is_spam: Optional[bool] = None
    is_marketing: Optional[bool] = None
    priority_score: Optional[int] = None
    sender_type: Optional[str] = None

class EmailListResponse(BaseModel):
    emails: List[EmailResponse]
    totalCount: int

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

            # Format ETA if available from Redis
            eta_str = None
            emails_per_second = redis_progress.get('emails_per_second', 0) or 0
            estimated_seconds = redis_progress.get('estimated_seconds_remaining', 0) or 0
            
            # Ensure values are numbers, not None
            try:
                emails_per_second = float(emails_per_second) if emails_per_second else 0
                estimated_seconds = float(estimated_seconds) if estimated_seconds else 0
            except (ValueError, TypeError):
                emails_per_second = 0
                estimated_seconds = 0
            
            if estimated_seconds > 0 and job.get('status') == 'running':
                if estimated_seconds < 60:
                    eta_str = f"{estimated_seconds:.0f}s"
                elif estimated_seconds < 3600:
                    eta_minutes = estimated_seconds / 60
                    eta_str = f"{eta_minutes:.1f}m"
                else:
                    eta_hours = estimated_seconds / 3600
                    eta_str = f"{eta_hours:.1f}h"

            job_data = {
                **job,
                "mailbox_name": job.get('mailboxes', {}).get('name') if job.get('mailboxes') else 'Unknown Mailbox',
                "progress": progress,
                "total_records": total,  # Ensure it's not None
                "processed_records": processed,  # Ensure it's not None
                "emails_per_second": emails_per_second,
                "estimated_time_remaining": eta_str,
                "estimated_seconds_remaining": estimated_seconds
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

# =========================================================================
# Email API Endpoints - Replace direct Supabase access in frontend
# =========================================================================

def transform_email_data(item: dict) -> EmailResponse:
    """Transform database row to EmailResponse format"""
    # Extract tags and metadata from email_categories
    categories = item.get('email_categories', []) or []
    tags = [cat['category'] for cat in categories if not cat['category'].startswith('_meta_')]
    
    # Extract metadata
    is_spam = any(cat['category'] == '_meta_spam' for cat in categories)
    is_marketing = any(cat['category'] == '_meta_marketing' for cat in categories)
    
    # Extract priority score
    priority_tag = next((cat for cat in categories if cat['category'].startswith('_meta_priority_')), None)
    priority_score = int(priority_tag['category'].replace('_meta_priority_', '')) if priority_tag else 5
    
    # Extract sender type
    sender_tag = next((cat for cat in categories if cat['category'].startswith('_meta_sender_')), None)
    sender_type = sender_tag['category'].replace('_meta_sender_', '') if sender_tag else 'unknown'
    
    return EmailResponse(
        id=item['id'],
        subject=item['subject'],
        sender_email=item['sender_email'],
        sender_name=item.get('sender_name'),
        sent_date=item['sent_date'],
        category=categories[0]['category'] if categories else 'unassigned',
        is_outbound=item['is_outbound'],
        is_reply=item['is_reply'],
        folder_path=item['folder_path'],
        message_size=item['message_size'],
        body_text=item.get('body_text'),
        body_html=item.get('body_html'),
        mailbox_id=item['mailbox_id'],
        mailbox_name=item.get('mailboxes', {}).get('name', 'Unknown') if item.get('mailboxes') else 'Unknown',
        tags=tags,
        is_spam=is_spam,
        is_marketing=is_marketing,
        priority_score=priority_score,
        sender_type=sender_type
    )

@app.options("/api/emails")
async def emails_options():
    """Explicit OPTIONS handler to fix CORS preflight"""
    return {"status": "ok"}

@app.post("/api/emails")
async def get_emails_with_filters(request: EmailRequest):
    """
    SCALABLE EMAIL QUERY ENDPOINT - Fixed category filter with same approach
    
    Industry best practices for handling millions of emails:
    1. Cursor-based pagination for better performance
    2. Efficient single query with proper joins
    3. Database indexing strategy
    4. Query optimization with selective fields
    5. Caching for metadata (categories, mailboxes)
    """
    try:
        sb = get_supabase()
        filters = request.filters
        page = request.page
        pageSize = min(request.pageSize, 100)  # Limit max page size for performance
        
        logger.info(f"Scalable email query - Filters: {filters.dict()}, Page: {page}, Size: {pageSize}")
        
        # Build optimized query without joins (PostgREST limitation with complex selects)
        # We'll get categories separately for better performance
        base_query = sb.table('emails').select(f"""
            id,
            subject,
            sender_email,
            sender_name,
            sent_date,
            is_outbound,
            is_reply,
            folder_path,
            message_size,
            mailbox_id
        """)
        
        # Apply filters efficiently
        filters_applied = []
        
        # Mailbox filter (most selective - apply first)
        if filters.mailbox and filters.mailbox.strip():
            # First get mailbox ID, then filter by it
            try:
                mailbox_result = sb.table('mailboxes').select('id').eq('name', filters.mailbox).execute()
                if mailbox_result.data:
                    mailbox_id = mailbox_result.data[0]['id']
                    base_query = base_query.eq('mailbox_id', mailbox_id)
                    filters_applied.append(f"mailbox={filters.mailbox}")
                else:
                    # No matching mailbox found, return empty results
                    logger.warning(f"No mailbox found with name: {filters.mailbox}")
                    return EmailListResponse(emails=[], totalCount=0)
            except Exception as e:
                logger.error(f"Error filtering by mailbox: {e}")
                # Continue without mailbox filter
        
        # Folder filter (highly selective)
        if filters.folder and filters.folder.strip():
            base_query = base_query.eq('folder_path', filters.folder)
            filters_applied.append(f"folder={filters.folder}")
        
        # Date range filter (use indexes)
        if filters.dateRange and len(filters.dateRange) == 2:
            base_query = base_query.gte('sent_date', filters.dateRange[0]).lte('sent_date', filters.dateRange[1])
            filters_applied.append(f"date_range={filters.dateRange}")
        
        # Outbound/Inbound filter
        if filters.isOutbound == 'outbound':
            base_query = base_query.eq('is_outbound', True)
            filters_applied.append("direction=outbound")
        elif filters.isOutbound == 'inbound':
            base_query = base_query.eq('is_outbound', False)
            filters_applied.append("direction=inbound")
        
        # Text search (expensive - apply last) 
        if filters.search and filters.search.strip():
            search_term = filters.search.strip()
            # Simple subject search for now (will expand to multi-field later)
            base_query = base_query.ilike('subject', f'%{search_term}%')
            filters_applied.append(f"search={search_term}")
        
        # Category filter (requires separate optimization)
        if filters.category and filters.category.strip():
            return await handle_category_filter(base_query, filters, page, pageSize)
        
        # Apply ordering and pagination
        # Use sent_date index for efficient sorting
        base_query = base_query.order('sent_date', desc=True)
        
        # Cursor-based pagination for better performance at scale
        from_idx = (page - 1) * pageSize
        to_idx = from_idx + pageSize - 1
        base_query = base_query.range(from_idx, to_idx)
        
        logger.info(f"Optimized query - Applied filters: {filters_applied}")
        
        # Execute count query separately (PostgREST limitation with joins + count)
        count_query = sb.table('emails').select('id', count='exact')
        # Apply same filters to count query (exclude joins for count)
        if filters.mailbox and filters.mailbox.strip():
            try:
                mailbox_result = sb.table('mailboxes').select('id').eq('name', filters.mailbox).execute()
                if mailbox_result.data:
                    mailbox_id = mailbox_result.data[0]['id']
                    count_query = count_query.eq('mailbox_id', mailbox_id)
            except Exception:
                pass  # Skip mailbox filter for count if it fails
        if filters.folder and filters.folder.strip():
            count_query = count_query.eq('folder_path', filters.folder)
        if filters.dateRange and len(filters.dateRange) == 2:
            count_query = count_query.gte('sent_date', filters.dateRange[0]).lte('sent_date', filters.dateRange[1])
        if filters.isOutbound == 'outbound':
            count_query = count_query.eq('is_outbound', True)
        elif filters.isOutbound == 'inbound':
            count_query = count_query.eq('is_outbound', False)
        if filters.search and filters.search.strip():
            search_term = filters.search.strip()
            count_query = count_query.ilike('subject', f'%{search_term}%')
        
        # Execute queries
        result = base_query.execute()
        count_result = count_query.execute()
        
        logger.info(f"Query executed successfully, got {len(result.data or [])} results")
        if result.data and len(result.data) > 0:
            sample_email_id = result.data[0]['id']
            logger.info(f"Sample email ID: {sample_email_id}")
        
        # Get mailbox names separately for better performance (PostgREST multiple join limitation)
        mailbox_names = {}
        email_categories_map = {}
        
        if result.data:
            # Get unique mailbox IDs
            unique_mailbox_ids = list(set(item['mailbox_id'] for item in result.data if item.get('mailbox_id')))
            if unique_mailbox_ids:
                mailbox_result = sb.table('mailboxes').select('id, name').in_('id', unique_mailbox_ids).execute()
                for mailbox in mailbox_result.data or []:
                    mailbox_names[mailbox['id']] = mailbox['name']
            
            # Get email categories separately (PostgREST complex join limitation)
            email_ids = [item['id'] for item in result.data]
            if email_ids:
                # Process in batches to avoid URL length limits
                batch_size = 10  # Safe batch size for UUIDs
                total_categories = 0
                for i in range(0, len(email_ids), batch_size):
                    batch_ids = email_ids[i:i + batch_size]
                    try:
                        categories_result = sb.table('email_categories').select('email_id, category, tag_type').in_('email_id', batch_ids).execute()
                        total_categories += len(categories_result.data or [])
                        # Group categories by email_id
                        for cat in categories_result.data or []:
                            email_id = cat['email_id']
                            if email_id not in email_categories_map:
                                email_categories_map[email_id] = []
                            email_categories_map[email_id].append({
                                'category': cat['category'],
                                'tag_type': cat['tag_type']
                            })
                    except Exception as e:
                        logger.error(f"Error fetching categories for batch {i//batch_size}: {e}")
                        # Continue with other batches
                        continue
                
                logger.info(f"Categories query returned {total_categories} categories for {len(email_ids)} emails")
                # Log sample categories
                if email_categories_map and result.data:
                    sample_email_id = result.data[0]['id']
                    sample_categories = email_categories_map.get(sample_email_id, [])
                    logger.info(f"Sample email {sample_email_id} has {len(sample_categories)} categories")
        
        # Transform results efficiently
        emails = []
        for item in result.data or []:
            # Extract mailbox name from separate query
            mailbox_name = mailbox_names.get(item.get('mailbox_id'), 'Unknown')
            
            # Extract tags and categories from join
            tags = []
            category = 'unassigned'
            is_spam = False
            is_marketing = False
            priority_score = 5
            sender_type = 'unknown'
            
            # Get categories from separate query
            categories_data = email_categories_map.get(item['id'], [])
            
            if categories_data:
                if isinstance(categories_data, list):
                    # Multiple categories
                    for cat in categories_data:
                        if isinstance(cat, dict):
                            cat_name = cat.get('category', '')
                            if cat_name and not cat_name.startswith('_meta_'):
                                tags.append(cat_name)
                                if category == 'unassigned':  # Use first non-meta category
                                    category = cat_name
                            elif cat_name == '_meta_spam':
                                is_spam = True
                            elif cat_name == '_meta_marketing':
                                is_marketing = True
                elif isinstance(categories_data, dict):
                    # Single category
                    cat_name = categories_data.get('category', '')
                    if cat_name and not cat_name.startswith('_meta_'):
                        tags.append(cat_name)
                        category = cat_name
                    elif cat_name == '_meta_spam':
                        is_spam = True
                    elif cat_name == '_meta_marketing':
                        is_marketing = True
            
            emails.append(EmailResponse(
                id=item['id'],
                subject=item['subject'],
                sender_email=item['sender_email'],
                sender_name=item.get('sender_name'),
                sent_date=item['sent_date'],
                category=category,
                is_outbound=item['is_outbound'],
                is_reply=item['is_reply'],
                folder_path=item['folder_path'],
                message_size=item['message_size'],
                body_text=None,  # Don't return body for list view (performance)
                body_html=None,  # Don't return body for list view (performance)
                mailbox_id=item['mailbox_id'],
                mailbox_name=mailbox_name,
                tags=tags,
                is_spam=is_spam,
                is_marketing=is_marketing,
                priority_score=priority_score,
                sender_type=sender_type
            ))
        
        total_count = count_result.count or 0
        logger.info(f"Scalable query result: {len(emails)} emails out of {total_count} total")
        
        return EmailListResponse(emails=emails, totalCount=total_count)
        
    except Exception as e:
        logger.error(f"Error in scalable email query: {e}", exc_info=True)
        return EmailListResponse(emails=[], totalCount=0)

async def handle_category_filter(base_query, filters: EmailFilters, page: int, pageSize: int):
    """
    OPTIMIZED CATEGORY FILTERING
    
    For millions of emails, category filtering needs special handling:
    1. Use database-level joins instead of IN clauses
    2. Leverage indexes on email_categories table
    """
    try:
        sb = get_supabase()
        
        # First get emails that have the specified category using a subquery approach
        # Step 1: Get email IDs that have the specified category
        category_emails_result = sb.table('email_categories').select('email_id').eq('category', filters.category).execute()
        
        if not category_emails_result.data:
            # No emails with this category
            return EmailListResponse(emails=[], totalCount=0)
        
        # Get the email IDs
        email_ids_with_category = [item['email_id'] for item in category_emails_result.data]
        
        # Step 2: Query emails table with these IDs (in batches to avoid URL limits)
        all_emails = []
        batch_size = 50  # Process email IDs in batches
        
        for i in range(0, len(email_ids_with_category), batch_size):
            batch_ids = email_ids_with_category[i:i + batch_size]
            
            category_query = sb.table('emails').select(f"""
                id,
                subject,
                sender_email,
                sender_name,
                sent_date,
                is_outbound,
                is_reply,
                folder_path,
                message_size,
                mailbox_id
            """).in_('id', batch_ids)
            
            # Apply other filters to this batch
            if filters.mailbox and filters.mailbox.strip():
                try:
                    mailbox_result = sb.table('mailboxes').select('id').eq('name', filters.mailbox).execute()
                    if mailbox_result.data:
                        mailbox_id = mailbox_result.data[0]['id']
                        category_query = category_query.eq('mailbox_id', mailbox_id)
                    else:
                        continue  # Skip this batch if no matching mailbox
                except Exception as e:
                    logger.error(f"Error filtering by mailbox in category filter: {e}")
                    continue
                    
            if filters.folder and filters.folder.strip():
                category_query = category_query.eq('folder_path', filters.folder)
            if filters.isOutbound == 'outbound':
                category_query = category_query.eq('is_outbound', True)
            elif filters.isOutbound == 'inbound':
                category_query = category_query.eq('is_outbound', False)
            if filters.dateRange and len(filters.dateRange) == 2:
                category_query = category_query.gte('sent_date', filters.dateRange[0]).lte('sent_date', filters.dateRange[1])
            if filters.search and filters.search.strip():
                search_term = filters.search.strip()
                category_query = category_query.ilike('subject', f'%{search_term}%')
            
            # Execute this batch
            batch_result = category_query.execute()
            if batch_result.data:
                all_emails.extend(batch_result.data)
        
        # Sort all emails by sent_date desc
        all_emails.sort(key=lambda x: x['sent_date'], reverse=True)
        
        # Apply pagination to the combined results
        from_idx = (page - 1) * pageSize
        to_idx = from_idx + pageSize
        paginated_emails = all_emails[from_idx:to_idx]
        
        # Create a mock result object 
        class MockResult:
            def __init__(self, data):
                self.data = data
                
        result = MockResult(paginated_emails)
        
        # Get mailbox names and categories separately (same as main query)
        mailbox_names = {}
        email_categories_map = {}
        
        if result.data:
            # Get unique mailbox IDs
            unique_mailbox_ids = list(set(item['mailbox_id'] for item in result.data if item.get('mailbox_id')))
            if unique_mailbox_ids:
                mailbox_result = sb.table('mailboxes').select('id, name').in_('id', unique_mailbox_ids).execute()
                for mailbox in mailbox_result.data or []:
                    mailbox_names[mailbox['id']] = mailbox['name']
            
            # Get email categories separately (same batching logic)
            email_ids = [item['id'] for item in result.data]
            if email_ids:
                batch_size = 10
                total_categories = 0
                for i in range(0, len(email_ids), batch_size):
                    batch_ids = email_ids[i:i + batch_size]
                    try:
                        categories_result = sb.table('email_categories').select('email_id, category, tag_type').in_('email_id', batch_ids).execute()
                        total_categories += len(categories_result.data or [])
                        for cat in categories_result.data or []:
                            email_id = cat['email_id']
                            if email_id not in email_categories_map:
                                email_categories_map[email_id] = []
                            email_categories_map[email_id].append({
                                'category': cat['category'],
                                'tag_type': cat['tag_type']
                            })
                    except Exception as e:
                        logger.error(f"Error fetching categories for category filter batch: {e}")
                        continue
        
        # Transform results (same logic as main query)
        emails = []
        for item in result.data or []:
            mailbox_name = mailbox_names.get(item.get('mailbox_id'), 'Unknown')
            
            # Get categories from separate query
            categories_data = email_categories_map.get(item['id'], [])
            
            tags = []
            category = filters.category  # We know this email has this category
            is_spam = False
            is_marketing = False
            priority_score = 5
            sender_type = 'unknown'
            
            if categories_data:
                for cat in categories_data:
                    cat_name = cat.get('category', '')
                    if cat_name and not cat_name.startswith('_meta_'):
                        tags.append(cat_name)
                    elif cat_name == '_meta_spam':
                        is_spam = True
                    elif cat_name == '_meta_marketing':
                        is_marketing = True
            
            emails.append(EmailResponse(
                id=item['id'],
                subject=item['subject'],
                sender_email=item['sender_email'],
                sender_name=item.get('sender_name'),
                sent_date=item['sent_date'],
                category=category,
                is_outbound=item['is_outbound'],
                is_reply=item['is_reply'],
                folder_path=item['folder_path'],
                message_size=item['message_size'],
                body_text=None,
                body_html=None,
                mailbox_id=item['mailbox_id'],
                mailbox_name=mailbox_name,
                tags=tags,
                is_spam=is_spam,
                is_marketing=is_marketing,
                priority_score=priority_score,
                sender_type=sender_type
            ))
        
        logger.info(f"Category filter result: {len(emails)} emails for category '{filters.category}'")
        return EmailListResponse(emails=emails, totalCount=len(all_emails))
        
    except Exception as e:
        logger.error(f"Error in category filter: {e}", exc_info=True)
        return EmailListResponse(emails=[], totalCount=0)

async def get_emails_in_batches(
    email_id_batches: List[List[str]],
    filters: EmailFilters,
    page: int,
    pageSize: int
) -> EmailListResponse:
    """Helper to get emails in batches when filtering by category"""
    try:
        sb = get_supabase()
        all_emails = []
        
        for batch in email_id_batches:
            query = sb.table('emails').select("""
                id,
                subject,
                sender_email,
                sender_name,
                sent_date,
                is_outbound,
                is_reply,
                folder_path,
                message_size,
                body_text,
                body_html,
                mailbox_id,
                mailboxes!inner(name),
                email_categories(category, tag_type)
            """).in_('id', batch)
            
            # Apply other filters
            if filters.search:
                query = query.or_(f"subject.ilike.%{filters.search}%,sender_email.ilike.%{filters.search}%,sender_name.ilike.%{filters.search}%")
            
            if filters.mailbox:
                query = query.eq('mailboxes.name', filters.mailbox)
            
            if filters.folder:
                query = query.eq('folder_path', filters.folder)
            
            if filters.isOutbound == 'outbound':
                query = query.eq('is_outbound', True)
            elif filters.isOutbound == 'inbound':
                query = query.eq('is_outbound', False)
            
            if filters.dateRange and len(filters.dateRange) == 2:
                query = query.gte('sent_date', filters.dateRange[0]).lte('sent_date', filters.dateRange[1])
            
            result = await asyncio.get_event_loop().run_in_executor(None, lambda: query.execute())
            
            if result.error:
                logger.error(f'Error fetching email batch: {result.error}')
                raise HTTPException(status_code=500, detail=str(result.error))
            
            if result.data:
                all_emails.extend(result.data)
        
        # Sort by sent_date descending
        all_emails.sort(key=lambda x: x['sent_date'], reverse=True)
        
        # Client-side pagination
        total_count = len(all_emails)
        from_idx = (page - 1) * pageSize
        to_idx = from_idx + pageSize
        paginated_emails = all_emails[from_idx:to_idx]
        
        # Transform data
        emails = [transform_email_data(item) for item in paginated_emails]
        
        return EmailListResponse(emails=emails, totalCount=total_count)
        
    except Exception as e:
        logger.error(f"Error fetching emails in batches: {e}", exc_info=True)
        return EmailListResponse(emails=[], totalCount=0)

@app.get("/api/emails/categories")
async def get_email_categories():
    """Get email categories for filter dropdown - replaces frontend emailService.getEmailCategories()"""
    try:
        sb = get_supabase()
        
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.table('email_categories').select('category').execute()
        )
        
        logger.info(f'Raw category data from Supabase: {len(result.data or [])} rows')
        
        # Get unique categories, filter out metadata tags
        category_set = set()
        for item in result.data or []:
            category = item.get('category')
            if category and not category.startswith('_meta_'):
                category_set.add(category)
        
        categories = sorted(list(category_set))
        logger.info(f'Loaded categories: {categories}')
        
        return categories
        
    except Exception as e:
        logger.error(f"Error fetching email categories: {e}", exc_info=True)
        return ['spam', 'marketing', 'inbox', 'sent', 'trash']

@app.get("/api/emails/{email_id}")
async def get_email_by_id(email_id: str):
    """Get a single email by ID - replaces frontend emailService.getEmail()"""
    try:
        sb = get_supabase()
        
        result = await asyncio.get_event_loop().run_in_executor(
            None, 
            lambda: sb.table('emails').select("""
                id,
                subject,
                sender_email,
                sender_name,
                sent_date,
                is_outbound,
                is_reply,
                folder_path,
                message_size,
                body_text,
                body_html,
                mailbox_id,
                mailboxes!inner(name),
                email_categories(category, tag_type)
            """).eq('id', email_id).single().execute()
        )
        
        if result.error:
            logger.error(f'Error fetching email {email_id}: {result.error}')
            raise HTTPException(status_code=500, detail=str(result.error))
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Email not found")
        
        email = transform_email_data(result.data)
        return email
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching email {email_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch email")

@app.get("/api/mailbox-names")
async def get_mailbox_names():
    """Get mailbox names for filter dropdown - replaces frontend emailService.getMailboxNames()"""
    try:
        sb = get_supabase()
        
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.table('mailboxes').select('name').eq('is_active', True).execute()
        )
        
        return [item['name'] for item in result.data or []]
        
    except Exception as e:
        logger.error(f"Error fetching mailbox names: {e}", exc_info=True)
        return []

# =========================================================================
# Dashboard API Endpoints - Replace direct Supabase access in frontend
# =========================================================================

@app.get("/api/dashboard/volume")
async def get_volume_data():
    """Get email volume data for the last 7 days"""
    try:
        sb = get_supabase()
        
        # Get data for last 7 days
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=6)).date().isoformat()
        today = datetime.now(timezone.utc).date().isoformat()
        
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.table('daily_email_volume').select('*').gte('date', seven_days_ago).lte('date', today).order('date', desc=False).execute()
        )
        
        # Transform to expected format
        volume_data = []
        for item in result.data or []:
            volume_data.append({
                'date': item['date'],
                'inbound': item.get('inbound', 0),
                'outbound': item.get('outbound', 0)
            })
        
        return volume_data
        
    except Exception as e:
        logger.error(f"Error fetching volume data: {e}", exc_info=True)
        return get_mock_volume_data()

def get_mock_volume_data():
    """Fallback mock data for volume chart"""
    data = []
    for i in range(6, -1, -1):
        date = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
        data.append({
            'date': date,
            'inbound': random.randint(30, 80),
            'outbound': random.randint(15, 45)
        })
    return data

@app.get("/api/dashboard/categories")
async def get_category_data():
    """Get email category distribution"""
    try:
        sb = get_supabase()
        
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.table('email_categories').select('category').execute()
        )
        
        # Count categories (exclude metadata)
        category_counts = {}
        for item in result.data or []:
            category = item.get('category')
            if category and not category.startswith('_meta_'):
                category_counts[category] = category_counts.get(category, 0) + 1
        
        colors = ['#8884d8', '#82ca9d', '#ffc658', '#ff8042', '#0088fe']
        
        # Convert to chart format
        category_data = []
        for idx, (name, value) in enumerate(sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]):
            category_data.append({
                'name': get_category_label(name),
                'value': value,
                'color': colors[idx % len(colors)]
            })
        
        return category_data
        
    except Exception as e:
        logger.error(f"Error fetching category data: {e}", exc_info=True)
        return get_mock_category_data()

def get_mock_category_data():
    """Fallback mock data for category chart"""
    return [
        {'name': 'Promotional', 'value': 45, 'color': '#8884d8'},
        {'name': 'Transactional', 'value': 25, 'color': '#82ca9d'},
        {'name': 'Social', 'value': 15, 'color': '#ffc658'},
        {'name': 'Updates', 'value': 15, 'color': '#ff8042'}
    ]

def get_category_label(category: str) -> str:
    """Helper function to format category labels"""
    labels = {
        'promotional': 'Promotional',
        'transactional': 'Transactional',
        'conversation': 'Conversation',
        'internal': 'Internal',
        'system': 'System',
        'social': 'Social',
        'updates': 'Updates'
    }
    return labels.get(category.lower(), category) if category else 'Unknown'

@app.get("/api/dashboard/recent-emails")
async def get_recent_emails():
    """Get recent emails"""
    try:
        sb = get_supabase()
        
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.table('emails').select("""
                id,
                subject,
                sender_email,
                sender_name,
                sent_date,
                email_categories(category)
            """).order('sent_date', desc=True).limit(5).execute()
        )
        
        recent_emails = []
        for email in result.data or []:
            categories = email.get('email_categories', []) or []
            category = categories[0]['category'] if categories else 'Unknown'
            
            recent_emails.append({
                'id': email['id'],
                'subject': email['subject'],
                'sender': email.get('sender_name') or email['sender_email'],
                'category': get_category_label(category),
                'received': format_relative_time(email['sent_date'])
            })
        
        return recent_emails
        
    except Exception as e:
        logger.error(f"Error fetching recent emails: {e}", exc_info=True)
        return []

def format_relative_time(date_string: str) -> str:
    """Helper function to format relative time"""
    try:
        date = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        diff_minutes = int((now - date).total_seconds() / 60)
        
        if diff_minutes < 60:
            return f"{diff_minutes} minutes ago"
        elif diff_minutes < 24 * 60:
            hours = diff_minutes // 60
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = diff_minutes // (24 * 60)
            return f"{days} day{'s' if days != 1 else ''} ago"
    except Exception:
        return "Unknown time"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)