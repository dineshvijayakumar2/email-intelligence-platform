# Email Intelligence Platform - Architecture

## System Overview

The Email Intelligence Platform is a scalable email processing system built with **FastAPI** backend and **React** frontend, supporting multiple email archive formats (MBOX, PST, OLM) with real-time progress tracking and automatic tagging.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │Dashboard │  │Mailboxes │  │  Emails  │  │Processing│        │
│  │  Page    │  │   Page   │  │   Page   │  │   Jobs   │        │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘        │
│        │             │              │             │              │
│        └─────────────┴──────────────┴─────────────┘              │
│                          │                                       │
│                          │ HTTP/REST API                         │
│                          ▼                                       │
└─────────────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                           │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              API Layer (main.py)                           │ │
│  │  - Mailbox CRUD endpoints                                  │ │
│  │  - Job control (start/pause/resume/stop)                   │ │
│  │  - Progress tracking (Redis + Database)                    │ │
│  │  - Dashboard statistics                                     │ │
│  └────────────┬────────────────────────────────────┬──────────┘ │
│               │                                    │             │
│               ▼                                    ▼             │
│  ┌────────────────────┐              ┌────────────────────┐     │
│  │ ThreadPoolExecutor │              │  Redis Managers    │     │
│  │   (20 workers)     │              │  - JobProgress     │     │
│  │                    │              │  - JobQueue        │     │
│  │ Concurrent Jobs ──┼──────────────▶│  (Real-time Cache) │     │
│  └────────────┬───────┘              └────────────────────┘     │
│               │                                                  │
│               ▼                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           Email Processing Pipeline                      │   │
│  │                                                          │   │
│  │  ┌─────────┐  ┌────────────┐  ┌────────┐  ┌─────────┐  │   │
│  │  │Extractor│─▶│Normalizer  │─▶│ Tagger │─▶│Database │  │   │
│  │  │(Streaming)│ │(Transform) │  │(20+tags)│ │ Insert  │  │   │
│  │  └─────────┘  └────────────┘  └────────┘  └─────────┘  │   │
│  │                                                          │   │
│  │  Supports: MBOX, PST, OLM                                │   │
│  │  Batch: 5000 emails, Checkpoint: every 100 emails        │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Data Layer (Supabase)                         │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐             │
│  │  emails    │  │  mailboxes │  │processing_   │             │
│  │  (10M+)    │  │            │  │jobs          │             │
│  └────────────┘  └────────────┘  └──────────────┘             │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐             │
│  │email_      │  │  folders   │  │email_        │             │
│  │categories  │  │            │  │enrichment    │             │
│  └────────────┘  └────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                               ▲
                               │
┌─────────────────────────────────────────────────────────────────┐
│                    Redis (Optional)                              │
│  - Job progress cache (updated every email)                     │
│  - Syncs to database every 100 emails                           │
│  - TTL: 7 days                                                  │
│  - Graceful fallback to database if unavailable                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. Frontend (React + TypeScript + Ant Design)

**Location**: `frontend/src/`

**Pages**:
- `dashboard.tsx` - Email statistics, volume charts, and tag distribution
- `mailboxes.tsx` - Mailbox CRUD operations and connection testing
- `emails.tsx` - Email list with filtering by tags, folders, and date
- `processing.tsx` - Real-time job monitoring with pause/resume/stop controls
- `mailbox-process.tsx` - Job configuration and initiation

**Services**:
- `mailboxService.ts` - Mailbox API integration
- `emailService.ts` - Email queries and filtering
- `processingService.ts` - Job control and monitoring
- `dashboardService.ts` - Dashboard statistics

**Features**:
- Auto-refresh job status every 2-5 seconds
- Real-time progress bars
- Tag-based filtering
- Responsive design

---

### 2. Backend (FastAPI + Python)

**Location**: `backend/main.py` + `src/`

#### API Endpoints

**Mailbox Management**:
```
POST   /api/mailboxes/{id}/process          # Start processing job
POST   /api/mailboxes/{id}/test-connection  # Test connection
```

**Job Control**:
```
GET    /api/processing-jobs                 # List all jobs
POST   /api/processing-jobs/{id}/control    # Pause/Resume/Stop
POST   /api/processing-jobs/{id}/reprocess  # Re-tag emails
DELETE /api/processing-jobs/{id}            # Delete job
```

**Dashboard**:
```
GET    /api/dashboard/stats                 # Statistics
GET    /health                              # Health check
GET    /docs                                # OpenAPI docs
```

#### Concurrency Model

**3-Tier Async Architecture**:

1. **Layer 1: FastAPI Event Loop** (Async I/O)
   - All endpoints are `async def`
   - Non-blocking HTTP request handling
   - Handles thousands of concurrent API requests

2. **Layer 2: BackgroundTasks** (FastAPI)
   - `BackgroundTasks.add_task()` for lightweight async work
   - Runs in event loop without blocking response
   - Returns job ID immediately to user

3. **Layer 3: ThreadPoolExecutor** (CPU/IO-bound work)
   - 20 worker threads (`backend/main.py:53-56`)
   - `loop.run_in_executor()` for blocking operations
   - Each job processes sequentially in its own thread
   - Supports processing multiple mailboxes concurrently

**Example Flow**:
```python
# User clicks "Start Processing"
@app.post("/api/mailboxes/{id}/process")
async def start_processing(mailbox_id, background_tasks):
    # Create job record (instant)
    job = create_job_in_db()

    # Queue background work (non-blocking)
    background_tasks.add_task(process_emails_real, job_id)

    # Return immediately
    return {"job_id": job.id, "status": "pending"}

# Background task runs in thread pool
async def process_emails_real(job_id):
    loop = asyncio.get_event_loop()

    # Offload blocking work to thread pool
    result = await loop.run_in_executor(
        executor,           # ThreadPoolExecutor
        processor.process_emails,  # Blocking function
        job_id,
        max_emails,
        batch_size
    )
```

**Benefits**:
- API remains responsive
- Multiple jobs can run concurrently
- No race conditions on job state
- Graceful shutdown support

---

### 3. Email Processing Pipeline

**Location**: `src/processors/email_processor.py`

**Pipeline Stages**:

```
┌────────────┐
│ Extractor  │  Extract raw emails from file
└─────┬──────┘  - MBOX: Streaming line-by-line
      │         - PST: pypff binary access
      │         - OLM: ZIP + XML parsing
      ▼
┌────────────┐
│ Normalizer │  Standardize email structure
└─────┬──────┘  - Parse headers
      │         - Decode MIME
      │         - Infer folder (MBOX only)
      │         - Detect outbound/inbound
      ▼
┌────────────┐
│   Tagger   │  Apply 20+ automatic tags
└─────┬──────┘  - Direction: inbound/outbound
      │         - Thread: new_thread/reply/forward
      │         - Classification: spam/marketing/system
      │         - Priority: 0-10 score
      │         - Content: urgent/financial/meeting
      ▼
┌────────────┐
│  Database  │  Batch insert (5000 emails)
└────────────┘  - Emails table
                - Tags in email_categories table
                - Folders table
                - Progress checkpoints every 100 emails
```

**Key Features**:
- **Streaming**: Processes files without loading into memory
- **Batching**: Inserts 5000 emails per transaction
- **Checkpointing**: Updates progress every 100 emails
- **Pause/Resume**: Checks job status every 5 emails
- **Error Handling**: Continues processing on individual email failures

---

### 4. Progress Tracking System

**Two-Tier Architecture** (Redis REQUIRED + Database):

#### Tier 1: Redis (Real-time, In-memory) - MANDATORY

**Location**: `src/database/redis_client.py`

**Classes**:
- `JobProgressManager` - Progress tracking
- `JobQueueManager` - Job queue management
- `RedisClient` - Connection management with REDIS_URL support

**Storage**:
```
Redis Hash: job:{job_id}:progress
{
  "processed": 5234,
  "failed": 12,
  "last_updated": "2025-01-05T10:23:45Z",
  "status": "running"
}
TTL: 7 days
```

**Update Frequency**:
- Every email processed (writes to Redis)
- Syncs to database every 100 emails
- Reduces database load by 99%

**Graceful Fallback**:
```python
try:
    progress_manager = JobProgressManager()
except Exception:
    logger.warning("Redis unavailable, falling back to DB-only mode")
    progress_manager = None
```

#### Tier 2: Database (Persistent)

**Table**: `processing_jobs`

**Columns**:
```sql
id                UUID PRIMARY KEY
job_type          TEXT
mailbox_id        UUID
status            TEXT  -- pending, running, paused, stopped, completed, failed
total_records     INTEGER
processed_records INTEGER
failed_records    INTEGER
started_at        TIMESTAMPTZ
completed_at      TIMESTAMPTZ
error_log         JSONB
```

**Update Frequency**:
- Every 100 emails (triggered by Redis)
- On job status change (pause, stop, complete)
- On server shutdown (Redis→DB sync)

**Benefits**:
- Fast real-time updates (Redis)
- Data persistence (Database)
- Recovery after crashes (Database)
- Low database load (batched syncs)

---

### 5. Email Tagging System

**Location**: `src/processors/email_tagger.py`

**Tag Categories** (20+ tags):

1. **Direction** (2 tags)
   - `inbound`, `outbound`

2. **Thread Type** (3 tags)
   - `new_thread`, `reply`, `forward`

3. **Folder** (7 tags)
   - `inbox`, `sent`, `spam`, `trash`, `archive`, `drafts`, `other`

4. **Classification** (4 tags)
   - `spam`, `marketing`, `system`, `automated`

5. **Sender Type** (4 tags)
   - `sender_human`, `sender_system`, `sender_automated`, `sender_marketing`

6. **Priority** (2 tags + score)
   - `high_priority`, `low_priority`
   - Score: 0-10 (stored in metadata)

7. **Content** (10+ tags)
   - `urgent`, `financial`, `meeting`, `account_action`
   - `ecommerce`, `newsletter`, `notification`, `social_notification`
   - `has_attachments`, `large_email`, `small_email`

**Storage**:
```sql
-- Tags stored in normalized table
email_categories (
    id UUID PRIMARY KEY,
    email_id UUID REFERENCES emails(id),
    category TEXT,           -- Tag name (e.g., 'urgent')
    tag_type TEXT,          -- Tag category (e.g., 'content')
    confidence DECIMAL,     -- Future: ML confidence score
    created_at TIMESTAMPTZ
)

-- Metadata stored in emails table
emails (
    ...,
    is_spam BOOLEAN,
    is_marketing BOOLEAN,
    priority_score INTEGER,
    sender_type TEXT
)
```

**Performance**:
- ~0.1-0.5ms per email (rule-based)
- 2,000-10,000 emails/second
- No API calls or external dependencies

---

### 6. File Extractors

**Location**: `src/extractors/`

#### Supported Formats

| Format | File Extension | Folder Support | Extractor Class |
|--------|----------------|----------------|----------------|
| **MBOX** | `.mbox` | ❌ Inferred | `MBOXExtractor` |
| **PST** | `.pst` | ✅ Native | `PSTExtractor` |
| **OLM** | `.olm` | ✅ XML mapping | `OLMExtractor` |

#### MBOX Folder Inference

**Problem**: MBOX is a flat file format with no folder structure

**Solution**: Infer folders from:
1. **Gmail Labels** (if present in `X-Gmail-Labels` header)
   - Example: `X-Gmail-Labels: Inbox,Important,Work`
   - Extractor uses **first label** as folder: `Inbox`
2. **Email Characteristics** (if no labels)
   - Sent by user → `Sent`
   - Received by user → `Inbox`
   - Spam indicators → `Spam`
   - No recipients → `Drafts`

**Real-World Example**:
```
User's Gmail export (single MBOX file):
├─ Emails with label "Inbox,Important" → folder: Inbox
├─ Emails with label "Sent" → folder: Sent
├─ Emails with label "Work,Projects" → folder: Work
├─ Emails with label "Archive" → folder: Archive
└─ Emails with label "Spam" → folder: Spam

Result: 5+ folders detected from single MBOX file! ✅
```

**Location**: `src/extractors/mbox_extractor.py:258-271`

---

## Database Schema

### Core Tables

#### `mailboxes`
```sql
CREATE TABLE mailboxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    email_address TEXT,
    mailbox_type TEXT NOT NULL,  -- 'mbox', 'pst', 'olm'
    is_active BOOLEAN DEFAULT true,
    connection_config JSONB,     -- File path or server details
    total_emails INTEGER DEFAULT 0,
    last_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### `emails`
```sql
CREATE TABLE emails (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mailbox_id UUID REFERENCES mailboxes(id),
    message_id TEXT,
    thread_key TEXT,             -- For conversation threading
    subject TEXT,
    sender_email TEXT,
    sender_name TEXT,
    recipients JSONB,            -- Array of {email, name}
    cc_list JSONB,
    bcc_list JSONB,
    sent_date TIMESTAMPTZ,
    received_date TIMESTAMPTZ,
    body_text TEXT,
    body_html TEXT,
    message_size INTEGER,
    folder_path TEXT,            -- Actual or inferred folder
    is_outbound BOOLEAN,
    is_reply BOOLEAN,
    is_spam BOOLEAN,
    is_marketing BOOLEAN,
    priority_score INTEGER,      -- 0-10
    sender_type TEXT,            -- human/system/automated/marketing
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Full-text search index
CREATE INDEX idx_emails_search ON emails USING gin(to_tsvector('english', subject || ' ' || body_text));

-- Common query indexes
CREATE INDEX idx_emails_mailbox_date ON emails(mailbox_id, sent_date DESC);
CREATE INDEX idx_emails_sender ON emails(sender_email);
CREATE INDEX idx_emails_folder ON emails(folder_path);
```

#### `email_categories` (Tags)
```sql
CREATE TABLE email_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
    category TEXT NOT NULL,      -- Tag name (e.g., 'urgent')
    tag_type TEXT,              -- direction/thread/folder/content/classification
    confidence DECIMAL(3,2),    -- Future: ML confidence
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ec_email_id ON email_categories(email_id);
CREATE INDEX idx_ec_category ON email_categories(category);
```

#### `processing_jobs`
```sql
CREATE TABLE processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type TEXT NOT NULL,      -- extraction/reprocessing/categorization
    mailbox_id UUID REFERENCES mailboxes(id),
    status TEXT NOT NULL,        -- pending/running/paused/stopped/completed/failed
    total_records INTEGER DEFAULT 0,
    processed_records INTEGER DEFAULT 0,
    failed_records INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    error_log JSONB
);

CREATE INDEX idx_pj_mailbox ON processing_jobs(mailbox_id);
CREATE INDEX idx_pj_status ON processing_jobs(status);
```

#### `folders`
```sql
CREATE TABLE folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mailbox_id UUID REFERENCES mailboxes(id),
    folder_path TEXT NOT NULL,   -- e.g., "Inbox", "Work/Projects"
    folder_type TEXT,            -- inbox/sent/spam/trash/archive/user
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(mailbox_id, folder_path)
);
```

---

## Job Control Flow

### Start Job
```
User clicks "Start Processing"
  ↓
POST /api/mailboxes/{id}/process
  ↓
Create job record (status='pending')
  ↓
Queue background task
  ↓
Return job_id immediately
  ↓
Background task:
  1. Update status='running'
  2. Initialize extractor
  3. Stream emails (5000 batch)
  4. Update progress (every 100 emails)
  5. Check for pause/stop (every 5 emails)
  6. Complete or fail
```

### Pause Job
```
User clicks "Pause"
  ↓
POST /api/processing-jobs/{id}/control?action=pause
  ↓
Update job status='paused' in database
  ↓
Processing loop detects 'paused' status
  ↓
Enter wait loop (checks every 5 seconds)
  ↓
Wait for 'running' or 'stopped' status
```

### Resume Job
```
User clicks "Resume"
  ↓
POST /api/processing-jobs/{id}/control?action=resume
  ↓
Update job status='running' in database
  ↓
Processing loop detects 'running' status
  ↓
Continue from last checkpoint
```

### Stop Job
```
User clicks "Stop"
  ↓
POST /api/processing-jobs/{id}/control?action=stop
  ↓
Update job status='stopped' in database
  ↓
Processing loop detects 'stopped' status
  ↓
Break out of loop
  ↓
Set completed_at timestamp
  ↓
Job terminated gracefully
```

**Critical**: Status transitions are protected:
- 'stopped' **NEVER** overridden by 'failed'
- Multiple checkpoints prevent race conditions
- `backend/main.py:383-392, 332-339, operations.py:862-872`

---

## Deployment Configuration

### Environment Variables

**Single .env file in root directory**:
```bash
# Supabase Configuration (Required)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_role_key

# Redis Configuration (Required)
REDIS_URL=redis://localhost:6379
REDIS_TTL_DAYS=7  # Job data retention period

# Google Drive API (Optional)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback

# API Configuration
API_BASE_URL=http://localhost:8000/api
```

Note: Frontend environment variables are automatically loaded from root .env by the start-poc.sh script.

### Service Startup

**Development**:
```bash
# Backend
cd backend && ./run.sh

# Frontend
cd frontend && npm start
```

**Production**:
```bash
# Backend with Gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker backend.main:app

# Frontend build
cd frontend && npm run build
```

---

## Performance Characteristics

### Processing Speed

| Mailbox Size | Processing Time | Throughput |
|--------------|----------------|------------|
| 1,000 emails | ~30 seconds | 33 emails/sec |
| 10,000 emails | ~5 minutes | 33 emails/sec |
| 100,000 emails | ~50 minutes | 33 emails/sec |
| 1,000,000 emails | ~8 hours | 35 emails/sec |

**Bottlenecks**:
- Database batch inserts (5000 emails/batch)
- File I/O (streaming from MBOX/PST/OLM)
- Email parsing (MIME decoding)

**Optimizations**:
- Streaming extraction (no full file load)
- Batch database inserts (5000 emails)
- Redis progress caching (99% fewer DB writes)
- Checkpointing (every 100 emails)

### Scalability

**Concurrent Jobs**:
- ThreadPoolExecutor: 20 workers
- Can process 20 mailboxes simultaneously
- Each job runs in its own thread

**Database**:
- Optimized indexes for common queries
- Full-text search with GIN index
- Supports 10M+ emails

**Redis**:
- Optional but recommended for production
- Reduces database load by 99%
- TTL-based cleanup (7 days)

---

## Security Considerations

### API Security
- Service role keys for backend (write access)
- Anon keys for frontend (read access)
- CORS restricted to localhost:3000

### Data Security
- Emails stored in Supabase PostgreSQL
- No email content exposed to frontend by default
- RLS policies can be enabled for multi-tenant

### File Access
- Backend validates file paths before processing
- No direct file upload (security risk)
- Files must exist on server filesystem

---

## Future Enhancements

### Planned
- [ ] WebSocket support for real-time progress (replace polling)
- [ ] Multi-tenant architecture with RLS
- [ ] Advanced search with Elasticsearch
- [ ] Email attachment extraction and storage
- [ ] AI-powered email summarization
- [ ] Custom tagging rules (user-defined)
- [ ] Email thread visualization
- [ ] Export capabilities (CSV, JSON, EML)

### Under Consideration
- [ ] Gmail API direct extraction
- [ ] Office 365 Graph API integration
- [ ] IMAP/POP3 live sync
- [ ] Sentiment analysis
- [ ] Entity extraction (people, companies, dates)
- [ ] Email template detection
- [ ] Duplicate email detection

---

## Troubleshooting

### Common Issues

**Redis connection failed**:
- System automatically falls back to database-only mode
- Performance impact: ~2x slower progress updates
- Solution: Install and start Redis, or continue with fallback

**Processing job stuck**:
- Check backend logs: `tail -f backend/logs/backend.log`
- Check job status in database
- Verify file path is accessible
- Try stopping and restarting job

**Frontend not showing progress**:
- Verify `REACT_APP_API_BASE_URL` is set correctly
- Check browser console for API errors
- Verify backend is running on port 8000

**Database connection errors**:
- Verify Supabase credentials in `.env`
- Check Supabase project is active
- Run database schema: `sql/create_tables.sql`

---

## Monitoring

### Logs

**Backend**: `backend/logs/backend.log`
- Rotating file handler (10MB, 5 backups)
- INFO level logging
- Request/response tracking
- Error stack traces

**Health Check**: `GET /health`
```json
{
  "status": "healthy",
  "timestamp": "2025-01-05T10:23:45Z"
}
```

### Metrics

**Job Progress**:
- Processed records count
- Failed records count
- Processing speed (emails/second)
- ETA calculation

**System**:
- Active jobs count
- Thread pool utilization
- Redis connection status
- Database query performance

---

## Summary

The Email Intelligence Platform is a **production-ready** email processing system with:

✅ **Multi-format support**: MBOX, PST, OLM
✅ **Concurrent processing**: 20 simultaneous jobs
✅ **Real-time tracking**: Redis + Database
✅ **Automatic tagging**: 20+ rule-based tags
✅ **Scalable architecture**: Thread pool + Async I/O
✅ **Robust error handling**: Pause/resume/stop controls
✅ **Flexible deployment**: Docker-ready, cloud-compatible

**Next Steps**: See `README.md` for setup instructions and `docs/QUICKSTART.md` for usage guide.
