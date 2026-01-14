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

## 📋 Stage 2 Plan: AI Enrichment, Business Analytics & Export

### **Goal**
Transform the platform into a comprehensive business intelligence tool by enriching 1,000-2,000 emails with AI-powered analysis, building a contacts/leads database, creating actionable analytics dashboards, and enabling smart export capabilities.

### **Expanded Scope** (Based on Business Email Analytics Best Practices)
1. **AI Email Enrichment**: Intent, tone, sentiment, quotes, pricing extraction
2. **Attachments Intelligence**: Track, categorize, and extract metadata from attachments
3. **Contacts & Lead Directory**: Build searchable contact database with lead scoring
4. **Email Signature Parsing**: Extract job titles, companies, phone numbers for lead targeting
5. **Business Analytics Dashboard**: Visualize trends, response times, engagement metrics
6. **Smart Export System**: CSV/Excel with customizable fields and filters

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

#### 2. **Attachments Intelligence**
**Capabilities**:
- **Metadata Extraction**: Filename, size, type, count per email
- **Content Categorization**: Documents (PDF, DOCX), images, spreadsheets, presentations
- **Business Document Detection**: Invoices, contracts, proposals, RFQs
- **Attachment Analytics**: Most common file types, size distribution, attachment trends

**Database Schema**:
```sql
CREATE TABLE email_attachments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  file_size INTEGER,
  mime_type TEXT,
  file_extension TEXT,
  attachment_type TEXT, -- 'document', 'image', 'spreadsheet', 'presentation', 'other'
  is_business_doc BOOLEAN DEFAULT FALSE,
  business_doc_type TEXT, -- 'invoice', 'contract', 'proposal', 'quote', 'rfq'
  created_at TIMESTAMPTZ DEFAULT NOW(),

  INDEX idx_attachment_email(email_id),
  INDEX idx_attachment_type(attachment_type),
  INDEX idx_business_docs(is_business_doc, business_doc_type)
);
```

#### 3. **Contacts & Lead Directory**
**Lead Intelligence System**:
- **Automatic Contact Extraction**: Parse From/To/CC fields to build contact database
- **Email Signature Parsing**: Extract job titles, company names, phone numbers, LinkedIn profiles
- **Lead Scoring**: Rank contacts by email frequency, engagement, business relevance
- **Deduplication**: Merge duplicate contacts across multiple email addresses
- **Company Grouping**: Group contacts by company domain for account-based insights

**Database Schema**:
```sql
CREATE TABLE contacts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email_address TEXT UNIQUE NOT NULL,
  full_name TEXT,
  first_name TEXT,
  last_name TEXT,

  -- Signature-extracted fields
  job_title TEXT,
  company_name TEXT,
  phone_number TEXT,
  linkedin_url TEXT,
  website TEXT,

  -- Analytics
  total_emails_sent INTEGER DEFAULT 0,
  total_emails_received INTEGER DEFAULT 0,
  first_contact_date TIMESTAMPTZ,
  last_contact_date TIMESTAMPTZ,
  lead_score INTEGER DEFAULT 0, -- 0-100 scoring

  -- Classification
  contact_type TEXT, -- 'customer', 'prospect', 'vendor', 'partner', 'internal'
  industry TEXT,

  -- Metadata
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  INDEX idx_contact_email(email_address),
  INDEX idx_contact_company(company_name),
  INDEX idx_lead_score(lead_score DESC),
  INDEX idx_contact_type(contact_type)
);

CREATE TABLE contact_email_map (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  contact_id UUID REFERENCES contacts(id) ON DELETE CASCADE,
  email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
  interaction_type TEXT, -- 'sent', 'received', 'cc', 'bcc'
  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(contact_id, email_id, interaction_type)
);
```

**Signature Parsing Strategy**:
```python
# AI-powered signature extraction
signature_prompt = """
Extract contact information from this email signature:
{signature_text}

Return JSON:
{
  "job_title": "Senior Sales Manager",
  "company_name": "Acme Corp",
  "phone": "+1-555-0123",
  "linkedin": "linkedin.com/in/johndoe",
  "website": "acme.com"
}
"""
```

#### 4. **Structured JSON Output**
**Enhanced Schema Design** (v2 - with attachments & contacts):
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
  "signature_data": {
    "job_title": "string or null",
    "company": "string or null",
    "phone": "string or null",
    "linkedin": "string or null"
  },
  "confidence_score": 0.0-1.0
}
```

**Validation**: Pydantic models with strict type checking

#### 5. **Business Analytics Dashboard**
**Key Metrics & Visualizations**:

**Email Volume Analytics**:
- Daily/weekly/monthly email trends (line charts)
- Inbound vs outbound volume comparison
- Peak email hours/days heatmap
- Email volume by folder/mailbox

**Response Time Analytics**:
- Average response time by sender/recipient
- Response time distribution (histogram)
- Longest unanswered threads
- Response rate percentage

**Engagement Metrics**:
- Top contacts by email frequency
- Thread length distribution
- Email read/reply patterns
- Engagement score by contact

**Business Intelligence**:
- Sentiment trends over time
- Quote/pricing analytics (total value, average deal size)
- Escalation tracking and resolution times
- Lead source analysis (which contacts generate most valuable conversations)

**Attachment Intelligence**:
- File type distribution (pie chart)
- Business documents tracker
- Attachment size trends
- Most shared document types

**Contact Analytics**:
- Top leads by score
- Company/domain distribution
- Contact acquisition funnel
- Industry breakdown

**UI Components** (Ant Design Charts):
```typescript
// Example dashboard widgets
<Row gutter={16}>
  <Col span={6}>
    <Card title="Total Emails">
      <Statistic value={12543} prefix={<MailOutlined />} />
    </Card>
  </Col>
  <Col span={6}>
    <Card title="Active Contacts">
      <Statistic value={342} prefix={<UserOutlined />} />
    </Card>
  </Col>
  <Col span={6}>
    <Card title="Avg Response Time">
      <Statistic value="2.4 hrs" prefix={<ClockCircleOutlined />} />
    </Card>
  </Col>
  <Col span={6}>
    <Card title="Lead Score Avg">
      <Statistic value={68} suffix="/ 100" />
    </Card>
  </Col>
</Row>

<Card title="Email Volume Trends">
  <Line data={emailVolumeData} />
</Card>

<Card title="Sentiment Distribution">
  <Pie data={sentimentData} />
</Card>
```

#### 6. **Database Design**
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

#### 7. **Error Handling & Retry Logic**
- **JSON Validation**: Catch malformed responses, request retry
- **API Errors**: Exponential backoff (1s, 2s, 4s, 8s)
- **Partial Success**: Save successful enrichments, retry failed ones
- **Logging**: Detailed logs for debugging
- **Monitoring**: Track success rate, avg processing time

#### 8. **Export Capabilities**
**CSV Export**:
- All email fields + enrichment data + contact details
- Attachments summary (count, types, business docs)
- Configurable column selection
- Filtered exports (by date, folder, tags, sentiment, lead score)
- Contact/lead exports with company grouping
- Scheduled exports (optional)

**Excel Export**:
- Multiple sheets (emails, enrichment, contacts, attachments, analytics summary)
- Formatted cells (sentiment colors, priority highlights, lead scores)
- Charts and pivot tables
- Contact directory with company grouping
- Attachment inventory by type

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

### **Attachments Module**
```
src/attachments/
├── attachment_extractor.py    # Extract attachment metadata
├── file_classifier.py         # Categorize file types
├── business_doc_detector.py   # Detect invoices, contracts, etc.
└── models.py                  # Attachment schemas
```

### **Contacts & Leads Module**
```
src/contacts/
├── contact_extractor.py       # Build contact database
├── signature_parser.py        # AI-powered signature extraction
├── lead_scorer.py             # Calculate lead scores
├── deduplication.py           # Merge duplicate contacts
└── models.py                  # Contact schemas
```

### **Analytics Module**
```
src/analytics/
├── email_analytics.py         # Email volume, trends
├── response_analytics.py      # Response time calculations
├── engagement_metrics.py      # Contact engagement scoring
├── dashboard_builder.py       # Aggregate dashboard data
└── models.py                  # Analytics schemas
```

### **Export Module**
```
src/exports/
├── export_engine.py           # Export orchestrator
├── csv_exporter.py            # CSV generation
├── excel_exporter.py          # Excel with multiple sheets
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

### **Week 1-2: AI Enrichment & Attachments**
- [ ] Claude API integration with retry logic
- [ ] Prompt engineering for batch processing
- [ ] JSON schema definition and validation
- [ ] Database schema for enrichment, attachments, contacts tables
- [ ] Basic batch processing (10 emails at a time)
- [ ] Attachment metadata extraction
- [ ] File type classification and business document detection
- [ ] Complete batch processor with error handling
- [ ] Entity extraction (people, companies, products)
- [ ] Quote/pricing detection and extraction
- [ ] Escalation detection logic
- [ ] Email signature parsing with AI

### **Week 3-4: Contacts & Analytics Dashboard**
- [ ] Contact extraction from From/To/CC fields
- [ ] Signature parsing integration
- [ ] Lead scoring algorithm implementation
- [ ] Contact deduplication and merging
- [ ] Company/domain grouping logic
- [ ] Email volume analytics (daily/weekly trends)
- [ ] Response time calculations
- [ ] Engagement metrics engine
- [ ] Dashboard API endpoints
- [ ] Frontend dashboard with Ant Design charts
- [ ] Top contacts/leads widgets
- [ ] Sentiment trend visualizations
- [ ] Attachment analytics widgets

### **Week 5: Export System**
- [ ] CSV export with customizable columns (emails, contacts, attachments)
- [ ] Excel export with multiple sheets
- [ ] Contact directory export with lead scores
- [ ] Attachment inventory export
- [ ] Export API endpoints
- [ ] Async export processing for large datasets
- [ ] Download link generation

### **Week 6: UI & Testing**
- [ ] AI enrichment trigger UI
- [ ] Contacts/leads directory UI
- [ ] Export configuration UI with advanced filters
- [ ] Progress monitoring for enrichment jobs
- [ ] End-to-end testing with 1,000+ emails
- [ ] Performance optimization and caching
- [ ] Dashboard performance tuning
- [ ] Lead scoring validation

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

### **Stage 2: AI Enrichment Endpoints (Planned)**
```http
# Trigger AI enrichment
POST /api/enrichment/batch
{
  "email_ids": ["uuid1", "uuid2"],
  "model": "claude-3-5-sonnet",
  "fields": ["intent", "sentiment", "quotes", "signature"]
}

# Get enrichment status
GET /api/enrichment/jobs/{job_id}

# Get enriched email details
GET /api/emails/{email_id}/enrichment
```

### **Stage 2: Contacts & Leads Endpoints (Planned)**
```http
# Get all contacts with filters
GET /api/contacts?company=Acme&min_score=70&sort=lead_score

# Get single contact details
GET /api/contacts/{contact_id}

# Get contact's email history
GET /api/contacts/{contact_id}/emails

# Get contacts grouped by company
GET /api/contacts/companies

# Update contact details
PATCH /api/contacts/{contact_id}
{
  "contact_type": "customer",
  "industry": "Technology"
}

# Merge duplicate contacts
POST /api/contacts/merge
{
  "primary_id": "uuid1",
  "duplicate_ids": ["uuid2", "uuid3"]
}
```

### **Stage 2: Analytics Dashboard Endpoints (Planned)**
```http
# Get dashboard summary
GET /api/analytics/dashboard

# Get email volume trends
GET /api/analytics/email-volume?period=7d&group_by=day

# Get response time analytics
GET /api/analytics/response-times?contact_id=uuid

# Get top contacts by engagement
GET /api/analytics/top-contacts?limit=50&metric=email_count

# Get sentiment trends
GET /api/analytics/sentiment-trends?period=30d

# Get attachment analytics
GET /api/analytics/attachments?group_by=type
```

### **Stage 2: Export Endpoints (Planned)**
```http
# Export enriched data
POST /api/exports/create
{
  "format": "csv" | "excel",
  "export_type": "emails" | "contacts" | "attachments" | "all",
  "filters": {
    "date_from": "2025-01-01",
    "sentiment": ["positive"],
    "lead_score_min": 70
  },
  "columns": ["subject", "sender", "sentiment", "lead_score"]
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
- **Dashboard Load Time**: < 3 seconds for analytics queries
- **Contact Extraction**: Process all emails in < 5 minutes for 10,000 emails

### **Quality Metrics**
- **Intent Classification Accuracy**: > 85%
- **Sentiment Analysis Accuracy**: > 90%
- **Quote Extraction Precision**: > 95%
- **Escalation Detection Recall**: > 90%
- **Signature Parsing Accuracy**: > 80% (job title, company extraction)
- **Contact Deduplication Precision**: > 95%
- **Lead Scoring Relevance**: Validated by business use case

### **Business Intelligence Metrics**
- **Contact Database**: Build directory of 500+ unique contacts from 10,000 emails
- **Lead Quality**: Identify top 50 leads with scores > 70/100
- **Business Documents**: Detect and categorize 100+ invoices/contracts/quotes
- **Attachment Coverage**: Extract metadata for > 95% of attachments
- **Dashboard Insights**: Provide 10+ actionable analytics widgets

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
