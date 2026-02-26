"""
WebSocket Connection Manager

Manages WebSocket connections, subscriptions, and broadcasts with RBAC filtering.

Room naming convention:
- "jobs:all" - All jobs (filtered by user's accessible mailboxes)
- "jobs:{job_id}" - Specific job updates
- "mailbox:{mailbox_id}" - All jobs for a specific mailbox
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Singleton instance
_manager: Optional['ConnectionManager'] = None


def get_connection_manager() -> Optional['ConnectionManager']:
    """Get the global connection manager instance."""
    return _manager


def init_connection_manager() -> 'ConnectionManager':
    """Initialize the global connection manager."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
        logger.info("[WebSocket] Connection manager initialized")
    return _manager


class ConnectionManager:
    """
    Manages WebSocket connections and room subscriptions.

    Handles:
    - Connection lifecycle (connect, disconnect)
    - Room subscriptions (subscribe, unsubscribe)
    - Broadcasting messages with RBAC filtering
    - Connection health monitoring
    """

    def __init__(self):
        # Active WebSocket connections: connection_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

        # User to connections mapping: user_id -> set of connection_ids
        self.user_connections: Dict[str, Set[str]] = {}

        # Room subscriptions: room_name -> set of connection_ids
        self.subscriptions: Dict[str, Set[str]] = {}

        # Connection metadata: connection_id -> user info dict
        self.connection_users: Dict[str, dict] = {}

        # Statistics
        self.stats = {
            'total_connections': 0,
            'total_messages_sent': 0,
            'total_broadcasts': 0,
        }

        logger.info("[WebSocket] ConnectionManager created")

    async def connect(self, websocket: WebSocket, user: dict) -> str:
        """
        Register a new WebSocket connection.

        Args:
            websocket: The WebSocket connection
            user: User info dict with user_id, email, roles, accessible_mailbox_ids

        Returns:
            Connection ID (UUID string)
        """
        await websocket.accept()

        connection_id = str(uuid.uuid4())
        user_id = user['user_id']

        # Store connection
        self.active_connections[connection_id] = websocket
        self.connection_users[connection_id] = {
            **user,
            'connected_at': datetime.utcnow().isoformat(),
        }

        # Track user's connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)

        self.stats['total_connections'] += 1

        logger.info(f"[WebSocket] Client connected: {connection_id} (user: {user.get('email', user_id)})")

        # Send connection confirmation
        await self.send_personal(connection_id, {
            'type': 'connected',
            'data': {
                'connectionId': connection_id,
                'user': {
                    'id': user_id,
                    'email': user.get('email'),
                    'roles': user.get('roles', []),
                }
            },
            'timestamp': datetime.utcnow().isoformat(),
        })

        return connection_id

    async def disconnect(self, connection_id: str):
        """
        Clean up a disconnected WebSocket.

        Args:
            connection_id: The connection to remove
        """
        if connection_id not in self.active_connections:
            return

        # Get user info before cleanup
        user_info = self.connection_users.get(connection_id, {})
        user_id = user_info.get('user_id')

        # Remove from active connections
        del self.active_connections[connection_id]

        # Remove from user tracking
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        # Remove from all subscriptions
        for room, connections in list(self.subscriptions.items()):
            connections.discard(connection_id)
            if not connections:
                del self.subscriptions[room]

        # Remove connection metadata
        if connection_id in self.connection_users:
            del self.connection_users[connection_id]

        logger.info(f"[WebSocket] Client disconnected: {connection_id}")

    async def subscribe(self, connection_id: str, room: str) -> bool:
        """
        Subscribe a connection to a room.

        Args:
            connection_id: The connection ID
            room: Room name (e.g., "jobs:all", "jobs:{job_id}", "mailbox:{mailbox_id}")

        Returns:
            True if subscription was successful
        """
        if connection_id not in self.active_connections:
            logger.warning(f"[WebSocket] Subscribe failed: connection {connection_id} not found")
            return False

        # Validate room name
        if not self._validate_room(room, connection_id):
            await self.send_personal(connection_id, {
                'type': 'error',
                'data': {'message': f'Invalid or unauthorized room: {room}'},
                'timestamp': datetime.utcnow().isoformat(),
            })
            return False

        # Add to subscription
        if room not in self.subscriptions:
            self.subscriptions[room] = set()
        self.subscriptions[room].add(connection_id)

        logger.debug(f"[WebSocket] {connection_id} subscribed to {room}")

        # Confirm subscription
        await self.send_personal(connection_id, {
            'type': 'subscribed',
            'room': room,
            'timestamp': datetime.utcnow().isoformat(),
        })

        return True

    async def unsubscribe(self, connection_id: str, room: str):
        """
        Unsubscribe a connection from a room.

        Args:
            connection_id: The connection ID
            room: Room name
        """
        if room in self.subscriptions:
            self.subscriptions[room].discard(connection_id)
            if not self.subscriptions[room]:
                del self.subscriptions[room]

        logger.debug(f"[WebSocket] {connection_id} unsubscribed from {room}")

        # Confirm unsubscription
        if connection_id in self.active_connections:
            await self.send_personal(connection_id, {
                'type': 'unsubscribed',
                'room': room,
                'timestamp': datetime.utcnow().isoformat(),
            })

    def _validate_room(self, room: str, connection_id: str) -> bool:
        """
        Validate that a room name is valid and the user can access it.

        Args:
            room: Room name to validate
            connection_id: Connection requesting access

        Returns:
            True if room is valid and accessible
        """
        # Valid room patterns:
        # - jobs:all
        # - jobs:{uuid}
        # - mailbox:{uuid}

        if room == 'jobs:all':
            return True

        parts = room.split(':', 1)
        if len(parts) != 2:
            return False

        prefix, identifier = parts

        if prefix == 'jobs':
            # Allow subscription to any specific job
            # RBAC filtering happens at broadcast time
            return True

        if prefix == 'mailbox':
            # Check if user has access to this mailbox
            user_info = self.connection_users.get(connection_id, {})
            accessible_ids = user_info.get('accessible_mailbox_ids', [])
            return identifier in accessible_ids

        return False

    async def send_personal(self, connection_id: str, message: dict):
        """
        Send a message to a specific connection.

        Args:
            connection_id: Target connection
            message: Message dict to send
        """
        websocket = self.active_connections.get(connection_id)
        if not websocket:
            logger.warning(f"[WebSocket] Connection {connection_id} not found")
            return

        try:
            await websocket.send_json(message)
            self.stats['total_messages_sent'] += 1
        except RuntimeError as e:
            # WebSocket state errors (not connected, already closed, need to accept first, etc.)
            error_str = str(e).lower()
            if "not connected" in error_str or "accept" in error_str or "closed" in error_str:
                logger.debug(f"[WebSocket] Connection {connection_id} invalid state: {e}")
            else:
                logger.error(f"[WebSocket] Runtime error sending to {connection_id}: {e}")
            # Connection is in bad state, clean it up
            await self.disconnect(connection_id)
        except Exception as e:
            logger.error(f"[WebSocket] Unexpected error sending to {connection_id}: {e}")
            # Connection may be dead, clean it up
            await self.disconnect(connection_id)

    async def broadcast_to_room(self, room: str, message: dict, exclude: Set[str] = None):
        """
        Broadcast a message to all connections in a room with RBAC filtering.

        Args:
            room: Target room
            message: Message dict to send
            exclude: Optional set of connection_ids to exclude
        """
        if room not in self.subscriptions:
            return

        exclude = exclude or set()
        connections = self.subscriptions[room].copy()

        self.stats['total_broadcasts'] += 1

        tasks = []
        for conn_id in connections:
            if conn_id in exclude:
                continue

            # RBAC filtering for job updates
            if message.get('type') == 'job_update':
                if not self._can_see_job(conn_id, message.get('data', {})):
                    continue

            tasks.append(self.send_personal(conn_id, message))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _can_see_job(self, connection_id: str, job_data: dict) -> bool:
        """
        Check if a connection can see a job update based on RBAC.

        Args:
            connection_id: The connection
            job_data: Job update data containing mailbox_id

        Returns:
            True if user can see this job
        """
        user_info = self.connection_users.get(connection_id)
        if not user_info:
            return False

        # Admins can see all jobs
        roles = user_info.get('roles', [])
        if 'admin' in roles:
            return True

        # Check if job's mailbox is accessible
        job_mailbox_id = job_data.get('mailbox_id')
        if not job_mailbox_id:
            return True  # No mailbox restriction

        accessible_ids = user_info.get('accessible_mailbox_ids', [])
        return job_mailbox_id in accessible_ids

    async def broadcast_job_update(self, job_id: str, mailbox_id: str, update_data: dict):
        """
        Broadcast a job update to relevant subscribers.

        This is the main method called when job progress changes.

        Args:
            job_id: The job ID
            mailbox_id: The mailbox ID (for RBAC filtering)
            update_data: Job progress data
        """
        message = {
            'type': 'job_update',
            'data': {
                'job_id': job_id,
                'mailbox_id': mailbox_id,
                **update_data,
            },
            'timestamp': datetime.utcnow().isoformat(),
        }

        # Broadcast to job-specific room
        await self.broadcast_to_room(f'jobs:{job_id}', message)

        # Broadcast to mailbox room
        await self.broadcast_to_room(f'mailbox:{mailbox_id}', message)

        # Broadcast to all-jobs room (with RBAC filtering)
        await self.broadcast_to_room('jobs:all', message)

    async def handle_client_message(self, connection_id: str, data: dict):
        """
        Handle an incoming message from a client.

        Args:
            connection_id: The sending connection
            data: Parsed JSON message
        """
        msg_type = data.get('type')

        if msg_type == 'subscribe':
            room = data.get('room')
            if room:
                await self.subscribe(connection_id, room)
            else:
                await self.send_personal(connection_id, {
                    'type': 'error',
                    'data': {'message': 'Missing room in subscribe message'},
                    'timestamp': datetime.utcnow().isoformat(),
                })

        elif msg_type == 'unsubscribe':
            room = data.get('room')
            if room:
                await self.unsubscribe(connection_id, room)

        elif msg_type == 'ping':
            await self.send_personal(connection_id, {
                'type': 'pong',
                'timestamp': datetime.utcnow().isoformat(),
            })

        else:
            logger.warning(f"[WebSocket] Unknown message type: {msg_type}")
            await self.send_personal(connection_id, {
                'type': 'error',
                'data': {'message': f'Unknown message type: {msg_type}'},
                'timestamp': datetime.utcnow().isoformat(),
            })

    def get_stats(self) -> dict:
        """Get connection manager statistics."""
        return {
            **self.stats,
            'active_connections': len(self.active_connections),
            'active_users': len(self.user_connections),
            'active_rooms': len(self.subscriptions),
        }

    def get_user_connection_count(self, user_id: str) -> int:
        """Get number of active connections for a user."""
        return len(self.user_connections.get(user_id, set()))
