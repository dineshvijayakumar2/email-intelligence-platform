# 📧 Email Intelligence Platform - POC

**Advanced Email Analysis Platform with AI Enrichment & Cloud Integration**

A comprehensive proof-of-concept for email intelligence gathering, processing, and AI-powered analysis with support for multiple archive formats, cloud storage, and automated tagging.

---

## 🎯 Project Status

### ✅ Stage 1: Complete - Email Extraction & Rule-Based Tagging
**Status**: Production-ready deployment complete (January 14, 2026)

**Delivered Capabilities**:
- ✅ Multi-format email extraction (MBOX, PST, OLM) with Google Drive streaming
- ✅ Rule-based tagging system (20+ tags: spam, marketing, system, automated, etc.)
- ✅ Real-time processing with Redis progress tracking
- ✅ Modern React UI with email preview and filtering
- ✅ Production deployment on Railway with Supabase database
- ✅ Google Drive OAuth2 integration for seamless file access

### 🚀 Stage 2: In Planning - AI Enrichment & Export
**Target Start**: January 2026
**Estimated Duration**: 3-4 weeks

**Planned Capabilities**:
- AI-powered intent, tone, and sentiment analysis
- Quote/pricing extraction from sales emails
- Batch processing with structured JSON output
- Export to CSV/Excel with customizable fields
- Advanced filtering and search with AI-enriched metadata

---

## 🌟 Stage 1 Features (Completed)

### **Email Processing Pipeline**
- ✅ **Multi-Format Support**: MBOX, PST, OLM archives
- ✅ **Streaming Architecture**: Process large files (65GB+) without downloading
- ✅ **Google Drive Integration**: OAuth2 authentication with automatic token refresh
- ✅ **Real-time Progress**: Redis-backed job tracking with ETA calculations
- ✅ **Concurrent Processing**: ThreadPool executor with 20 workers
- ✅ **Cancellable Jobs**: Stop processing at any time

### **Rule-Based Tagging System** 🎯
**20+ Automated Tags**:
- **Direction**: `inbound`, `outbound`
- **Thread Type**: `new_thread`, `reply`, `forward`
- **Classification**: `spam`, `marketing`, `system`, `automated`
- **Sender Type**: `sender_human`, `sender_marketing`, `sender_system`
- **Priority**: `high_priority`, `low_priority`, `urgent`
- **Content**: `has_attachments`, `financial`, `meeting`, `newsletter`
- **Social**: `social_notification`, `account_action`, `ecommerce`

**Tagging Criteria**:
- Spam detection (10+ patterns)
- Marketing identification (unsubscribe links, sender patterns)
- System/automated email detection
- Priority scoring (0-10 scale)
- Content-based categorization

### **Modern Web Interface**
- ✅ **Responsive Dashboard**: Real-time metrics and processing status
- ✅ **Email Browser**: Filter by tags, folders, mailboxes, dates
- ✅ **Email Preview Modal**: Two-column layout with metadata and content
- ✅ **Mailbox Management**: Create, edit, process email sources
- ✅ **Google Drive Picker**: Browse and select files from Drive
- ✅ **Job Monitoring**: Live progress with speed and ETA

### **Production Infrastructure**
- ✅ **Railway Deployment**: Auto-scaling backend
- ✅ **Supabase Database**: PostgreSQL with RLS and functions
- ✅ **Redis Caching**: Job progress and queue management
- ✅ **Environment Management**: Separate dev/prod configurations
- ✅ **Error Handling**: Retry logic, graceful failures, logging

---

## 📋 Stage 2 Plan: AI Enrichment & Export

### **Goal**
Enrich 1,000-2,000 structured emails with AI-powered analysis to extract intent, tone, sentiment, and business-critical details (quotes, pricing, escalations).

### **Core Requirements**

#### 1. **AI Batch Processing**
**Architecture Decision**: Claude API with Batch Message API
- **Model**: Claude 3.5 Sonnet (optimal cost/performance)
- **Batch Size**: 10-20 emails per API call
- **Rate Limiting**: Respect API limits with exponential backoff
- **Cost Optimization**: Cache embeddings, reuse responses

**Batching Strategy**:
```python
# Pseudo-code structure
batches = chunk_emails(emails, size=15)
for batch in batches:
    prompt = build_batch_prompt(batch)
    response = claude_api.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    enrichments = parse_batch_response(response)
    save_to_database(enrichments)
```

#### 2. **Structured JSON Output**
**Schema Design** (v1 - Iterative):
```json
{
  "email_id": "uuid",
  "email_type": "customer_inquiry | sales_quote | support_escalation | newsletter | internal",
  "tone": "professional | friendly | urgent | frustrated | neutral",
  "sentiment": "positive | negative | neutral | mixed",
  "happiness_index": 0.0-1.0,
  "escalation_needed": true|false,
  "escalation_reason": "string or null",
  "short_summary": "1-2 sentence summary",
  "key_entities": {
    "people": ["names"],
    "companies": ["company names"],
    "products": ["product mentions"]
  },
  "quote_details": {
    "has_quote": true|false,
    "quoted_amount": number or null,
    "currency": "USD" or null,
    "products_quoted": ["product list"]
  },
  "action_items": ["extracted action items"],
  "confidence_score": 0.0-1.0
}
```

**Validation**: Pydantic models with strict type checking

#### 3. **Database Design**
**New Table**: `email_enrichment`
```sql
CREATE TABLE email_enrichment (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email_id UUID REFERENCES emails(id) ON DELETE CASCADE,

  -- Classification
  email_type TEXT NOT NULL,
  tone TEXT,
  sentiment TEXT,
  happiness_index DECIMAL(3,2),
  confidence_score DECIMAL(3,2),

  -- Analysis
  short_summary TEXT,
  escalation_needed BOOLEAN DEFAULT FALSE,
  escalation_reason TEXT,

  -- Structured data (JSONB for flexibility)
  key_entities JSONB,
  quote_details JSONB,
  action_items JSONB,
  raw_ai_response JSONB,

  -- Metadata
  model_version TEXT,
  processing_time_ms INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(email_id)
);

CREATE INDEX idx_email_enrichment_type ON email_enrichment(email_type);
CREATE INDEX idx_email_enrichment_sentiment ON email_enrichment(sentiment);
CREATE INDEX idx_email_enrichment_escalation ON email_enrichment(escalation_needed);
CREATE INDEX idx_email_enrichment_entities ON email_enrichment USING GIN(key_entities);
```

#### 4. **Error Handling & Retry Logic**
- **JSON Validation**: Catch malformed responses, request retry
- **API Errors**: Exponential backoff (1s, 2s, 4s, 8s)
- **Partial Success**: Save successful enrichments, retry failed ones
- **Logging**: Detailed logs for debugging
- **Monitoring**: Track success rate, avg processing time

#### 5. **Export Capabilities**
**CSV Export**:
- All email fields + enrichment data
- Configurable column selection
- Filtered exports (by date, folder, tags, sentiment)
- Scheduled exports (optional)

**Excel Export**:
- Multiple sheets (emails, enrichment, summary stats)
- Formatted cells (sentiment colors, priority highlights)
- Charts and pivot tables

**Export API**:
```python
POST /api/exports/create
{
  "format": "csv" | "excel",
  "filters": {
    "date_from": "2025-01-01",
    "mailbox_ids": ["uuid1", "uuid2"],
    "sentiment": ["positive", "negative"],
    "has_quote": true
  },
  "columns": ["subject", "sender", "sentiment", "quote_amount"]
}

Response: {
  "export_id": "uuid",
  "status": "processing",
  "download_url": null
}

GET /api/exports/{export_id}/download
```

---

## 🏗️ Stage 2 Architecture

### **AI Enrichment Module**
```
src/ai/
├── enrichment_engine.py      # Main orchestrator
├── claude_client.py           # Claude API wrapper
├── prompt_templates.py        # Prompt engineering
├── batch_processor.py         # Batch management
├── response_parser.py         # JSON validation
├── retry_handler.py           # Error handling
└── models.py                  # Pydantic schemas
```

### **Export Module**
```
src/exports/
├── export_engine.py           # Export orchestrator
├── csv_exporter.py            # CSV generation
├── excel_exporter.py          # Excel generation
├── formatters.py              # Data formatting
└── models.py                  # Export schemas
```

### **Processing Flow**
```
┌─────────────────────────────────────────────┐
│  Frontend: Trigger AI Enrichment           │
│  (Select emails, configure options)         │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│  Backend: Create Enrichment Job            │
│  - Validate selection                       │
│  - Create job record                        │
│  - Queue for processing                     │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│  AI Enrichment Engine                       │
│  ├─ Batch emails (10-20 per call)           │
│  ├─ Build prompts with email context        │
│  ├─ Call Claude API (with retry)            │
│  ├─ Parse & validate JSON responses         │
│  └─ Save to email_enrichment table          │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│  Database: email_enrichment table           │
│  (Available for queries and exports)        │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│  Export Engine (triggered by user)         │
│  ├─ Query emails + enrichment data          │
│  ├─ Apply filters                           │
│  ├─ Format as CSV/Excel                     │
│  └─ Generate download link                  │
└─────────────────────────────────────────────┘
```

---

## 📊 Stage 2 Deliverables

### **Week 1: AI Enrichment Foundation**
- [ ] Claude API integration with retry logic
- [ ] Prompt engineering for batch processing
- [ ] JSON schema definition and validation
- [ ] Database schema for enrichment table
- [ ] Basic batch processing (10 emails at a time)

### **Week 2: Enrichment Engine**
- [ ] Complete batch processor with error handling
- [ ] Entity extraction (people, companies, products)
- [ ] Quote/pricing detection and extraction
- [ ] Escalation detection logic
- [ ] Confidence scoring system

### **Week 3: Export System**
- [ ] CSV export with customizable columns
- [ ] Excel export with multiple sheets
- [ ] Export API endpoints
- [ ] Async export processing for large datasets
- [ ] Download link generation

### **Week 4: UI & Testing**
- [ ] AI enrichment trigger UI
- [ ] Export configuration UI
- [ ] Progress monitoring for enrichment jobs
- [ ] End-to-end testing with 1,000+ emails
- [ ] Performance optimization and caching

---

## 🚀 Quick Start (Stage 1)

### **Prerequisites**
- Python 3.8+ with pip
- Node.js 16+ with npm
- Redis Server (required)
- Supabase Account

### **1. Clone & Setup**
```bash
git clone <repository-url>
cd email-intelligence-platform

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend setup
cd ../frontend
npm install
```

### **2. Environment Configuration**
Create `.env.development` in project root:
```env
# Database
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_role_key

# Redis (REQUIRED)
REDIS_URL=redis://localhost:6379
REDIS_TTL_DAYS=7

# Google Drive OAuth2
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
GOOGLE_REDIRECT_URI=http://localhost:3000

# API
API_BASE_URL=http://localhost:8000/api
API_HOST=0.0.0.0
API_PORT=8000
```

### **3. Database Setup**
Run in Supabase SQL Editor:
1. `scripts/create_tables.sql` (main schema)
2. `migrations/add_user_integrations.sql` (OAuth tables)
3. `migrations/fix_folder_counts_permissions.sql` (RLS permissions)

### **4. Start Services**
```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Backend
cd backend
python main.py

# Terminal 3: Frontend
cd frontend
npm run dev
```

### **5. Access Application**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## 📖 Documentation

### **Stage 1 Docs**
- [Google Drive Integration](docs/GOOGLE_DRIVE_INTEGRATION.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Email Tagging System](docs/EMAIL_TAGGING.md)
- [Deployment Guide](docs/DEPLOYMENT.md)

### **Stage 2 Docs (Coming Soon)**
- AI Enrichment Guide
- Export System Documentation
- Prompt Engineering Best Practices
- Performance Optimization

---

## 🔧 API Reference

### **Email Endpoints**
```http
# Get emails with filters
POST /api/emails
{
  "offset": 0,
  "limit": 50,
  "filters": {
    "mailbox_ids": ["uuid"],
    "tags": ["spam", "marketing"],
    "date_from": "2025-01-01"
  }
}

# Get single email with enrichment
GET /api/emails/{email_id}
```

### **Tagging Endpoints**
```http
# Get available tags
GET /api/emails/categories

# Reprocess emails with updated tagging
POST /api/processing-jobs/{job_id}/reprocess
```

### **Stage 2: Enrichment Endpoints (Planned)**
```http
# Trigger AI enrichment
POST /api/enrichment/batch
{
  "email_ids": ["uuid1", "uuid2"],
  "model": "claude-3-5-sonnet",
  "fields": ["intent", "sentiment", "quotes"]
}

# Get enrichment status
GET /api/enrichment/jobs/{job_id}

# Export enriched data
POST /api/exports/create
{
  "format": "csv",
  "filters": {...},
  "columns": [...]
}

GET /api/exports/{export_id}/download
```

---

## 🛠️ Tech Stack

### **Backend**
- **Framework**: FastAPI 0.104+
- **Database**: Supabase (PostgreSQL)
- **Cache**: Redis 7.0+
- **AI**: Claude 3.5 Sonnet API (Stage 2)
- **Cloud Storage**: Google Drive API
- **Processing**: ThreadPoolExecutor (20 workers)

### **Frontend**
- **Framework**: React 18 + TypeScript
- **UI Library**: Ant Design 5.x
- **State Management**: React Hooks
- **API Client**: Axios
- **Build Tool**: Vite

### **Infrastructure**
- **Hosting**: Railway (backend + Redis)
- **Database**: Supabase Cloud
- **Storage**: Google Drive (user files)
- **Monitoring**: Application logs + Redis metrics

---

## 🐛 Troubleshooting

### **Common Issues**

#### **Tagging Not Working**
Run these migrations in Supabase:
```sql
-- migrations/fix_email_categories_permissions.sql
-- migrations/fix_update_folder_counts_function.sql
```

#### **Mailbox Shows "Unknown"**
Restart backend (fixed in v16):
```bash
cd backend && python main.py
```

#### **Email Count Shows 0**
Run folder counts update:
```sql
SELECT update_folder_counts();
```

#### **Redis Connection Failed**
```bash
# Start Redis
redis-server

# Test connection
redis-cli ping
# Should return: PONG
```

---

## 📈 Stage 2 Success Metrics

### **Performance Targets**
- **AI Processing**: < 2 seconds per email
- **Batch Throughput**: 500-1,000 emails/hour
- **JSON Parse Success**: > 95%
- **Export Generation**: < 30 seconds for 10,000 emails

### **Quality Metrics**
- **Intent Classification Accuracy**: > 85%
- **Sentiment Analysis Accuracy**: > 90%
- **Quote Extraction Precision**: > 95%
- **Escalation Detection Recall**: > 90%

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

---

## 📄 License

MIT License - see LICENSE file for details

---

## 🙋 Support

- **Documentation**: Check `/docs` folder
- **Issues**: GitHub Issues
- **API Docs**: http://localhost:8000/docs

---

**Stage 1 Complete ✅ | Stage 2 Coming Soon 🚀**

*Built with ❤️ using Python, TypeScript, React, Claude AI, and Google Cloud APIs*
