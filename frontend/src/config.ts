// Configuration loaded from frontend environment variables
// All variables must be prefixed with VITE_ to be exposed to the client

const config = {
  // API - Use environment variable, fallback to relative path
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || '/api',

  // Google Drive
  googleClientId: import.meta.env.VITE_GOOGLE_CLIENT_ID || '',
  googleRedirectUri: import.meta.env.VITE_GOOGLE_REDIRECT_URI || 'http://localhost:3000/auth/google/callback',

  // Environment
  isDevelopment: import.meta.env.DEV,
  isProduction: import.meta.env.PROD,
  nodeEnv: import.meta.env.MODE || 'development',
};

export default config;