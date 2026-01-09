# Railway Deployment Guide for Email Intelligence Platform

## Overview
This guide covers deploying the Email Intelligence POC on Railway with multi-tenant support for 5-10 SMB clients.

## Architecture

```
┌─────────────────────────────────────────────┐
│                  Railway                     │
├─────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Frontend │  │   API    │  │  Worker  │  │
│  │  (React) │  │(FastAPI) │  │ (Python) │  │
│  └──────────┘  └──────────┘  └──────────┘  │
│        │            │              │        │
│        └────────────┼──────────────┘        │
│                     │                       │
│              ┌──────────┐                   │
│              │  Redis   │                   │
│              └──────────┘                   │
└─────────────────────────────────────────────┘
                     │
                     │ External
                     ▼
            ┌──────────────┐
            │   Supabase   │
            │  (Database)  │
            └──────────────┘
```

## Multi-Tenant Strategy

### 1. Database Isolation (Row-Level Security)
- Each tenant has a `tenant_id` 
- Supabase RLS policies enforce data isolation
- Shared tables with tenant filtering

### 2. Tenant Identification
- Subdomain-based: `client1.yourdomain.com`
- Header-based: `X-Tenant-ID`
- JWT claims: Embedded in auth token

## Deployment Steps

### Step 1: Prepare Supabase

1. **Create Multi-Tenant Schema**
```sql
-- Add tenant table
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    subdomain TEXT UNIQUE,
    plan TEXT DEFAULT 'starter',
    max_mailboxes INT DEFAULT 5,
    max_storage_gb INT DEFAULT 10,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Add tenant_id to existing tables
ALTER TABLE mailboxes ADD COLUMN tenant_id UUID REFERENCES tenants(id);
ALTER TABLE emails ADD COLUMN tenant_id UUID REFERENCES tenants(id);
ALTER TABLE processing_jobs ADD COLUMN tenant_id UUID REFERENCES tenants(id);

-- Create indexes
CREATE INDEX idx_mailboxes_tenant ON mailboxes(tenant_id);
CREATE INDEX idx_emails_tenant ON emails(tenant_id);

-- Enable RLS
ALTER TABLE mailboxes ENABLE ROW LEVEL SECURITY;
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Tenant isolation for mailboxes" ON mailboxes
    FOR ALL USING (tenant_id = current_setting('app.current_tenant')::uuid);

CREATE POLICY "Tenant isolation for emails" ON emails
    FOR ALL USING (tenant_id = current_setting('app.current_tenant')::uuid);
```

2. **Configure Supabase Environment**
- Create production project
- Set up service role keys
- Configure storage buckets per tenant

### Step 2: Railway Setup

1. **Install Railway CLI**
```bash
npm install -g @railway/cli
railway login
```

2. **Create Railway Project**
```bash
railway init
railway link [project-id]
```

3. **Add Services**
```bash
# Add Redis
railway add redis

# Deploy backend
railway up -s backend

# Deploy frontend
railway up -s frontend

# Deploy worker
railway up -s worker
```

### Step 3: Environment Variables

Create `.env.production` for Railway:

```env
# Supabase Production
SUPABASE_URL=https://your-prod-project.supabase.co
SUPABASE_ANON_KEY=your_prod_anon_key
SUPABASE_SERVICE_KEY=your_prod_service_key

# Redis (Railway provides)
REDIS_URL=${{REDIS_URL}}
REDIS_TTL_DAYS=30

# Google Drive API
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=https://your-app.railway.app/auth/google/callback

# Multi-tenant Config
ENABLE_MULTI_TENANT=true
DEFAULT_TENANT_PLAN=starter
MAX_FREE_MAILBOXES=3

# Worker Configuration
WORKER_CONCURRENCY=4
MAX_EMAILS_PER_BATCH=100
PROCESSING_TIMEOUT=3600

# API Configuration
API_BASE_URL=https://your-api.railway.app
CORS_ORIGINS=https://your-app.railway.app
```

### Step 4: Configure Railway Variables

In Railway dashboard or CLI:

```bash
# Set environment variables
railway variables set SUPABASE_URL="your-url"
railway variables set SUPABASE_SERVICE_KEY="your-key"
railway variables set ENABLE_MULTI_TENANT="true"

# Link Redis
railway link redis
```

### Step 5: Deploy

```bash
# Deploy all services
railway up

# Or deploy individually
railway up -s backend
railway up -s frontend
railway up -s worker
```

## Scaling for Multi-Tenant

### 1. **Tenant Onboarding Flow**

```python
# backend/main.py addition
@app.post("/api/tenants/onboard")
async def onboard_tenant(tenant_data: TenantCreate):
    # Create tenant record
    tenant = await create_tenant(tenant_data)
    
    # Create default mailbox
    await create_default_mailbox(tenant.id)
    
    # Set up storage bucket
    await setup_tenant_storage(tenant.id)
    
    # Send welcome email
    await send_onboarding_email(tenant)
    
    return tenant
```

### 2. **Request Middleware for Tenant Context**

```python
# backend/middleware/tenant.py
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    # Extract tenant from subdomain or header
    tenant_id = extract_tenant_id(request)
    
    # Set tenant context for RLS
    request.state.tenant_id = tenant_id
    
    # Add to database session
    async with get_db_session() as db:
        await db.execute(f"SET app.current_tenant = '{tenant_id}'")
    
    response = await call_next(request)
    return response
```

### 3. **Resource Limits per Tenant**

```python
# backend/utils/limits.py
TENANT_LIMITS = {
    'starter': {
        'max_mailboxes': 3,
        'max_emails_per_day': 1000,
        'max_storage_gb': 5
    },
    'professional': {
        'max_mailboxes': 10,
        'max_emails_per_day': 10000,
        'max_storage_gb': 25
    },
    'enterprise': {
        'max_mailboxes': None,
        'max_emails_per_day': None,
        'max_storage_gb': 100
    }
}
```

## Monitoring & Maintenance

### 1. **Railway Monitoring**
- Built-in metrics dashboard
- Log aggregation
- Alerting on errors

### 2. **Health Checks**
```python
# backend/main.py
@app.get("/health/detailed")
async def health_detailed():
    return {
        "api": "healthy",
        "database": await check_database(),
        "redis": await check_redis(),
        "workers": await check_workers(),
        "tenant_count": await get_tenant_count()
    }
```

### 3. **Backup Strategy**
- Supabase automatic backups
- Export tenant data weekly
- Google Drive backup integration

## Cost Estimation

### Railway Costs (Monthly)
- **Starter**: $5 (included resources)
- **Backend**: ~$10-20 (based on usage)
- **Frontend**: ~$5-10 (static serving)
- **Worker**: ~$10-20 (processing load)
- **Redis**: ~$10
- **Total**: ~$40-65/month

### Supabase Costs
- **Free tier**: 2 projects, 500MB database
- **Pro**: $25/month per project
- **Recommended**: Pro plan for production

### Total for 5-10 Clients
- **Infrastructure**: ~$65-90/month
- **Per client cost**: ~$6-18/month
- **Suggested pricing**: $49-99/client/month

## Security Considerations

1. **API Rate Limiting**
```python
from slowapi import Limiter
limiter = Limiter(key_func=get_tenant_id)

@app.get("/api/emails")
@limiter.limit("100/hour")
async def get_emails():
    pass
```

2. **Tenant Data Isolation**
- Row-level security in Supabase
- Separate storage buckets
- Encrypted sensitive data

3. **Authentication**
- Supabase Auth with tenant context
- JWT tokens with tenant claims
- API key per tenant for integrations

## Deployment Checklist

- [ ] Supabase production project created
- [ ] Multi-tenant schema applied
- [ ] Railway project initialized
- [ ] Environment variables configured
- [ ] Redis service added
- [ ] Backend deployed and running
- [ ] Frontend deployed and accessible
- [ ] Worker service processing jobs
- [ ] Health checks passing
- [ ] SSL certificates active
- [ ] Monitoring configured
- [ ] First tenant onboarded
- [ ] Backup strategy implemented

## Rollback Strategy

```bash
# View deployment history
railway deployments

# Rollback to previous version
railway rollback [deployment-id]

# Or use GitHub integration for automatic rollback
git revert HEAD
git push origin main
```

## Support & Scaling

### When to Scale
- CPU usage > 80% consistently
- Memory usage > 90%
- Queue depth > 1000 jobs
- Response time > 2 seconds

### How to Scale
```bash
# Scale workers
railway scale worker --replicas 3

# Upgrade Railway plan
railway team upgrade

# Add more dynos
railway up -s worker2
```

## Next Steps

1. **Set up staging environment** on Railway
2. **Configure CI/CD** with GitHub Actions
3. **Implement monitoring** with Datadog/Sentry
4. **Add custom domain** with SSL
5. **Create admin dashboard** for tenant management