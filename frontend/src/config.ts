// Configuration loaded from frontend environment variables
// All variables must be prefixed with VITE_ to be exposed to the client

/**
 * Default locale for all date/number formatting.
 * Keep in sync with utils/numberFormat.ts formatNumber() default and with
 * utils/dateUtils.ts core formatters. Used so formatting is consistent
 * regardless of the viewer's browser locale.
 */
export const LOCALE = 'en-AU';

// Helper to derive WebSocket URL from API URL
const deriveWsUrl = (apiUrl: string): string => {
  if (import.meta.env.VITE_WS_BASE_URL) {
    return import.meta.env.VITE_WS_BASE_URL;
  }
  // Convert http(s) to ws(s)
  if (apiUrl.startsWith('http://')) {
    return apiUrl.replace('http://', 'ws://').replace('/api', '');
  }
  if (apiUrl.startsWith('https://')) {
    return apiUrl.replace('https://', 'wss://').replace('/api', '');
  }
  // Relative URL - use current origin
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}`;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api';

const config = {
  // API - Use environment variable, fallback to relative path
  apiBaseUrl,

  // WebSocket - Derived from API URL or use explicit env variable
  wsBaseUrl: deriveWsUrl(apiBaseUrl),

  // Supabase (for auth)
  supabaseUrl: import.meta.env.VITE_SUPABASE_URL || '',
  supabaseAnonKey: import.meta.env.VITE_SUPABASE_ANON_KEY || '',

  // Google Drive & Gmail
  googleClientId: import.meta.env.VITE_GOOGLE_CLIENT_ID || '',
  googleRedirectUri: import.meta.env.VITE_GOOGLE_REDIRECT_URI || 'http://localhost:3000/auth/google/callback',

  // Microsoft (Outlook/O365)
  microsoftClientId: import.meta.env.VITE_MICROSOFT_CLIENT_ID || '',
  microsoftRedirectUri: import.meta.env.VITE_MICROSOFT_REDIRECT_URI || 'http://localhost:3000/auth/microsoft/callback',

  // Environment
  isDevelopment: import.meta.env.DEV,
  isProduction: import.meta.env.PROD,
  nodeEnv: import.meta.env.MODE || 'development',
};

export default config;