"""
Redis client wrapper for job progress tracking and queue management
"""
import os
import redis
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import timedelta

logger = logging.getLogger(__name__)


class RedisClient:
    """Wrapper for Redis client with connection management"""

    _instance: Optional[redis.Redis] = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        """
        Get or create Redis client (singleton pattern)

        Returns:
            Redis client instance
        """
        if cls._instance is None:
            # Get Redis connection URL from environment
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
            
            # Parse Redis URL or use individual settings
            if redis_url.startswith('redis://'):
                cls._instance = redis.from_url(
                    redis_url,
                    decode_responses=True,  # Automatically decode responses to strings
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
            else:
                # Fallback to individual settings for backward compatibility
                redis_host = os.getenv('REDIS_HOST', 'localhost')
                redis_port = int(os.getenv('REDIS_PORT', '6379'))
                redis_db = int(os.getenv('REDIS_DB', '0'))
                redis_password = os.getenv('REDIS_PASSWORD', None)

                cls._instance = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    password=redis_password,
                    decode_responses=True,  # Automatically decode responses to strings
                    socket_connect_timeout=5,
                    socket_timeout=5
                )

            # Test connection
            try:
                cls._instance.ping()
                if redis_url.startswith('redis://'):
                    logger.info(f"Redis client initialized successfully using URL: {redis_url}")
                else:
                    logger.info(f"Redis client initialized successfully (host={redis_host}, port={redis_port}, db={redis_db})")
            except redis.ConnectionError as e:
                logger.error(f"Failed to connect to Redis: {e}")
                cls._instance = None
                raise

        return cls._instance

    @classmethod
    def test_connection(cls) -> bool:
        """Test Redis connection"""
        try:
            client = cls.get_client()
            client.ping()
            logger.info("Redis connection test successful")
            return True
        except Exception as e:
            logger.error(f"Redis connection test failed: {e}")
            return False


class JobProgressManager:
    """Manages job progress tracking in Redis"""

    def __init__(self):
        self.client = RedisClient.get_client()
        self.progress_prefix = "job:progress:"
        self.queue_prefix = "job:queue:"
        self.errors_prefix = "job:errors:"
        self.error_counts_prefix = "job:error_counts:"
        # Get TTL from environment or use default of 7 days
        ttl_days = int(os.getenv('REDIS_TTL_DAYS', '7'))
        self.default_ttl = timedelta(days=ttl_days)  # Auto-cleanup after configured days
        self.max_sample_errors = 50  # Maximum sample errors to store per job

    def _progress_key(self, job_id: str) -> str:
        """Generate Redis key for job progress"""
        return f"{self.progress_prefix}{job_id}"

    def update_progress(self, job_id: str, processed: int, failed: int = 0, **kwargs) -> bool:
        """
        Update job progress in Redis

        Args:
            job_id: Job ID
            processed: Number of emails processed
            failed: Number of failed emails
            **kwargs: Additional fields to store (status, total_records, etc.)

        Returns:
            True if successful
        """
        try:
            key = self._progress_key(job_id)
            data = {
                'processed': processed,
                'failed': failed,
                **kwargs
            }

            # Redis doesn't accept boolean values - convert to strings
            for k, v in data.items():
                if isinstance(v, bool):
                    data[k] = 'true' if v else 'false'

            # Store as hash for efficient partial updates
            self.client.hset(key, mapping=data)

            # Set TTL for auto-cleanup
            self.client.expire(key, self.default_ttl)

            return True
        except Exception as e:
            logger.error(f"Failed to update progress in Redis for job {job_id}: {e}")
            return False

    def get_progress(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job progress from Redis

        Args:
            job_id: Job ID

        Returns:
            Dictionary with progress data or None if not found
        """
        try:
            key = self._progress_key(job_id)
            data = self.client.hgetall(key)

            if not data:
                return None

            # Convert string values to appropriate types
            return {
                'processed': int(data.get('processed', 0)),
                'failed': int(data.get('failed', 0)),
                'status': data.get('status'),
                'total_records': int(data.get('total_records', 0)) if data.get('total_records') else 0,
                **{k: v for k, v in data.items() if k not in ['processed', 'failed', 'status', 'total_records']}
            }
        except Exception as e:
            logger.error(f"Failed to get progress from Redis for job {job_id}: {e}")
            return None

    def increment_progress(self, job_id: str, by: int = 1) -> int:
        """
        Atomically increment job progress counter

        Args:
            job_id: Job ID
            by: Amount to increment by (default 1)

        Returns:
            New progress value
        """
        try:
            key = self._progress_key(job_id)
            new_value = self.client.hincrby(key, 'processed', by)
            self.client.expire(key, self.default_ttl)
            return new_value
        except Exception as e:
            logger.error(f"Failed to increment progress in Redis for job {job_id}: {e}")
            return 0

    def delete_progress(self, job_id: str) -> bool:
        """
        Delete job progress from Redis

        Args:
            job_id: Job ID

        Returns:
            True if successful
        """
        try:
            key = self._progress_key(job_id)
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete progress from Redis for job {job_id}: {e}")
            return False

    def get_all_active_jobs(self) -> List[str]:
        """
        Get all active job IDs from Redis

        Returns:
            List of job IDs
        """
        try:
            pattern = f"{self.progress_prefix}*"
            keys = self.client.keys(pattern)
            # Extract job IDs from keys
            return [key.replace(self.progress_prefix, '') for key in keys]
        except Exception as e:
            logger.error(f"Failed to get active jobs from Redis: {e}")
            return []

    # =========================================================================
    # Error Tracking Methods (Stage 2)
    # =========================================================================

    def _errors_key(self, job_id: str) -> str:
        """Generate Redis key for job errors list"""
        return f"{self.errors_prefix}{job_id}"

    def _error_counts_key(self, job_id: str) -> str:
        """Generate Redis key for error counts"""
        return f"{self.error_counts_prefix}{job_id}"

    def track_error(
        self,
        job_id: str,
        error_type: str,
        error_message: str,
        email_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Track a processing error for a job.

        Args:
            job_id: Job ID
            error_type: Type of error (encoding_error, parse_error, etc.)
            error_message: Error message/description
            email_info: Optional dict with email details (message_id, subject, sender)

        Returns:
            True if successful
        """
        try:
            from datetime import datetime

            errors_key = self._errors_key(job_id)
            counts_key = self._error_counts_key(job_id)

            # Build error record
            error_record = {
                'error_type': error_type,
                'error_message': error_message[:500],  # Truncate long messages
                'timestamp': datetime.utcnow().isoformat(),
                **(email_info or {})
            }

            # Store error in list (limited to max_sample_errors)
            self.client.lpush(errors_key, json.dumps(error_record))
            self.client.ltrim(errors_key, 0, self.max_sample_errors - 1)
            self.client.expire(errors_key, self.default_ttl)

            # Increment error type counter
            self.client.hincrby(counts_key, error_type, 1)
            self.client.hincrby(counts_key, 'total', 1)
            self.client.expire(counts_key, self.default_ttl)

            # Also increment the failed counter in progress
            self.increment_failed(job_id)

            return True
        except Exception as e:
            logger.error(f"Failed to track error in Redis for job {job_id}: {e}")
            return False

    def increment_failed(self, job_id: str, by: int = 1) -> int:
        """
        Atomically increment job failed counter

        Args:
            job_id: Job ID
            by: Amount to increment by (default 1)

        Returns:
            New failed value
        """
        try:
            key = self._progress_key(job_id)
            new_value = self.client.hincrby(key, 'failed', by)
            self.client.expire(key, self.default_ttl)
            return new_value
        except Exception as e:
            logger.error(f"Failed to increment failed count in Redis for job {job_id}: {e}")
            return 0

    def get_errors(self, job_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        Get recent errors for a job.

        Args:
            job_id: Job ID
            limit: Maximum number of errors to return
            offset: Offset for pagination

        Returns:
            List of error dictionaries
        """
        try:
            errors_key = self._errors_key(job_id)
            errors_raw = self.client.lrange(errors_key, offset, offset + limit - 1)
            return [json.loads(e) for e in errors_raw]
        except Exception as e:
            logger.error(f"Failed to get errors from Redis for job {job_id}: {e}")
            return []

    def get_error_counts(self, job_id: str) -> Dict[str, int]:
        """
        Get error counts by type for a job.

        Returns:
            Dictionary with error type as key and count as value
        """
        try:
            counts_key = self._error_counts_key(job_id)
            counts = self.client.hgetall(counts_key)
            return {k: int(v) for k, v in counts.items()}
        except Exception as e:
            logger.error(f"Failed to get error counts from Redis for job {job_id}: {e}")
            return {}

    def get_error_summary(self, job_id: str) -> Dict[str, Any]:
        """
        Get comprehensive error summary for a job.

        Returns:
            Dictionary with total_errors, error_types breakdown, and sample_errors
        """
        counts = self.get_error_counts(job_id)
        sample_errors = self.get_errors(job_id, limit=10)

        total = counts.pop('total', 0)

        # Error type descriptions
        error_descriptions = {
            'encoding_error': 'Character encoding issues',
            'parse_error': 'Failed to parse email structure',
            'timeout_error': 'Processing timed out',
            'connection_error': 'Database or network connection failed',
            'duplicate_error': 'Duplicate email detected',
            'memory_error': 'Insufficient memory',
            'permission_error': 'Access denied',
            'other_error': 'Unclassified error'
        }

        error_types_with_desc = {}
        for error_type, count in counts.items():
            error_types_with_desc[error_type] = {
                'count': count,
                'description': error_descriptions.get(error_type, 'Unknown error type')
            }

        return {
            'total_errors': total,
            'error_types': error_types_with_desc,
            'sample_errors': sample_errors,
            'has_more_errors': total > len(sample_errors)
        }

    def build_error_summary_json(self, job_id: str) -> Dict:
        """
        Build error summary JSON for database storage.

        Called when a job completes to persist the error summary.
        """
        from datetime import datetime

        summary = self.get_error_summary(job_id)
        return {
            'total_errors': summary['total_errors'],
            'error_types': {
                k: v['count'] for k, v in summary['error_types'].items()
            },
            'sample_errors': summary['sample_errors'][:10],
            'generated_at': datetime.utcnow().isoformat()
        }

    def clear_errors(self, job_id: str) -> bool:
        """Clear all errors for a job from Redis"""
        try:
            self.client.delete(self._errors_key(job_id))
            self.client.delete(self._error_counts_key(job_id))
            logger.info(f"Cleared errors for job {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear errors for job {job_id}: {e}")
            return False


class JobQueueManager:
    """Manages job queues in Redis"""

    def __init__(self):
        self.client = RedisClient.get_client()
        self.queue_key = "job:queue:pending"

    def enqueue(self, job_id: str, priority: int = 0) -> bool:
        """
        Add job to pending queue

        Args:
            job_id: Job ID
            priority: Priority score (higher = processed first)

        Returns:
            True if successful
        """
        try:
            self.client.zadd(self.queue_key, {job_id: priority})
            logger.info(f"Enqueued job {job_id} with priority {priority}")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue job {job_id}: {e}")
            return False

    def dequeue(self) -> Optional[str]:
        """
        Get next job from queue (highest priority)

        Returns:
            Job ID or None if queue is empty
        """
        try:
            # Get highest priority job and remove it atomically
            result = self.client.zpopmax(self.queue_key)
            if result:
                job_id, priority = result[0]
                logger.info(f"Dequeued job {job_id} (priority: {priority})")
                return job_id
            return None
        except Exception as e:
            logger.error(f"Failed to dequeue job: {e}")
            return None

    def get_queue_size(self) -> int:
        """Get number of jobs in queue"""
        try:
            return self.client.zcard(self.queue_key)
        except Exception as e:
            logger.error(f"Failed to get queue size: {e}")
            return 0

    def remove_from_queue(self, job_id: str) -> bool:
        """Remove specific job from queue"""
        try:
            self.client.zrem(self.queue_key, job_id)
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id} from queue: {e}")
            return False
