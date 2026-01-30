/**
 * Supabase Client
 *
 * Initializes the Supabase client for authentication.
 * Used throughout the application for auth operations.
 */

import { createClient } from '@supabase/supabase-js';
import config from '../config';

// Validate configuration
if (!config.supabaseUrl || !config.supabaseAnonKey) {
  console.warn(
    'Supabase configuration missing. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in your environment.'
  );
}

// Create Supabase client
export const supabase = createClient(
  config.supabaseUrl || 'https://placeholder.supabase.co',
  config.supabaseAnonKey || 'placeholder-key',
  {
    auth: {
      // Persist session in localStorage
      persistSession: true,
      // Auto-refresh tokens before they expire
      autoRefreshToken: true,
      // Detect session from URL (for OAuth callbacks)
      detectSessionInUrl: true,
    },
  }
);

/**
 * Get the current access token for API calls
 */
export async function getAccessToken(): Promise<string | null> {
  const { data: { session } } = await supabase.auth.getSession();
  return session?.access_token || null;
}

/**
 * Check if Supabase is properly configured
 */
export function isSupabaseConfigured(): boolean {
  return !!(config.supabaseUrl && config.supabaseAnonKey);
}

export default supabase;
