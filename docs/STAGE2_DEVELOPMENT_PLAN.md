# Stage 2 Phase 1 - Development Plan

**Email Intelligence Platform Enhancement**  
**Start Date:** January 2026  
**Duration:** 7-9 weeks  
**Budget:** $5,500 USD (~183-232 hours @ $30/hr)

---

## 🎯 Overview

Building on top of existing Stage 1 email processing platform to add:
- Business hierarchy (Account Managers → Clients → Customer Companies → Contacts)
- Real-time Gmail/Outlook sync (replacing MBOX-only workflow)
- Date range processing (replacing fixed count limits)
- Customer recognition and organization
- Contact database with signature parsing
- Business analytics dashboard
- Visual rules engine

---

## 🔧 Current System (Stage 1 - Already Built)

### Existing Features:
- ✅ MBOX/PST/OLM file upload and processing
- ✅ Google Drive integration
- ✅ Rule-based email tagging (spam, marketing, system, etc.)
- ✅ Email storage in Supabase PostgreSQL
- ✅ Redis job queue for background processing
- ✅ React frontend with Ant Design
- ✅ FastAPI backend
- ✅ Railway deployment

### Current Database Tables:
- `mailboxes` - Email sources (MBOX files)
- `emails` - Individual email records
- `processing_jobs` - Background job tracking
- `email_categories` - Tag assignments
- `user_integrations` - OAuth tokens

### Known Issues to Fix First:
- ❌ Error handling on processing page shows "800 failed" with no details
- ❌ No way to see which specific emails failed or why

---

## 🚨 PREREQUISITE: Improve Error Handling (Week 1)

**Priority:** CRITICAL - Fix before starting other features

### Current Problem:
Processing page shows:
```
Processed: 1,000 / 1,000 (800 failed)
```
No information about:
- Which emails failed
- Why they failed
- Error messages
- Ability to retry failed emails

### Required Solution:

#### 1. Database Schema Addition
```sql
-- Add error tracking to emails table
ALTER TABLE emails ADD COLUMN IF NOT EXISTS processing_error TEXT;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS processing_status TEXT DEFAULT 'pending';
-- Values: 'pending', 'processing', 'success', 'failed'
ALTER TABLE emails ADD COLUMN IF NOT EXISTS processing_attempts INTEGER DEFAULT 0;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS last_processing_attempt TIMESTAMPTZ;

-- Create index for failed emails
CREATE INDEX IF NOT EXISTS idx_emails_processing_status ON emails(processing_status);

-- Add error tracking to processing_jobs
ALTER TABLE processing_jobs ADD COLUMN IF NOT EXISTS error_summary JSONB;
-- Structure: {"total_errors": 800, "error_types": {"parse_error": 450, "encoding_error": 350}}
```

#### 2. Backend Changes

**File: `backend/services/email_processor.py`**

Update email processing to capture errors:

```python
def process_single_email(email_data, job_id):
    """Process a single email and track errors"""
    try:
        # Existing email processing logic
        email_record = parse_and_save_email(email_data)
        
        # Update success status
        update_email_status(email_record.id, status='success', error=None)
        
        return {'success': True, 'email_id': email_record.id}
        
    except Exception as e:
        error_message = f"{type(e).__name__}: {str(e)}"
        
        # Log error to database
        if 'email_id' in locals():
            update_email_status(
                email_id=email_record.id,
                status='failed',
                error=error_message
            )
        
        # Track error in Redis for real-time updates
        track_processing_error(job_id, error_message)
        
        return {
            'success': False, 
            'error': error_message,
            'email_subject': email_data.get('subject', 'Unknown')
        }

def update_email_status(email_id, status, error=None):
    """Update email processing status"""
    supabase.table('emails').update({
        'processing_status': status,
        'processing_error': error,
        'processing_attempts': supabase.raw('processing_attempts + 1'),
        'last_processing_attempt': 'now()'
    }).eq('id', email_id).execute()
```

**File: `backend/services/job_tracker.py`**

Add error aggregation:

```python
def track_processing_error(job_id, error_message):
    """Track error in Redis for real-time job monitoring"""
    redis_key = f"job:{job_id}:errors"
    
    # Store error with timestamp
    error_data = {
        'timestamp': datetime.now().isoformat(),
        'message': error_message
    }
    
    redis_client.lpush(redis_key, json.dumps(error_data))
    redis_client.expire(redis_key, 86400)  # 24 hours
    
    # Increment error counter
    redis_client.hincrby(f"job:{job_id}:stats", "failed", 1)

def get_job_errors(job_id, limit=100):
    """Get recent errors for a job"""
    redis_key = f"job:{job_id}:errors"
    errors = redis_client.lrange(redis_key, 0, limit - 1)
    return [json.loads(e) for e in errors]
```

#### 3. API Endpoints

**File: `backend/routers/jobs.py`**

```python
@router.get("/processing-jobs/{job_id}/errors")
async def get_processing_errors(job_id: str, limit: int = 100):
    """Get errors for a specific processing job"""
    
    # Get errors from Redis (for active jobs)
    redis_errors = get_job_errors(job_id, limit)
    
    # Get failed emails from database (for completed jobs)
    db_errors = supabase.table('emails').select(
        'id, subject, from_address, processing_error, last_processing_attempt'
    ).eq('mailbox_id', job_id).eq('processing_status', 'failed').limit(limit).execute()
    
    return {
        'job_id': job_id,
        'recent_errors': redis_errors,
        'failed_emails': db_errors.data,
        'total_failed': len(db_errors.data)
    }

@router.post("/processing-jobs/{job_id}/retry-failed")
async def retry_failed_emails(job_id: str):
    """Retry processing failed emails"""
    
    # Get all failed emails for this job
    failed_emails = supabase.table('emails').select('*').eq(
        'mailbox_id', job_id
    ).eq('processing_status', 'failed').execute()
    
    # Queue them for reprocessing
    # ... (implementation details)
    
    return {
        'message': f'Queued {len(failed_emails.data)} emails for retry',
        'job_id': job_id
    }
```

#### 4. Frontend Changes

**File: `frontend/src/pages/ProcessingJobs.tsx`**

Add error display section:

```typescript
const ProcessingJobDetail = ({ job }) => {
  const [errors, setErrors] = useState([]);
  const [showErrors, setShowErrors] = useState(false);

  useEffect(() => {
    if (job.failed > 0) {
      // Fetch errors
      fetch(`/api/processing-jobs/${job.id}/errors`)
        .then(res => res.json())
        .then(data => setErrors(data.failed_emails))
        .catch(err => console.error(err));
    }
  }, [job.id, job.failed]);

  return (
    <Card>
      <Statistic.Group>
        <Statistic title="Total" value={job.total} />
        <Statistic title="Processed" value={job.processed} />
        <Statistic title="Success" value={job.success} valueStyle={{ color: '#3f8600' }} />
        <Statistic 
          title="Failed" 
          value={job.failed} 
          valueStyle={{ color: job.failed > 0 ? '#cf1322' : '#999' }} 
        />
      </Statistic.Group>

      {/* NEW: Error Details Section */}
      {job.failed > 0 && (
        <div style={{ marginTop: 20 }}>
          <Button 
            type="link" 
            onClick={() => setShowErrors(!showErrors)}
            icon={<ExclamationCircleOutlined />}
          >
            {showErrors ? 'Hide' : 'Show'} Error Details ({job.failed} failed)
          </Button>

          {showErrors && (
            <>
              <Table
                dataSource={errors}
                columns={[
                  { title: 'Subject', dataIndex: 'subject', key: 'subject' },
                  { title: 'From', dataIndex: 'from_address', key: 'from' },
                  { title: 'Error', dataIndex: 'processing_error', key: 'error', 
                    render: (text) => <Text type="danger" code>{text}</Text> 
                  },
                  { title: 'Attempted', dataIndex: 'last_processing_attempt', key: 'time',
                    render: (time) => new Date(time).toLocaleString()
                  }
                ]}
                pagination={{ pageSize: 10 }}
                size="small"
                style={{ marginTop: 10 }}
              />

              <Button 
                type="primary" 
                danger 
                icon={<ReloadOutlined />}
                onClick={() => retryFailedEmails(job.id)}
                style={{ marginTop: 10 }}
              >
                Retry Failed Emails
              </Button>
            </>
          )}
        </div>
      )}
    </Card>
  );
};
```

#### 5. Testing Checklist

- [ ] Process MBOX file with known errors (corrupted emails, encoding issues)
- [ ] Verify error messages are captured in database
- [ ] Verify error count matches actual failures
- [ ] Test error display on frontend
- [ ] Test retry functionality
- [ ] Verify Redis error tracking works
- [ ] Test with 10k+ emails to ensure performance

---

## 📋 Stage 2 Phase 1 Development Plan

### Week 1: Foundation & Error Handling
**Hours: 30-35**

**Tasks:**
1. ✅ Fix error handling (above) - MUST BE DONE FIRST
2. Database schema design for new tables
3. Set up database migrations
4. Create initial API structure

**Deliverables:**
- Error tracking working on processing page
- Database schema document
- Migration scripts ready

---

### Week 2-3: Account Manager & Client Hierarchy
**Hours: 40-50**

#### Database Schema

**File: `migrations/add_stage2_tables.sql`**

```sql
-- 1. Account Managers (Users)
CREATE TABLE account_managers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  role TEXT NOT NULL DEFAULT 'account_manager',
  -- Roles: 'admin', 'account_manager', 'viewer'
  password_hash TEXT,
  active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Clients (The Data Collaborative's consulting clients)
CREATE TABLE clients (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  account_manager_id UUID REFERENCES account_managers(id),
  client_name TEXT NOT NULL,
  client_label TEXT, -- Short label like "Carbon8", "EBNT"
  industry TEXT,
  status TEXT DEFAULT 'active', -- 'active', 'inactive', 'prospect'
  
  -- Client's systems configuration
  uses_quickbase BOOLEAN DEFAULT FALSE,
  quickbase_realm TEXT,
  quickbase_api_token TEXT, -- encrypted
  
  uses_printiq BOOLEAN DEFAULT FALSE,
  printiq_api_url TEXT,
  printiq_api_key TEXT, -- encrypted
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Customer Companies (Each client's customers)
CREATE TABLE customer_companies (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
  company_name TEXT NOT NULL,
  email_domains JSONB, -- ["abcmfg.com", "abc-manufacturing.com"]
  industry TEXT,
  
  -- Engagement metrics
  first_contact_date TIMESTAMPTZ,
  last_contact_date TIMESTAMPTZ,
  total_emails INTEGER DEFAULT 0,
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Customer Contacts (Individuals at customer companies)
CREATE TABLE customer_contacts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  customer_company_id UUID REFERENCES customer_companies(id) ON DELETE CASCADE,
  client_id UUID REFERENCES clients(id), -- denormalized for easy querying
  
  email_address TEXT NOT NULL,
  full_name TEXT,
  first_name TEXT,
  last_name TEXT,
  
  -- Signature-extracted fields
  job_title TEXT,
  company_name TEXT, -- from signature, may differ from customer_company
  phone_number TEXT,
  linkedin_url TEXT,
  
  -- Engagement
  first_contacted_at TIMESTAMPTZ,
  last_contacted_at TIMESTAMPTZ,
  total_emails_sent INTEGER DEFAULT 0,
  total_emails_received INTEGER DEFAULT 0,
  
  signature_data JSONB, -- full parsed signature
  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(customer_company_id, email_address)
);

-- 5. Update existing mailboxes table
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS account_manager_id UUID REFERENCES account_managers(id);
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS mailbox_type TEXT DEFAULT 'mbox';
-- Values: 'mbox', 'gmail', 'outlook'
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS oauth_token TEXT; -- encrypted
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS oauth_refresh_token TEXT; -- encrypted
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMPTZ;
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS sync_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE mailboxes ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ;

-- 6. Update existing emails table
ALTER TABLE emails ADD COLUMN IF NOT EXISTS client_id UUID REFERENCES clients(id);
ALTER TABLE emails ADD COLUMN IF NOT EXISTS customer_company_id UUID REFERENCES customer_companies(id);
ALTER TABLE emails ADD COLUMN IF NOT EXISTS customer_contact_id UUID REFERENCES customer_contacts(id);
ALTER TABLE emails ADD COLUMN IF NOT EXISTS direction TEXT; -- 'inbound', 'outbound'

-- 7. Customer Recognition Rules
CREATE TABLE customer_recognition_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id UUID REFERENCES clients(id), -- NULL = applies to all
  rule_name TEXT NOT NULL,
  rule_type TEXT NOT NULL, -- 'from_domain', 'from_email', 'subject_contains', 'keyword_match'
  pattern TEXT NOT NULL, -- e.g., "*@ebntsolar.com", "Quote #"
  customer_company_id UUID REFERENCES customer_companies(id), -- which company to tag
  priority INTEGER DEFAULT 0, -- execution order
  active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_clients_account_manager ON clients(account_manager_id);
CREATE INDEX idx_customer_companies_client ON customer_companies(client_id);
CREATE INDEX idx_customer_contacts_company ON customer_contacts(customer_company_id);
CREATE INDEX idx_customer_contacts_email ON customer_contacts(email_address);
CREATE INDEX idx_emails_client ON emails(client_id);
CREATE INDEX idx_emails_customer_company ON emails(customer_company_id);
CREATE INDEX idx_emails_customer_contact ON emails(customer_contact_id);
CREATE INDEX idx_rules_client ON customer_recognition_rules(client_id);
CREATE INDEX idx_rules_active ON customer_recognition_rules(active) WHERE active = TRUE;
```

#### API Endpoints

**File: `backend/routers/account_managers.py`**

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/account-managers", tags=["account-managers"])

class AccountManagerCreate(BaseModel):
    name: str
    email: str
    role: str = "account_manager"

@router.post("/")
async def create_account_manager(data: AccountManagerCreate):
    """Create new account manager"""
    # Implementation
    pass

@router.get("/")
async def list_account_managers():
    """List all account managers"""
    # Implementation
    pass

@router.get("/{manager_id}")
async def get_account_manager(manager_id: str):
    """Get account manager details"""
    # Implementation
    pass
```

**File: `backend/routers/clients.py`**

```python
@router.post("/")
async def create_client(data: ClientCreate):
    """Create new client"""
    pass

@router.get("/")
async def list_clients(account_manager_id: str = None):
    """List clients, optionally filtered by account manager"""
    pass

@router.get("/{client_id}")
async def get_client(client_id: str):
    """Get client details with customer counts"""
    pass

@router.patch("/{client_id}")
async def update_client(client_id: str, data: ClientUpdate):
    """Update client information"""
    pass
```

**File: `backend/routers/customers.py`**

```python
@router.post("/")
async def create_customer_company(data: CustomerCompanyCreate):
    """Create new customer company"""
    pass

@router.get("/")
async def list_customer_companies(client_id: str):
    """List customer companies for a client"""
    pass

@router.get("/{company_id}")
async def get_customer_company(company_id: str):
    """Get customer company with contacts and email stats"""
    pass
```

**Deliverables:**
- All database tables created and migrated
- CRUD APIs for account managers, clients, customers
- Basic admin UI to create test data
- Seed data: 1 account manager (Jeff), 3 clients (Carbon8, EBNT, Wisk)

---

### Week 4-5: Gmail & Outlook OAuth Integration
**Hours: 45-55**

#### Gmail Integration

**File: `backend/services/gmail_sync.py`**

```python
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta

class GmailSyncService:
    def __init__(self, mailbox_id, oauth_token, refresh_token):
        self.mailbox_id = mailbox_id
        self.credentials = Credentials(
            token=oauth_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET
        )
        self.service = build('gmail', 'v1', credentials=self.credentials)
    
    def fetch_emails_by_date_range(self, start_date, end_date=None):
        """Fetch emails within date range"""
        if end_date is None:
            end_date = datetime.now()
        
        # Build Gmail query
        query = f"after:{start_date.strftime('%Y/%m/%d')}"
        if end_date:
            query += f" before:{end_date.strftime('%Y/%m/%d')}"
        
        # Fetch message IDs
        messages = []
        page_token = None
        
        while True:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=500,
                pageToken=page_token
            ).execute()
            
            messages.extend(results.get('messages', []))
            page_token = results.get('nextPageToken')
            
            if not page_token:
                break
        
        return messages
    
    def fetch_single_email(self, message_id):
        """Fetch full email content"""
        message = self.service.users().messages().get(
            userId='me',
            id=message_id,
            format='full'
        ).execute()
        
        return self.parse_gmail_message(message)
    
    def parse_gmail_message(self, message):
        """Parse Gmail message to standard format"""
        headers = {h['name']: h['value'] for h in message['payload']['headers']}
        
        # Extract body
        body = self.extract_body(message['payload'])
        
        return {
            'message_id': message['id'],
            'thread_id': message.get('threadId'),
            'subject': headers.get('Subject', ''),
            'from_address': headers.get('From', ''),
            'to_addresses': headers.get('To', '').split(','),
            'cc_addresses': headers.get('Cc', '').split(',') if headers.get('Cc') else [],
            'date': headers.get('Date', ''),
            'body_text': body.get('text', ''),
            'body_html': body.get('html', ''),
            'labels': message.get('labelIds', [])
        }
    
    def fetch_gmail_filters(self):
        """Fetch existing Gmail filters"""
        filters = self.service.users().settings().filters().list(
            userId='me'
        ).execute()
        
        return filters.get('filter', [])
```

**File: `backend/routers/gmail_oauth.py`**

```python
from fastapi import APIRouter, HTTPException
from google_auth_oauthlib.flow import Flow

router = APIRouter(prefix="/gmail", tags=["gmail"])

@router.get("/oauth/authorize")
async def gmail_authorize():
    """Start Gmail OAuth flow"""
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
            }
        },
        scopes=[
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.settings.basic'
        ]
    )
    
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    return {"auth_url": auth_url, "state": state}

@router.get("/oauth/callback")
async def gmail_callback(code: str, state: str):
    """Handle Gmail OAuth callback"""
    # Exchange code for tokens
    # Save tokens to database
    # Create mailbox record
    pass

@router.post("/sync/{mailbox_id}/initial")
async def initial_sync(
    mailbox_id: str,
    start_date: str,
    end_date: str = None
):
    """Start initial Gmail sync for date range"""
    # Queue background job to fetch emails
    pass

@router.post("/sync/{mailbox_id}/realtime")
async def enable_realtime_sync(mailbox_id: str):
    """Enable real-time Gmail sync"""
    # Set up periodic sync every 15 minutes
    pass
```

#### Outlook Integration

**File: `backend/services/outlook_sync.py`**

Similar structure to Gmail, using Microsoft Graph API.

**Deliverables:**
- Gmail OAuth flow working
- Outlook OAuth flow working
- Date range sync working
- Auto-import of Gmail filters
- Auto-import of Outlook rules
- Real-time sync scheduler (15-min intervals)

---

### Week 6: Customer Recognition & Rules Engine
**Hours: 35-45**

**File: `backend/services/customer_matcher.py`**

```python
class CustomerMatcher:
    def __init__(self):
        self.rules = self.load_rules()
    
    def load_rules(self):
        """Load all active rules from database"""
        rules = supabase.table('customer_recognition_rules').select('*').eq(
            'active', True
        ).order('priority', desc=True).execute()
        
        return rules.data
    
    def match_email_to_customer(self, email_data):
        """Apply rules to identify customer company"""
        
        for rule in self.rules:
            if self.rule_matches(rule, email_data):
                return rule['customer_company_id']
        
        return None
    
    def rule_matches(self, rule, email_data):
        """Check if rule matches email"""
        
        if rule['rule_type'] == 'from_domain':
            # Check if sender domain matches pattern
            sender_domain = email_data['from_address'].split('@')[-1]
            pattern = rule['pattern'].replace('*@', '')
            return sender_domain == pattern
        
        elif rule['rule_type'] == 'from_email':
            # Exact email match
            return email_data['from_address'] == rule['pattern']
        
        elif rule['rule_type'] == 'subject_contains':
            # Subject contains keyword
            return rule['pattern'].lower() in email_data['subject'].lower()
        
        elif rule['rule_type'] == 'keyword_match':
            # Body contains keyword
            return rule['pattern'].lower() in email_data['body_text'].lower()
        
        return False
```

**File: `backend/routers/rules.py`**

```python
@router.post("/")
async def create_rule(data: RuleCreate):
    """Create customer recognition rule"""
    pass

@router.get("/")
async def list_rules(client_id: str = None):
    """List rules, optionally filtered by client"""
    pass

@router.post("/{rule_id}/test")
async def test_rule(rule_id: str, email_id: str):
    """Test rule against a sample email"""
    pass

@router.post("/apply-to-historical")
async def apply_rules_to_historical(
    start_date: str,
    end_date: str,
    client_id: str = None
):
    """Apply rules to historical emails"""
    pass
```

**Frontend: Rules Engine UI**

**File: `frontend/src/pages/RulesEngine.tsx`**

```typescript
const RuleBuilder = () => {
  const [ruleType, setRuleType] = useState('from_domain');
  const [pattern, setPattern] = useState('');
  const [customerCompany, setCustomerCompany] = useState(null);

  return (
    <Card title="Create Customer Recognition Rule">
      <Form layout="vertical">
        <Form.Item label="Rule Type">
          <Select value={ruleType} onChange={setRuleType}>
            <Option value="from_domain">From Domain (e.g., *@company.com)</Option>
            <Option value="from_email">From Email (exact match)</Option>
            <Option value="subject_contains">Subject Contains</Option>
            <Option value="keyword_match">Body Contains Keyword</Option>
          </Select>
        </Form.Item>

        <Form.Item label="Pattern">
          <Input 
            value={pattern}
            onChange={e => setPattern(e.target.value)}
            placeholder={getPatternPlaceholder(ruleType)}
          />
        </Form.Item>

        <Form.Item label="Tag as Customer Company">
          <Select 
            value={customerCompany}
            onChange={setCustomerCompany}
            showSearch
          >
            {/* Load customer companies */}
          </Select>
        </Form.Item>

        <Form.Item label="Test Rule">
          <Button onClick={testRule}>Test Against Sample Email</Button>
        </Form.Item>

        <Button type="primary" onClick={saveRule}>
          Save Rule
        </Button>
      </Form>
    </Card>
  );
};
```

**Deliverables:**
- Rule matching engine working
- Rules CRUD APIs
- Rules UI with visual builder
- Test rule functionality
- Apply to historical emails functionality
- Import Filters.json/Signatures.json for MBOX uploads

---

### Week 7: Contact Extraction & Signature Parsing
**Hours: 35-45**

**File: `backend/services/signature_parser.py`**

```python
import re
from anthropic import Anthropic

class SignatureParser:
    def __init__(self):
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    
    def extract_signature(self, email_body):
        """Extract signature block from email body"""
        
        # Common signature separators
        separators = [
            r'\n--\s*\n',
            r'\n_{3,}\n',
            r'\nSent from',
            r'\nBest regards,',
            r'\nThanks,',
            r'\nCheers,'
        ]
        
        for separator in separators:
            match = re.search(separator, email_body, re.IGNORECASE)
            if match:
                return email_body[match.end():].strip()
        
        # Fallback: last 5 lines
        lines = email_body.split('\n')
        return '\n'.join(lines[-5:])
    
    def parse_signature_with_ai(self, signature_text):
        """Use Claude to parse signature"""
        
        prompt = f"""Extract contact information from this email signature.
Return ONLY valid JSON with these fields (use null if not found):

{{
  "job_title": "Senior Sales Manager",
  "company_name": "Acme Corp",
  "phone": "+1-555-0123",
  "linkedin_url": "linkedin.com/in/johndoe"
}}

Signature:
{signature_text}
"""
        
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse JSON response
        import json
        return json.loads(response.content[0].text)
    
    def parse_signature_with_regex(self, signature_text):
        """Fallback regex-based parsing"""
        
        result = {
            "job_title": None,
            "company_name": None,
            "phone": None,
            "linkedin_url": None
        }
        
        # Phone pattern
        phone_pattern = r'[\+]?[(]?[0-9]{1,4}[)]?[-\s\.]?[(]?[0-9]{1,4}[)]?[-\s\.]?[0-9]{1,4}[-\s\.]?[0-9]{1,9}'
        phone_match = re.search(phone_pattern, signature_text)
        if phone_match:
            result['phone'] = phone_match.group(0)
        
        # LinkedIn pattern
        linkedin_pattern = r'linkedin\.com/in/[\w-]+'
        linkedin_match = re.search(linkedin_pattern, signature_text)
        if linkedin_match:
            result['linkedin_url'] = linkedin_match.group(0)
        
        return result
```

**File: `backend/services/contact_extractor.py`**

```python
class ContactExtractor:
    def __init__(self):
        self.signature_parser = SignatureParser()
    
    def extract_contact_from_email(self, email_data):
        """Extract contact from email From field and signature"""
        
        from_address = email_data['from_address']
        
        # Parse name from From field
        # "John Doe <john@company.com>" -> name: "John Doe", email: "john@company.com"
        name_match = re.match(r'^([^<]+)<([^>]+)>$', from_address)
        if name_match:
            full_name = name_match.group(1).strip()
            email = name_match.group(2).strip()
        else:
            full_name = None
            email = from_address.strip()
        
        # Parse signature for additional info
        signature_text = self.signature_parser.extract_signature(
            email_data.get('body_text', '')
        )
        
        signature_data = self.signature_parser.parse_signature_with_ai(signature_text)
        
        # Split name into first/last
        first_name, last_name = self.split_name(full_name)
        
        return {
            'email_address': email,
            'full_name': full_name,
            'first_name': first_name,
            'last_name': last_name,
            'job_title': signature_data.get('job_title'),
            'company_name': signature_data.get('company_name'),
            'phone_number': signature_data.get('phone'),
            'linkedin_url': signature_data.get('linkedin_url'),
            'signature_data': signature_data
        }
    
    def get_or_create_contact(self, contact_data, customer_company_id, client_id):
        """Get existing contact or create new one"""
        
        # Check if contact exists
        existing = supabase.table('customer_contacts').select('*').eq(
            'customer_company_id', customer_company_id
        ).eq('email_address', contact_data['email_address']).execute()
        
        if existing.data:
            # Update with new signature data
            return self.update_contact(existing.data[0]['id'], contact_data)
        else:
            # Create new contact
            return self.create_contact(contact_data, customer_company_id, client_id)
```

**Deliverables:**
- Signature parsing working (AI + regex fallback)
- Contact extraction from emails
- Deduplication logic
- Contact CRUD APIs
- Contact directory UI
- Link contacts to customer companies

---

### Week 8: Analytics Dashboard
**Hours: 40-50**

**File: `backend/routers/analytics.py`**

```python
@router.get("/dashboard")
async def get_dashboard_summary(account_manager_id: str = None):
    """Get dashboard summary statistics"""
    
    # Client counts
    # Customer counts
    # Email volumes
    # Top customers by engagement
    # Recently quiet customers
    pass

@router.get("/email-volume")
async def get_email_volume(
    client_id: str = None,
    group_by: str = "day",  # day, week, month
    period: str = "30d"  # 7d, 30d, 90d, 6m, 1y
):
    """Get email volume trends"""
    pass

@router.get("/customer-engagement")
async def get_customer_engagement(client_id: str):
    """Get customer engagement metrics"""
    
    # Active (emailed in last 30 days)
    # Quiet (31-60 days)
    # At risk (60+ days)
    pass

@router.get("/response-times")
async def get_response_times(
    client_id: str = None,
    customer_company_id: str = None
):
    """Get response time analytics"""
    pass
```

**Frontend Dashboard Components**

```typescript
// Email Volume Chart
const EmailVolumeChart = ({ clientId }) => {
  const [data, setData] = useState([]);

  useEffect(() => {
    fetch(`/api/analytics/email-volume?client_id=${clientId}&period=30d`)
      .then(res => res.json())
      .then(setData);
  }, [clientId]);

  return (
    <Card title="Email Volume (Last 30 Days)">
      <Line data={data} />
    </Card>
  );
};

// Customer Engagement Metrics
const CustomerEngagement = ({ clientId }) => {
  return (
    <Row gutter={16}>
      <Col span={8}>
        <Statistic 
          title="Active Customers" 
          value={189} 
          prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
        />
      </Col>
      <Col span={8}>
        <Statistic 
          title="Quiet (31-60 days)" 
          value={34} 
          prefix={<ClockCircleOutlined style={{ color: '#faad14' }} />}
        />
      </Col>
      <Col span={8}>
        <Statistic 
          title="At Risk (60+ days)" 
          value={24} 
          prefix={<WarningOutlined style={{ color: '#f5222d' }} />}
        />
      </Col>
    </Row>
  );
};

// Top Customers Table
const TopCustomers = ({ clientId }) => {
  return (
    <Table
      columns={[
        { title: 'Customer', dataIndex: 'company_name' },
        { title: 'Emails', dataIndex: 'email_count', sorter: true },
        { title: 'Last Contact', dataIndex: 'last_contact_date' },
        { title: 'Contacts', dataIndex: 'contact_count' }
      ]}
      dataSource={customers}
    />
  );
};
```

**Deliverables:**
- Dashboard summary API
- Email volume analytics
- Customer engagement metrics
- Response time tracking
- Top customers ranking
- Analytics UI with charts
- Export to CSV functionality

---

### Week 9: Testing & Deployment
**Hours: 30-40**

**Testing Checklist:**

- [ ] End-to-end test: Create account manager → Add client → Import Gmail
- [ ] Test Gmail OAuth flow
- [ ] Test Outlook OAuth flow
- [ ] Test date range processing (last 30 days, 6 months, custom)
- [ ] Test customer recognition rules with sample data
- [ ] Test contact extraction with various signature formats
- [ ] Test error handling and display
- [ ] Test analytics dashboard with real data
- [ ] Performance test with 10k+ emails
- [ ] Security audit: OAuth tokens encrypted, no SQL injection
- [ ] Deploy to Railway staging
- [ ] Client UAT testing
- [ ] Deploy to Railway production

**Documentation:**

- [ ] API documentation (Swagger/OpenAPI)
- [ ] User guide for account managers
- [ ] Admin guide for rules engine
- [ ] Deployment runbook

---

## 🔑 Environment Variables Required

```bash
# Existing
DATABASE_URL=
REDIS_URL=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=

# New for Stage 2
ANTHROPIC_API_KEY=  # For signature parsing
MICROSOFT_CLIENT_ID=  # For Outlook OAuth
MICROSOFT_CLIENT_SECRET=
MICROSOFT_REDIRECT_URI=

# Security
ENCRYPTION_KEY=  # For OAuth token encryption
JWT_SECRET=  # For session management
```

---

## 📊 Success Metrics

### Technical Metrics:
- Gmail sync: Process 10k emails in < 30 minutes
- Outlook sync: Process 10k emails in < 30 minutes
- Rule matching: < 100ms per email
- Contact extraction: < 500ms per email (with AI)
- Dashboard load: < 3 seconds
- Error rate: < 5% of emails

### Business Metrics:
- 100% of existing MBOX functionality preserved
- Real-time sync working within 15 minutes
- Rules accuracy: > 90% emails correctly tagged
- Contact extraction: > 80% signatures parsed correctly
- Zero data loss during migration

---

## 🚀 Getting Started

### Day 1: Error Handling Fix

1. Review current error handling code
2. Implement database schema changes
3. Update `email_processor.py` to capture errors
4. Create `/processing-jobs/{id}/errors` API endpoint
5. Update frontend to display errors
6. Test with known-bad MBOX files
7. Verify error display works

### Day 2-3: Database Setup

1. Review and run migration scripts
2. Create seed data (1 account manager, 3 clients)
3. Test foreign key relationships
4. Create CRUD APIs for account managers
5. Create CRUD APIs for clients
6. Build basic admin UI

### Week 2 onwards: Follow plan above

---

## 📞 Questions to Resolve Before Starting

1. **OAuth Apps**: Do we have Google/Microsoft OAuth apps created?
2. **Anthropic API**: Do we have API key for Claude (signature parsing)?
3. **Encryption**: Which encryption library for OAuth tokens?
4. **Migration Strategy**: Migrate existing mailboxes or start fresh?
5. **Existing Data**: Should we backfill customer/contact data from Stage 1 emails?

---

## 🛑 Blockers & Risks

### Potential Blockers:
- Google OAuth app approval (can take 1-2 weeks)
- Microsoft OAuth app configuration
- Gmail/Outlook API rate limits
- Signature parsing accuracy with Claude API

### Mitigation:
- Start OAuth app approvals ASAP
- Implement rate limiting and retry logic
- Build regex fallback for signature parsing
- Add extensive error handling

---

## 📝 Notes

- This plan builds incrementally - each week delivers working features
- Error handling MUST be fixed first (Week 1, Day 1-2)
- Database migrations should be reversible
- All APIs should have proper error handling
- Frontend should show loading states
- Use TypeScript for type safety
- Write integration tests for critical flows
- Document as you build

---

**Ready to start? Begin with error handling fix (above) then proceed week by week!**
