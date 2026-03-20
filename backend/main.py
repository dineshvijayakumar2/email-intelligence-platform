from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends  # v26 - Fix shutdown not waiting, daemon threads for graceful exit
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import sys
import signal
import atexit
from dotenv import load_dotenv
from supabase import create_client, Client
import asyncio
import json
from datetime import datetime, timedelta, timezone
import random
import logging
from concurrent.futures import ThreadPoolExecutor
from google_auth_oauthlib.flow import Flow

# IMPORTANT: Load environment variables BEFORE importing any modules that use them
python_env = os.getenv('PYTHON_ENV', 'development')
backend_dir = os.path.dirname(__file__)
env_file = os.path.join(backend_dir, f'.env.{python_env}')
if os.path.exists(env_file):
    load_dotenv(dotenv_path=env_file)
else:
    fallback_env = os.path.join(backend_dir, '.env')
    if os.path.exists(fallback_env):
        load_dotenv(dotenv_path=fallback_env)

# Version: 1.2.0 - Email count estimation + folder/tag separation + Redis
# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.processors.email_processor import EmailProcessor
from src.database.redis_client import JobProgressManager, JobQueueManager, RedisClient

# Stage 2: Business Hierarchy Routers
from src.routers.account_managers import router as account_managers_router, init_account_managers_router
from src.routers.clients import router as clients_router, init_clients_router
from src.routers.customers import router as customers_router, init_customers_router
from src.routers.contacts import router as contacts_router, init_contacts_router

# Sprint 2 Phase 5A: Analytics Router
from src.routers.analytics import router as analytics_router, init_analytics_router

# Admin Data View Router
from src.routers.admin import router as admin_router, init_admin_router

# Sprint 3: AI Intelligence Router
from src.routers.ai import router as ai_router, init_ai_router

# Email Rules Intelligence
from src.routers.rules import router as rules_router, init_rules_router

# Quickbase Integration
from src.routers.quickbase import router as quickbase_router, init_quickbase_router

# Stage 2: Error Router
from src.routers.errors import router as errors_router, init_error_router

# Stage 2: Job Error Logger
from src.services.job_error_logger import JobErrorLogger, init_error_logger, get_error_logger

# Stage 2: Gmail LIVE Integration
from src.routers.gmail import router as gmail_router, init_gmail_router
from src.services.gmail_sync_service import get_gmail_sync_service, GmailSyncService

# Stage 2: Outlook LIVE Integration
from src.routers.outlook import router as outlook_router, init_outlook_router
from src.services.outlook_sync_service import get_outlook_sync_service, OutlookSyncService

# Stage 2: Authentication & RBAC
from src.routers.auth import router as auth_router, init_auth_router
from src.dependencies.auth import init_auth_dependencies, require_role, get_current_user, get_accessible_mailbox_ids

# Audit logging
from src.utils.audit import init_audit

# WebSocket for real-time updates
from src.websocket.routes import router as websocket_router
from src.websocket.manager import init_connection_manager, get_connection_manager
from src.websocket.auth import init_websocket_auth

# Configure logging to both file and console
import logging.handlers
import sys

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)

# Custom formatter that handles Unicode on Windows
class SafeFormatter(logging.Formatter):
    """Formatter that replaces emojis with text equivalents on Windows"""
    EMOJI_MAP = {
        '📦': '[PKG]',
        '📊': '[STATS]',
        '📧': '[EMAIL]',
        '🌊': '[STREAM]',
        '🏁': '[DONE]',
        '❌': '[ERROR]',
        '⚠️': '[WARN]',
        '✅': '[OK]',
        '🔄': '[SYNC]',
        '⏸️': '[PAUSE]',
        '▶️': '[PLAY]',
    }

    def format(self, record):
        msg = super().format(record)
        # Only replace emojis on Windows console
        if sys.platform == 'win32':
            for emoji, replacement in self.EMOJI_MAP.items():
                msg = msg.replace(emoji, replacement)
        return msg

# Create formatters
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
file_formatter = logging.Formatter(log_format)
console_formatter = SafeFormatter(log_format)

# Create handlers
file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(log_dir, 'backend.log'),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'  # Ensure UTF-8 for file
)
file_handler.setFormatter(file_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(console_formatter)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

# Reduce logging verbosity for noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
logging.getLogger("googleapiclient.discovery").setLevel(logging.WARNING)

# Log which environment we're running in
logger.info(f"Loading {python_env} environment variables from: {env_file if os.path.exists(env_file) else 'backend/.env'}")
logger.info(f"Running in {python_env} mode")

# Persistent download directory - uses Railway volume in production, temp dir in development
# In Railway, this maps to a persistent volume that survives redeployments
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', '/data/downloads' if python_env == 'production' else None)
VOLUME_MOUNTED = False  # Track if volume is properly mounted

def check_volume_status():
    """Check if the download directory is a properly mounted volume."""
    global VOLUME_MOUNTED

    if not DOWNLOAD_DIR:
        logger.info("Using temporary directory for downloads (files will be lost on restart)")
        return False

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Check if it's a mount point (Linux/Unix) or has enough space
    try:
        # On Linux, check if it's a mount point
        if hasattr(os.path, 'ismount') and os.path.ismount(DOWNLOAD_DIR):
            VOLUME_MOUNTED = True
            logger.info(f"✅ VOLUME MOUNTED: {DOWNLOAD_DIR} is a mounted volume")
        else:
            # Check disk space - if /data exists and has space, assume volume is mounted
            import shutil
            total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
            free_gb = free / (1024**3)
            total_gb = total / (1024**3)

            # Railway volumes typically show as separate mount with their own space
            # If /data/downloads exists and has reasonable space, consider it mounted
            if DOWNLOAD_DIR.startswith('/data') and total_gb > 1:
                VOLUME_MOUNTED = True
                logger.info(f"✅ VOLUME DETECTED: {DOWNLOAD_DIR} ({free_gb:.1f}GB free of {total_gb:.1f}GB)")
            else:
                logger.warning(f"⚠️ VOLUME NOT MOUNTED: {DOWNLOAD_DIR} appears to be on root filesystem")
                logger.warning(f"   Disk space: {free_gb:.1f}GB free of {total_gb:.1f}GB")
                logger.warning("   Downloads may be lost on redeployment!")
                logger.warning("   Please ensure Railway volume is attached at /data/downloads")

        # Write a marker file to track volume persistence
        marker_file = os.path.join(DOWNLOAD_DIR, '.volume_marker')
        marker_exists = os.path.exists(marker_file)

        if marker_exists:
            with open(marker_file, 'r') as f:
                previous_boot = f.read().strip()
            logger.info(f"   Volume marker found from previous boot: {previous_boot}")

        # Update marker with current boot time
        with open(marker_file, 'w') as f:
            f.write(datetime.now(timezone.utc).isoformat())

        return VOLUME_MOUNTED

    except Exception as e:
        logger.error(f"Error checking volume status: {e}")
        return False

# Check volume on startup
check_volume_status()

app = FastAPI(title="Email Intelligence API", version="1.0.0")

# Configure CORS for frontend access
# Parse allowed origins from environment variable (comma-separated)
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "*")

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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

logger.info(f"CORS middleware configured - Origins: {allowed_origins}, Credentials: {allow_credentials}")

# Global OPTIONS handler to fix CORS preflight issues
@app.options("/{path:path}")
async def options_handler(path: str):
    """Global OPTIONS handler for all CORS preflight requests"""
    return {"status": "ok"}

logger.info("Global OPTIONS handler configured for all routes")

# Configure thread pool for concurrent job processing
# Allows up to 20 concurrent background jobs (file processing is I/O bound)
# This ensures multiple mailboxes can be processed simultaneously
# Note: We use regular ThreadPoolExecutor + proper cancellation via cancel_all_downloads()
# and port cleanup in start scripts instead of daemon threads (can't set daemon on active threads)
executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="email_processor")


def force_shutdown(signum=None, frame=None):
    """Force shutdown handler for SIGTERM/SIGINT"""
    logger.info(f"=== RECEIVED SIGNAL {signum}, forcing shutdown ===")

    # Cancel all parallel downloads
    try:
        from src.storage.parallel_downloader import cancel_all_downloads
        cancel_all_downloads()
    except Exception as e:
        logger.warning(f"Error cancelling downloads during signal handler: {e}")

    # Shutdown executor
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except Exception as e:
        logger.warning(f"Error shutting down executor: {e}")

    logger.info("Shutdown complete, exiting...")
    # Use os._exit to force immediate exit without waiting for threads
    os._exit(0)


# Register signal handlers for graceful shutdown
try:
    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, force_shutdown)
        signal.signal(signal.SIGINT, force_shutdown)
        logger.info("Signal handlers registered for graceful shutdown (Unix)")
    else:
        # On Windows, register atexit handler as fallback
        def windows_cleanup():
            logger.info("=== ATEXIT CLEANUP (Windows) ===")
            try:
                from src.storage.parallel_downloader import cancel_all_downloads
                cancel_all_downloads()
            except Exception as e:
                logger.warning(f"Error in atexit cleanup: {e}")
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

        atexit.register(windows_cleanup)
        logger.info("Atexit handler registered for graceful shutdown (Windows)")
except Exception as e:
    logger.warning(f"Could not register shutdown handlers: {e}")


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

    from src.utils.progress_tracker import initialize_progress_managers, register_job_mailbox, unregister_job
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
    logger.info("=== SERVER SHUTDOWN INITIATED ===")

    # Stop Gmail sync service
    logger.info("Step 0: Stopping Gmail sync service...")
    try:
        if _gmail_sync_service:
            await _gmail_sync_service.stop()
    except Exception as e:
        logger.warning(f"Error stopping Gmail sync service: {e}")

    # Stop Outlook sync service
    logger.info("Step 0.1: Stopping Outlook sync service...")
    try:
        if _outlook_sync_service:
            await _outlook_sync_service.stop()
    except Exception as e:
        logger.warning(f"Error stopping Outlook sync service: {e}")

    # Cancel any active parallel downloads first
    logger.info("Step 1: Cancelling any active parallel downloads...")
    try:
        from src.storage.parallel_downloader import cancel_all_downloads
        cancel_all_downloads()
    except Exception as e:
        logger.warning(f"Error cancelling downloads: {e}")

    logger.info("Step 2: Syncing Redis progress to database...")
    sync_redis_to_database()

    logger.info("Step 3: Shutting down thread pool executor...")
    try:
        # Don't wait for threads - daemon threads will be killed on exit
        # cancel_futures requires Python 3.9+
        import sys
        if sys.version_info >= (3, 9):
            executor.shutdown(wait=False, cancel_futures=True)
        else:
            executor.shutdown(wait=False)
    except Exception as e:
        logger.warning(f"Error during executor shutdown: {e}")

    logger.info("=== SERVER SHUTDOWN COMPLETE ===")

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

    Note: WebSocket broadcasts are handled by the shared progress_tracker module.
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

        # Create Supabase client
        # Note: Timeout configuration for batch operations is handled through:
        # 1. Reduced batch size (500 instead of 5000) in database/operations.py
        # 2. Exponential backoff retry logic with 2s, 4s, 8s delays
        # Supabase v2.0.2 doesn't expose timeout configuration in client options
        _supabase_client = create_client(
            supabase_url,
            supabase_key
        )
        logger.info("Supabase client initialized successfully")

        # Initialize error logger with Supabase client
        init_error_logger(_supabase_client)
        logger.info("Job error logger initialized")

    return _supabase_client

# For backwards compatibility
supabase = None

# =========================================================================
# Stage 2: Business Hierarchy API Routers
# =========================================================================

# Initialize routers with Supabase client
def initialize_business_hierarchy_routers():
    """Initialize all business hierarchy routers with Supabase client"""
    sb = get_supabase()
    init_account_managers_router(sb)
    init_clients_router(sb)
    init_customers_router(sb)
    init_contacts_router(sb)
    init_analytics_router(sb)  # Sprint 2 Phase 5A
    init_admin_router(sb)  # Admin Data View
    init_ai_router(sb)  # Sprint 3 AI Intelligence
    init_rules_router(sb)  # Email Rules Intelligence
    init_quickbase_router(sb)  # Quickbase Integration
    # Initialize error router with Supabase client and job error logger
    error_logger = get_error_logger()
    init_error_router(
        error_tracker=None,  # Redis error tracker - deprecated in favor of job_errors table
        db_error_tracker=None,  # Old DB error tracker - deprecated
        supabase_client=sb,
        redis_client=None,
        job_error_logger=error_logger
    )
    # Initialize auth router and dependencies (Stage 2 RBAC)
    init_auth_dependencies(sb)
    init_auth_router(sb)
    init_audit(sb)  # Audit logging
    logger.info("Business hierarchy routers initialized (including auth, audit)")

# Register routers with API prefix
app.include_router(auth_router, prefix="/api")  # Auth router first for login/me endpoints
app.include_router(account_managers_router, prefix="/api")
app.include_router(clients_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")
app.include_router(analytics_router, prefix="/api/v1")  # Sprint 2 Phase 5A
app.include_router(admin_router, prefix="/api/v1")  # Admin Data View
app.include_router(ai_router, prefix="/api/v1")  # Sprint 3 AI Intelligence
app.include_router(rules_router, prefix="/api/v1")  # Email Rules Intelligence
app.include_router(quickbase_router, prefix="/api/v1")  # Quickbase Integration
app.include_router(errors_router, prefix="/api")
app.include_router(gmail_router, prefix="/api")
app.include_router(outlook_router, prefix="/api")

# WebSocket router (no /api prefix - WebSocket uses /ws directly)
app.include_router(websocket_router)

# Sync service instances (initialized in startup event)
_gmail_sync_service: GmailSyncService = None
_outlook_sync_service: OutlookSyncService = None

# Initialize routers (lazy init when first request comes in)
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global _gmail_sync_service, _outlook_sync_service

    # Sync prompt JSON files → DB (S4.0: keeps JSON and DB always in sync)
    try:
        from src.services.ai_prompt_loader import sync_from_json_files
        sync_from_json_files(get_supabase())
    except Exception as e:
        logger.warning(f"Prompt JSON sync failed (non-critical): {e}")

    try:
        initialize_business_hierarchy_routers()
    except Exception as e:
        logger.warning(f"Failed to initialize business hierarchy routers: {e}")
        # Don't fail startup - routers will init on first use

    # Initialize WebSocket infrastructure
    try:
        init_connection_manager()
        init_websocket_auth(get_supabase())
        logger.info("WebSocket infrastructure initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize WebSocket: {e}")
        # Don't fail startup - WebSocket is optional enhancement

    # Initialize Gmail sync service (Stage 2)
    try:
        _gmail_sync_service = get_gmail_sync_service(get_supabase())
        init_gmail_router(get_supabase(), _gmail_sync_service)

        # Start the 15-minute sync loop
        await _gmail_sync_service.start()
        logger.info("Gmail sync service started successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Gmail sync service: {e}")
        # Don't fail startup - Gmail sync is optional

    # Initialize Outlook sync service (Stage 2)
    try:
        _outlook_sync_service = get_outlook_sync_service(get_supabase())
        init_outlook_router(get_supabase(), _outlook_sync_service)

        # Start the 15-minute sync loop
        await _outlook_sync_service.start()
        logger.info("Outlook sync service started successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Outlook sync service: {e}")
        # Don't fail startup - Outlook sync is optional

    # Clean up orphaned jobs from previous server restart
    try:
        await cleanup_orphaned_jobs()
    except Exception as e:
        logger.warning(f"Failed to cleanup orphaned jobs: {e}")


async def cleanup_orphaned_jobs():
    """
    Mark any jobs that were running/pending/downloading when server restarted as 'interrupted'.
    This prevents the frontend from spinning forever waiting for a dead job.
    """
    try:
        sb = get_supabase()

        # Find jobs that are stuck in running/pending/downloading status
        result = sb.table('processing_jobs').select('id, status, mailbox_id').in_(
            'status', ['running', 'pending', 'downloading']
        ).execute()

        orphaned_jobs = result.data or []

        if orphaned_jobs:
            logger.info(f"Found {len(orphaned_jobs)} orphaned jobs from previous session, marking as interrupted")

            for job in orphaned_jobs:
                job_id = job['id']
                try:
                    sb.table('processing_jobs').update({
                        'status': 'interrupted',
                        'error_log': 'Job was interrupted by server restart. You can restart this job.',
                        'completed_at': datetime.now(timezone.utc).isoformat()
                    }).eq('id', job_id).execute()

                    logger.info(f"Marked job {job_id} as interrupted")
                except Exception as e:
                    logger.warning(f"Failed to update job {job_id}: {e}")

            logger.info(f"Cleanup complete: {len(orphaned_jobs)} jobs marked as interrupted")
        else:
            logger.info("No orphaned jobs found during startup")

    except Exception as e:
        logger.error(f"Error during orphaned job cleanup: {e}")

# Pydantic models
class MailboxConfig(BaseModel):
    name: str
    email_address: Optional[str] = None
    mailbox_type: str
    is_active: bool = True
    connection_config: Optional[Dict[str, Any]] = {}
    client_id: Optional[str] = None
    user_id: Optional[str] = None

class ProcessingJobConfig(BaseModel):
    """
    Configuration for email processing jobs.

    Processing Limits:
    - max_emails: Maximum number of emails to process (None = all emails in file)
    - batch_size: Database batch insert size (default 250, auto-splits on timeout for reliability)

    Date Filters (for processing only emails within a date range):
    - start_date: Process emails sent on or after this date (ISO format: YYYY-MM-DD)
    - end_date: Process emails sent on or before this date (ISO format: YYYY-MM-DD)

    Download Options (for Google Drive files):
    - download_first: Download file completely before processing (faster for large files)
    - download_threads: Number of parallel threads for download (default: 8)

    Example: To process only emails from 2024:
        start_date: "2024-01-01"
        end_date: "2024-12-31"
    """
    job_type: str
    # Processing limits
    max_emails: Optional[int] = None  # Maximum emails to process (None = all)
    batch_size: Optional[int] = 250  # Optimal batch size for Supabase (auto-splits on timeout)
    # Date-based filtering
    start_date: Optional[str] = None  # ISO date: YYYY-MM-DD (process emails from this date)
    end_date: Optional[str] = None    # ISO date: YYYY-MM-DD (process emails until this date)
    # Feature flags
    enable_categorization: Optional[bool] = True
    enable_enrichment: Optional[bool] = False
    # Download options for Google Drive files
    download_first: Optional[bool] = True  # Download file before processing (3-5x faster for large files)
    download_threads: Optional[int] = 8     # Number of parallel download threads
    keep_downloaded_file: Optional[bool] = True  # Keep file after processing for re-use
    use_cached_file: Optional[bool] = True  # Use cached file if available (skip download)
    # Deprecated field (use max_emails instead)
    total_records: Optional[int] = None  # Kept for backwards compatibility
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
    recipients: Optional[List[Dict[str, str]]] = None
    cc_list: Optional[List[Dict[str, str]]] = None
    bcc_list: Optional[List[Dict[str, str]]] = None
    sent_date: str
    received_date: Optional[str] = None
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
    attachments: Optional[List[Dict[str, Any]]] = None
    provider_web_link: Optional[str] = None
    mailbox_type: Optional[str] = None

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
        logger.info(f"🔐 Starting OAuth2 token exchange for user: {request.user_id}")
        
        # Validate required environment variables
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error("❌ Missing Google OAuth credentials")
            raise HTTPException(status_code=500, detail="Server configuration error: Missing Google credentials")

        # For popup-based OAuth flow (frontend uses ux_mode: 'popup'), Google uses "postmessage"
        # This works for both local development and Railway deployment
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI_OVERRIDE", "postmessage")
        logger.info(f"🔧 Using redirect URI: {redirect_uri}")

        # Create OAuth2 flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=[
                'https://www.googleapis.com/auth/drive.readonly',
                'https://www.googleapis.com/auth/userinfo.email',
                'openid',
                'https://www.googleapis.com/auth/userinfo.profile'
            ]
        )

        flow.redirect_uri = redirect_uri
        
        logger.info(f"🔄 Exchanging authorization code...")
        
        # Exchange authorization code for tokens
        flow.fetch_token(code=request.code)
        
        logger.info(f"✅ Token exchange successful, storing tokens...")
        
        # Store tokens securely in database
        access_token = flow.credentials.token
        refresh_token = flow.credentials.refresh_token
        
        if not access_token:
            raise HTTPException(status_code=500, detail="No access token received from Google")
            
        success = store_user_google_tokens(
            user_id=request.user_id,
            access_token=access_token,
            refresh_token=refresh_token or ""
        )
        
        if not success:
            logger.error(f"❌ Failed to store tokens for user: {request.user_id}")
            raise HTTPException(status_code=500, detail="Failed to store Google Drive tokens")
        
        logger.info(f"✅ Google Drive connection successful for user: {request.user_id}")
        
        return {
            "status": "success",
            "message": "Google Drive connected successfully",
            "user_id": request.user_id
        }
        
    except Exception as e:
        logger.error(f"❌ OAuth2 token exchange failed for user {request.user_id}: {e}")
        logger.error(f"❌ Exception type: {type(e).__name__}")
        logger.error(f"❌ Exception details: {str(e)}")
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
@app.get("/api/health")
async def health_check():
    """Health check with volume status for Railway."""
    import shutil

    volume_info = {
        "mounted": VOLUME_MOUNTED,
        "path": DOWNLOAD_DIR
    }

    if DOWNLOAD_DIR and os.path.exists(DOWNLOAD_DIR):
        try:
            total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
            volume_info["total_gb"] = round(total / (1024**3), 2)
            volume_info["used_gb"] = round(used / (1024**3), 2)
            volume_info["free_gb"] = round(free / (1024**3), 2)

            # Count cached files
            cached_files = [f for f in os.listdir(DOWNLOAD_DIR) if not f.startswith('.')]
            volume_info["cached_files"] = len(cached_files)
        except Exception:
            pass

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "volume": volume_info
    }

# Mailbox endpoints
@app.get("/api/mailboxes")
async def get_mailboxes(accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)):
    """Get mailboxes accessible to current user with email counts - Filtered by role"""
    try:
        sb = get_supabase()

        # If user has no accessible mailboxes, return empty list
        if not accessible_mailbox_ids:
            logger.warning("[Mailboxes API] No accessible mailboxes for user")
            return []

        # Get only accessible mailboxes
        mailboxes_result = sb.table('mailboxes').select('*').in_('id', accessible_mailbox_ids).order('created_at', desc=True).execute()

        if not mailboxes_result.data:
            return []

        # Try to get email counts via RPC (most efficient)
        count_map = {}
        try:
            counts_result = sb.rpc('get_email_counts_by_mailbox', {}).execute()
            if counts_result.data:
                for row in counts_result.data:
                    # Only include counts for accessible mailboxes
                    if row['mailbox_id'] in accessible_mailbox_ids:
                        count_map[row['mailbox_id']] = row['email_count']
        except Exception as rpc_error:
            logger.debug(f"RPC not available, using fallback: {rpc_error}")
            # Fallback: get counts individually (simple sync approach)
            for mailbox in mailboxes_result.data:
                try:
                    count_result = sb.table('emails').select('id', count='exact').eq('mailbox_id', mailbox['id']).limit(1).execute()
                    count_map[mailbox['id']] = count_result.count or 0
                except Exception as count_error:
                    logger.debug(f"Count failed for {mailbox['id']}: {count_error}")
                    count_map[mailbox['id']] = 0

        # Merge mailboxes with counts
        mailboxes_with_counts = []
        for mailbox in mailboxes_result.data:
            mailboxes_with_counts.append({
                **mailbox,
                'total_emails': count_map.get(mailbox['id'], 0)
            })

        return mailboxes_with_counts

    except Exception as e:
        logger.error(f"Error fetching mailboxes: {e}", exc_info=True)
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
async def create_mailbox(mailbox_data: MailboxConfig, current_user: dict = Depends(get_current_user)):
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
            "total_emails": 0,
            "client_id": mailbox_data.client_id,
            "user_id": mailbox_data.user_id,
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
            from src.utils.audit import audit_from_user
            audit_from_user(current_user, "mailbox_create", "mailbox", resource_id=mailbox_id, details={"name": mailbox_data.name, "type": mailbox_data.mailbox_type})
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

        # Fetch current mailbox to validate email_address changes
        current_mailbox = sb.table('mailboxes').select('*').eq('id', mailbox_id).single().execute()
        if not current_mailbox.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        # Validate email_address if being updated
        if mailbox_data.email_address:
            current_config = current_mailbox.data.get('connection_config') or {}
            gmail_email = current_config.get('gmail_email')
            outlook_email = current_config.get('outlook_email')

            # If there's a Gmail connection, email must match
            if gmail_email and mailbox_data.email_address.lower() != gmail_email.lower():
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot change email address to {mailbox_data.email_address}. This mailbox is connected to Gmail account {gmail_email}. Please disconnect Gmail first or use the connected email address."
                )

            # If there's an Outlook connection, email must match
            if outlook_email and mailbox_data.email_address.lower() != outlook_email.lower():
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot change email address to {mailbox_data.email_address}. This mailbox is connected to Outlook account {outlook_email}. Please disconnect Outlook first or use the connected email address."
                )

        # Prepare update data
        update_data = {
            "name": mailbox_data.name,
            "mailbox_type": mailbox_data.mailbox_type,
            "is_active": mailbox_data.is_active,
            "connection_config": mailbox_data.connection_config,
            "client_id": mailbox_data.client_id,
            "user_id": mailbox_data.user_id,
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
async def delete_mailbox(mailbox_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a mailbox and all related data.

    Explicitly deletes related records first to avoid Supabase statement
    timeout on large cascade deletes.
    """
    try:
        sb = get_supabase()

        # Check if mailbox exists
        check_result = sb.table('mailboxes').select('id').eq('id', mailbox_id).execute()
        if not check_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        # Delete related records explicitly to avoid cascade timeout.
        # Order: AI layer → Sprint 2 analytics → emails → folders → mailbox
        related_tables = [
            "ai_daily_digests",
            "ai_email_intelligence",
            "ai_business_entities",
            "ai_usage_log",
            "unified_email_rules",
            "thread_status",
            # email_response_metrics has no mailbox_id — cascades via email_id
        ]
        for table in related_tables:
            try:
                sb.table(table).delete().eq("mailbox_id", mailbox_id).execute()
            except Exception as e:
                logger.warning(f"Failed to clean {table} for mailbox {mailbox_id}: {e}")

        # Delete emails in batches (can be large)
        deleted_total = 0
        while True:
            batch = sb.table("emails").select("id").eq("mailbox_id", mailbox_id).limit(500).execute()
            ids = [r["id"] for r in (batch.data or [])]
            if not ids:
                break
            sb.table("emails").delete().in_("id", ids).execute()
            deleted_total += len(ids)
            logger.info(f"Deleted {deleted_total} emails for mailbox {mailbox_id}...")

        # Clean up folders and processing jobs
        for table in ["folders", "processing_jobs"]:
            try:
                sb.table(table).delete().eq("mailbox_id", mailbox_id).execute()
            except Exception as e:
                logger.warning(f"Failed to clean {table} for mailbox {mailbox_id}: {e}")

        # Finally delete the mailbox itself
        sb.table('mailboxes').delete().eq('id', mailbox_id).execute()

        logger.info(f"Mailbox {mailbox_id} deleted with {deleted_total} emails")
        from src.utils.audit import audit_from_user
        audit_from_user(current_user, "mailbox_delete", "mailbox", resource_id=mailbox_id, details={"emails_deleted": deleted_total})
        return {"message": "Mailbox deleted successfully", "emails_deleted": deleted_total}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting mailbox {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete mailbox: {str(e)}")

@app.patch("/api/mailboxes/{mailbox_id}/assign-client")
async def assign_mailbox_to_client(
    mailbox_id: str,
    assignment: dict,
    current_user: dict = Depends(require_role('admin'))
):
    """Assign a mailbox to a client (admin only)"""
    try:
        sb = get_supabase()

        client_id = assignment.get('client_id')

        # Update mailbox with client_id
        result = sb.table('mailboxes').update({
            'client_id': client_id
        }).eq('id', mailbox_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        return {
            "success": True,
            "message": f"Mailbox assigned to client successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning mailbox to client: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to assign mailbox: {str(e)}")

@app.patch("/api/mailboxes/{mailbox_id}/assign-user")
async def assign_mailbox_to_user(
    mailbox_id: str,
    assignment: dict,
    current_user: dict = Depends(require_role('admin'))
):
    """Assign a mailbox to an account manager (admin only)"""
    try:
        sb = get_supabase()

        user_id = assignment.get('user_id')

        # Update mailbox with user_id
        result = sb.table('mailboxes').update({
            'user_id': user_id
        }).eq('id', mailbox_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        return {
            "success": True,
            "message": f"Mailbox assigned to account manager successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning mailbox to user: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to assign mailbox: {str(e)}")

@app.post("/api/mailboxes/{mailbox_id}/resync-metadata")
async def resync_metadata(mailbox_id: str, background_tasks: BackgroundTasks):
    """
    Re-extract emails from mail provider to backfill attachment names
    and provider web links for existing emails.
    """
    try:
        sb = get_supabase()
        mb_result = sb.table('mailboxes').select(
            'id, mailbox_type, connection_config'
        ).eq('id', mailbox_id).single().execute()

        if not mb_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        mailbox = mb_result.data
        if mailbox.get('mailbox_type', '') not in ('outlook_live', 'outlook'):
            raise HTTPException(status_code=400, detail="Only Outlook mailboxes support metadata re-sync")

        # Create tracking job
        job_data = {
            "job_type": "reprocessing",
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": 0,
            "processed_records": 0,
            "failed_records": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        result = sb.table('processing_jobs').insert(job_data).execute()
        job_id = result.data[0]['id']

        background_tasks.add_task(run_reprocessing, job_id, mailbox)
        return {"message": "Metadata re-sync started", "job_id": job_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start metadata re-sync for {mailbox_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

@app.get("/api/mailboxes/{mailbox_id}/cached-download")
async def check_cached_download(mailbox_id: str):
    """
    Check if there's a cached download available for this mailbox's Google Drive file.
    Returns cache info if available, or null if no cache exists.
    """
    try:
        sb = get_supabase()

        # Get mailbox connection config
        mailbox_result = sb.table('mailboxes').select('connection_config').eq('id', mailbox_id).single().execute()
        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        connection_config = mailbox_result.data.get('connection_config', {})

        # Only relevant for Google Drive files
        if connection_config.get('file_source') != 'google_drive':
            return {"cached": False, "reason": "Not a Google Drive file"}

        google_drive_file_id = connection_config.get('google_drive_file_id')
        if not google_drive_file_id:
            return {"cached": False, "reason": "No Google Drive file ID"}

        # Check for cached download
        cache_result = sb.table('downloaded_files').select('*').eq(
            'google_drive_file_id', google_drive_file_id
        ).eq('is_valid', True).execute()

        if not cache_result.data:
            return {"cached": False, "reason": "No cached download found"}

        cached = cache_result.data[0]

        # Check if file still exists (for local storage)
        import os
        if cached.get('storage_type') == 'local':
            if not os.path.exists(cached.get('storage_path', '')):
                # Mark as invalid
                sb.table('downloaded_files').update({'is_valid': False}).eq('id', cached['id']).execute()
                return {"cached": False, "reason": "Cached file no longer exists on disk"}

        # Calculate age
        from datetime import datetime, timezone
        downloaded_at = datetime.fromisoformat(cached['downloaded_at'].replace('Z', '+00:00'))
        age_hours = (datetime.now(timezone.utc) - downloaded_at).total_seconds() / 3600

        # Format file size
        file_size = cached.get('file_size', 0)
        if file_size >= 1024 * 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024 * 1024):.2f} GB"
        elif file_size >= 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{file_size / 1024:.1f} KB"

        return {
            "cached": True,
            "cache_id": cached['id'],
            "file_name": cached['file_name'],
            "file_size": file_size,
            "file_size_formatted": size_str,
            "storage_type": cached['storage_type'],
            "storage_path": cached['storage_path'],
            "downloaded_at": cached['downloaded_at'],
            "age_hours": round(age_hours, 1),
            "age_formatted": f"{int(age_hours)} hours ago" if age_hours < 24 else f"{int(age_hours / 24)} days ago",
            "last_used_at": cached.get('last_used_at')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check cached download: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/cached-downloads/{cache_id}")
async def invalidate_cached_download(cache_id: str):
    """Invalidate (mark as invalid) a cached download."""
    try:
        sb = get_supabase()
        result = sb.table('downloaded_files').update({'is_valid': False}).eq('id', cache_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Cache entry not found")

        return {"success": True, "message": "Cache invalidated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

        # Create processing job with filter parameters for audit trail
        job_data = {
            "job_type": config.job_type,
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": config.total_records,
            "processed_records": 0,
            "failed_records": 0,
            "filtered_records": 0,  # Track emails skipped by date filter
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
            "error_log": [],
            # Stage 2: Store date filter parameters for visibility/audit
            "filter_start_date": config.start_date if config.start_date else None,
            "filter_end_date": config.end_date if config.end_date else None
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

    Note: Gmail/Outlook LIVE jobs are handled by their own background tasks
    (_run_date_range_fetch in gmail.py/outlook.py) and should skip this function.
    """

    downloaded_file_path = None  # Track downloaded file for cleanup
    cache_entry_id = None  # Track cache entry for updating last_used_at
    google_drive_file_id = None  # Track for cache registration

    try:
        logger.info(f"Starting REAL email processing for job {job_id}")

        # Handle Gmail/Outlook LIVE jobs - trigger their sync services instead
        if config.mailbox_type in ['gmail', 'outlook_live']:
            logger.info(f"Job {job_id} is for {config.mailbox_type} LIVE mailbox - triggering sync service")

            # Update job status to running
            await update_job_status(job_id, "running", {
                "started_at": datetime.now(timezone.utc).isoformat()
            })

            try:
                if config.mailbox_type == 'outlook_live' and _outlook_sync_service:
                    # Trigger Outlook sync for this mailbox
                    await _outlook_sync_service.trigger_mailbox_sync(config.mailbox_id)
                    await update_job_status(job_id, "completed", {
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "error_log": ["Outlook LIVE sync triggered successfully. Emails will sync in background."]
                    })
                elif config.mailbox_type == 'gmail' and _gmail_sync_service:
                    # Trigger Gmail sync for this mailbox
                    await _gmail_sync_service.trigger_mailbox_sync(config.mailbox_id)
                    await update_job_status(job_id, "completed", {
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "error_log": ["Gmail LIVE sync triggered successfully. Emails will sync in background."]
                    })
                else:
                    await update_job_status(job_id, "failed", {
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "error_log": [f"{config.mailbox_type} sync service not available. Please check server configuration."]
                    })
            except Exception as sync_error:
                logger.error(f"Failed to trigger {config.mailbox_type} sync: {sync_error}")
                await update_job_status(job_id, "failed", {
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "error_log": [f"Failed to trigger sync: {str(sync_error)}"]
                })
            return

        # Register job-mailbox mapping for WebSocket broadcasts
        try:
            register_job_mailbox(job_id, config.mailbox_id)
        except Exception:
            pass  # Non-critical

        # Immediately update status to 'running' so user sees it's active
        await update_job_status(job_id, "running", {
            "started_at": datetime.now(timezone.utc).isoformat()
        })

        # Check if parallel download is requested for Google Drive files
        connection_config = config.connection_config.copy() if config.connection_config else {}

        if (config.download_first and
            connection_config.get('file_source') == 'google_drive' and
            connection_config.get('google_drive_file_id')):

            google_drive_file_id = connection_config.get('google_drive_file_id')
            file_name = connection_config.get('google_drive_file_name', 'download')

            # Check for cached download if use_cached_file is enabled (default: True)
            use_cached = config.use_cached_file if config.use_cached_file is not None else True

            if use_cached:
                logger.info(f"Checking for cached download of {google_drive_file_id}")
                sb = get_supabase()
                cache_result = sb.table('downloaded_files').select('*').eq(
                    'google_drive_file_id', google_drive_file_id
                ).eq('is_valid', True).execute()

                if cache_result.data:
                    cached = cache_result.data[0]
                    cached_path = cached.get('storage_path', '')

                    # For local storage, verify file still exists
                    if cached.get('storage_type') == 'local' and os.path.exists(cached_path):
                        logger.info(f"Using cached download: {cached_path}")

                        # Update last_used_at
                        cache_entry_id = cached['id']
                        sb.table('downloaded_files').update({
                            'last_used_at': datetime.now(timezone.utc).isoformat(),
                            'last_job_id': job_id
                        }).eq('id', cache_entry_id).execute()

                        # Use cached file instead of downloading
                        downloaded_file_path = cached_path
                        connection_config['file_source'] = 'local'
                        connection_config['file_path'] = cached_path
                        connection_config.pop('google_drive_file_id', None)
                        connection_config.pop('google_drive_file_name', None)

                        # Update job status to indicate cache was used
                        if progress_manager:
                            progress_manager.update_progress(
                                job_id, 0, 0,
                                status='running',
                                download_percent=100,
                                using_cache=True
                            )
                    else:
                        # Cached file doesn't exist - mark as invalid
                        logger.warning(f"Cached file no longer exists: {cached_path}")
                        sb.table('downloaded_files').update({'is_valid': False}).eq('id', cached['id']).execute()

            # If no cached file was found/used, proceed with download
            if not downloaded_file_path:
                logger.info(f"Parallel download requested for job {job_id} with {config.download_threads} threads")

                # Import parallel downloader
                from src.storage.parallel_downloader import ParallelDownloader

                # Get access token from stored credentials and refresh if needed
                user_id = connection_config.get('user_id', 'default')
                tokens_result = get_supabase().table('user_integrations').select(
                    'access_token,refresh_token'
                ).eq('user_id', user_id).eq('provider', 'google_drive').execute()

                if not tokens_result.data:
                    raise Exception("No Google Drive credentials found. Please re-authenticate.")

                access_token = tokens_result.data[0].get('access_token')
                refresh_token = tokens_result.data[0].get('refresh_token')

                if not access_token:
                    raise Exception("Invalid Google Drive access token")

                # Refresh the access token to ensure it's valid
                if refresh_token:
                    try:
                        from google.oauth2.credentials import Credentials
                        from google.auth.transport.requests import Request

                        credentials = Credentials(
                            token=access_token,
                            refresh_token=refresh_token,
                            token_uri="https://oauth2.googleapis.com/token",
                            client_id=os.getenv("GOOGLE_CLIENT_ID"),
                            client_secret=os.getenv("GOOGLE_CLIENT_SECRET")
                        )

                        # Force refresh the token
                        credentials.refresh(Request())
                        access_token = credentials.token

                        # Store the new access token
                        update_user_access_token(user_id, access_token)
                        logger.info(f"Refreshed Google Drive access token for parallel download")
                    except Exception as refresh_error:
                        logger.warning(f"Token refresh failed, using existing token: {refresh_error}")

                # Progress callback to update Redis
                def download_progress_callback(downloaded: int, total: int, speed_mbps: float):
                    if progress_manager and total > 0:
                        percent = int(downloaded / total * 100)
                        # Store download progress in Redis (using negative values to indicate download phase)
                        progress_manager.update_progress(
                            job_id, 0, 0,
                            status='downloading',
                            download_percent=percent,
                            download_speed_mbps=round(speed_mbps, 1)
                        )

                # Perform parallel download with error logging
                logger.info(f"Starting parallel download: {file_name} ({google_drive_file_id})")
                error_logger = get_error_logger()
                downloader = ParallelDownloader(
                    access_token=access_token,
                    num_threads=config.download_threads or 8,
                    progress_callback=download_progress_callback,
                    job_id=job_id,
                    mailbox_id=str(config.mailbox_id) if config.mailbox_id else None,
                    error_logger=error_logger
                )

                # Run download in thread pool - use persistent directory if configured
                loop = asyncio.get_event_loop()
                downloaded_file_path = await loop.run_in_executor(
                    executor,
                    lambda: downloader.download(google_drive_file_id, file_name, output_dir=DOWNLOAD_DIR)
                )

                if not downloaded_file_path:
                    raise Exception("Parallel download failed")

                logger.info(f"Parallel download complete: {downloaded_file_path}")

                # Register downloaded file in cache for future reuse
                keep_file = config.keep_downloaded_file if config.keep_downloaded_file is not None else True
                if keep_file:
                    try:
                        file_size = os.path.getsize(downloaded_file_path) if os.path.exists(downloaded_file_path) else 0
                        sb = get_supabase()
                        cache_insert = sb.table('downloaded_files').upsert({
                            'google_drive_file_id': google_drive_file_id,
                            'file_name': file_name,
                            'file_size': file_size,
                            'storage_type': 'local',
                            'storage_path': downloaded_file_path,
                            'mailbox_id': str(config.mailbox_id) if config.mailbox_id else None,
                            'last_job_id': job_id,
                            'downloaded_at': datetime.now(timezone.utc).isoformat(),
                            'last_used_at': datetime.now(timezone.utc).isoformat(),
                            'is_valid': True
                        }, on_conflict='google_drive_file_id').execute()

                        if cache_insert.data:
                            cache_entry_id = cache_insert.data[0]['id']
                            logger.info(f"Registered download in cache: {cache_entry_id}")
                    except Exception as cache_error:
                        logger.warning(f"Failed to register download in cache: {cache_error}")

                # Update connection config to use local file instead of streaming
                connection_config['file_source'] = 'local'
                connection_config['file_path'] = downloaded_file_path
                # Remove Google Drive specific fields
                connection_config.pop('google_drive_file_id', None)
                connection_config.pop('google_drive_file_name', None)

            # Download complete (either from cache or fresh download) - update status to 'running'
            logger.info(f"Download phase complete for job {job_id}, transitioning to processing phase")

            # Update database status to 'running'
            await update_job_status(job_id, "running", {})

            # Update Redis to clear download state and show processing phase
            if progress_manager:
                progress_manager.update_progress(
                    job_id, 0, 0,
                    status='running',
                    download_percent=100,  # Keep at 100 to show download completed
                    download_complete=True  # Flag to indicate download phase is done
                )

        # Initialize processor with actual configuration (may be modified for local file)
        error_logger = get_error_logger()
        processor = EmailProcessor(
            mailbox_id=config.mailbox_id,
            connection_config=connection_config,
            error_logger=error_logger
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

        # Determine max_emails: prefer new max_emails field, fallback to deprecated total_records
        effective_max_emails = config.max_emails or config.total_records  # None means process all

        # Parse date filters
        date_filter = None
        if config.start_date or config.end_date:
            date_filter = {}
            if config.start_date:
                try:
                    date_filter['start_date'] = datetime.fromisoformat(config.start_date).replace(tzinfo=timezone.utc)
                    logger.info(f"Date filter: start_date = {config.start_date}")
                except ValueError:
                    logger.warning(f"Invalid start_date format: {config.start_date}, expected YYYY-MM-DD")
            if config.end_date:
                try:
                    # End date should include the entire day
                    date_filter['end_date'] = datetime.fromisoformat(config.end_date).replace(
                        hour=23, minute=59, second=59, tzinfo=timezone.utc
                    )
                    logger.info(f"Date filter: end_date = {config.end_date}")
                except ValueError:
                    logger.warning(f"Invalid end_date format: {config.end_date}, expected YYYY-MM-DD")

        logger.info(f"Processing config: max_emails={effective_max_emails}, batch_size={config.batch_size or 250}, date_filter={date_filter}")

        # Process emails with streaming
        # Run in dedicated thread pool to avoid blocking event loop
        # Using custom executor allows multiple concurrent jobs
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,  # Custom thread pool with 20 workers
            lambda: processor.process_emails(
                job_id=job_id,
                max_emails=effective_max_emails,  # max_emails (None for all)
                batch_size=config.batch_size or 250,  # batch_size for DB inserts (auto-splits on timeout)
                skip_duplicates=True,  # skip_duplicates
                enable_categorization=config.enable_categorization,  # enable_categorization
                date_filter=date_filter  # NEW: date-based filtering
            )
        )

        logger.info(f"Processing completed for job {job_id}: {result}")

        # Cleanup
        processor.disconnect()

        # Cleanup downloaded file if parallel download was used AND keep_downloaded_file is False
        keep_file = config.keep_downloaded_file if config.keep_downloaded_file is not None else True
        if downloaded_file_path and not keep_file:
            try:
                if os.path.exists(downloaded_file_path):
                    os.remove(downloaded_file_path)
                    logger.info(f"Cleaned up downloaded file: {downloaded_file_path}")

                    # Mark cache entry as invalid since file is deleted
                    if cache_entry_id:
                        try:
                            get_supabase().table('downloaded_files').update({
                                'is_valid': False
                            }).eq('id', cache_entry_id).execute()
                        except Exception:
                            pass

                # Also try to remove the temp directory
                parent_dir = os.path.dirname(downloaded_file_path)
                if parent_dir and os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup downloaded file: {cleanup_error}")
        elif downloaded_file_path and keep_file:
            logger.info(f"Keeping downloaded file for future reuse: {downloaded_file_path}")

    except Exception as e:
        error_msg = f"Processing error: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Decide whether to keep file on error
        # If keep_downloaded_file is True (default), keep it for debugging/retry
        # If file was from cache, always keep it
        keep_file = config.keep_downloaded_file if config.keep_downloaded_file is not None else True

        if downloaded_file_path and not keep_file and not cache_entry_id:
            # Only cleanup if explicitly told not to keep AND it's not a cached file
            try:
                if os.path.exists(downloaded_file_path):
                    os.remove(downloaded_file_path)
                    logger.info(f"Cleaned up downloaded file after error: {downloaded_file_path}")
                parent_dir = os.path.dirname(downloaded_file_path)
                if parent_dir and os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup downloaded file: {cleanup_error}")
        elif downloaded_file_path:
            logger.info(f"Keeping downloaded file after error for debugging/retry: {downloaded_file_path}")

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

    # Broadcast status update via WebSocket
    try:
        manager = get_connection_manager()
        if manager:
            # Get mailbox_id for the job
            mailbox_id = None
            if job_id in active_jobs:
                mailbox_id = active_jobs[job_id].get('mailbox_id')
            else:
                job_result = get_supabase().table('processing_jobs').select('mailbox_id').eq('id', job_id).execute()
                if job_result.data:
                    mailbox_id = job_result.data[0].get('mailbox_id')

            if mailbox_id:
                # Get current progress from Redis for complete update
                progress = get_job_progress(job_id)
                await manager.broadcast_job_update(job_id, mailbox_id, {
                    'status': status,
                    'processed_records': progress.get('processed', 0),
                    'failed_records': progress.get('failed', 0),
                    'total_records': progress.get('total_records', 0),
                    **updates
                })
    except Exception as e:
        logger.debug(f"WebSocket broadcast failed (non-critical): {e}")

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
async def get_processing_jobs(
    mailbox_id: str = None,
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """Get processing jobs filtered by user's accessible mailboxes. Optionally filter by specific mailbox_id."""

    try:
        logger.info(f"[Processing Jobs] User {current_user['user_id']} accessing with {len(accessible_mailbox_ids)} mailboxes, filter mailbox_id={mailbox_id}")

        # If user has no accessible mailboxes, return empty list
        if not accessible_mailbox_ids:
            logger.warning("[Processing Jobs] User has no accessible mailboxes")
            return []

        # Determine which mailbox IDs to filter by
        if mailbox_id:
            # If specific mailbox requested, verify it's accessible
            if mailbox_id not in accessible_mailbox_ids:
                logger.warning(f"[Processing Jobs] Requested mailbox {mailbox_id} not in accessible list")
                return []
            filter_mailbox_ids = [mailbox_id]
        else:
            filter_mailbox_ids = accessible_mailbox_ids

        # Get processing jobs for the filtered mailboxes
        # Note: error_log excluded from list response (can be 100KB+ per job, use /processing-jobs/{id} for details)
        result = get_supabase().table('processing_jobs').select(
            'id, job_type, mailbox_id, status, total_records, processed_records, failed_records, filtered_records, started_at, completed_at, created_at, filter_start_date, filter_end_date, mailboxes(name)'
        ).in_('mailbox_id', filter_mailbox_ids).order('created_at', desc=True).limit(100).execute()
        
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
            filtered = job.get('filtered_records') or 0

            # Progress calculation:
            # - If completed: always 100%
            # - If has total: (processed + filtered) / total (filtered emails count as processed for progress)
            # - Otherwise: 0%
            if job.get('status') == 'completed':
                progress = 100  # Completed jobs always show 100%
            elif total > 0:
                # Include filtered records in progress calculation
                effective_processed = processed + filtered
                progress = min(100, round((effective_processed / total) * 100))
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

            # Get download progress if in downloading phase
            download_percent_raw = redis_progress.get('download_percent', 0)
            download_speed_raw = redis_progress.get('download_speed_mbps', 0)

            # Convert to numbers (Redis stores as strings)
            try:
                download_percent = float(download_percent_raw) if download_percent_raw else 0
            except (ValueError, TypeError):
                download_percent = 0

            try:
                download_speed_mbps = float(download_speed_raw) if download_speed_raw else 0
            except (ValueError, TypeError):
                download_speed_mbps = 0

            redis_status = redis_progress.get('status')

            # Override status if downloading
            effective_status = job.get('status')
            if redis_status == 'downloading' and effective_status == 'running':
                effective_status = 'downloading'
                logger.debug(f"Job {job['id']} status overridden to 'downloading' - percent: {download_percent}, speed: {download_speed_mbps}")

            # Calculate duration
            duration_str = None
            duration_seconds = None
            if job.get('started_at'):
                try:
                    started = datetime.fromisoformat(job['started_at'].replace('Z', '+00:00'))
                    if job.get('completed_at'):
                        # Completed job - calculate actual duration
                        completed = datetime.fromisoformat(job['completed_at'].replace('Z', '+00:00'))
                        duration_delta = completed - started
                        duration_seconds = duration_delta.total_seconds()
                    elif job.get('status') in ['running', 'downloading']:
                        # Running job - calculate elapsed time
                        now = datetime.now(timezone.utc)
                        duration_delta = now - started
                        duration_seconds = duration_delta.total_seconds()

                    # Format duration string
                    if duration_seconds:
                        if duration_seconds < 60:
                            duration_str = f"{duration_seconds:.0f}s"
                        elif duration_seconds < 3600:
                            duration_minutes = duration_seconds / 60
                            duration_str = f"{duration_minutes:.1f}m"
                        else:
                            duration_hours = duration_seconds / 3600
                            duration_str = f"{duration_hours:.1f}h"
                except (ValueError, TypeError) as e:
                    logger.debug(f"Error calculating duration for job {job['id']}: {e}")

            job_data = {
                **job,
                "mailbox_name": job.get('mailboxes', {}).get('name') if job.get('mailboxes') else 'Unknown Mailbox',
                "status": effective_status,
                "progress": progress,
                "total_records": total,  # Ensure it's not None
                "processed_records": processed,  # Ensure it's not None
                "emails_per_second": emails_per_second,
                "estimated_time_remaining": eta_str,
                "estimated_seconds_remaining": estimated_seconds,
                "download_percent": download_percent,
                "download_speed_mbps": download_speed_mbps,
                "duration": duration_str,
                "duration_seconds": duration_seconds
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

@app.post("/api/processing-jobs/{job_id}/restart")
async def restart_interrupted_job(job_id: str, background_tasks: BackgroundTasks):
    """
    Restart an interrupted job.

    This will:
    1. Check if there's a cached download available (reuse it)
    2. Create a new job with same configuration
    3. Start processing (with fresh download if needed)
    """
    try:
        sb = get_supabase()

        # Get the original job details
        job_result = sb.table('processing_jobs').select('*').eq('id', job_id).execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        original_job = job_result.data[0]

        # Only allow restarting interrupted/failed/stopped jobs
        if original_job['status'] not in ['interrupted', 'failed', 'stopped']:
            raise HTTPException(
                status_code=400,
                detail=f"Can only restart interrupted, failed, or stopped jobs. Current status: {original_job['status']}"
            )

        mailbox_id = original_job['mailbox_id']

        # Get mailbox details
        mailbox_result = sb.table('mailboxes').select('*').eq('id', mailbox_id).execute()
        if not mailbox_result.data:
            raise HTTPException(status_code=404, detail="Associated mailbox not found")

        mailbox = mailbox_result.data[0]
        connection_config = mailbox.get('connection_config', {})
        google_drive_file_id = connection_config.get('google_drive_file_id')

        # Check for cached download
        cached_file = None
        if google_drive_file_id:
            cache_result = sb.table('downloaded_files').select('*').eq(
                'google_drive_file_id', google_drive_file_id
            ).eq('is_valid', True).execute()

            if cache_result.data:
                cached = cache_result.data[0]
                cached_path = cached.get('storage_path', '')

                if os.path.exists(cached_path):
                    cached_file = cached_path
                    logger.info(f"Found cached download for restart: {cached_path}")
                else:
                    # Invalidate the cache entry since file doesn't exist
                    sb.table('downloaded_files').update({'is_valid': False}).eq('id', cached['id']).execute()
                    logger.info(f"Cached file not found, will re-download: {cached_path}")

        # Create new job
        new_job_data = {
            "job_type": original_job['job_type'],
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": 0,
            "processed_records": 0,
            "failed_records": 0,
            "filtered_records": 0,
            "filter_start_date": original_job.get('filter_start_date'),
            "filter_end_date": original_job.get('filter_end_date'),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        result = sb.table('processing_jobs').insert(new_job_data).execute()
        new_job_id = result.data[0]['id']

        # Mark old job as superseded
        sb.table('processing_jobs').update({
            'error_log': f'Job restarted. New job ID: {new_job_id}'
        }).eq('id', job_id).execute()

        # Build config for the new job
        config = ProcessingJobConfig(
            mailbox_id=mailbox_id,
            job_type=original_job['job_type'],
            download_first=True,
            download_threads=8,
            keep_downloaded_file=True,
            use_cached_file=True  # Will use the cached file if available
        )

        if original_job.get('filter_start_date'):
            config.start_date = original_job['filter_start_date'][:10]  # Extract date part
        if original_job.get('filter_end_date'):
            config.end_date = original_job['filter_end_date'][:10]

        # Add mailbox connection config to processing config (required by process_emails_real)
        config.connection_config = mailbox.get('connection_config', {})
        config.mailbox_type = mailbox.get('mailbox_type')

        # Start processing in background using the same function as start_processing
        background_tasks.add_task(process_emails_real, new_job_id, config)

        return {
            "message": "Job restarted successfully",
            "new_job_id": new_job_id,
            "original_job_id": job_id,
            "cached_file_available": cached_file is not None,
            "cached_file_path": cached_file
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restart job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to restart job: {str(e)}")

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
    """
    Re-sync a mailbox from the mail provider to backfill attachment names
    and provider web links for existing emails.  Uses the same upsert path
    as live sync so existing rows are updated in-place.
    """
    try:
        job_result = get_supabase().table('processing_jobs').select('*').eq('id', job_id).execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = job_result.data[0]
        mailbox_id = job['mailbox_id']

        # Look up mailbox to get type + connection config
        mb_result = get_supabase().table('mailboxes').select(
            'id, mailbox_type, connection_config'
        ).eq('id', mailbox_id).single().execute()

        if not mb_result.data:
            raise HTTPException(status_code=404, detail="Mailbox not found")

        mailbox = mb_result.data
        mailbox_type = mailbox.get('mailbox_type', '')

        if mailbox_type not in ('outlook_live', 'outlook'):
            raise HTTPException(
                status_code=400,
                detail=f"Reprocess not supported for mailbox type '{mailbox_type}'. Only Outlook mailboxes can be re-synced."
            )

        # Create a tracking job
        reprocess_job = {
            "job_type": "reprocessing",
            "mailbox_id": mailbox_id,
            "status": "pending",
            "total_records": 0,
            "processed_records": 0,
            "failed_records": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        result = get_supabase().table('processing_jobs').insert(reprocess_job).execute()
        new_job_id = result.data[0]['id']

        background_tasks.add_task(run_reprocessing, new_job_id, mailbox)
        return {"message": "Reprocessing started — re-syncing from mail provider", "job_id": new_job_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start reprocessing: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def run_reprocessing(job_id: str, mailbox: dict):
    """
    Re-extract emails from the mail provider (Outlook Graph API) and upsert
    them into the DB.  This backfills attachment filenames, sizes, and
    provider_web_link for all existing emails.
    """
    mailbox_id = mailbox['id']
    config = mailbox.get('connection_config') or {}

    try:
        from src.extractors.outlook_extractor import OutlookExtractor
        from src.database.operations import EmailOperations

        logger.info(f"Reprocessing job {job_id}: re-syncing mailbox {mailbox_id} from Outlook Graph API")

        await update_job_status(job_id, "running", {
            "started_at": datetime.now(timezone.utc).isoformat()
        })

        # Connect to Outlook
        extractor = OutlookExtractor({
            'access_token': config.get('outlook_access_token') or config.get('access_token', ''),
            'refresh_token': config.get('outlook_refresh_token') or config.get('refresh_token'),
            'mailbox_id': mailbox_id,
            # Intentionally omit delta_links → full re-fetch, not incremental
        })

        if not extractor.connect():
            error = extractor.auth_error or 'Failed to connect to Outlook API'
            await update_job_status(job_id, "failed", {"error_log": [error]})
            return

        email_ops = EmailOperations()
        success = 0
        failed = 0
        batch = []
        batch_size = 100

        for email in extractor.extract_emails():
            batch.append(email)
            if len(batch) >= batch_size:
                result = email_ops.batch_insert_emails(batch, mailbox_id)
                success += result.get('success', 0)
                failed += result.get('failed', 0)
                batch = []

                await update_job_status(job_id, "running", {
                    "processed_records": success,
                    "failed_records": failed
                })
                logger.info(f"Reprocess progress: {success} upserted, {failed} failed")

                # Check for stop/cancel
                job_check = get_supabase().table('processing_jobs').select('status').eq('id', job_id).execute()
                if job_check.data and job_check.data[0]['status'] in ('stopped', 'cancelled'):
                    logger.info(f"Reprocessing job {job_id} stopped by user")
                    break

        # Flush remaining
        if batch:
            result = email_ops.batch_insert_emails(batch, mailbox_id)
            success += result.get('success', 0)
            failed += result.get('failed', 0)

        extractor.disconnect()

        await update_job_status(job_id, "completed", {
            "processed_records": success,
            "failed_records": failed,
            "total_records": success + failed,
            "completed_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Reprocessing job {job_id} done: {success} upserted, {failed} failed")

    except Exception as e:
        error_msg = f"Reprocessing error: {e}"
        logger.error(error_msg, exc_info=True)
        job_result = get_supabase().table('processing_jobs').select('status').eq('id', job_id).execute()
        if job_result.data and job_result.data[0].get('status') in ['stopped', 'cancelled']:
            logger.warning(f"Reprocessing exception after stop: {error_msg}")
        else:
            await update_job_status(job_id, "failed", {
                "error_log": [error_msg],
                "completed_at": datetime.now(timezone.utc).isoformat()
            })

# =============================================================================
# Stage 2: Error Handling Endpoints
# =============================================================================

@app.get("/api/processing-jobs/{job_id}/errors")
async def get_processing_errors(
    job_id: str,
    limit: int = 50,
    offset: int = 0
):
    """
    Get errors for a specific processing job.

    Returns both Redis-cached errors (for active jobs) and
    database-persisted errors (for completed jobs).
    """
    try:
        # Get mailbox_id from job
        job_result = get_supabase().table('processing_jobs').select('mailbox_id').eq('id', job_id).single().execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        mailbox_id = job_result.data.get('mailbox_id')
        if not mailbox_id:
            raise HTTPException(status_code=400, detail="Job has no associated mailbox")

        # Get errors from Redis (for active jobs)
        redis_errors = []
        redis_total = 0
        if progress_manager:
            redis_errors = progress_manager.get_errors(job_id, limit, offset)
            error_counts = progress_manager.get_error_counts(job_id)
            redis_total = error_counts.get('total', 0)

        # Get failed emails from database (for persistence and completed jobs)
        db_result = get_supabase().table('emails').select(
            'id, message_id, subject, sender_email, sent_date, '
            'processing_error, processing_attempts, last_processing_attempt'
        ).eq(
            'mailbox_id', mailbox_id
        ).eq(
            'processing_status', 'failed'
        ).order(
            'last_processing_attempt', desc=True
        ).range(offset, offset + limit - 1).execute()

        db_errors = db_result.data or []

        # Get total failed count
        count_result = get_supabase().table('emails').select(
            'id', count='exact'
        ).eq('mailbox_id', mailbox_id).eq('processing_status', 'failed').execute()
        db_total = count_result.count or 0

        # Use the higher count between Redis and DB
        total_failed = max(redis_total, db_total)

        # Format response - prefer DB records as they have email IDs
        emails = []
        seen_message_ids = set()

        for err in db_errors:
            emails.append({
                'id': err.get('id', ''),
                'message_id': err.get('message_id'),
                'subject': err.get('subject'),
                'sender_email': err.get('sender_email'),
                'sent_date': err.get('sent_date'),
                'processing_error': err.get('processing_error'),
                'processing_attempts': err.get('processing_attempts', 1),
                'last_processing_attempt': err.get('last_processing_attempt')
            })
            if err.get('message_id'):
                seen_message_ids.add(err.get('message_id'))

        # Add Redis errors that aren't in DB yet (from active processing)
        for err in redis_errors:
            if err.get('message_id') and err.get('message_id') not in seen_message_ids:
                emails.append({
                    'id': err.get('email_id', ''),
                    'message_id': err.get('message_id'),
                    'subject': err.get('subject'),
                    'sender_email': err.get('sender_email'),
                    'sent_date': None,
                    'processing_error': err.get('error_message'),
                    'processing_attempts': err.get('attempt_number', 1),
                    'last_processing_attempt': err.get('timestamp')
                })

        return {
            'job_id': job_id,
            'mailbox_id': mailbox_id,
            'total_failed': total_failed,
            'emails': emails[:limit],
            'has_more': total_failed > offset + limit
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get processing errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/processing-jobs/{job_id}/errors/summary")
async def get_error_summary(job_id: str):
    """Get aggregated error summary for a processing job."""
    try:
        # Get mailbox_id from job
        job_result = get_supabase().table('processing_jobs').select(
            'mailbox_id, error_summary, failed_records'
        ).eq('id', job_id).single().execute()

        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = job_result.data
        mailbox_id = job.get('mailbox_id')

        # Try Redis first for active jobs
        if progress_manager:
            summary = progress_manager.get_error_summary(job_id)
            if summary.get('total_errors', 0) > 0:
                return summary

        # Check stored error_summary in processing_jobs
        if job.get('error_summary'):
            error_summary = job.get('error_summary')
            return {
                'total_errors': error_summary.get('total_errors', job.get('failed_records', 0)),
                'error_types': error_summary.get('error_types', {}),
                'sample_errors': error_summary.get('sample_errors', []),
                'has_more_errors': False
            }

        # Return basic summary from failed_records count
        return {
            'total_errors': job.get('failed_records', 0),
            'error_types': {},
            'sample_errors': [],
            'has_more_errors': False
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get error summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/processing-jobs/{job_id}/retry-failed")
async def retry_failed_emails(job_id: str, max_attempts: int = 3):
    """Reset failed emails to pending status for retry processing."""
    try:
        # Get mailbox_id from job
        job_result = get_supabase().table('processing_jobs').select('mailbox_id').eq('id', job_id).single().execute()
        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        mailbox_id = job_result.data.get('mailbox_id')
        if not mailbox_id:
            raise HTTPException(status_code=400, detail="Job has no associated mailbox")

        # Get emails that can be retried
        emails_to_reset = get_supabase().table('emails').select('id').eq(
            'mailbox_id', mailbox_id
        ).eq(
            'processing_status', 'failed'
        ).lt(
            'processing_attempts', max_attempts
        ).execute()

        if not emails_to_reset.data:
            return {
                'job_id': job_id,
                'mailbox_id': mailbox_id,
                'emails_reset': 0,
                'message': 'No emails to retry (all have exceeded max attempts or none failed)'
            }

        email_ids = [e['id'] for e in emails_to_reset.data]

        # Reset them to pending
        get_supabase().table('emails').update({
            'processing_status': 'pending',
            'processing_error': None
        }).in_('id', email_ids).execute()

        # Clear Redis error cache for this job
        if progress_manager:
            progress_manager.clear_errors(job_id)

        # Update job status to allow reprocessing
        get_supabase().table('processing_jobs').update({
            'status': 'pending'
        }).eq('id', job_id).eq('status', 'completed').execute()

        logger.info(f"Reset {len(email_ids)} failed emails for retry in job {job_id}")

        return {
            'job_id': job_id,
            'mailbox_id': mailbox_id,
            'emails_reset': len(email_ids),
            'message': f'Reset {len(email_ids)} failed emails for retry'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry failed emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Email analysis endpoints for dashboard
@app.get("/api/dashboard/stats")
async def get_dashboard_stats(
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """Get dashboard statistics filtered by user's accessible mailboxes"""

    try:
        sb = get_supabase()

        logger.info(f"[Dashboard Stats] User {current_user['user_id']} accessing with {len(accessible_mailbox_ids)} mailboxes")

        # If user has no accessible mailboxes, return zeros
        if not accessible_mailbox_ids:
            logger.warning("[Dashboard Stats] User has no accessible mailboxes")
            return {
                "totalEmails": 0,
                "totalMailboxes": 0,
                "todayEmails": 0,
                "processingJobs": 0
            }

        # Count emails in accessible mailboxes
        emails_count = sb.table('emails').select('id', count='exact').in_('mailbox_id', accessible_mailbox_ids).execute()

        # Count accessible mailboxes
        mailboxes_count = len(accessible_mailbox_ids)

        # Count today's emails in accessible mailboxes
        today = datetime.now(timezone.utc).date().isoformat()
        today_emails = sb.table('emails').select('id', count='exact').in_('mailbox_id', accessible_mailbox_ids).gte('sent_date', today).execute()

        # Count active processing jobs for accessible mailboxes
        processing_jobs_count = sb.table('processing_jobs').select('id', count='exact').in_('mailbox_id', accessible_mailbox_ids).in_('status', ['pending', 'running', 'downloading']).execute()

        stats = {
            "totalEmails": emails_count.count or 0,
            "totalMailboxes": mailboxes_count,
            "todayEmails": today_emails.count or 0,
            "processingJobs": processing_jobs_count.count or 0
        }

        logger.info(f"[Dashboard Stats] Returning stats: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        # Return zeros instead of mock data
        return {
            "totalEmails": 0,
            "totalMailboxes": 0,
            "todayEmails": 0,
            "processingJobs": 0
        }

def _normalize_folder_name(raw: str) -> str:
    """Normalize folder_path values so 'INBOX'/'inbox' both become 'Inbox', etc."""
    FOLDER_MAP = {
        'inbox': 'Inbox', 'sent': 'Sent', 'sent items': 'Sent', 'sent mail': 'Sent',
        'sentitems': 'Sent', 'drafts': 'Drafts', 'draft': 'Drafts',
        'spam': 'Spam', 'junk': 'Spam', 'junk email': 'Spam', 'junk e-mail': 'Spam',
        'trash': 'Trash', 'deleted items': 'Trash', 'deleted': 'Trash',
        'starred': 'Starred', 'flagged': 'Starred', 'important': 'Important',
    }
    return FOLDER_MAP.get(raw.strip().lower(), raw.strip())

# Reverse map: canonical name → all raw aliases that should match
_FOLDER_ALIASES = {
    'sent': ['Sent', 'Sent Items', 'Sent Mail'],
    'trash': ['Trash', 'Deleted Items'],
    'spam': ['Spam', 'Junk Email', 'Junk E-Mail'],
    'drafts': ['Drafts', 'Draft'],
    'starred': ['Starred', 'Flagged'],
}

def _apply_folder_filter(query, folder_name: str):
    """Apply folder filter with alias expansion for backward compatibility.

    For well-known folders (Sent, Trash, Spam, etc.), expands the filter to
    match all aliases (e.g. 'Sent' also matches 'Sent Items' in DB).
    For user-created folders, does a simple case-insensitive match.
    """
    aliases = _FOLDER_ALIASES.get(folder_name.strip().lower())
    if aliases and len(aliases) > 1:
        # Match any alias (case-insensitive)
        conditions = ','.join(f'folder_path.ilike.{a}' for a in aliases)
        return query.or_(conditions)
    else:
        return query.ilike('folder_path', folder_name)

@app.get("/api/emails/folders")
async def get_folder_names(mailbox_id: Optional[str] = None):
    """Get distinct folder names from emails for filter dropdown - Optimized with direct SQL"""
    try:
        sb = get_supabase()

        if mailbox_id:
            logger.info(f"Fetching distinct folder names for mailbox {mailbox_id}...")
            # Paginate through ALL emails (selecting only folder_path) to find every folder
            # Without this, .limit(10000) could miss custom folders with few emails
            all_folders = set()
            offset = 0
            batch_size = 5000
            while True:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda off=offset: sb.table('emails')
                        .select('folder_path')
                        .eq('mailbox_id', mailbox_id)
                        .range(off, off + batch_size - 1)
                        .execute()
                )
                if not result.data:
                    break
                for row in result.data:
                    folder = row.get('folder_path')
                    if folder:
                        all_folders.add(_normalize_folder_name(folder))
                if len(result.data) < batch_size:
                    break
                offset += len(result.data)

            folders_list = sorted(list(all_folders))
            logger.info(f"✓ Found {len(folders_list)} unique folders for mailbox {mailbox_id}: {folders_list}")
            return folders_list

        logger.info("Fetching distinct folder names (optimized)...")

        # Use PostgreSQL DISTINCT query for efficient folder retrieval
        # This is much faster than fetching all rows
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.rpc('get_distinct_folders', {}).execute()
        )

        if result.data:
            folders_list = sorted(set(
                _normalize_folder_name(f['folder_path'])
                for f in result.data if f.get('folder_path')
            ))
            logger.info(f"✓ Found {len(folders_list)} unique folders: {folders_list}")
            return folders_list

        # Fallback: If RPC function doesn't exist, use regular query with limit
        # This will only work if there aren't too many unique folders
        logger.warning("RPC function not found, using fallback method")
        all_folders = set()
        offset = 0
        batch_size = 5000
        while True:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda off=offset: sb.table('emails')
                    .select('folder_path')
                    .range(off, off + batch_size - 1)
                    .execute()
            )
            if not result.data:
                break
            for row in result.data:
                folder = row.get('folder_path')
                if folder:
                    all_folders.add(_normalize_folder_name(folder))
            if len(result.data) < batch_size:
                break
            offset += len(result.data)

        folders_list = sorted(list(all_folders))
        logger.info(f"✓ Found {len(folders_list)} unique folders (fallback): {folders_list}")
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
    
    # Extract mailbox name + type from nested structure
    mailbox_name = 'Unknown'
    mailbox_type = None
    mailboxes_data = item.get('mailboxes')
    if mailboxes_data:
        # Handle both dict and list formats
        if isinstance(mailboxes_data, dict):
            mailbox_name = mailboxes_data.get('name', 'Unknown')
            mailbox_type = mailboxes_data.get('mailbox_type')
        elif isinstance(mailboxes_data, list) and len(mailboxes_data) > 0:
            mailbox_name = mailboxes_data[0].get('name', 'Unknown')
            mailbox_type = mailboxes_data[0].get('mailbox_type')

    return EmailResponse(
        id=item['id'],
        subject=item['subject'],
        sender_email=item['sender_email'],
        sender_name=item.get('sender_name'),
        recipients=item.get('recipients'),
        cc_list=item.get('cc_list'),
        bcc_list=item.get('bcc_list'),
        sent_date=item['sent_date'],
        received_date=item.get('received_date'),
        category=categories[0]['category'] if categories else 'unassigned',
        is_outbound=item['is_outbound'],
        is_reply=item['is_reply'],
        folder_path=item['folder_path'],
        message_size=item['message_size'],
        body_text=item.get('body_text'),
        body_html=item.get('body_html'),
        mailbox_id=item['mailbox_id'],
        mailbox_name=mailbox_name,
        mailbox_type=mailbox_type,
        tags=tags,
        is_spam=is_spam,
        is_marketing=is_marketing,
        priority_score=priority_score,
        sender_type=sender_type,
        attachments=item.get('attachments') or [],
        provider_web_link=item.get('provider_web_link') or None,
    )

@app.post("/api/emails")
async def get_emails_with_filters(
    request: EmailRequest,
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """
    SCALABLE EMAIL QUERY ENDPOINT - Fixed category filter with same approach

    Industry best practices for handling millions of emails:
    1. Cursor-based pagination for better performance
    2. Efficient single query with proper joins
    3. Database indexing strategy
    4. Query optimization with selective fields
    5. Caching for metadata (categories, mailboxes)
    6. Row-level security - only accessible mailboxes
    """
    try:
        sb = get_supabase()
        filters = request.filters
        page = request.page
        pageSize = min(request.pageSize, 100)  # Limit max page size for performance
        
        logger.debug(f"Scalable email query - Filters: {filters.dict()}, Page: {page}, Size: {pageSize}")
        
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
            # First get mailbox ID from accessible mailboxes only
            try:
                # Filter by name AND accessible mailbox IDs
                mailbox_result = sb.table('mailboxes').select('id').eq('name', filters.mailbox).in_('id', accessible_mailbox_ids).execute()
                if mailbox_result.data:
                    mailbox_id = mailbox_result.data[0]['id']
                    base_query = base_query.eq('mailbox_id', mailbox_id)
                    filters_applied.append(f"mailbox={filters.mailbox}")
                else:
                    # No matching accessible mailbox found, return empty results
                    logger.warning(f"No accessible mailbox found with name: {filters.mailbox}")
                    return EmailListResponse(emails=[], totalCount=0)
            except Exception as e:
                logger.error(f"Error filtering by mailbox: {e}")
                # Continue without mailbox filter
        else:
            # No specific mailbox filter - restrict to accessible mailboxes only
            if accessible_mailbox_ids:
                base_query = base_query.in_('mailbox_id', accessible_mailbox_ids)
                filters_applied.append(f"accessible_mailboxes={len(accessible_mailbox_ids)}")
            else:
                # User has no accessible mailboxes, return empty
                logger.warning("User has no accessible mailboxes")
                return EmailListResponse(emails=[], totalCount=0)

        # Folder filter with alias expansion (e.g. "Sent" also matches "Sent Items")
        if filters.folder and filters.folder.strip():
            base_query = _apply_folder_filter(base_query, filters.folder)
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
        
        logger.debug(f"Optimized query - Applied filters: {filters_applied}")
        
        # Execute count query separately (PostgREST limitation with joins + count)
        count_query = sb.table('emails').select('id', count='exact')
        # Apply same filters to count query (exclude joins for count)
        if filters.mailbox and filters.mailbox.strip():
            try:
                # Filter by name AND accessible mailbox IDs
                mailbox_result = sb.table('mailboxes').select('id').eq('name', filters.mailbox).in_('id', accessible_mailbox_ids).execute()
                if mailbox_result.data:
                    mailbox_id = mailbox_result.data[0]['id']
                    count_query = count_query.eq('mailbox_id', mailbox_id)
            except Exception:
                pass  # Skip mailbox filter for count if it fails
        else:
            # No specific mailbox filter - restrict to accessible mailboxes
            if accessible_mailbox_ids:
                count_query = count_query.in_('mailbox_id', accessible_mailbox_ids)
        if filters.folder and filters.folder.strip():
            count_query = _apply_folder_filter(count_query, filters.folder)
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
        
        logger.debug(f"Query executed successfully, got {len(result.data or [])} results")
        
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
                        categories_result = sb.table('email_categories').select('email_id, category').in_('email_id', batch_ids).execute()
                        total_categories += len(categories_result.data or [])
                        # Group categories by email_id
                        for cat in categories_result.data or []:
                            email_id = cat['email_id']
                            if email_id not in email_categories_map:
                                email_categories_map[email_id] = []
                            email_categories_map[email_id].append({
                                'category': cat['category']
                            })
                    except Exception as e:
                        logger.error(f"Error fetching categories for batch {i//batch_size}: {e}")
                        # Continue with other batches
                        continue
                
                logger.debug(f"Categories query returned {total_categories} categories for {len(email_ids)} emails")
        
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
        logger.debug(f"Scalable query result: {len(emails)} emails out of {total_count} total")
        
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
                category_query = _apply_folder_filter(category_query, filters.folder)
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
                        categories_result = sb.table('email_categories').select('email_id, category').in_('email_id', batch_ids).execute()
                        total_categories += len(categories_result.data or [])
                        for cat in categories_result.data or []:
                            email_id = cat['email_id']
                            if email_id not in email_categories_map:
                                email_categories_map[email_id] = []
                            email_categories_map[email_id].append({
                                'category': cat['category']
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
                email_categories(category)
            """).in_('id', batch)
            
            # Apply other filters
            if filters.search:
                query = query.or_(f"subject.ilike.%{filters.search}%,sender_email.ilike.%{filters.search}%,sender_name.ilike.%{filters.search}%")
            
            if filters.mailbox:
                query = query.eq('mailboxes.name', filters.mailbox)
            
            if filters.folder:
                query = _apply_folder_filter(query, filters.folder)
            
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
    logger.info('[Categories API] Request received')
    try:
        sb = get_supabase()

        # Use filter to exclude _meta_ prefixed categories at database level
        # and fetch more rows to ensure we get actual categories
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.table('email_categories')
                .select('category')
                .not_.like('category', '_meta_%')
                .limit(10000)
                .execute()
        )

        row_count = len(result.data or [])
        logger.info(f'[Categories API] Fetched {row_count} non-meta category rows')

        # Get unique categories
        category_set = set()
        for item in result.data or []:
            category = item.get('category')
            if category:
                category_set.add(category)

        categories = sorted(list(category_set))
        logger.info(f'[Categories API] Returning {len(categories)} categories: {categories}')

        return categories

    except Exception as e:
        logger.error(f"[Categories API] Error fetching email categories: {e}", exc_info=True)
        return []

@app.get("/api/emails/{email_id}")
async def get_email_by_id(email_id: str):
    """Get a single email by ID - replaces frontend emailService.getEmail()"""
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            sb = get_supabase()

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: sb.table('emails').select("""
                    id,
                    subject,
                    sender_email,
                    sender_name,
                    recipients,
                    cc_list,
                    bcc_list,
                    attachments,
                    provider_web_link,
                    sent_date,
                    received_date,
                    is_outbound,
                    is_reply,
                    folder_path,
                    message_size,
                    body_text,
                    body_html,
                    mailbox_id,
                    mailboxes!inner(name,mailbox_type),
                    email_categories(category)
                """).eq('id', email_id).single().execute()
            )

            if not result.data:
                raise HTTPException(status_code=404, detail="Email not found")

            email = transform_email_data(result.data)
            return email
        except HTTPException:
            raise
        except Exception as e:
            if attempt < max_retries - 1 and "WinError 10035" in str(e):
                logger.warning(f"Retry {attempt + 1}/{max_retries} for email {email_id} due to socket error")
                await asyncio.sleep(retry_delay)
                continue
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
async def get_volume_data(
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """Get email volume data for the last 7 days filtered by accessible mailboxes"""
    try:
        sb = get_supabase()

        if not accessible_mailbox_ids:
            return []

        # Get data for last 7 days from emails table (aggregate by date)
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=6)).date().isoformat()
        today = datetime.now(timezone.utc).date().isoformat()

        # Query emails in accessible mailboxes
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.table('emails').select('sent_date, direction').in_('mailbox_id', accessible_mailbox_ids).gte('sent_date', seven_days_ago).lte('sent_date', today).execute()
        )

        # Aggregate by date
        volume_by_date = {}
        for item in result.data or []:
            date = item['sent_date'][:10]  # Extract date part
            if date not in volume_by_date:
                volume_by_date[date] = {'inbound': 0, 'outbound': 0}

            direction = item.get('direction', 'inbound')
            if direction == 'outbound':
                volume_by_date[date]['outbound'] += 1
            else:
                volume_by_date[date]['inbound'] += 1

        # Transform to expected format
        volume_data = []
        for i in range(6, -1, -1):
            date = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
            volume_data.append({
                'date': date,
                'inbound': volume_by_date.get(date, {}).get('inbound', 0),
                'outbound': volume_by_date.get(date, {}).get('outbound', 0)
            })

        return volume_data

    except Exception as e:
        logger.error(f"Error fetching volume data: {e}", exc_info=True)
        return []

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
async def get_category_data(
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """Get email category distribution filtered by accessible mailboxes"""
    try:
        sb = get_supabase()

        if not accessible_mailbox_ids:
            return []

        # Get categories for emails in accessible mailboxes
        # Note: email_categories table should have email_id, need to join with emails
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.table('email_categories').select('category, email_id, emails!inner(mailbox_id)').in_('emails.mailbox_id', accessible_mailbox_ids).execute()
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
        return []

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
async def get_recent_emails(
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """Get recent emails filtered by accessible mailboxes"""
    try:
        sb = get_supabase()

        if not accessible_mailbox_ids:
            return []

        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: sb.table('emails').select("""
                id,
                subject,
                sender_email,
                sender_name,
                sent_date,
                email_categories(category)
            """).in_('mailbox_id', accessible_mailbox_ids).order('sent_date', desc=True).limit(5).execute()
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
# Trigger restart



