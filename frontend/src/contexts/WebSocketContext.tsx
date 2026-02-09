/**
 * WebSocket Context Provider
 *
 * Manages WebSocket connection lifecycle based on authentication state.
 * Provides subscription API for components to receive real-time updates.
 */

import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { useAuth } from './AuthContext';
import {
  websocketService,
  ConnectionStatus,
  JobUpdate,
} from '../services/websocketService';

interface WebSocketContextType {
  /** Current connection status */
  connectionStatus: ConnectionStatus;
  /** Whether WebSocket is connected */
  isConnected: boolean;
  /** Subscribe to job updates for a room */
  subscribe: (room: string, callback: (data: JobUpdate) => void) => () => void;
  /** Manually trigger reconnection */
  reconnect: () => Promise<void>;
}

const WebSocketContext = createContext<WebSocketContextType | null>(null);

interface WebSocketProviderProps {
  children: React.ReactNode;
}

export const WebSocketProvider: React.FC<WebSocketProviderProps> = ({ children }) => {
  const { session, isAuthenticated } = useAuth();
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const isConnecting = useRef(false);

  // Connect when authenticated
  useEffect(() => {
    if (isAuthenticated && session?.access_token && !isConnecting.current) {
      isConnecting.current = true;
      websocketService.connect().finally(() => {
        isConnecting.current = false;
      });
    }

    // Disconnect when logged out
    if (!isAuthenticated) {
      websocketService.disconnect();
    }

    return () => {
      // Don't disconnect on unmount - let service manage connection
    };
  }, [isAuthenticated, session?.access_token]);

  // Listen to connection status changes
  useEffect(() => {
    const unsubscribe = websocketService.onConnectionChange((status) => {
      setConnectionStatus(status);
    });

    return unsubscribe;
  }, []);

  // Subscribe to a room
  const subscribe = useCallback(
    (room: string, callback: (data: JobUpdate) => void) => {
      return websocketService.subscribe(room, callback);
    },
    []
  );

  // Manual reconnection
  const reconnect = useCallback(async () => {
    websocketService.disconnect();
    await websocketService.connect();
  }, []);

  const value: WebSocketContextType = {
    connectionStatus,
    isConnected: connectionStatus === 'connected',
    subscribe,
    reconnect,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};

/**
 * Hook to access WebSocket context.
 * Returns safe defaults if used outside WebSocketProvider (graceful degradation).
 */
export const useWebSocket = (): WebSocketContextType => {
  const context = useContext(WebSocketContext);

  // Return safe defaults if context not available (graceful degradation)
  if (!context) {
    return {
      connectionStatus: 'disconnected',
      isConnected: false,
      subscribe: () => () => {}, // No-op unsubscribe
      reconnect: async () => {},
    };
  }

  return context;
};

/**
 * Hook to get WebSocket connection status.
 * Safe to use outside WebSocketProvider (returns disconnected).
 */
export const useWebSocketStatus = (): ConnectionStatus => {
  const context = useContext(WebSocketContext);
  return context?.connectionStatus ?? 'disconnected';
};

export default WebSocketContext;
