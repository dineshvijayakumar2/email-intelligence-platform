import { createClient } from "@supabase/supabase-js";

// Replace these with your actual Supabase URL and anon key
// These should be in environment variables in production
const supabaseUrl = process.env.REACT_APP_SUPABASE_URL || "https://pimoidzoxjzdzcccjneg.supabase.co";
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY || "your-anon-key-here";

export const supabaseClient = createClient(supabaseUrl, supabaseAnonKey);