"""
WebSocket Module for Real-Time Updates

Provides WebSocket infrastructure for pushing real-time job progress updates
to connected clients, replacing polling-based updates.

Components:
- manager.py: Connection and subscription management
- auth.py: JWT authentication for WebSocket connections
- routes.py: FastAPI WebSocket endpoint
"""

from .manager import ConnectionManager, get_connection_manager
from .auth import authenticate_websocket

__all__ = [
    'ConnectionManager',
    'get_connection_manager',
    'authenticate_websocket',
]
