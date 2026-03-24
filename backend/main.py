"""
Email Intelligence Platform — FastAPI Application Entry Point

Handles: app creation, middleware, logging, Redis/Supabase init, signal handlers,
router registration, and lifespan (startup/shutdown).

All endpoint logic lives in src/routers/*.py modules.
"""

from fastapi import FastAPI, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
import signal
import atexit
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime, timezone
import logging
import logging.handlers
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

# ═══════════════════════════════════════════════════════════════════════════
# 1. Environment
# ═══════════════════════════════════════════════════════════════════════════

python_env = os.getenv('PYTHON_ENV', 'development')
backend_dir = os.path.dirname(__file__)
env_file = os.path.join(backend_dir, f'.env.{python_env}')
if os.path.exists(env_file):
    load_dotenv(dotenv_path=env_file)
else:
    fallback_env = os.path.join(backend_dir, '.env')
    if os.path.exists(fallback_env):
        load_dotenv(dotenv_path=fallback_env)

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# ═══════════════════════════════════════════════════════════════════════════
# 2. Logging
# ═══════════════════════════════════════════════════════════════════════════

log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)


class SafeFormatter(logging.Formatter):
    """Formatter that replaces emojis with text equivalents on Windows."""
    EMOJI_MAP = {
        '📦': '[PKG]', '📊': '[STATS]', '📧': '[EMAIL]', '🌊': '[STREAM]',
        '🏁': '[DONE]', '❌': '[ERROR]', '⚠️': '[WARN]', '✅': '[OK]',
        '🔄': '[SYNC]', '⏸️': '[PAUSE]', '▶️': '[PLAY]',
    }

    def format(self, record):
        msg = super().format(record)
        if sys.platform == 'win32':
            for emoji, replacement in self.EMOJI_MAP.items():
                msg = msg.replace(emoji, replacement)
        return msg


log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
file_handler = logging.handlers.RotatingFileHandler(
    os.path.join(log_dir, 'backend.log'), maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(log_format))
console_handler = logging.StreamHandler()
console_handler.setFormatter(SafeFormatter(log_format))
logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

# Reduce noisy libraries
for lib in ["httpx", "httpcore", "urllib3", "googleapiclient.discovery"]:
    logging.getLogger(lib).setLevel(logging.WARNING)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

logger.info(f"Running in {python_env} mode")

# ═══════════════════════════════════════════════════════════════════════════
# 3. Volume / Download Directory
# ═══════════════════════════════════════════════════════════════════════════

DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', '/data/downloads' if python_env == 'production' else None)
VOLUME_MOUNTED = False


def check_volume_status():
    """Check if the download directory is a properly mounted volume."""
    global VOLUME_MOUNTED
    if not DOWNLOAD_DIR:
        logger.info("Using temporary directory for downloads (files will be lost on restart)")
        return False
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    try:
        if hasattr(os.path, 'ismount') and os.path.ismount(DOWNLOAD_DIR):
            VOLUME_MOUNTED = True
            logger.info(f"VOLUME MOUNTED: {DOWNLOAD_DIR} is a mounted volume")
        else:
            import shutil
            total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
            free_gb, total_gb = free / (1024**3), total / (1024**3)
            if DOWNLOAD_DIR.startswith('/data') and total_gb > 1:
                VOLUME_MOUNTED = True
                logger.info(f"VOLUME DETECTED: {DOWNLOAD_DIR} ({free_gb:.1f}GB free of {total_gb:.1f}GB)")
            else:
                logger.warning(f"VOLUME NOT MOUNTED: {DOWNLOAD_DIR} appears to be on root filesystem")
        # Write marker file
        marker_file = os.path.join(DOWNLOAD_DIR, '.volume_marker')
        if os.path.exists(marker_file):
            with open(marker_file, 'r') as f:
                logger.info(f"   Volume marker from previous boot: {f.read().strip()}")
        with open(marker_file, 'w') as f:
            f.write(datetime.now(timezone.utc).isoformat())
        return VOLUME_MOUNTED
    except Exception as e:
        logger.error(f"Error checking volume status: {e}")
        return False


check_volume_status()

# ═══════════════════════════════════════════════════════════════════════════
# 4. Redis
# ═══════════════════════════════════════════════════════════════════════════

from src.database.redis_client import JobProgressManager, JobQueueManager, RedisClient

try:
    progress_manager = JobProgressManager()
    queue_manager = JobQueueManager()
    logger.info("Redis managers initialized successfully")
    if not RedisClient.test_connection():
        raise Exception("Redis connection test failed")
except Exception as e:
    logger.error(f"Failed to initialize Redis managers: {e}")
    logger.error("Redis is REQUIRED for job processing. Please ensure Redis is running.")
    raise RuntimeError("Redis is required but not available. Cannot start application.")

# Initialize shared progress tracker
try:
    from src.utils.progress_tracker import initialize_progress_managers
    initialize_progress_managers(progress_manager, queue_manager)
    logger.info("Shared progress tracker initialized")
except Exception as e:
    logger.error(f"Failed to initialize shared progress tracker: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# 5. Supabase Client
# ═══════════════════════════════════════════════════════════════════════════

_supabase_client = None


def get_supabase() -> Client:
    """Get or create Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment")
        _supabase_client = create_client(supabase_url, supabase_key)
        logger.info("Supabase client initialized successfully")

        from src.services.job_error_logger import init_error_logger
        init_error_logger(_supabase_client)
        logger.info("Job error logger initialized")
    return _supabase_client


# ═══════════════════════════════════════════════════════════════════════════
# 6. Thread Pool & Signal Handlers
# ═══════════════════════════════════════════════════════════════════════════

executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="email_processor")


def force_shutdown(signum=None, frame=None):
    """Force shutdown handler for SIGTERM/SIGINT."""
    logger.info(f"=== RECEIVED SIGNAL {signum}, forcing shutdown ===")
    try:
        from src.storage.parallel_downloader import cancel_all_downloads
        cancel_all_downloads()
    except Exception as e:
        logger.warning(f"Error cancelling downloads during signal handler: {e}")
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except Exception as e:
        logger.warning(f"Error shutting down executor: {e}")
    logger.info("Shutdown complete, exiting...")
    os._exit(0)


try:
    if sys.platform != 'win32':
        signal.signal(signal.SIGTERM, force_shutdown)
        signal.signal(signal.SIGINT, force_shutdown)
        logger.info("Signal handlers registered for graceful shutdown (Unix)")
    else:
        def windows_cleanup():
            logger.info("=== ATEXIT CLEANUP (Windows) ===")
            try:
                from src.storage.parallel_downloader import cancel_all_downloads
                cancel_all_downloads()
            except Exception:
                pass
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        atexit.register(windows_cleanup)
        logger.info("Atexit handler registered for graceful shutdown (Windows)")
except Exception as e:
    logger.warning(f"Could not register shutdown handlers: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# 7. Router Imports
# ═══════════════════════════════════════════════════════════════════════════

# Pre-existing routers (Sprint 1–3)
from src.routers.account_managers import router as account_managers_router, init_account_managers_router
from src.routers.clients import router as clients_router, init_clients_router
from src.routers.customers import router as customers_router, init_customers_router
from src.routers.contacts import router as contacts_router, init_contacts_router
from src.routers.analytics import router as analytics_router, init_analytics_router
from src.routers.admin import router as admin_router, init_admin_router
from src.routers.ai import router as ai_router, init_ai_router
from src.routers.rules import router as rules_router, init_rules_router
from src.routers.quickbase import router as quickbase_router, init_quickbase_router
from src.routers.intelligence_config import router as intelligence_config_router, init_intelligence_config_router
from src.routers.errors import router as errors_router, init_error_router
from src.routers.gmail import router as gmail_router, init_gmail_router
from src.routers.outlook import router as outlook_router, init_outlook_router
from src.routers.auth import router as auth_router, init_auth_router

# New extracted routers
from src.routers.mailboxes import router as mailboxes_router, init_mailboxes_router
from src.routers.emails import router as emails_router, init_emails_router
from src.routers.dashboard import router as dashboard_router, init_dashboard_router
from src.routers.google_auth import router as google_auth_router, init_google_auth_router
from src.routers.processing_jobs import (
    router as processing_jobs_router,
    init_processing_jobs_router,
    set_gmail_sync_service as pj_set_gmail,
    set_outlook_sync_service as pj_set_outlook,
    start_processing as pj_start_processing,
    invalidate_cached_download as pj_invalidate_cache,
    cleanup_orphaned_jobs,
    sync_redis_to_database,
    run_reprocessing,
)

from src.services.job_error_logger import get_error_logger
from src.services.gmail_sync_service import get_gmail_sync_service, GmailSyncService
from src.services.outlook_sync_service import get_outlook_sync_service, OutlookSyncService
from src.dependencies.auth import init_auth_dependencies, get_current_user, get_accessible_mailbox_ids
from src.utils.audit import init_audit
from src.websocket.routes import router as websocket_router
from src.websocket.manager import init_connection_manager
from src.websocket.auth import init_websocket_auth
from src.models.api_models import ProcessingJobConfig

# ═══════════════════════════════════════════════════════════════════════════
# 8. App Creation & Middleware
# ═══════════════════════════════════════════════════════════════════════════

# Sync service instances (initialized in startup)
_gmail_sync_service: GmailSyncService = None
_outlook_sync_service: OutlookSyncService = None


@asynccontextmanager
async def lifespan(app):
    """Modern lifespan handler for startup/shutdown."""
    await startup_event()
    yield
    await shutdown_event()


app = FastAPI(title="Email Intelligence API", version="1.0.0", lifespan=lifespan)

# CORS
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "*")
if allowed_origins_str.strip() == "*":
    allowed_origins = ["*"]
    allow_credentials = False
else:
    allowed_origins = [o.strip() for o in allowed_origins_str.split(",") if o.strip()]
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
logger.info(f"CORS configured — Origins: {allowed_origins}, Credentials: {allow_credentials}")


@app.options("/{path:path}")
async def options_handler(path: str):
    """Global OPTIONS handler for CORS preflight requests."""
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════
# 9. Router Registration
# ═══════════════════════════════════════════════════════════════════════════

# Auth (first)
app.include_router(auth_router, prefix="/api")

# Business hierarchy
app.include_router(account_managers_router, prefix="/api")
app.include_router(clients_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(contacts_router, prefix="/api")

# Analytics & AI
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(rules_router, prefix="/api/v1")
app.include_router(quickbase_router, prefix="/api/v1")
app.include_router(intelligence_config_router, prefix="/api/v1")

# Email providers
app.include_router(gmail_router, prefix="/api")
app.include_router(outlook_router, prefix="/api")
app.include_router(errors_router, prefix="/api")

# New extracted routers
app.include_router(mailboxes_router, prefix="/api")
app.include_router(emails_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(google_auth_router, prefix="/api")
app.include_router(processing_jobs_router, prefix="/api")

# WebSocket (no /api prefix)
app.include_router(websocket_router)


# ═══════════════════════════════════════════════════════════════════════════
# 10. Standalone Endpoints (paths that don't fit a router prefix)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"message": "Email Intelligence API", "status": "running"}


@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Health check with volume status for Railway."""
    import shutil
    volume_info = {"mounted": VOLUME_MOUNTED, "path": DOWNLOAD_DIR}
    if DOWNLOAD_DIR and os.path.exists(DOWNLOAD_DIR):
        try:
            total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
            volume_info["total_gb"] = round(total / (1024**3), 2)
            volume_info["used_gb"] = round(used / (1024**3), 2)
            volume_info["free_gb"] = round(free / (1024**3), 2)
            volume_info["cached_files"] = len([f for f in os.listdir(DOWNLOAD_DIR) if not f.startswith('.')])
        except Exception:
            pass
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat(), "volume": volume_info}


@app.post("/api/mailboxes/{mailbox_id}/process")
async def start_processing(mailbox_id: str, config: ProcessingJobConfig, background_tasks: BackgroundTasks):
    """Start email processing for a mailbox (delegates to processing_jobs router)."""
    return await pj_start_processing(mailbox_id, config, background_tasks)


@app.delete("/api/cached-downloads/{cache_id}")
async def invalidate_cached_download(cache_id: str):
    """Invalidate a cached download (delegates to processing_jobs router)."""
    return await pj_invalidate_cache(cache_id)


# ═══════════════════════════════════════════════════════════════════════════
# 11. Startup & Shutdown
# ═══════════════════════════════════════════════════════════════════════════

def initialize_all_routers():
    """Initialize all routers with Supabase client."""
    sb = get_supabase()

    # Pre-existing routers
    init_account_managers_router(sb)
    init_clients_router(sb)
    init_customers_router(sb)
    init_contacts_router(sb)
    init_analytics_router(sb)
    init_admin_router(sb)
    init_ai_router(sb)
    init_rules_router(sb)
    init_quickbase_router(sb)
    init_intelligence_config_router(sb)

    error_logger = get_error_logger()
    init_error_router(
        error_tracker=None, db_error_tracker=None,
        supabase_client=sb, redis_client=None, job_error_logger=error_logger
    )

    init_auth_dependencies(sb)
    init_auth_router(sb)
    init_audit(sb)

    # New extracted routers
    init_mailboxes_router(get_supabase, run_reprocessing_fn=run_reprocessing)
    init_emails_router(get_supabase)
    init_dashboard_router(get_supabase)
    init_google_auth_router(get_supabase)
    init_processing_jobs_router(get_supabase, progress_manager, queue_manager, executor, DOWNLOAD_DIR)

    logger.info("All routers initialized")


async def startup_event():
    """Initialize services on startup."""
    global _gmail_sync_service, _outlook_sync_service

    try:
        initialize_all_routers()
    except Exception as e:
        logger.warning(f"Failed to initialize routers: {e}")

    # WebSocket
    try:
        init_connection_manager()
        init_websocket_auth(get_supabase())
        logger.info("WebSocket infrastructure initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize WebSocket: {e}")

    # Gmail sync
    try:
        _gmail_sync_service = get_gmail_sync_service(get_supabase())
        init_gmail_router(get_supabase(), _gmail_sync_service)
        pj_set_gmail(_gmail_sync_service)
        await _gmail_sync_service.start()
        logger.info("Gmail sync service started successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Gmail sync service: {e}")

    # Outlook sync
    try:
        _outlook_sync_service = get_outlook_sync_service(get_supabase())
        init_outlook_router(get_supabase(), _outlook_sync_service)
        pj_set_outlook(_outlook_sync_service)
        await _outlook_sync_service.start()
        logger.info("Outlook sync service started successfully")
    except Exception as e:
        logger.warning(f"Failed to initialize Outlook sync service: {e}")

    # Clean up orphaned jobs
    try:
        await cleanup_orphaned_jobs()
    except Exception as e:
        logger.warning(f"Failed to cleanup orphaned jobs: {e}")


async def shutdown_event():
    """Cleanup on server shutdown."""
    logger.info("=== SERVER SHUTDOWN INITIATED ===")

    for name, svc in [("Gmail", _gmail_sync_service), ("Outlook", _outlook_sync_service)]:
        try:
            if svc:
                await svc.stop()
        except Exception as e:
            logger.warning(f"Error stopping {name} sync service: {e}")

    try:
        from src.storage.parallel_downloader import cancel_all_downloads
        cancel_all_downloads()
    except Exception as e:
        logger.warning(f"Error cancelling downloads: {e}")

    sync_redis_to_database()

    try:
        if sys.version_info >= (3, 9):
            executor.shutdown(wait=False, cancel_futures=True)
        else:
            executor.shutdown(wait=False)
    except Exception as e:
        logger.warning(f"Error during executor shutdown: {e}")

    logger.info("=== SERVER SHUTDOWN COMPLETE ===")


# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
