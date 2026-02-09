"""
WebSocket Routes

FastAPI WebSocket endpoint for real-time job updates.
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from .manager import get_connection_manager, init_connection_manager
from .auth import authenticate_websocket, get_accessible_mailbox_ids_for_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token")
):
    """
    Main WebSocket endpoint for real-time updates.

    Connection flow:
    1. Client connects with ?token=<jwt>
    2. Server validates JWT, gets user info
    3. Server registers connection
    4. Client sends subscription messages
    5. Server pushes updates based on subscriptions

    Client message format:
        { "type": "subscribe", "room": "jobs:all" }
        { "type": "unsubscribe", "room": "jobs:abc123" }
        { "type": "ping" }

    Server message format:
        { "type": "connected", "data": { "connectionId": "...", "user": {...} } }
        { "type": "subscribed", "room": "jobs:all" }
        { "type": "job_update", "data": { "job_id": "...", "status": "...", ... } }
        { "type": "pong" }
        { "type": "error", "data": { "message": "..." } }
    """
    manager = get_connection_manager()
    if not manager:
        logger.error("[WebSocket] Connection manager not initialized")
        await websocket.close(code=1011, reason="Server not ready")
        return

    connection_id = None

    try:
        # Authenticate user
        user = await authenticate_websocket(token)
        logger.info(f"[WebSocket] User authenticated: {user.get('email', user['user_id'])}")

        # Get accessible mailbox IDs for RBAC
        accessible_mailbox_ids = await get_accessible_mailbox_ids_for_user(user['user_id'])
        user['accessible_mailbox_ids'] = accessible_mailbox_ids

        # Register connection
        connection_id = await manager.connect(websocket, user)

        # Message loop
        while True:
            try:
                data = await websocket.receive_json()
                await manager.handle_client_message(connection_id, data)
            except ValueError as e:
                # Invalid JSON
                logger.warning(f"[WebSocket] Invalid JSON from {connection_id}: {e}")
                await manager.send_personal(connection_id, {
                    'type': 'error',
                    'data': {'message': 'Invalid JSON message'},
                })

    except WebSocketDisconnect:
        logger.info(f"[WebSocket] Client disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"[WebSocket] Error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e)[:120])
        except Exception:
            pass
    finally:
        if connection_id:
            await manager.disconnect(connection_id)


@router.get("/ws/stats")
async def websocket_stats():
    """
    Get WebSocket connection statistics.

    Returns connection counts, room counts, and message stats.
    Useful for monitoring and debugging.
    """
    manager = get_connection_manager()
    if not manager:
        return {
            'status': 'not_initialized',
            'active_connections': 0,
        }

    return {
        'status': 'ok',
        **manager.get_stats(),
    }
