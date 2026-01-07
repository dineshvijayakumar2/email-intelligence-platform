/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Centralized environment variables (no VITE_ prefix needed)
  readonly SUPABASE_URL: string
  readonly SUPABASE_ANON_KEY: string
  readonly SUPABASE_SERVICE_KEY: string
  readonly API_BASE_URL: string
  readonly GOOGLE_CLIENT_ID: string
  readonly GOOGLE_CLIENT_SECRET: string
  readonly GOOGLE_REDIRECT_URI: string
  readonly NODE_ENV: string
  readonly PYTHON_ENV: string
  readonly REDIS_URL: string
  readonly REDIS_TTL_DAYS: string
  
  // Vite built-in variables
  readonly MODE: string
  readonly BASE_URL: string
  readonly PROD: boolean
  readonly DEV: boolean
  readonly SSR: boolean
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}