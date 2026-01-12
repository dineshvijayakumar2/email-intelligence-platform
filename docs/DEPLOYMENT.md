# Deployment Guide

## Railway Deployment Setup

### Prerequisites
1. Railway account with project created
2. Redis service deployed in Railway
3. Supabase project with database setup

### Backend Service Configuration

1. **Create Backend Service** in Railway
   - Connect to GitHub repository
   - Set root directory to `/backend`

2. **Set Environment Variables** in Railway dashboard:
   ```
   PYTHON_ENV=production
   ALLOWED_ORIGINS=https://frontend-production-7b0b.up.railway.app
   SUPABASE_URL=<your-supabase-url>
   SUPABASE_ANON_KEY=<your-supabase-anon-key>
   SUPABASE_SERVICE_KEY=<your-supabase-service-key>
   REDIS_URL=${{Redis.REDIS_URL}}
   REDIS_TTL_DAYS=30
   GOOGLE_CLIENT_ID=<your-google-client-id>
   GOOGLE_CLIENT_SECRET=<your-google-client-secret>
   GOOGLE_REDIRECT_URI=https://frontend-production-7b0b.up.railway.app/auth/google/callback
   SECRET_KEY=<your-secret-key>
   ```

   **Note**: Replace the hardcoded frontend URL with your actual frontend Railway domain.

### Frontend Service Configuration

1. **Create Frontend Service** in Railway
   - Connect to GitHub repository
   - Set root directory to `/frontend`

2. **Set Environment Variables** in Railway dashboard:
   ```
   NODE_ENV=production
   VITE_API_BASE_URL=https://backend-production-42f4.up.railway.app/api
   VITE_GOOGLE_CLIENT_ID=<your-google-client-id>
   VITE_GOOGLE_REDIRECT_URI=https://frontend-production-7b0b.up.railway.app/auth/google/callback
   ```

   **Note**: Replace the hardcoded backend URL with your actual backend Railway domain.

### Using Railway Reference Variables (Recommended)

Instead of hardcoding URLs, use Railway's reference variables:

**Backend Service**:
- `ALLOWED_ORIGINS=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}`
- `GOOGLE_REDIRECT_URI=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}/auth/google/callback`

**Frontend Service**:
- `VITE_API_BASE_URL=https://${{backend.RAILWAY_PUBLIC_DOMAIN}}/api`
- `VITE_GOOGLE_REDIRECT_URI=https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}/auth/google/callback`

**Note**: The service names (`frontend` and `backend`) must match your Railway service names.

### Troubleshooting CORS Issues

1. **Check Environment Variables**: Ensure `ALLOWED_ORIGINS` is set correctly in Railway
2. **Verify Logs**: Check backend logs for "CORS configured with allowed origins" message
3. **Check Frontend URL**: Make sure the frontend URL in ALLOWED_ORIGINS matches exactly
4. **Multiple Origins**: Use comma-separated values for multiple allowed origins

### Database Setup

Run the database setup script in Supabase SQL editor:
```sql
-- Run scripts/create_tables.sql in Supabase SQL editor
```

### Testing Deployment

1. Visit your frontend URL
2. Check browser console for any CORS errors
3. Check backend logs for successful API calls
4. Test email processing functionality

### Common Issues

1. **CORS Error**: Environment variable `ALLOWED_ORIGINS` not set or incorrect
2. **API Connection Failed**: Wrong `VITE_API_BASE_URL` in frontend
3. **Database Error**: Supabase credentials not set correctly
4. **Redis Error**: Redis service not linked properly