import { createClient } from "@supabase/supabase-js";
import config from './config';

// Use config for Supabase URL and key (supports VITE_ prefix)
const supabaseUrl = config.supabaseUrl;
const supabaseAnonKey = config.supabaseAnonKey;

// Note: Direct Supabase access should be replaced with backend API calls
// This is kept temporarily for backward compatibility
export const supabaseClient = createClient(supabaseUrl, supabaseAnonKey);