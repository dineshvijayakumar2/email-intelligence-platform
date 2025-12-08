# Email Intelligence Platform - Technical Design Document

## Project Overview

**Goal:** Build a two-stage POC that converts email archives into structured, AI-enriched datasets for business intelligence.

**Stage 1:** Email Archive → Structured Dataset (2-3 weeks)
**Stage 2:** AI Enrichment Layer (2-3 weeks)

**Your Context:**
- First professional AI implementation project
- Using vibe coding (AI-assisted development with Claude Code)
- Need to demonstrate competence without overcommitting
- Data science background, familiar with Python

---

## Technology Stack Decisions

### Core Stack: Supabase + Python + Retool → FastAPI + Streamlit

**Stage 1 (Quick Demo):**
- **Database:** Supabase (PostgreSQL with instant REST API)
- **Processing:** Python scripts (local/Railway deployment)
- **Frontend:** Retool (drag-and-drop UI builder)
- **Deployment:** Supabase Cloud + Railway.app

**Stage 2 (AI Integration):**
- **Backend API:** FastAPI (async, modern, Python-native)
- **AI Service:** Anthropic Claude API
- **Frontend:** Streamlit (Python-only, rapid development)
- **Deployment:** Railway.app or Render.com

### Why NOT MongoDB?

Email data is inherently relational and structured:
- Fixed schema (sender, recipient, date, subject, body)
- Relational queries (folders, threads, replies)
- PostgreSQL's SQL excels at filtering and sorting
- Supabase provides instant REST API (no custom API needed for Stage 1)

**MongoDB is better for:**
- Flexible/evolving schemas
- Document storage (like resource chunks)
- Heavy vector search workloads

**This project needs:**
- Relational structure
- Complex filtering
- Full-text search (PostgreSQL built-in)

### Why Retool for Stage 1?

- **Speed:** Build professional UI in 4-6 hours vs 3-4 days coding
- **Demo-ready:** Looks polished, works immediately
- **No frontend coding:** Focus on backend logic
- **Easy client access:** Share URL, they can explore
- **POC-perfect:** Quick wins build confidence

### Why FastAPI + Streamlit for Stage 2?

- **FastAPI:** You're familiar (Alzheimer-Bot pattern)
- **Streamlit:** Pure Python, rapid data app development
- **AI Integration:** Native async support for Anthropic API
- **Full Control:** Complex AI workflows need custom logic
- **Maintainable:** Clean separation of concerns

---

## Architecture Overview

### Stage 1: Extraction & Structuring

```
┌─────────────────┐
│  Email Archive  │
│  (MBOX/PST)     │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ Python Pipeline │
│  - Extract      │
│  - Normalize    │
│  - Categorize   │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ Supabase        │
│ (PostgreSQL)    │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ Retool          │
│ Dashboard       │
└─────────────────┘
```

### Stage 2: AI Enrichment

```
┌─────────────────┐
│ Supabase DB     │
└────────┬────────┘
         │
         v
┌─────────────────┐      ┌──────────────┐
│ FastAPI Backend │◄────►│ Claude API   │
│  - Batch Process│      │ (Anthropic)  │
│  - Enrichment   │      └──────────────┘
│  - Queue Mgmt   │
└────────┬────────┘
         │
         v
┌─────────────────┐
│ Streamlit UI    │
│  - Dashboard    │
│  - AI Controls  │
│  - Results View │
└─────────────────┘
```

---

## Database Schema (Supabase/PostgreSQL)

### Core Tables

```sql
-- Main emails table
CREATE TABLE emails (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id TEXT UNIQUE NOT NULL,
  thread_id TEXT,
  folder_path TEXT,
  sender_email TEXT NOT NULL,
  sender_name TEXT,
  recipients JSONB,  -- Array of {email, name} objects
  cc_list JSONB,
  bcc_list JSONB,
  subject TEXT,
  body_text TEXT,
  body_html TEXT,
  sent_date TIMESTAMPTZ NOT NULL,
  received_date TIMESTAMPTZ,
  is_outbound BOOLEAN DEFAULT false,
  is_reply BOOLEAN DEFAULT false,
  message_size INTEGER,
  raw_headers JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Folder hierarchy
CREATE TABLE folders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  folder_path TEXT UNIQUE NOT NULL,
  parent_folder_id UUID REFERENCES folders(id),
  folder_type TEXT,  -- inbox, sent, spam, archive, user
  message_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Basic categorization (rule-based)
CREATE TABLE email_categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
  category TEXT NOT NULL,  -- system, spam, marketing, transactional, conversation
  confidence DECIMAL(3,2) DEFAULT 1.0,
  detection_method TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(email_id, category)
);

-- AI enrichment (Stage 2)
CREATE TABLE email_enrichment (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id UUID REFERENCES emails(id) ON DELETE CASCADE UNIQUE,
  email_type TEXT,
  tone TEXT,
  sentiment TEXT,
  happiness_index DECIMAL(3,2),
  escalation_needed BOOLEAN,
  short_summary TEXT,
  extracted_entities JSONB,
  custom_fields JSONB,  -- Flexible for evolving schema
  enriched_at TIMESTAMPTZ DEFAULT NOW(),
  model_version TEXT
);

-- Processing status tracking
CREATE TABLE processing_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_type TEXT NOT NULL,  -- extraction, enrichment
  status TEXT NOT NULL,  -- pending, running, completed, failed
  total_records INTEGER,
  processed_records INTEGER DEFAULT 0,
  failed_records INTEGER DEFAULT 0,
  error_log JSONB,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance indexes
CREATE INDEX idx_emails_sent_date ON emails(sent_date);
CREATE INDEX idx_emails_sender ON emails(sender_email);
CREATE INDEX idx_emails_folder ON emails(folder_path);
CREATE INDEX idx_emails_thread ON emails(thread_id);
CREATE INDEX idx_emails_subject ON emails USING gin(to_tsvector('english', subject));
CREATE INDEX idx_emails_body ON emails USING gin(to_tsvector('english', body_text));

-- Full-text search function
CREATE OR REPLACE FUNCTION search_emails(search_query TEXT)
RETURNS TABLE (
  id UUID,
  subject TEXT,
  sender_email TEXT,
  sent_date TIMESTAMPTZ,
  rank REAL
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    e.id,
    e.subject,
    e.sender_email,
    e.sent_date,
    ts_rank(
      to_tsvector('english', e.subject || ' ' || COALESCE(e.body_text, '')),
      plainto_tsquery('english', search_query)
    ) as rank
  FROM emails e
  WHERE to_tsvector('english', e.subject || ' ' || COALESCE(e.body_text, ''))
    @@ plainto_tsquery('english', search_query)
  ORDER BY rank DESC;
END;
$$ LANGUAGE plpgsql;
```

### Database Views (For Retool/Queries)

```sql
-- Email statistics by folder
CREATE VIEW folder_stats AS
SELECT 
  f.folder_path,
  f.folder_type,
  COUNT(e.id) as email_count,
  MIN(e.sent_date) as earliest_email,
  MAX(e.sent_date) as latest_email,
  COUNT(CASE WHEN e.is_outbound THEN 1 END) as outbound_count,
  COUNT(CASE WHEN NOT e.is_outbound THEN 1 END) as inbound_count
FROM folders f
LEFT JOIN emails e ON e.folder_path = f.folder_path
GROUP BY f.id, f.folder_path, f.folder_type;

-- Daily email volume
CREATE VIEW daily_email_volume AS
SELECT 
  DATE(sent_date) as date,
  COUNT(*) as total_emails,
  COUNT(CASE WHEN is_outbound THEN 1 END) as outbound,
  COUNT(CASE WHEN NOT is_outbound THEN 1 END) as inbound,
  COUNT(DISTINCT sender_email) as unique_senders
FROM emails
GROUP BY DATE(sent_date)
ORDER BY date;

-- Top correspondents
CREATE VIEW top_correspondents AS
SELECT 
  sender_email,
  sender_name,
  COUNT(*) as email_count,
  MIN(sent_date) as first_email,
  MAX(sent_date) as last_email
FROM emails
GROUP BY sender_email, sender_name
ORDER BY email_count DESC;
```

---

## Project Structure

### Stage 1: Processing Pipeline

```
email-intelligence-poc/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── config/
│   ├── config.yaml              # Processing configuration
│   ├── supabase_config.py       # DB connection settings
│   └── categories.yaml          # Categorization rules
│
├── src/
│   ├── __init__.py
│   │
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── base_extractor.py   # Abstract base class
│   │   ├── mbox_extractor.py   # MBOX format handler
│   │   └── pst_extractor.py    # PST format handler (Stage 1.5)
│   │
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── normalizer.py       # Clean and standardize data
│   │   ├── categorizer.py      # Rule-based categorization
│   │   └── thread_detector.py  # Thread relationship detection
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── supabase_client.py  # Supabase connection wrapper
│   │   └── operations.py       # CRUD operations
│   │
│   └── utils/
│       ├── __init__.py
│       ├── text_cleaner.py     # HTML stripping, UTF-8 handling
│       ├── date_parser.py      # Robust date parsing
│       └── logger.py           # Logging configuration
│
├── scripts/
│   ├── run_extraction.py        # Main pipeline runner
│   ├── create_tables.sql        # Database schema
│   └── sample_data_generator.py # Test data for development
│
├── tests/
│   ├── __init__.py
│   ├── test_extractors.py
│   ├── test_normalizer.py
│   └── test_database.py
│
└── docs/
    ├── SETUP.md                 # Installation instructions
    ├── RETOOL_GUIDE.md          # Retool configuration
    └── API_REFERENCE.md         # (For Stage 2)
```

### Stage 2: API + Streamlit

```
email-intelligence-poc/
├── (all Stage 1 files)
│
├── api/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── emails.py            # Email CRUD endpoints
│   │   ├── enrichment.py        # AI enrichment endpoints
│   │   └── search.py            # Search endpoints
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ai_service.py        # Anthropic API integration
│   │   ├── batch_processor.py  # Batch AI processing
│   │   └── queue_manager.py    # Processing queue
│   │
│   └── models/
│       ├── __init__.py
│       ├── requests.py          # Pydantic request models
│       └── responses.py         # Pydantic response models
│
├── streamlit_app/
│   ├── Home.py                  # Main entry point
│   │
│   ├── pages/
│   │   ├── 1_📊_Dashboard.py
│   │   ├── 2_🔍_Search.py
│   │   ├── 3_🤖_AI_Enrichment.py
│   │   └── 4_⚙️_Settings.py
│   │
│   ├── components/
│   │   ├── __init__.py
│   │   ├── charts.py            # Reusable chart components
│   │   └── filters.py           # Filter components
│   │
│   └── utils/
│       ├── __init__.py
│       ├── api_client.py        # FastAPI client wrapper
│       └── session_state.py    # State management helpers
│
├── docker-compose.yml           # Local development setup
└── railway.json                 # Railway deployment config
```

---

## Implementation Guide

### Phase 1: Database Setup (Day 1, 1-2 hours)

**1. Create Supabase Project**
```bash
# Sign up at https://supabase.com
# Create new project
# Note: Database URL, API Key, anon key
```

**2. Run Schema Creation**
```sql
-- Copy the CREATE TABLE statements from above
-- Run in Supabase SQL Editor
-- Verify tables created successfully
```

**3. Create `.env` file**
```bash
# .env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key

# For Stage 2
ANTHROPIC_API_KEY=your-anthropic-key
```

### Phase 2: Email Extraction (Day 1-2, 6-8 hours)

**Key Files to Create:**

**`src/extractors/base_extractor.py`**
```python
from abc import ABC, abstractmethod
from typing import Iterator, Dict
import logging

logger = logging.getLogger(__name__)

class BaseExtractor(ABC):
    """Abstract base class for email extractors"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.stats = {
            'total': 0,
            'success': 0,
            'failed': 0
        }
    
    @abstractmethod
    def extract(self) -> Iterator[Dict]:
        """Extract emails and yield as dictionaries"""
        pass
    
    def get_stats(self) -> Dict:
        """Return extraction statistics"""
        return self.stats
```

**`src/extractors/mbox_extractor.py`**
```python
import mailbox
from email import message_from_binary_file
from email.header import decode_header
from typing import Iterator, Dict
import logging

from .base_extractor import BaseExtractor

logger = logging.getLogger(__name__)

class MBOXExtractor(BaseExtractor):
    """Extract emails from MBOX format"""
    
    def extract(self) -> Iterator[Dict]:
        """Extract emails from MBOX file"""
        try:
            mbox = mailbox.mbox(self.file_path)
            
            for idx, message in enumerate(mbox):
                self.stats['total'] += 1
                
                try:
                    email_data = self._parse_message(message, idx)
                    self.stats['success'] += 1
                    yield email_data
                    
                except Exception as e:
                    self.stats['failed'] += 1
                    logger.error(f"Failed to parse message {idx}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Failed to read MBOX file: {e}")
            raise
    
    def _parse_message(self, msg, idx: int) -> Dict:
        """Parse email.message.Message into dict"""
        return {
            'message_id': self._clean_header(msg.get('Message-ID', f'generated-{idx}')),
            'subject': self._decode_header(msg.get('Subject', '')),
            'sender_email': self._extract_email(msg.get('From', '')),
            'sender_name': self._extract_name(msg.get('From', '')),
            'recipients': self._parse_recipients(msg.get('To', '')),
            'cc_list': self._parse_recipients(msg.get('Cc', '')),
            'date': msg.get('Date', ''),
            'body_text': self._get_body_text(msg),
            'body_html': self._get_body_html(msg),
            'in_reply_to': self._clean_header(msg.get('In-Reply-To', '')),
            'references': self._parse_references(msg.get('References', '')),
            'raw_headers': dict(msg.items())
        }
    
    def _decode_header(self, header: str) -> str:
        """Decode email header to UTF-8 string"""
        if not header:
            return ''
        
        decoded_parts = decode_header(header)
        decoded_str = ''
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    decoded_str += part.decode(encoding or 'utf-8', errors='replace')
                except:
                    decoded_str += part.decode('utf-8', errors='replace')
            else:
                decoded_str += str(part)
        
        return decoded_str.strip()
    
    def _extract_email(self, from_field: str) -> str:
        """Extract email address from 'Name <email>' format"""
        import re
        match = re.search(r'<(.+?)>', from_field)
        if match:
            return match.group(1).lower()
        return from_field.lower().strip()
    
    def _extract_name(self, from_field: str) -> str:
        """Extract name from 'Name <email>' format"""
        import re
        match = re.match(r'(.+?)\s*<', from_field)
        if match:
            return self._decode_header(match.group(1).strip())
        return ''
    
    def _parse_recipients(self, recipients_field: str) -> list:
        """Parse comma-separated recipients"""
        if not recipients_field:
            return []
        
        recipients = []
        for recipient in recipients_field.split(','):
            recipient = recipient.strip()
            recipients.append({
                'email': self._extract_email(recipient),
                'name': self._extract_name(recipient)
            })
        
        return recipients
    
    def _get_body_text(self, msg) -> str:
        """Extract plain text body"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        try:
                            return payload.decode('utf-8', errors='replace')
                        except:
                            return payload.decode('latin-1', errors='replace')
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                try:
                    return payload.decode('utf-8', errors='replace')
                except:
                    return payload.decode('latin-1', errors='replace')
        
        return ''
    
    def _get_body_html(self, msg) -> str:
        """Extract HTML body"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    payload = part.get_payload(decode=True)
                    if payload:
                        try:
                            return payload.decode('utf-8', errors='replace')
                        except:
                            return payload.decode('latin-1', errors='replace')
        
        return ''
    
    def _clean_header(self, header: str) -> str:
        """Clean message ID and similar headers"""
        return header.strip('<>').strip()
    
    def _parse_references(self, references: str) -> list:
        """Parse References header into list of message IDs"""
        if not references:
            return []
        
        import re
        return [self._clean_header(ref) for ref in re.findall(r'<[^>]+>', references)]
```

### Phase 3: Data Normalization (Day 2, 4-6 hours)

**`src/processors/normalizer.py`**
```python
from datetime import datetime
from dateutil import parser as date_parser
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class EmailNormalizer:
    """Normalize and clean email data"""
    
    def __init__(self, user_domains: list = None):
        self.user_domains = user_domains or []
    
    def normalize(self, raw_email: Dict) -> Dict:
        """Normalize raw email data"""
        
        normalized = {
            'message_id': raw_email.get('message_id'),
            'thread_id': self._determine_thread_id(raw_email),
            'folder_path': raw_email.get('folder_path', 'INBOX'),
            'sender_email': raw_email.get('sender_email', '').lower(),
            'sender_name': raw_email.get('sender_name', ''),
            'recipients': raw_email.get('recipients', []),
            'cc_list': raw_email.get('cc_list', []),
            'subject': self._clean_subject(raw_email.get('subject', '')),
            'body_text': self._clean_body(raw_email.get('body_text', '')),
            'body_html': raw_email.get('body_html', ''),
            'sent_date': self._parse_date(raw_email.get('date')),
            'is_outbound': self._is_outbound(raw_email),
            'is_reply': self._is_reply(raw_email),
            'message_size': len(raw_email.get('body_text', '')),
            'raw_headers': raw_email.get('raw_headers', {})
        }
        
        return normalized
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse email date to datetime"""
        if not date_str:
            return None
        
        try:
            return date_parser.parse(date_str)
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
            return None
    
    def _determine_thread_id(self, email: Dict) -> str:
        """Determine thread ID from References or In-Reply-To"""
        # Use the root message ID from References
        references = email.get('references', [])
        if references:
            return references[0]
        
        # Fall back to In-Reply-To
        in_reply_to = email.get('in_reply_to')
        if in_reply_to:
            return in_reply_to
        
        # This is the start of a new thread
        return email.get('message_id')
    
    def _is_outbound(self, email: Dict) -> bool:
        """Check if email is outbound based on sender domain"""
        if not self.user_domains:
            return False
        
        sender = email.get('sender_email', '')
        return any(sender.endswith(f'@{domain}') for domain in self.user_domains)
    
    def _is_reply(self, email: Dict) -> bool:
        """Check if email is a reply"""
        subject = email.get('subject', '')
        in_reply_to = email.get('in_reply_to')
        
        # Check subject line for Re:, RE:, etc.
        if subject.lower().startswith(('re:', 're :', 'aw:', 'aw :')):
            return True
        
        # Check for In-Reply-To header
        if in_reply_to:
            return True
        
        return False
    
    def _clean_subject(self, subject: str) -> str:
        """Clean email subject"""
        # Remove multiple spaces
        import re
        cleaned = re.sub(r'\s+', ' ', subject)
        return cleaned.strip()
    
    def _clean_body(self, body: str) -> str:
        """Clean email body text"""
        if not body:
            return ''
        
        # Remove excessive whitespace
        import re
        cleaned = re.sub(r'\n{3,}', '\n\n', body)
        cleaned = re.sub(r' {2,}', ' ', cleaned)
        
        return cleaned.strip()
```

### Phase 4: Database Operations (Day 2-3, 4 hours)

**`src/database/supabase_client.py`**
```python
import os
from supabase import create_client, Client
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class SupabaseClient:
    """Wrapper for Supabase client with connection pooling"""
    
    _instance: Optional[Client] = None
    
    @classmethod
    def get_client(cls) -> Client:
        """Get or create Supabase client (singleton pattern)"""
        if cls._instance is None:
            url = os.getenv('SUPABASE_URL')
            key = os.getenv('SUPABASE_SERVICE_KEY')  # Use service key for backend
            
            if not url or not key:
                raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
            
            cls._instance = create_client(url, key)
            logger.info("Supabase client initialized")
        
        return cls._instance
```

**`src/database/operations.py`**
```python
from typing import List, Dict, Optional
from datetime import datetime
import logging
from .supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class EmailOperations:
    """Database operations for emails"""
    
    def __init__(self):
        self.client = SupabaseClient.get_client()
    
    def batch_insert_emails(self, emails: List[Dict], batch_size: int = 100) -> Dict:
        """Insert emails in batches"""
        total = len(emails)
        success = 0
        failed = 0
        
        for i in range(0, total, batch_size):
            batch = emails[i:i + batch_size]
            
            try:
                result = self.client.table('emails').insert(batch).execute()
                success += len(batch)
                logger.info(f"Inserted batch {i//batch_size + 1}: {len(batch)} emails")
                
            except Exception as e:
                failed += len(batch)
                logger.error(f"Failed to insert batch {i//batch_size + 1}: {e}")
        
        return {
            'total': total,
            'success': success,
            'failed': failed
        }
    
    def get_email_by_message_id(self, message_id: str) -> Optional[Dict]:
        """Retrieve email by message_id"""
        try:
            result = self.client.table('emails')\
                .select('*')\
                .eq('message_id', message_id)\
                .execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get email {message_id}: {e}")
            return None
    
    def search_emails(
        self,
        query: str = None,
        sender: str = None,
        date_from: datetime = None,
        date_to: datetime = None,
        folder: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """Search emails with filters"""
        
        query_builder = self.client.table('emails').select('*')
        
        if sender:
            query_builder = query_builder.ilike('sender_email', f'%{sender}%')
        
        if date_from:
            query_builder = query_builder.gte('sent_date', date_from.isoformat())
        
        if date_to:
            query_builder = query_builder.lte('sent_date', date_to.isoformat())
        
        if folder:
            query_builder = query_builder.eq('folder_path', folder)
        
        query_builder = query_builder.order('sent_date', desc=True).limit(limit)
        
        try:
            result = query_builder.execute()
            return result.data
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def get_folder_stats(self) -> List[Dict]:
        """Get email statistics by folder"""
        try:
            result = self.client.table('folder_stats').select('*').execute()
            return result.data
        except Exception as e:
            logger.error(f"Failed to get folder stats: {e}")
            return []
    
    def update_folder_counts(self):
        """Update message counts in folders table"""
        try:
            # This would typically be a database trigger or stored procedure
            # For now, we can do it manually
            result = self.client.rpc('update_folder_counts').execute()
            logger.info("Folder counts updated")
        except Exception as e:
            logger.error(f"Failed to update folder counts: {e}")
```

### Phase 5: Main Pipeline (Day 3, 4-6 hours)

**`scripts/run_extraction.py`**
```python
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import logging
from tqdm import tqdm

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.extractors.mbox_extractor import MBOXExtractor
from src.processors.normalizer import EmailNormalizer
from src.processors.categorizer import EmailCategorizer
from src.database.operations import EmailOperations

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('extraction.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_pipeline(
    archive_path: str,
    user_domains: list = None,
    batch_size: int = 100
):
    """Run the complete extraction and processing pipeline"""
    
    logger.info(f"Starting pipeline for: {archive_path}")
    
    # Initialize components
    extractor = MBOXExtractor(archive_path)
    normalizer = EmailNormalizer(user_domains=user_domains)
    categorizer = EmailCategorizer()
    db_ops = EmailOperations()
    
    # Process in batches
    batch = []
    total_processed = 0
    
    try:
        # Extract and process
        for raw_email in tqdm(extractor.extract(), desc="Processing emails"):
            # Normalize
            normalized = normalizer.normalize(raw_email)
            
            # Categorize
            categories = categorizer.categorize(normalized)
            
            # Add to batch
            batch.append(normalized)
            
            # Insert batch when full
            if len(batch) >= batch_size:
                result = db_ops.batch_insert_emails(batch)
                total_processed += result['success']
                logger.info(f"Processed {total_processed} emails so far")
                batch = []
        
        # Insert remaining
        if batch:
            result = db_ops.batch_insert_emails(batch)
            total_processed += result['success']
        
        # Print statistics
        stats = extractor.get_stats()
        logger.info(f"Pipeline complete!")
        logger.info(f"Total emails: {stats['total']}")
        logger.info(f"Successfully processed: {stats['success']}")
        logger.info(f"Failed: {stats['failed']}")
        logger.info(f"Inserted to database: {total_processed}")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract and process email archive')
    parser.add_argument('archive_path', help='Path to email archive file')
    parser.add_argument('--domains', nargs='+', help='User domains for outbound detection')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for DB inserts')
    
    args = parser.parse_args()
    
    run_pipeline(
        archive_path=args.archive_path,
        user_domains=args.domains,
        batch_size=args.batch_size
    )
```

### Phase 6: Retool Dashboard Setup (Day 3-4, 4-6 hours)

**Retool Configuration Guide:**

1. **Create New Retool App**
   - Go to https://retool.com
   - Create new app: "Email Intelligence Dashboard"

2. **Add Supabase Resource**
   - Resources → Add Resource → PostgreSQL
   - Host: `db.your-project.supabase.co`
   - Database: `postgres`
   - User: `postgres`
   - Password: [from Supabase project settings]
   - Port: `5432`
   - SSL: Enable

3. **Dashboard Layout**

**Page 1: Overview**
- Statistics cards (total emails, date range, folders)
- Line chart: daily email volume
- Bar chart: top senders
- Pie chart: folder distribution

**Page 2: Email List**
- Table component connected to `emails` table
- Filters: date range, sender, folder, search
- Click row → show email detail in modal
- Export button

**Page 3: Analysis**
- Time series analysis
- Conversation patterns
- Response time metrics

4. **Key Queries**

**Email List Query:**
```sql
SELECT 
  id,
  subject,
  sender_email,
  sent_date,
  folder_path,
  is_outbound,
  is_reply
FROM emails
WHERE 
  ({{search_input.value}} IS NULL OR 
   subject ILIKE '%' || {{search_input.value}} || '%' OR
   sender_email ILIKE '%' || {{search_input.value}} || '%')
  AND ({{date_from.value}} IS NULL OR sent_date >= {{date_from.value}})
  AND ({{date_to.value}} IS NULL OR sent_date <= {{date_to.value}})
ORDER BY sent_date DESC
LIMIT 1000;
```

**Daily Volume Query:**
```sql
SELECT * FROM daily_email_volume
WHERE date >= {{date_from.value}}
  AND date <= {{date_to.value}}
ORDER BY date;
```

---

## Stage 2: AI Enrichment Implementation

### Phase 7: FastAPI Setup (Week 3, Day 1-2)

**`api/main.py`**
```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging

from .routers import emails, enrichment, search

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Email Intelligence API",
    description="API for email processing and AI enrichment",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(emails.router, prefix="/api/emails", tags=["emails"])
app.include_router(enrichment.router, prefix="/api/enrichment", tags=["enrichment"])
app.include_router(search.router, prefix="/api/search", tags=["search"])

@app.get("/")
async def root():
    return {"message": "Email Intelligence API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

**`api/services/ai_service.py`**
```python
import os
from anthropic import Anthropic
from typing import Dict, List
import json
import logging

logger = logging.getLogger(__name__)

class AIEnrichmentService:
    """Service for AI-powered email enrichment using Claude"""
    
    def __init__(self):
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
    
    def enrich_email(self, email: Dict) -> Dict:
        """Enrich a single email with AI analysis"""
        
        prompt = self._build_enrichment_prompt(email)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            # Parse JSON response
            content = response.content[0].text
            enrichment_data = json.loads(content)
            
            return enrichment_data
            
        except Exception as e:
            logger.error(f"Enrichment failed for email {email.get('id')}: {e}")
            raise
    
    def batch_enrich_emails(self, emails: List[Dict]) -> List[Dict]:
        """Enrich multiple emails in a single API call"""
        
        prompt = self._build_batch_prompt(emails)
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            content = response.content[0].text
            enrichments = json.loads(content)
            
            return enrichments
            
        except Exception as e:
            logger.error(f"Batch enrichment failed: {e}")
            raise
    
    def _build_enrichment_prompt(self, email: Dict) -> str:
        """Build prompt for single email enrichment"""
        
        return f"""Analyze this email and return ONLY a JSON object with the following structure:

{{
  "email_type": "quote_request|support|complaint|inquiry|notification|other",
  "tone": "professional|casual|urgent|friendly|angry|neutral",
  "sentiment": "positive|negative|neutral",
  "happiness_index": <0.0 to 1.0>,
  "escalation_needed": <true|false>,
  "short_summary": "<one sentence summary>",
  "extracted_entities": {{
    "products": [],
    "dates": [],
    "amounts": [],
    "people": []
  }}
}}

Email:
From: {email.get('sender_email')}
Subject: {email.get('subject')}
Body: {email.get('body_text', '')[:1000]}

Return ONLY the JSON, no other text."""
    
    def _build_batch_prompt(self, emails: List[Dict]) -> str:
        """Build prompt for batch email enrichment"""
        
        emails_text = ""
        for idx, email in enumerate(emails):
            emails_text += f"\n---EMAIL {idx}---\n"
            emails_text += f"ID: {email.get('id')}\n"
            emails_text += f"From: {email.get('sender_email')}\n"
            emails_text += f"Subject: {email.get('subject')}\n"
            emails_text += f"Body: {email.get('body_text', '')[:500]}\n"
        
        return f"""Analyze these {len(emails)} emails and return ONLY a JSON array with enrichment data for each:

[
  {{
    "email_id": "<id from input>",
    "email_type": "quote_request|support|complaint|inquiry|notification|other",
    "tone": "professional|casual|urgent|friendly|angry|neutral",
    "sentiment": "positive|negative|neutral",
    "happiness_index": <0.0 to 1.0>,
    "escalation_needed": <true|false>,
    "short_summary": "<one sentence>",
    "extracted_entities": {{
      "products": [],
      "dates": [],
      "amounts": []
    }}
  }}
]

{emails_text}

Return ONLY the JSON array, no other text."""
```

**`api/routers/enrichment.py`**
```python
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import logging

from ..services.ai_service import AIEnrichmentService
from ...src.database.operations import EmailOperations

logger = logging.getLogger(__name__)
router = APIRouter()

ai_service = AIEnrichmentService()
email_ops = EmailOperations()

class EnrichmentRequest(BaseModel):
    email_ids: List[str]
    batch_size: int = 20

class EnrichmentResponse(BaseModel):
    job_id: str
    status: str
    total_emails: int

@router.post("/enrich", response_model=EnrichmentResponse)
async def enrich_emails(
    request: EnrichmentRequest,
    background_tasks: BackgroundTasks
):
    """Start email enrichment process"""
    
    try:
        # Create job
        job_id = "job-" + str(uuid.uuid4())
        
        # Start background task
        background_tasks.add_task(
            process_enrichment,
            job_id,
            request.email_ids,
            request.batch_size
        )
        
        return EnrichmentResponse(
            job_id=job_id,
            status="started",
            total_emails=len(request.email_ids)
        )
        
    except Exception as e:
        logger.error(f"Failed to start enrichment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_enrichment(
    job_id: str,
    email_ids: List[str],
    batch_size: int
):
    """Background task to process email enrichment"""
    
    logger.info(f"Starting enrichment job {job_id} for {len(email_ids)} emails")
    
    # Process in batches
    for i in range(0, len(email_ids), batch_size):
        batch_ids = email_ids[i:i + batch_size]
        
        try:
            # Get emails
            emails = [email_ops.get_email_by_id(eid) for eid in batch_ids]
            
            # Enrich
            enrichments = ai_service.batch_enrich_emails(emails)
            
            # Save to database
            for enrichment in enrichments:
                email_ops.save_enrichment(enrichment)
            
            logger.info(f"Processed batch {i//batch_size + 1}")
            
        except Exception as e:
            logger.error(f"Batch {i//batch_size + 1} failed: {e}")
    
    logger.info(f"Job {job_id} completed")
```

### Phase 8: Streamlit Frontend (Week 3-4, Day 3-5)

**`streamlit_app/Home.py`**
```python
import streamlit as st
import pandas as pd
from utils.api_client import APIClient

st.set_page_config(
    page_title="Email Intelligence",
    page_icon="📧",
    layout="wide"
)

# Initialize API client
if 'api_client' not in st.session_state:
    st.session_state.api_client = APIClient()

st.title("📧 Email Intelligence Platform")
st.markdown("---")

# Quick stats
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Emails", "125,432")
    
with col2:
    st.metric("Enriched", "2,150")
    
with col3:
    st.metric("Pending", "850")
    
with col4:
    st.metric("Folders", "28")

st.markdown("---")

# Recent activity
st.subheader("Recent Activity")

# Placeholder for activity feed
activities = [
    {"time": "10 minutes ago", "action": "Enriched 50 emails"},
    {"time": "1 hour ago", "action": "Processed new archive (5,234 emails)"},
    {"time": "3 hours ago", "action": "Export completed"}
]

for activity in activities:
    st.text(f"{activity['time']}: {activity['action']}")
```

**`streamlit_app/pages/3_🤖_AI_Enrichment.py`**
```python
import streamlit as st
import pandas as pd
from datetime import datetime
from utils.api_client import APIClient

st.set_page_config(page_title="AI Enrichment", layout="wide")

st.title("🤖 AI Email Enrichment")

api_client = st.session_state.get('api_client')

# Email selection
st.subheader("Select Emails to Enrich")

col1, col2 = st.columns(2)

with col1:
    date_from = st.date_input("From Date")
    
with col2:
    date_to = st.date_input("To Date")

folder = st.selectbox("Folder", ["All", "INBOX", "Sent", "Archive"])
max_emails = st.number_input("Max Emails", min_value=100, max_value=10000, value=1000)

if st.button("Search Emails"):
    with st.spinner("Searching..."):
        emails = api_client.search_emails(
            date_from=date_from,
            date_to=date_to,
            folder=folder if folder != "All" else None,
            limit=max_emails
        )
        
        st.session_state.selected_emails = emails
        st.success(f"Found {len(emails)} emails")

# Display selected emails
if 'selected_emails' in st.session_state:
    st.subheader(f"Selected Emails ({len(st.session_state.selected_emails)})")
    
    df = pd.DataFrame(st.session_state.selected_emails)
    st.dataframe(df[['subject', 'sender_email', 'sent_date']])
    
    # Enrichment controls
    st.markdown("---")
    st.subheader("Enrichment Settings")
    
    batch_size = st.slider("Batch Size", min_value=10, max_value=50, value=20)
    
    if st.button("Start Enrichment", type="primary"):
        with st.spinner("Starting enrichment job..."):
            email_ids = [e['id'] for e in st.session_state.selected_emails]
            
            result = api_client.start_enrichment(
                email_ids=email_ids,
                batch_size=batch_size
            )
            
            st.success(f"Enrichment job started! Job ID: {result['job_id']}")
            st.session_state.current_job_id = result['job_id']

# Job status
if 'current_job_id' in st.session_state:
    st.markdown("---")
    st.subheader("Job Status")
    
    if st.button("Refresh Status"):
        status = api_client.get_job_status(st.session_state.current_job_id)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Status", status['status'])
        with col2:
            st.metric("Processed", f"{status['processed']}/{status['total']}")
        with col3:
            progress = status['processed'] / status['total'] if status['total'] > 0 else 0
            st.metric("Progress", f"{progress:.1%}")
        
        st.progress(progress)
```

---

## Configuration Files

### `requirements.txt`
```
# Core dependencies
python-dotenv==1.0.0
pydantic==2.5.0

# Email processing
email-parser==0.3.0
python-dateutil==2.8.2

# Database
supabase==2.0.0
psycopg2-binary==2.9.9

# Stage 2: API & AI
fastapi==0.104.1
uvicorn[standard]==0.24.0
anthropic==0.25.0
httpx==0.25.1

# Stage 2: Frontend
streamlit==1.29.0
plotly==5.18.0
pandas==2.1.3

# Utilities
tqdm==4.66.1
pyyaml==6.0.1

# Development
pytest==7.4.3
black==23.11.0
```

### `config/config.yaml`
```yaml
# Email processing configuration

# User domains for outbound detection
user_domains:
  - example.com
  - company.com

# Processing settings
processing:
  batch_size: 100
  max_workers: 4
  
# Categorization rules
categories:
  spam:
    keywords:
      - "viagra"
      - "lottery"
      - "nigerian prince"
    confidence: 0.9
  
  marketing:
    keywords:
      - "unsubscribe"
      - "promotional"
      - "discount"
    confidence: 0.8
  
  system:
    senders:
      - "noreply@"
      - "no-reply@"
      - "mailer-daemon@"
    confidence: 1.0

# AI enrichment settings (Stage 2)
ai_enrichment:
  model: "claude-sonnet-4-20250514"
  batch_size: 20
  max_tokens: 4000
  timeout: 30

# Database settings
database:
  batch_insert_size: 100
  connection_pool_size: 10
```

### `.env.example`
```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key

# Anthropic (Stage 2)
ANTHROPIC_API_KEY=your-api-key

# API Settings (Stage 2)
API_HOST=0.0.0.0
API_PORT=8000

# Streamlit (Stage 2)
STREAMLIT_SERVER_PORT=8501
```

### `docker-compose.yml` (for local development)
```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./src:/app/src
      - ./api:/app/api
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
  
  streamlit:
    build: .
    ports:
      - "8501:8501"
    environment:
      - API_URL=http://api:8000
    volumes:
      - ./streamlit_app:/app/streamlit_app
    command: streamlit run streamlit_app/Home.py
    depends_on:
      - api
```

---

## Development Workflow with Claude Code

### Day-by-Day Plan

**Day 1: Foundation**
```bash
# In VSCode terminal with Claude Code

# 1. Create project structure
claude-code "Create the project structure from the technical design document. Set up all directories and create empty __init__.py files."

# 2. Set up database
claude-code "Create the Supabase tables using the SQL schema from the design doc. Include all indexes and views."

# 3. Create base extractor
claude-code "Implement the base_extractor.py with the abstract base class as specified in the design."

# 4. Create MBOX extractor
claude-code "Implement mbox_extractor.py with full email parsing, header decoding, and body extraction."
```

**Day 2: Processing Pipeline**
```bash
# 5. Email normalizer
claude-code "Implement normalizer.py with date parsing, thread detection, and body cleaning."

# 6. Database client
claude-code "Create supabase_client.py with singleton pattern and operations.py with batch insert functions."

# 7. Main pipeline
claude-code "Implement run_extraction.py that ties together extractor, normalizer, and database operations with progress tracking."

# 8. Test with sample data
python scripts/run_extraction.py sample.mbox --domains example.com
```

**Day 3: Retool Setup**
```bash
# 9. Verify data in Supabase
# Check Supabase dashboard, run test queries

# 10. Build Retool dashboard
# Follow Retool guide, connect to Supabase, create views

# 11. Demo preparation
# Load real data, test all features
```

**Week 2: Stage 2 Preparation**
```bash
# 12. FastAPI setup
claude-code "Create FastAPI application structure with routers for emails, enrichment, and search endpoints."

# 13. AI service
claude-code "Implement ai_service.py with Anthropic Claude integration for email enrichment."

# 14. Streamlit app
claude-code "Create Streamlit multi-page app with dashboard, search, and AI enrichment pages."
```

### Claude Code Best Practices

**1. Be Specific with Context**
```bash
# Good
claude-code "Create the MBOXExtractor class that inherits from BaseExtractor. It should handle email header decoding with proper UTF-8 support and extract both plain text and HTML bodies. Include error handling for malformed emails."

# Bad
claude-code "Make the email extractor"
```

**2. Iterative Development**
```bash
# Start simple
claude-code "Create a basic MBOX extractor that just reads messages and extracts subject and sender."

# Then enhance
claude-code "Add body extraction with HTML/plaintext detection to the MBOX extractor."

# Finally polish
claude-code "Add robust error handling and UTF-8 encoding support to the MBOX extractor."
```

**3. Reference Design Doc**
```bash
claude-code "Implement the database schema from EMAIL_INTELLIGENCE_POC_DESIGN.md, including all tables, indexes, and views."
```

---

## Deployment Guide

### Railway.app Deployment (Recommended)

**1. Install Railway CLI**
```bash
npm install -g @railway/cli
railway login
```

**2. Initialize Project**
```bash
railway init
railway link
```

**3. Add PostgreSQL**
```bash
railway add postgresql
```

**4. Set Environment Variables**
```bash
railway variables set ANTHROPIC_API_KEY=your-key
```

**5. Deploy**
```bash
# For FastAPI
railway up

# For Streamlit (separate service)
railway add
# Select "Empty Service"
# Deploy Streamlit app
```

### Alternative: Render.com

**1. Create `render.yaml`**
```yaml
services:
  - type: web
    name: email-intelligence-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn api.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: SUPABASE_URL
        sync: false
      - key: SUPABASE_SERVICE_KEY
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
  
  - type: web
    name: email-intelligence-ui
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: streamlit run streamlit_app/Home.py --server.port $PORT
```

**2. Connect GitHub & Deploy**
- Push code to GitHub
- Connect repository in Render dashboard
- Auto-deploys on push

---

## Success Metrics & Demo Script

### What to Show Client (Week 2-3)

**1. Retool Dashboard Demo (10 minutes)**
- Show email volume over time
- Demonstrate filtering by date/sender/folder
- Display top senders analysis
- Export sample data to CSV

**2. Database Tour (5 minutes)**
- Show structured data in Supabase
- Run sample SQL queries
- Demonstrate data quality

**3. Processing Pipeline (5 minutes)**
- Run extraction on new archive
- Show real-time progress
- Discuss error handling

### Stage 2 Demo (Week 5-6)

**1. Streamlit Interface (10 minutes)**
- Interactive dashboard
- Search and filtering
- AI enrichment controls

**2. AI Enrichment (10 minutes)**
- Select emails for enrichment
- Show batch processing
- Display enriched results
- Explain JSON schema

---

## Risk Management

### Technical Risks

**1. Email Format Variations**
- **Risk:** Real archives have malformed emails
- **Mitigation:** Extensive try/except, failed_emails table
- **Status:** Monitor extraction logs

**2. API Rate Limits**
- **Risk:** Claude API throttling
- **Mitigation:** Batch processing, exponential backoff
- **Status:** Monitor API usage

**3. Database Performance**
- **Risk:** Slow queries on large datasets
- **Mitigation:** Proper indexing, query optimization
- **Status:** Profile queries regularly

### Project Risks

**1. Scope Creep**
- **Risk:** Client requests new features
- **Mitigation:** Clear Stage 1/2 boundaries
- **Response:** "Great idea! Let's add to Stage 3 plan"

**2. Timeline Pressure**
- **Risk:** Underestimated complexity
- **Mitigation:** Conservative estimates, weekly demos
- **Response:** Show progress, adjust scope if needed

---

## Next Steps After POC

### Potential Stage 3 Features

1. **Advanced AI Classification**
   - Multi-category taxonomy (10-15 categories)
   - Quote detection and extraction
   - Missing information identification

2. **Reply Generation**
   - AI-powered draft responses
   - Template management
   - Approval workflow

3. **Real-time Processing**
   - Email webhook integration
   - Live classification
   - Automated routing

4. **Advanced Analytics**
   - Response time analysis
   - Conversation sentiment trends
   - Team performance metrics

---

## Cost Breakdown

### Stage 1 (POC)
- **Development:** Your time (3-4 weeks)
- **Supabase:** Free tier (up to 500MB, 50,000 rows)
- **Retool:** Free tier (5 users)
- **Railway:** Free tier or $5/month
- **Total:** ~$0-5/month during POC

### Stage 2 (AI Integration)
- **Anthropic API:** ~$1-3 per 1,000 emails enriched
- **Railway:** $10-15/month (API + Streamlit)
- **POC Volume (2,000 emails):** ~$2-6 one-time
- **Total:** ~$20-30 for POC completion

---

## Key Success Factors

1. ✅ **Start Simple:** MBOX only, basic categorization
2. ✅ **Show Progress Early:** Week 1 demo with 100 emails
3. ✅ **Document Everything:** README, inline comments
4. ✅ **Client Communication:** Weekly updates with screenshots
5. ✅ **Modular Design:** Easy to extend and modify
6. ✅ **Error Handling:** Graceful failures, detailed logs
7. ✅ **Realistic Timeline:** Under-promise, over-deliver

---

## Final Checklist

### Before Client Demo
- [ ] Test with real email archive (>10k emails)
- [ ] Verify all database indexes working
- [ ] Retool dashboard fully functional
- [ ] Export feature tested
- [ ] Documentation complete
- [ ] Error logs reviewed
- [ ] Demo script practiced

### Before Stage 2
- [ ] Stage 1 client-approved
- [ ] Anthropic API access confirmed
- [ ] Cost estimate approved
- [ ] Timeline agreed
- [ ] Success metrics defined

---

## Conclusion

This design gives you:
- **Clear path**: Step-by-step implementation
- **Proven stack**: Technologies that work well together
- **AI-friendly**: Perfect for Claude Code development
- **Demo-ready**: Client can see results quickly
- **Extensible**: Easy to add Stage 2 features
- **Professional**: Shows architectural thinking

**Remember:**
- You don't need to build everything at once
- Show working features early and often
- Document as you code
- Test with real data regularly
- Keep client informed

You've got this! The combination of this design + Claude Code + your data science background = success. 🚀
