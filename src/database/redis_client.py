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
        # Get TTL from environment or use default of 7 days
        ttl_days = int(os.getenv('REDIS_TTL_DAYS', '7'))
        self.default_ttl = timedelta(days=ttl_days)  # Auto-cleanup after configured days

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
                'total_records': int(data.get('total_records', 0)) if data.get('total_records') else None,
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
