// Configuration loaded from centralized environment variables
// Uses the same variables as backend - no duplication needed

const config = {
  // Supabase
  supabaseUrl: import.meta.env.SUPABASE_URL || '',
  supabaseAnonKey: import.meta.env.SUPABASE_ANON_KEY || '',
  
  // API
  apiBaseUrl: import.meta.env.API_BASE_URL || '/api',
  
  // Google Drive
  googleClientId: import.meta.env.GOOGLE_CLIENT_ID || '',
  googleRedirectUri: import.meta.env.GOOGLE_REDIRECT_URI || 'http://localhost:3000/auth/google/callback',
  
  // Environment
  isDevelopment: import.meta.env.DEV,
  isProduction: import.meta.env.PROD,
  nodeEnv: import.meta.env.NODE_ENV || 'development',
};

export default config;