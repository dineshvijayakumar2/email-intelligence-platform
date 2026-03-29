"""
Live Log Stream — Captures structured log entries into a Redis ring buffer.

Non-blocking: uses a background thread to flush entries to Redis.
The main logging call returns immediately with zero latency impact.
"""

import json
import logging
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_KEY = "log:stream"

# Thread-local context: set once at the start of a pipeline, inherited by all
# log calls within that thread (company_resolver, email_linker, etc.)
import threading
_thread_context = threading.local()


def set_log_context(*, mailbox_id: str = None, client_id: str = None, job_id: str = None):
    """Set thread-local log context. Called once at pipeline start."""
    if mailbox_id:
        _thread_context.mailbox_id = mailbox_id
    if client_id:
        _thread_context.client_id = client_id
    if job_id:
        _thread_context.job_id = job_id


def clear_log_context():
    """Clear thread-local context at pipeline end."""
    for attr in ('mailbox_id', 'client_id', 'job_id'):
        if hasattr(_thread_context, attr):
            delattr(_thread_context, attr)
MAX_ENTRIES = 500
FLUSH_INTERVAL = 1.0  # seconds between Redis flushes
BATCH_SIZE = 50       # max entries per flush

# Patterns to extract context from log messages
_MAILBOX_RE = re.compile(r'mailbox[_ ](?:id)?[=: ]*([0-9a-f-]{36})', re.IGNORECASE)
_CLIENT_RE = re.compile(r'client[_ ](?:id)?[=: ]*([0-9a-f-]{36})', re.IGNORECASE)
_JOB_RE = re.compile(r'job[_ ](?:id)?[=: ]*([0-9a-f-]{36})', re.IGNORECASE)
_STEP_RE = re.compile(r'Step (\d+)(?:/\d+)?', re.IGNORECASE)

# Service name mapping from logger names
_SERVICE_MAP = {
    'src.services.extraction_orchestrator': 'extraction',
    'src.services.quickbase_sync': 'qb_sync',
    'src.services.quickbase_client': 'qb_api',
    'src.services.ai_email_analyzer': 'ai_analysis',
    'src.services.ai_digest_generator': 'ai_digest',
    'src.services.ai_insights_engine': 'ai_insights',
    'src.services.vector_service': 'vector',
    'src.services.capability_classifier': 'classifier',
    'src.services.gmail_sync_service': 'gmail_sync',
    'src.services.outlook_sync_service': 'outlook_sync',
    'src.services.email_linker': 'email_linker',
    'src.services.engagement_scorer': 'engagement',
    'src.services.thread_tracker': 'threads',
    'src.services.comm_pattern_analyzer': 'patterns',
    'src.services.customer_analytics_service': 'analytics',
    'src.services.recommendation_engine': 'recommendations',
    'src.routers.quickbase': 'qb_router',
    'src.routers.analytics': 'analytics_router',
    'src.routers.ai': 'ai_router',
    'src.routers.intelligence_config': 'config_router',
    'main': 'main',
}


class LogStreamHandler(logging.Handler):
    """Non-blocking logging handler that captures entries for live monitoring.

    Entries are queued in memory and flushed to Redis in a background thread.
    The emit() call is O(1) — just appends to a deque.
    """

    def __init__(self, redis_client=None, level=logging.INFO):
        super().__init__(level)
        self._queue: deque = deque(maxlen=MAX_ENTRIES * 2)  # in-memory buffer
        self._redis = redis_client
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def set_redis(self, redis_client):
        """Set Redis client (deferred init to avoid import cycles)."""
        self._redis = redis_client
        if not self._running:
            self._start_flush_thread()

    def _start_flush_thread(self):
        self._running = True
        self._thread = threading.Thread(target=self._flush_loop, daemon=True, name="log-stream-flush")
        self._thread.start()

    def _flush_loop(self):
        while self._running:
            try:
                self._flush_batch()
            except Exception:
                pass  # never crash the flush thread
            time.sleep(FLUSH_INTERVAL)

    def _flush_batch(self):
        if not self._redis or not self._queue:
            return
        batch = []
        for _ in range(min(BATCH_SIZE, len(self._queue))):
            try:
                batch.append(self._queue.popleft())
            except IndexError:
                break
        if not batch:
            return
        pipe = self._redis.pipeline(transaction=False)
        for entry in batch:
            pipe.lpush(REDIS_KEY, entry)
        pipe.ltrim(REDIS_KEY, 0, MAX_ENTRIES - 1)
        pipe.execute()

    def emit(self, record: logging.LogRecord):
        """Non-blocking: serialize and queue the log entry."""
        try:
            entry = self._format_entry(record)
            self._queue.append(json.dumps(entry, default=str))
        except Exception:
            pass  # never fail the caller's log call

    def _format_entry(self, record: logging.LogRecord) -> dict:
        msg = record.getMessage()

        # 1. Prefer explicit context from extra={} kwargs (structured logging)
        mailbox_id = getattr(record, 'mailbox_id', None)
        client_id = getattr(record, 'client_id', None)
        job_id = getattr(record, 'job_id', None)
        step = getattr(record, 'step', None)

        # 2. Fallback: thread-local context (set once at pipeline start)
        if not mailbox_id:
            mailbox_id = getattr(_thread_context, 'mailbox_id', None)
        if not client_id:
            client_id = getattr(_thread_context, 'client_id', None)
        if not job_id:
            job_id = getattr(_thread_context, 'job_id', None)

        # 3. Last resort: extract from message text (legacy log calls)
        if not mailbox_id:
            mailbox_id = _extract(_MAILBOX_RE, msg)
        if not client_id:
            client_id = _extract(_CLIENT_RE, msg)
        if not job_id:
            job_id = _extract(_JOB_RE, msg)
        if not step:
            step = _extract(_STEP_RE, msg)

        # Map logger name to short service name
        service = _SERVICE_MAP.get(record.name, record.name.split('.')[-1])

        return {
            'ts': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'service': service,
            'message': msg[:500],  # cap message length
            'mailbox_id': mailbox_id,
            'client_id': client_id,
            'job_id': job_id,
            'step': step,
        }

    def close(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        # Final flush
        try:
            self._flush_batch()
        except Exception:
            pass
        super().close()


def _extract(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(1) if m else None


# Singleton handler instance — attached to root logger in main.py
_handler: Optional[LogStreamHandler] = None


def get_log_stream_handler() -> LogStreamHandler:
    global _handler
    if _handler is None:
        _handler = LogStreamHandler(level=logging.INFO)
    return _handler


def init_log_stream(redis_client):
    """Call after Redis is available to start the flush thread."""
    handler = get_log_stream_handler()
    handler.set_redis(redis_client)
    logger.info("Log stream handler initialized with Redis")


def get_recent_logs(
    redis_client,
    limit: int = 100,
    level: Optional[str] = None,
    service: Optional[str] = None,
    search: Optional[str] = None,
    mailbox_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> list[dict]:
    """Read recent log entries from Redis with optional filtering."""
    has_filter = any([level, service, search, mailbox_id, client_id])
    fetch_count = limit * 3 if has_filter else limit
    raw = redis_client.lrange(REDIS_KEY, 0, min(fetch_count, MAX_ENTRIES) - 1)

    entries = []
    for item in raw:
        try:
            entry = json.loads(item)
        except (json.JSONDecodeError, TypeError):
            continue

        # Apply filters
        if level and entry.get('level') != level.upper():
            continue
        if service and entry.get('service') != service:
            continue
        if search and search.lower() not in (entry.get('message') or '').lower():
            continue
        if mailbox_id and entry.get('mailbox_id') != mailbox_id:
            continue
        if client_id and entry.get('client_id') != client_id:
            continue

        entries.append(entry)
        if len(entries) >= limit:
            break

    return entries
