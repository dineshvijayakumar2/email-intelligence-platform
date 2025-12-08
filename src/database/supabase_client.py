import os
from supabase import create_client, Client
from typing import Optional
import logging

logger = logging.getLogger(__name__)

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
    def test_connection(cls) -> bool:
        """Test database connection"""
        try:
            client = cls.get_client(use_service_key=True)
            
            # Simple query to test connection
            result = client.table('emails').select('count').limit(1).execute()
            logger.info("Database connection test successful")
            return True
            
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False