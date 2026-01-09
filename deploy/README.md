# Deployment Guide

This directory contains all deployment configurations and scripts for the Email Intelligence Platform.

## Directory Structure

```
deploy/
├── railway/           # Railway.app deployment configs
│   ├── railway.json   # Service configuration
│   └── railway.toml   # Deployment settings
├── docker/            # Docker configurations
│   ├── Dockerfile.production
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
├── k8s/              # Kubernetes manifests (future)
│   ├── deployment.yaml
│   ├── service.yaml
│   └── ingress.yaml
├── scripts/          # Deployment automation
│   ├── deploy.sh     # Universal deployment script
│   └── rollback.sh   # Rollback script
└── README.md         # This file
```

## Quick Start

### Deploy to Railway (Recommended for Production)

```bash
# Deploy to staging
./deploy/scripts/deploy.sh staging railway

# Deploy to production
./deploy/scripts/deploy.sh production railway
```

### Deploy with Docker (Local/Self-hosted)

```bash
# Deploy locally
./deploy/scripts/deploy.sh development docker

# Deploy to self-hosted production
./deploy/scripts/deploy.sh production docker
```

## Environment Configuration

### 1. Create Environment File

Copy the appropriate template and fill in your values:

```bash
# For production
cp config/production/.env.example config/production/.env

# For staging
cp config/staging/.env.example config/staging/.env

# For development
cp config/development/.env.example config/development/.env
```

### 2. Required Environment Variables

**Critical variables that MUST be set:**

- `SUPABASE_URL` - Your Supabase project URL
- `SUPABASE_SERVICE_KEY` - Service role key (keep secret!)
- `REDIS_URL` - Redis connection string
- `JWT_SECRET_KEY` - Random 32+ character string
- `GOOGLE_CLIENT_ID` - For Google Drive integration
- `GOOGLE_CLIENT_SECRET` - OAuth client secret

### 3. Environment-Specific Settings

| Environment | Debug | Workers | Rate Limit | Domain |
|------------|-------|---------|------------|---------|
| Production | false | 4-8 | 1000/hour | app.emailintel.app |
| Staging | true | 2 | 5000/hour | staging.emailintel.app |
| Development | true | 1 | unlimited | localhost |

## Deployment Platforms

### Railway (Recommended)

**Pros:**
- Automatic deployments from GitHub
- Built-in Redis
- Easy scaling
- Good for multi-tenant

**Setup:**
1. Install Railway CLI: `npm i -g @railway/cli`
2. Login: `railway login`
3. Deploy: `railway up`

**Costs:** ~$40-65/month for full stack

### Docker Compose

**Pros:**
- Full control
- Self-hosted option
- Good for on-premise

**Setup:**
1. Install Docker & Docker Compose
2. Configure `.env` file
3. Run: `docker-compose up -d`

**Requirements:**
- 2 CPU cores minimum
- 4GB RAM minimum
- 20GB storage

### Kubernetes (Future)

**Pros:**
- Maximum scalability
- Multi-region support
- Advanced orchestration

**Setup:**
1. Configure kubectl
2. Apply manifests: `kubectl apply -f deploy/k8s/`
3. Monitor: `kubectl get pods`

## Multi-Tenant Deployment

### Database Setup

Run the multi-tenant migration:

```sql
-- In Supabase SQL Editor
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    subdomain TEXT UNIQUE,
    plan TEXT DEFAULT 'starter',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Add tenant_id to all tables
ALTER TABLE emails ADD COLUMN tenant_id UUID REFERENCES tenants(id);
ALTER TABLE mailboxes ADD COLUMN tenant_id UUID REFERENCES tenants(id);

-- Enable RLS
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE mailboxes ENABLE ROW LEVEL SECURITY;
```

### Tenant Isolation

The platform uses Row-Level Security (RLS) in Supabase:

1. **Subdomain-based**: client1.app.com → tenant_id extracted
2. **Header-based**: X-Tenant-ID header
3. **JWT-based**: Tenant claim in auth token

### Scaling Strategy

| Tenants | Workers | Redis | Database | Cost/Month |
|---------|---------|-------|----------|------------|
| 1-5 | 2 | 1GB | Shared | ~$40 |
| 5-10 | 4 | 2GB | Shared | ~$65 |
| 10-25 | 8 | 4GB | Dedicated | ~$150 |
| 25+ | 16+ | 8GB+ | Dedicated + Read Replicas | ~$300+ |

## Monitoring & Maintenance

### Health Checks

All deployments include health check endpoints:

- `/health` - Basic health check
- `/health/detailed` - Detailed system status
- `/metrics` - Prometheus metrics (if enabled)

### Logs

**Railway:**
```bash
railway logs --service backend-api
railway logs --service email-worker
```

**Docker:**
```bash
docker-compose logs -f backend
docker-compose logs -f worker
```

### Backup Strategy

1. **Database**: Supabase automatic daily backups
2. **Redis**: Periodic snapshots (RDB)
3. **File Storage**: Weekly exports to S3/GCS

## Security Checklist

- [ ] Environment files are NOT committed to git
- [ ] Production uses strong JWT secret (32+ chars)
- [ ] Database uses service role key (not anon key)
- [ ] Redis has password authentication
- [ ] HTTPS/TLS enabled on all endpoints
- [ ] CORS properly configured
- [ ] Rate limiting enabled
- [ ] Input validation on all endpoints
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS protection headers set

## Rollback Procedure

### Railway
```bash
railway rollback
```

### Docker
```bash
docker-compose down
git checkout previous-version
docker-compose up -d
```

## Troubleshooting

### Common Issues

**Backend won't start:**
- Check Redis connection
- Verify Supabase credentials
- Check Python dependencies

**Worker not processing:**
- Verify Redis is running
- Check worker logs
- Ensure queue names match

**Frontend can't connect:**
- Check CORS settings
- Verify API_BASE_URL
- Check network policies

### Debug Mode

Enable debug mode for troubleshooting:

```bash
# Set in environment file
DEBUG=true
LOG_LEVEL=debug
```

## Support

For deployment issues:
1. Check logs first
2. Review this documentation
3. Check deploy/scripts/ for automation options
4. Contact team lead or DevOps

## Next Steps

After successful deployment:

1. **Configure domain**: Point DNS to deployment
2. **Set up SSL**: Automatic with Railway/most platforms
3. **Configure monitoring**: Set up Sentry/Datadog
4. **Test multi-tenant**: Create test tenants
5. **Load testing**: Run performance tests
6. **Documentation**: Update with your specific setup