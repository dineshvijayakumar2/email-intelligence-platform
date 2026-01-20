/**
 * API Client with timeout, retry, and connection status tracking
 *
 * Provides resilient API calls that handle backend restarts gracefully.
 */

import config from '../config';

// Connection status tracking
let isConnected = true;
let connectionListeners: ((connected: boolean) => void)[] = [];
let lastConnectionCheck = 0;
const CONNECTION_CHECK_INTERVAL = 5000; // 5 seconds

/**
 * Subscribe to connection status changes
 */
export function onConnectionChange(listener: (connected: boolean) => void): () => void {
  connectionListeners.push(listener);
  // Return unsubscribe function
  return () => {
    connectionListeners = connectionListeners.filter(l => l !== listener);
  };
}

/**
 * Get current connection status
 */
export function getConnectionStatus(): boolean {
  return isConnected;
}

/**
 * Update connection status and notify listeners
 */
function setConnectionStatus(connected: boolean) {
  if (isConnected !== connected) {
    isConnected = connected;
    console.log(`[API] Connection status changed: ${connected ? 'CONNECTED' : 'DISCONNECTED'}`);
    connectionListeners.forEach(listener => {
      try {
        listener(connected);
      } catch (e) {
        console.error('Error in connection listener:', e);
      }
    });
  }
}

/**
 * Check if backend is reachable
 */
export async function checkConnection(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);

    const response = await fetch(`${config.apiBaseUrl}/health`, {
      method: 'GET',
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    const connected = response.ok;
    setConnectionStatus(connected);
    return connected;
  } catch {
    setConnectionStatus(false);
    return false;
  }
}

/**
 * Fetch with timeout support
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 10000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

/**
 * API request options
 */
interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
  body?: any;
  headers?: Record<string, string>;
  timeout?: number;
  retries?: number;
  retryDelay?: number;
  /** If true, won't throw on network errors but return null */
  silentOnNetworkError?: boolean;
}

/**
 * Make an API request with automatic retry and connection handling
 */
export async function apiRequest<T>(
  endpoint: string,
  options: ApiRequestOptions = {}
): Promise<T | null> {
  const {
    method = 'GET',
    body,
    headers = {},
    timeout = 10000,
    retries = 2,
    retryDelay = 1000,
    silentOnNetworkError = false,
  } = options;

  const url = `${config.apiBaseUrl}${endpoint}`;

  const fetchOptions: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
  };

  if (body && method !== 'GET') {
    fetchOptions.body = JSON.stringify(body);
  }

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetchWithTimeout(url, fetchOptions, timeout);

      // Connection is working
      setConnectionStatus(true);

      if (!response.ok) {
        // Server responded but with an error status
        const errorText = await response.text();
        let errorDetail = `HTTP ${response.status}`;
        try {
          const errorJson = JSON.parse(errorText);
          errorDetail = errorJson.detail || errorJson.message || errorDetail;
        } catch {
          if (errorText) errorDetail = errorText;
        }
        throw new Error(errorDetail);
      }

      // Handle empty responses
      const text = await response.text();
      if (!text) return null;

      return JSON.parse(text) as T;

    } catch (error: any) {
      lastError = error;

      // Check if it's a network/connection error
      const isNetworkError =
        error.name === 'AbortError' ||
        error.name === 'TypeError' ||
        error.message?.includes('Failed to fetch') ||
        error.message?.includes('NetworkError') ||
        error.message?.includes('Network request failed');

      if (isNetworkError) {
        setConnectionStatus(false);

        // Check if we should retry
        if (attempt < retries) {
          console.log(`[API] Request failed, retrying in ${retryDelay}ms (attempt ${attempt + 1}/${retries + 1})...`);
          await new Promise(resolve => setTimeout(resolve, retryDelay));
          continue;
        }

        if (silentOnNetworkError) {
          console.warn(`[API] Network error on ${method} ${endpoint}:`, error.message);
          return null;
        }
      }

      // Non-network error or all retries exhausted
      throw error;
    }
  }

  // All retries exhausted
  if (silentOnNetworkError) {
    return null;
  }
  throw lastError || new Error('Request failed after all retries');
}

/**
 * Convenience methods
 */
export const api = {
  get: <T>(endpoint: string, options?: Omit<ApiRequestOptions, 'method'>) =>
    apiRequest<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, body?: any, options?: Omit<ApiRequestOptions, 'method' | 'body'>) =>
    apiRequest<T>(endpoint, { ...options, method: 'POST', body }),

  put: <T>(endpoint: string, body?: any, options?: Omit<ApiRequestOptions, 'method' | 'body'>) =>
    apiRequest<T>(endpoint, { ...options, method: 'PUT', body }),

  delete: <T>(endpoint: string, options?: Omit<ApiRequestOptions, 'method'>) =>
    apiRequest<T>(endpoint, { ...options, method: 'DELETE' }),

  patch: <T>(endpoint: string, body?: any, options?: Omit<ApiRequestOptions, 'method' | 'body'>) =>
    apiRequest<T>(endpoint, { ...options, method: 'PATCH', body }),
};

export default api;
