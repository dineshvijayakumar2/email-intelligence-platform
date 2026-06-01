import os
import time
import functools
from supabase import create_client, Client
from typing import Optional, TypeVar, Callable
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


_RETRYABLE_ERROR_PATTERNS = (
    'WinError 10035',  # WSAEWOULDBLOCK — Windows httpx socket exhaustion
    'WSAEWOULDBLOCK',
    'ReadError',
    'ConnectError',
    'TimeoutException',
    'Connection reset',
    'Connection refused',
    'Temporary failure',
    # Postgres statement_timeout. A RPC/query that hit the server-side timeout
    # may finish successfully on retry when connection/cache pressure eases.
    # Listed with a narrow-ish match to avoid over-retrying other 57xxx codes.
    'canceling statement due to statement timeout',
    '57014',  # statement_timeout SQLSTATE
)


def _is_retryable_error(err: Exception) -> bool:
    s = str(err)
    return any(p in s for p in _RETRYABLE_ERROR_PATTERNS)


def with_retry(max_retries: int = 3, base_delay: float = 0.5, backoff_factor: float = 2.0):
    """
    Decorator to add retry logic for transient errors (especially Windows socket errors).

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay on each retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            delay = base_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if not _is_retryable_error(e) or attempt == max_retries:
                        raise

                    last_exception = e
                    logger.warning(
                        f"Transient error in {func.__name__} (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= backoff_factor

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper
    return decorator


async def retry_async(
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    base_delay: float = 0.5,
    backoff_factor: float = 2.0,
    label: str = "op",
) -> T:
    """Async retry helper for a zero-arg callable that runs a Supabase/HTTP call.

    Use this inside async code where the sync `with_retry` decorator won't work.
    `fn` is typically a lambda that calls `await self._db(...)` or similar.

    Example:
        result = await retry_async(
            lambda: self._db(lambda: self._sb.rpc(...).execute()),
            label="batch_update_embeddings",
        )

    Retries on the same transient error patterns as `with_retry`. Non-retryable
    errors are raised immediately. `asyncio.sleep` is used between attempts so
    the event loop is not blocked.
    """
    import asyncio
    delay = base_delay
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            if not _is_retryable_error(e) or attempt == max_retries:
                raise
            logger.warning(
                f"[retry_async] Transient error in {label} "
                f"(attempt {attempt + 1}/{max_retries + 1}): {e}. Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)
            delay *= backoff_factor
    raise RuntimeError("retry_async: unexpected exit")  # unreachable

class SupabaseClient:
    """Wrapper for Supabase client with connection management"""
    
    _instance: Optional[Client] = None
    _service_instance: Optional[Client] = None
    
    @classmethod
    def get_client(cls, use_service_key: bool = False) -> Client:
        """
        Get or create Supabase client (singleton pattern)
        
        Args:
            use_service_key: Use service role key for backend operations
        """
        if use_service_key:
            if cls._service_instance is None:
                url = os.getenv('SUPABASE_URL')
                key = os.getenv('SUPABASE_SERVICE_KEY')
                
                if not url or not key:
                    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
                
                cls._service_instance = create_client(url, key)
                logger.info("Supabase service client initialized")
            
            return cls._service_instance
        else:
            if cls._instance is None:
                url = os.getenv('SUPABASE_URL')
                key = os.getenv('SUPABASE_KEY')
                
                if not url or not key:
                    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
                
                cls._instance = create_client(url, key)
                logger.info("Supabase client initialized")
            
            return cls._instance
    
    @classmethod
    @with_retry(max_retries=3, base_delay=0.5)
    def test_connection(cls) -> bool:
        """Test database connection with automatic retry for transient errors"""
        try:
            client = cls.get_client(use_service_key=True)

            # Simple query to test connection
            result = client.table('emails').select('count').limit(1).execute()
            logger.info("Database connection test successful")
            return True

        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False


def retry_on_transient_error(func: Callable[..., T]) -> Callable[..., T]:
    """
    Convenience decorator for retrying on transient network errors.
    Use this on any function that makes Supabase/HTTP calls.

    Example:
        @retry_on_transient_error
        def fetch_data():
            return client.table('emails').select('id, subject, sender_email').execute()
    """
    return with_retry(max_retries=3, base_delay=0.5)(func)