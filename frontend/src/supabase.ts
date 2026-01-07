import { createClient } from "@supabase/supabase-js";

// Use centralized environment variables (loaded by Vite from root .env files)
const supabaseUrl = import.meta.env.SUPABASE_URL || "https://pimoidzoxjzdzcccjneg.supabase.co";
const supabaseAnonKey = import.meta.env.SUPABASE_ANON_KEY || "REMOVED_ANON_KEY";

export const supabaseClient = createClient(supabaseUrl, supabaseAnonKey);