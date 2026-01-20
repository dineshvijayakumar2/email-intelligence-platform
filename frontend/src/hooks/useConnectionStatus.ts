/**
 * React hook for tracking backend connection status
 */

import { useState, useEffect, useCallback } from 'react';
import { onConnectionChange, getConnectionStatus, checkConnection } from '../services/apiClient';

interface UseConnectionStatusOptions {
  /** Interval to check connection when disconnected (ms) */
  reconnectInterval?: number;
  /** Whether to auto-check connection on mount */
  checkOnMount?: boolean;
}

interface ConnectionStatus {
  isConnected: boolean;
  isChecking: boolean;
  lastChecked: Date | null;
  checkNow: () => Promise<boolean>;
}

export function useConnectionStatus(options: UseConnectionStatusOptions = {}): ConnectionStatus {
  const { reconnectInterval = 5000, checkOnMount = true } = options;

  const [isConnected, setIsConnected] = useState(getConnectionStatus());
  const [isChecking, setIsChecking] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  const checkNow = useCallback(async (): Promise<boolean> => {
    setIsChecking(true);
    try {
      const connected = await checkConnection();
      setLastChecked(new Date());
      return connected;
    } finally {
      setIsChecking(false);
    }
  }, []);

  // Subscribe to connection status changes
  useEffect(() => {
    const unsubscribe = onConnectionChange((connected) => {
      setIsConnected(connected);
    });

    return unsubscribe;
  }, []);

  // Check connection on mount if requested
  useEffect(() => {
    if (checkOnMount) {
      checkNow();
    }
  }, [checkOnMount, checkNow]);

  // Auto-reconnect check when disconnected
  useEffect(() => {
    if (!isConnected && reconnectInterval > 0) {
      const interval = setInterval(() => {
        checkNow();
      }, reconnectInterval);

      return () => clearInterval(interval);
    }
  }, [isConnected, reconnectInterval, checkNow]);

  return {
    isConnected,
    isChecking,
    lastChecked,
    checkNow,
  };
}

export default useConnectionStatus;
