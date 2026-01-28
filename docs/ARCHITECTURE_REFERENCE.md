# Architecture & Technical Reference

This consolidated document contains the complete technical reference for the Email Intelligence Platform, merging information from multiple documentation files.

---

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Database Schema](#database-schema)
4. [Email Processing Pipeline](#email-processing-pipeline)
5. [File Format Support](#file-format-support)
6. [Email Tagging System](#email-tagging-system)
7. [Cloud Storage Integration](#cloud-storage-integration)
8. [Gmail LIVE Sync](#gmail-live-sync)
9. [Deployment](#deployment)
10. [Performance & Benchmarks](#performance--benchmarks)
11. [Troubleshooting](#troubleshooting)

---

## System Overview

### Tech Stack
- **Backend**: FastAPI 0.104+ (Python 3.8+)
- **Frontend**: React 18 + TypeScript + Ant Design 5.x
- **Database**: Supabase (PostgreSQL)
- **Cache**: Redis 7.0+ (required)
- **Cloud Storage**: Google Drive API
- **AI**: Claude 3.5 Sonnet API (Stage 2 Sprint 3)

### Core Capabilities
- Multi-format email extraction (MBOX, PST, OLM)
- Google Drive streaming for large files (65GB+)
- Rule-based tagging system (20+ tags)
- Real-time processing with Redis progress tracking
- Gmail LIVE synchronization with incremental sync
- Per-mailbox Gmail connections (multiple accounts)

---

## Architecture

### 3-Tier Async Architecture

```
Frontend (React)
      ↓ HTTP/REST
FastAPI Event Loop
      ↓ BackgroundTasks
ThreadPoolExecutor (20 workers)
      ↓
Email Processing Pipeline
      ↓
Redis (Progress) + Supabase (Storage)
```

### Concurrency Model
- **FastAPI Event Loop**: Handles HTTP requests, non-blocking I/O
- **BackgroundTasks**: Lightweight task scheduling
- **ThreadPoolExecutor**: 20 workers for CPU-intensive email processing
- **Redis**: Real-time progress updates (every email)
- **Database Sync**: Batch inserts every 100 emails

### Job Control Flow
```
Created → Pending → Running → [Paused] → Completed/Failed/Cancelled
                        ↓
                   Downloading (for large files)
```

---

## Database Schema

### Core Tables

```sql
-- Mailboxes: Email source configurations
CREATE TABLE mailboxes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    email_address VARCHAR(255),
    mailbox_type VARCHAR(50) NOT NULL, -- mbox, pst, olm
    connection_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Emails: Normalized email records
CREATE TABLE emails (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id),
    message_id VARCHAR(512) UNIQUE,
    subject TEXT,
    sender TEXT,
    recipients JSONB,
    date_sent TIMESTAMP WITH TIME ZONE,
    body_text TEXT,
    body_html TEXT,
    headers JSONB,
    attachments JSONB,
    folder_id UUID REFERENCES folders(id),
    processing_status VARCHAR(50) DEFAULT 'success',
    processing_error TEXT,
    processing_attempts INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Email Categories (Tags)
CREATE TABLE email_categories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
    category_type VARCHAR(100) NOT NULL,
    category_value VARCHAR(255) NOT NULL,
    confidence DECIMAL(3,2) DEFAULT 1.00,
    source VARCHAR(50) DEFAULT 'rule',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(email_id, category_type, category_value)
);

-- Processing Jobs
CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id),
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    total_records INTEGER DEFAULT 0,
    processed_records INTEGER DEFAULT 0,
    failed_records INTEGER DEFAULT 0,
    error_log JSONB,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Folders
CREATE TABLE folders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id),
    name VARCHAR(255) NOT NULL,
    path VARCHAR(1024),
    parent_id UUID REFERENCES folders(id),
    email_count INTEGER DEFAULT 0,
    UNIQUE(mailbox_id, path)
);
```

### Stage 2 Tables

```sql
-- Account Managers
CREATE TABLE account_managers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Clients
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    account_manager_id UUID REFERENCES account_managers(id),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Customer Companies
CREATE TABLE customer_companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(id),
    name VARCHAR(255) NOT NULL,
    domain VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Customer Contacts
CREATE TABLE customer_contacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES customer_companies(id),
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    title VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User Integrations (Gmail/Outlook OAuth)
CREATE TABLE user_integrations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL, -- gmail, outlook
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    email_address VARCHAR(255),
    last_sync_at TIMESTAMP WITH TIME ZONE,
    last_history_id VARCHAR(255),
    sync_status VARCHAR(50) DEFAULT 'idle',
    email_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, provider)
);

-- App Configuration
CREATE TABLE app_config (
    key VARCHAR(255) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Indexes for Performance

```sql
-- Email search and filtering
CREATE INDEX idx_emails_mailbox ON emails(mailbox_id);
CREATE INDEX idx_emails_date ON emails(date_sent DESC);
CREATE INDEX idx_emails_folder ON emails(folder_id);
CREATE INDEX idx_emails_message_id ON emails(message_id);
CREATE INDEX idx_emails_processing_status ON emails(processing_status);

-- Tag filtering
CREATE INDEX idx_categories_email ON email_categories(email_id);
CREATE INDEX idx_categories_type_value ON email_categories(category_type, category_value);

-- Full-text search
CREATE INDEX idx_emails_subject_fts ON emails USING gin(to_tsvector('english', subject));
CREATE INDEX idx_emails_body_fts ON emails USING gin(to_tsvector('english', body_text));
```

---

## Email Processing Pipeline

### Pipeline Flow

```
Source File → Extractor → Normalizer → Tagger → Database Insert
                ↓              ↓           ↓
           Format-specific   Unified    20+ tags
           (MBOX/PST/OLM)    schema     applied
```

### Key Components

1. **Extractors** (`backend/src/extractors/`)
   - `mbox_extractor.py`: Streaming text processing
   - `pst_extractor.py`: Binary database parsing
   - `olm_extractor.py`: ZIP + XML extraction
   - `gmail_extractor.py`: Gmail API integration

2. **Normalizer** (`backend/src/processors/email_normalizer.py`)
   - Standardizes email format across all sources
   - Extracts headers, body, attachments
   - Infers folder from Gmail labels

3. **Tagger** (`backend/src/processors/email_tagger.py`)
   - Applies 20+ rule-based tags
   - Categories: direction, thread, classification, priority, content

4. **Database Operations** (`backend/src/database/operations.py`)
   - Batch inserts (100 emails per batch)
   - Duplicate detection via message_id
   - Error tracking and retry logic

---

## File Format Support

### MBOX (Universal Format)
- **Sources**: Gmail export, Thunderbird, Apple Mail
- **Processing**: Text streaming, line-by-line
- **Folder Detection**: Inferred from X-Gmail-Labels header
- **Performance**: ~30 min for 1M emails

### PST (Windows Outlook)
- **Sources**: Outlook for Windows
- **Processing**: Binary database with `libpst`
- **Folder Detection**: Native folder structure preserved
- **Performance**: ~20 min for 1M emails

### OLM (Mac Outlook)
- **Sources**: Outlook for Mac
- **Processing**: ZIP archive with XML content
- **Folder Detection**: Mapped from OLM structure
- **Performance**: ~35 min for 1M emails
- **Streaming**: RemoteZip for Google Drive files (65GB+)

### Auto-Detection Logic
1. File extension (primary)
2. Magic bytes (fallback)
3. Content analysis (final fallback)

---

## Email Tagging System

### Tag Categories (20+ Tags)

| Category | Tags | Detection Method |
|----------|------|------------------|
| Direction | `inbound`, `outbound` | Compare sender to mailbox email |
| Thread | `new_thread`, `reply`, `forward` | Subject prefix analysis |
| Classification | `spam`, `marketing`, `system`, `automated` | Multi-signal detection |
| Sender Type | `sender_human`, `sender_marketing`, `sender_system` | Email pattern matching |
| Priority | `high_priority`, `low_priority`, `urgent` | Keyword + header analysis |
| Content | `has_attachments`, `financial`, `meeting`, `newsletter` | Content scanning |
| Social | `social_notification`, `account_action`, `ecommerce` | Domain + keyword matching |

### Spam Detection (6 Triggers)
- Sender contains "noreply", "mailer-daemon"
- Subject has spam keywords (URGENT!!!, FREE, etc.)
- Multiple exclamation/question marks
- ALL CAPS subject
- Known spam domains
- Suspicious header patterns

### Marketing Detection (5 Signals)
- Unsubscribe link present
- List-Unsubscribe header
- Marketing domains (mailchimp, sendgrid, etc.)
- Bulk sender patterns
- Marketing keywords in content

### Priority Scoring (0-10 Scale)
- Base score: 5
- Modifiers: urgent keywords (+3), VIP sender (+2), attachments (+1)
- High priority: score >= 7
- Low priority: score <= 3

### Performance
- Processing: 0.1-0.5ms per email
- Throughput: 2,000-10,000 emails/second
- Accuracy: Spam ~85-90%, Marketing ~90-95%, System ~95%+

---

## Cloud Storage Integration

### Google Drive (Primary)

#### OAuth2 Setup
1. Create project in Google Cloud Console
2. Enable Google Drive API
3. Configure OAuth consent screen
4. Create OAuth 2.0 credentials
5. Set authorized redirect URIs

#### Environment Variables
```env
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
```

#### Streaming Architecture
- **Small files (<5GB)**: Direct streaming
- **Large files (5GB+)**: Optional parallel download with byte-range requests
- **OLM files**: RemoteZip for targeted file access within ZIP

### S3 (Alternative)

#### URI Format
```
s3://bucket-name/path/to/file.mbox
```

#### Required IAM Permissions
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:GetObject", "s3:ListBucket"],
    "Resource": [
      "arn:aws:s3:::bucket-name",
      "arn:aws:s3:::bucket-name/*"
    ]
  }]
}
```

---

## Gmail LIVE Sync

### Architecture (Per-Mailbox)

Each mailbox stores its own Gmail tokens in `connection_config`:

```json
{
  "gmail_sync_enabled": true,
  "gmail_email": "user@gmail.com",
  "gmail_access_token": "ya29...",
  "gmail_refresh_token": "1//0...",
  "gmail_token_expires_at": "2026-01-28T12:00:00Z",
  "gmail_last_history_id": "12345678",
  "gmail_sync_status": "idle",
  "gmail_email_count": 1500
}
```

### Sync Service
- **Location**: `backend/src/services/gmail_sync_service.py`
- **Interval**: Configurable (1-1440 minutes, default 15)
- **Method**: Incremental sync using Gmail historyId
- **Rate Limit**: 10,000 queries/day (96 syncs feasible)

### API Endpoints
```
POST   /api/gmail/mailbox/{id}/connect    - OAuth connection
DELETE /api/gmail/mailbox/{id}/disconnect - Remove connection
GET    /api/gmail/mailbox/{id}/status     - Sync status
POST   /api/gmail/mailbox/{id}/sync       - Manual sync trigger
GET    /api/gmail/config                  - Global sync settings
PUT    /api/gmail/config                  - Update settings
```

### OAuth Scopes Required
```
https://www.googleapis.com/auth/gmail.readonly
https://www.googleapis.com/auth/gmail.settings.basic
https://www.googleapis.com/auth/userinfo.email
openid
```

---

## Deployment

### Local Development

```bash
# Prerequisites
- Python 3.8+
- Node.js 16+
- Redis Server
- Supabase Account

# Backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py  # Starts on port 8000

# Frontend
cd frontend
npm install
npm run dev  # Starts on port 3000

# Redis
redis-server
```

### Railway Deployment

#### Services Required
1. **Frontend**: Static site from `frontend/`
2. **Backend**: Python service from `backend/`
3. **Redis**: Railway Redis plugin

#### Environment Variables (Backend)
```env
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=xxx
SUPABASE_SERVICE_KEY=xxx
REDIS_URL=${Redis.REDIS_URL}
REDIS_TTL_DAYS=7
GOOGLE_CLIENT_ID=xxx
GOOGLE_CLIENT_SECRET=xxx
API_HOST=0.0.0.0
API_PORT=8000
```

#### Environment Variables (Frontend)
```env
VITE_API_BASE_URL=https://${backend.RAILWAY_PRIVATE_DOMAIN}/api
VITE_GOOGLE_CLIENT_ID=xxx
```

### Multi-Tenant Setup

#### Row-Level Security (RLS)
```sql
-- Enable RLS
ALTER TABLE emails ENABLE ROW LEVEL SECURITY;

-- Tenant isolation policy
CREATE POLICY tenant_isolation ON emails
FOR ALL USING (
  mailbox_id IN (
    SELECT id FROM mailboxes
    WHERE client_id = current_setting('app.current_client_id')::uuid
  )
);
```

#### Resource Limits by Plan
| Plan | Mailboxes | Emails | Storage |
|------|-----------|--------|---------|
| Starter | 3 | 100K | 1GB |
| Professional | 10 | 500K | 5GB |
| Enterprise | Unlimited | Unlimited | 50GB |

---

## Performance & Benchmarks

### Processing Throughput
- **Email Rate**: ~33 emails/second sustained
- **1M Emails**: ~8 hours processing time
- **Batch Size**: 100 emails per database insert
- **Workers**: 20 concurrent threads

### Memory Usage
- **MBOX Streaming**: ~50MB constant
- **PST Processing**: ~200MB peak
- **OLM Streaming**: ~100MB constant

### Database Performance
- **Insert Rate**: 3,000 emails/second (batch)
- **Query Time**: <100ms for tag filtering
- **Full-text Search**: <500ms for 1M emails

### Optimization Tips
1. Use "Download Before Processing" for files >5GB
2. Enable parallel download for Google Drive
3. Use date range filters for initial imports
4. Monitor Redis memory usage

---

## Troubleshooting

### Common Issues

#### Backend Won't Start
```bash
# Check Redis
redis-cli ping  # Should return PONG

# Check port
netstat -an | grep 8000
```

#### Gmail OAuth Errors
- Verify redirect URI matches exactly
- Check client ID/secret are correct
- Ensure required scopes are approved

#### Processing Stalls
- Check Redis connection
- Verify sufficient disk space
- Monitor worker thread count

#### Email Count Shows 0
```sql
-- Update folder counts
SELECT update_folder_counts();
```

### Migration Scripts

#### Fix Folder Case Issues
```sql
UPDATE emails
SET folder_id = (
  SELECT id FROM folders
  WHERE mailbox_id = emails.mailbox_id
  AND LOWER(name) = LOWER(current_folder_name)
)
WHERE folder_id IS NULL;
```

#### Migrate Gmail Tokens to Mailbox
```sql
-- Migration 007: Per-mailbox Gmail tokens
UPDATE mailboxes m
SET connection_config = COALESCE(m.connection_config, '{}'::jsonb) || jsonb_build_object(
    'gmail_access_token', ui.access_token,
    'gmail_refresh_token', ui.refresh_token,
    'gmail_token_expires_at', ui.token_expires_at,
    'gmail_last_history_id', ui.last_history_id,
    'gmail_sync_status', COALESCE(ui.sync_status, 'idle')
)
FROM user_integrations ui
WHERE ui.provider = 'gmail'
AND ui.user_id = m.connection_config->>'gmail_user_id'
AND m.connection_config->>'gmail_sync_enabled' = 'true';
```

---

## Development Roadmap

### Stage 2 Sprints

**Sprint 1: Foundation (Weeks 1-3)** - In Progress
- [x] Account Manager & Client Hierarchy
- [ ] Role-Based Access Control
- [x] Gmail LIVE Sync Integration
- [ ] Outlook OAuth Integration
- [x] Date Range Processing

**Sprint 2: Intelligence (Weeks 4-6)**
- [ ] Customer Recognition System
- [ ] Rules Management Interface
- [ ] Contact Database
- [ ] Communication History

**Sprint 3: AI Layer (Weeks 7-9)**
- [ ] AI Email Classification
- [ ] Business Entity Extraction
- [ ] Manual Correction UI
- [ ] Accuracy Testing (85% target)

---

*Last Updated: January 28, 2026*
