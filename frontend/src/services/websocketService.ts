/**
 * WebSocket Service for Real-Time Updates
 *
 * Manages WebSocket connection lifecycle, subscriptions, and auto-reconnection.
 * Provides real-time job progress updates to replace polling.
 */

import config from '../config';
import { getAccessToken } from '../lib/supabase';

// Message types
export interface JobUpdate {
  job_id: string;
  mailbox_id: string;
  status: 'pending' | 'running' | 'downloading' | 'completed' | 'failed' | 'stopped' | 'interrupted';
  processed_records: number;
  failed_records: number;
  filtered_records?: number;
  total_records: number;
  progress_percent?: number;
  emails_per_second?: number;
  estimated_seconds_remaining?: number;
  download_percent?: number;
  download_speed_mbps?: number;
}

export interface ServerMessage {
  type: 'connected' | 'subscribed' | 'unsubscribed' | 'job_update' | 'error' | 'pong';
  room?: string;
  data?: any;
  timestamp?: string;
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';
export type ConnectionListener = (status: ConnectionStatus) => void;
export type MessageListener = (message: ServerMessage) => void;

class WebSocketService {
  private socket: WebSocket | null = null;
  private connectionStatus: ConnectionStatus = 'disconnected';
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1 second
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  // Subscriptions: room -> set of callbacks
  private subscriptions = new Map<string, Set<(data: JobUpdate) => void>>();

  // Connection status listeners
  private connectionListeners = new Set<ConnectionListener>();

  // Message listeners (for debugging/logging)
  private messageListeners = new Set<MessageListener>();

  // Message queue for messages sent while disconnected
  private messageQueue: any[] = [];

  /**
   * Connect to the WebSocket server.
   */
  async connect(): Promise<void> {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    if (this.connectionStatus === 'connecting') {
      return; // Already connecting
    }

    try {
      this.setConnectionStatus('connecting');

      const token = await getAccessToken();
      if (!token) {
        console.warn('[WebSocket] Not authenticated, skipping connection');
        this.setConnectionStatus('disconnected');
        return;
      }

      const wsUrl = `${config.wsBaseUrl}/ws?token=${encodeURIComponent(token)}`;
      console.log('[WebSocket] Connecting to', wsUrl.replace(/token=.*/, 'token=***'));

      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => this.handleOpen();
      this.socket.onclose = (event) => this.handleClose(event);
      this.socket.onerror = (error) => this.handleError(error);
      this.socket.onmessage = (event) => this.handleMessage(event);

    } catch (error) {
      console.error('[WebSocket] Connection error:', error);
      this.setConnectionStatus('error');
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from the WebSocket server.
   */
  disconnect(): void {
    this.clearReconnectTimer();
    this.clearPingInterval();

    if (this.socket) {
      this.socket.onclose = null; // Prevent handleClose from reconnecting
      this.socket.close(1000, 'Client disconnect');
      this.socket = null;
    }

    this.setConnectionStatus('disconnected');
    this.subscriptions.clear();
    this.messageQueue = [];
    this.reconnectAttempts = 0;
  }

  /**
   * Subscribe to a room for updates.
   *
   * @param room Room name (e.g., "jobs:all", "jobs:{job_id}", "mailbox:{mailbox_id}")
   * @param callback Callback for job updates
   * @returns Unsubscribe function
   */
  subscribe(room: string, callback: (data: JobUpdate) => void): () => void {
    // Add to local subscriptions
    if (!this.subscriptions.has(room)) {
      this.subscriptions.set(room, new Set());

      // Send subscribe message if connected
      this.send({ type: 'subscribe', room });
    }

    this.subscriptions.get(room)!.add(callback);

    // Return unsubscribe function
    return () => {
      const subs = this.subscriptions.get(room);
      if (subs) {
        subs.delete(callback);
        if (subs.size === 0) {
          this.subscriptions.delete(room);
          this.send({ type: 'unsubscribe', room });
        }
      }
    };
  }

  /**
   * Add a connection status listener.
   */
  onConnectionChange(listener: ConnectionListener): () => void {
    this.connectionListeners.add(listener);
    // Immediately notify of current status
    listener(this.connectionStatus);
    return () => this.connectionListeners.delete(listener);
  }

  /**
   * Add a message listener (for debugging).
   */
  onMessage(listener: MessageListener): () => void {
    this.messageListeners.add(listener);
    return () => this.messageListeners.delete(listener);
  }

  /**
   * Get current connection status.
   */
  getConnectionStatus(): ConnectionStatus {
    return this.connectionStatus;
  }

  /**
   * Check if connected.
   */
  isConnected(): boolean {
    return this.connectionStatus === 'connected';
  }

  // --- Private methods ---

  private handleOpen(): void {
    console.log('[WebSocket] Connected');
    this.reconnectAttempts = 0;
    this.setConnectionStatus('connected');

    // Re-subscribe to all rooms
    for (const room of this.subscriptions.keys()) {
      this.send({ type: 'subscribe', room });
    }

    // Send any queued messages
    while (this.messageQueue.length > 0) {
      const msg = this.messageQueue.shift();
      this.send(msg);
    }

    // Start ping interval
    this.startPingInterval();
  }

  private handleClose(event: CloseEvent): void {
    console.log('[WebSocket] Disconnected:', event.code, event.reason);
    this.socket = null;
    this.clearPingInterval();

    if (event.code === 1000) {
      // Normal close - don't reconnect
      this.setConnectionStatus('disconnected');
    } else {
      // Unexpected close - try to reconnect
      this.setConnectionStatus('disconnected');
      this.scheduleReconnect();
    }
  }

  private handleError(error: Event): void {
    console.error('[WebSocket] Error:', error);
    this.setConnectionStatus('error');
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const message: ServerMessage = JSON.parse(event.data);

      // Notify message listeners
      this.messageListeners.forEach(listener => {
        try {
          listener(message);
        } catch (e) {
          console.error('[WebSocket] Message listener error:', e);
        }
      });

      // Handle message types
      switch (message.type) {
        case 'connected':
          console.log('[WebSocket] Server confirmed connection:', message.data?.connectionId);
          break;

        case 'subscribed':
          console.log('[WebSocket] Subscribed to room:', message.room);
          break;

        case 'unsubscribed':
          console.log('[WebSocket] Unsubscribed from room:', message.room);
          break;

        case 'job_update':
          this.handleJobUpdate(message.data);
          break;

        case 'pong':
          // Heartbeat response - connection is alive
          break;

        case 'error':
          console.warn('[WebSocket] Server error:', message.data?.message);
          break;

        default:
          console.log('[WebSocket] Unknown message type:', message.type);
      }
    } catch (error) {
      console.error('[WebSocket] Failed to parse message:', error);
    }
  }

  private handleJobUpdate(data: JobUpdate): void {
    if (!data?.job_id) return;

    // Notify subscribers of the specific job room
    const jobRoom = `jobs:${data.job_id}`;
    this.notifySubscribers(jobRoom, data);

    // Notify subscribers of the mailbox room
    if (data.mailbox_id) {
      const mailboxRoom = `mailbox:${data.mailbox_id}`;
      this.notifySubscribers(mailboxRoom, data);
    }

    // Notify subscribers of the all-jobs room
    this.notifySubscribers('jobs:all', data);
  }

  private notifySubscribers(room: string, data: JobUpdate): void {
    const subscribers = this.subscriptions.get(room);
    if (subscribers) {
      subscribers.forEach(callback => {
        try {
          callback(data);
        } catch (e) {
          console.error('[WebSocket] Subscriber callback error:', e);
        }
      });
    }
  }

  private send(message: any): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    } else {
      // Queue message for later
      this.messageQueue.push(message);
    }
  }

  private setConnectionStatus(status: ConnectionStatus): void {
    if (this.connectionStatus !== status) {
      this.connectionStatus = status;
      this.connectionListeners.forEach(listener => {
        try {
          listener(status);
        } catch (e) {
          console.error('[WebSocket] Connection listener error:', e);
        }
      });
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn('[WebSocket] Max reconnection attempts reached');
      this.setConnectionStatus('error');
      return;
    }

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`);

    this.reconnectTimer = setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private startPingInterval(): void {
    // Send ping every 30 seconds to keep connection alive
    this.pingInterval = setInterval(() => {
      this.send({ type: 'ping' });
    }, 30000);
  }

  private clearPingInterval(): void {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }
}

// Singleton instance
export const websocketService = new WebSocketService();

export default websocketService;
