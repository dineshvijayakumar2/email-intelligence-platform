import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => {
  // Load env file based on `mode` from parent directory
  // Load all variables to access them, but only expose safe ones to frontend
  const env = loadEnv(mode, '../', '')
  
  return {
    plugins: [react()],
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: env.API_BASE_URL || 'http://localhost:8000',
          changeOrigin: true,
          secure: false,
        },
      },
    },
    build: {
      outDir: 'build',
      sourcemap: true,
    },
    resolve: {
      alias: {
        '@': '/src',
      },
    },
    envDir: '../', // Look for env files in parent directory
    define: {
      // Explicitly expose only the frontend-safe environment variables
      'import.meta.env.SUPABASE_URL': JSON.stringify(env.SUPABASE_URL),
      'import.meta.env.SUPABASE_ANON_KEY': JSON.stringify(env.SUPABASE_ANON_KEY),
      'import.meta.env.API_BASE_URL': JSON.stringify(env.API_BASE_URL),
      'import.meta.env.GOOGLE_CLIENT_ID': JSON.stringify(env.GOOGLE_CLIENT_ID),
      'import.meta.env.GOOGLE_REDIRECT_URI': JSON.stringify(env.GOOGLE_REDIRECT_URI),
      'import.meta.env.NODE_ENV': JSON.stringify(env.NODE_ENV || mode),
      'import.meta.env.MODE': JSON.stringify(mode),
    },
  }
})