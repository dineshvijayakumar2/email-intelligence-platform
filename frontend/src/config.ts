// Configuration loaded from centralized environment variables
// Uses the same variables as backend - no duplication needed

const config = {
  // API - Use environment variable, fallback to relative path
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || import.meta.env.API_BASE_URL || '/api',
  
  // Google Drive
  googleClientId: import.meta.env.VITE_GOOGLE_CLIENT_ID || import.meta.env.GOOGLE_CLIENT_ID || '',
  googleRedirectUri: import.meta.env.VITE_GOOGLE_REDIRECT_URI || import.meta.env.GOOGLE_REDIRECT_URI || 'http://localhost:3000/auth/google/callback',
  
  // Environment
  isDevelopment: import.meta.env.DEV,
  isProduction: import.meta.env.PROD,
  nodeEnv: import.meta.env.NODE_ENV || 'development',
};

export default config;