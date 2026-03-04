# Email Intelligence Platform — 3-Week AI MVP Plan (FINAL)
## Vibe Coding with Claude Code

**Date:** February 27, 2026 | **Finalized:** March 3, 2026
**Starting Point:** Sprint 2 fully complete (pipeline + analytics frontend + admin data view)
**Goal:** Transform from "data dashboard" → "intelligence platform" with action-oriented insights

**Evolution:** Classification-only → merged entity extraction (+27% intelligence, same cost) → action buckets + confidence thresholds + human feedback + privacy stripping → session estimates + weekly schedule + deployment checklist → **multi-axis classification (action_type + business_signal + thread_role)**

---

## 3-Week Schedule Overview (5-6h/day Vibe Coding)

### Week 1: Intelligence Engine + Buckets + Digest (28h)
**Exit Criteria:** Can trigger analysis → see buckets → get digest → browse smart inbox

| Day | Session | Deliverable | Hours |
|-----|---------|-------------|-------|
| Day 1 | Session 1 | DB migration + AI client + privacy filter + usage tracker | 5h |
| Day 2 | Session 2 | Email analyzer (classify + extract + justify) | 6h |
| Day 3 | Session 3 | Action bucket engine (zero AI cost) | 5h |
| Day 4 | Session 4 | Entity aggregator + all API endpoints | 6h |
| Day 5 | Session 5 | Digest service (bucket-aware) | 5h |

### Week 2: Dashboard Integration + Opportunities (28h)
**Exit Criteria:** Company pages show AI intelligence, opportunities page works, gap alerts live

| Day | Session | Deliverable | Hours |
|-----|---------|-------------|-------|
| Day 6 | Session 6 | Digest + Smart Inbox frontend (with bucket tags + feedback) | 6h |
| Day 7 | Session 7 | Relationship summary service | 5h |
| Day 8 | Session 8 | Company detail page AI cards | 6h |
| Day 9 | Session 9 | Opportunities page (5 tabs) | 5h |
| Day 10 | Session 10 | AM Comparison + Gap Alerts (bucket-enriched) | 6h |

### Week 3: Polish + Deploy (14h)
**Exit Criteria:** All pages wired, deployed to Railway, integration tests pass

| Day | Session | Deliverable | Hours |
|-----|---------|-------------|-------|
| Day 11 | Session 11 | Navigation + usage page + cross-linking | 5h |
| Day 12 | Session 12 | Integration testing | 4h |
| Day 13 | Session 13 | Production deploy + docs | 3h |
| Day 14 | Buffer | Bug fixes + polish | 2h |

**Total: ~70 hours across 14 sessions ≈ 5h/day × 14 working days**

---

## Strategic Architecture: Three-Layer Intelligence Model

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: Per-Email AI Intelligence (Claude Haiku — ONE call)   │
│  ai_email_analyzer.py                                           │
│  INPUT: sanitized email body (500 chars max)                    │
│  OUTPUT: intent, urgency, sentiment, entities, competitors,     │
│          budgets, buying signals, justification, confidence      │
│          + action_type, business_signal, thread_role (v3.2)      │
│  Cost: ~$0.001/email                                            │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 2: Relationship Pattern Detection (NO AI — Python rules) │
│  ai_action_bucket_engine.py + Sprint 2 existing data            │
│  INPUTS: Layer 1 results + engagement scores + thread_status    │
│          + email_response_metrics + contact seniority           │
│  DETECTS: Silent Champion, Stakeholder Entry, Unresolved Block, │
│           Missed Opportunity, Competitor Threat                  │
│  Cost: $0                                                       │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 3: Action-First Presentation (Frontend)                  │
│                                                                  │
│  confidence ≥ 0.8  → Full colored tag: "💰 Buying Signal"      │
│  confidence 0.5-0.8 → Muted: "💰 Buying Signal · Review"       │
│  confidence < 0.5  → Hidden from user                           │
│                                                                  │
│  Every tag has 👍/👎 → human_feedback column                    │
│  Every tag has justification tooltip → "Why: mentions 'budget   │
│    for Q3 deployment' and 'procurement team involved'"          │
│                                                                  │
│  Business Owner sees: Opportunities, Gap Alerts, AM Comparison  │
│  Account Manager sees: Daily Digest, Smart Inbox, Action Buckets│
└─────────────────────────────────────────────────────────────────┘
```

### The 8 Action Buckets

| Bucket | Source Layer | Trigger Logic | Action | Priority |
|--------|-------------|--------------|--------|----------|
| 💰 **Buying Signal** | Layer 1 (AI) | has_buying_signal OR has_budget_signal | Trigger proposal / sales follow-up | 🟥 Critical |
| 📈 **Expansion Signal** | Layer 1 (AI) | intent == 'expansion_signal' | Schedule upsell / strategy call | 🟥 Critical |
| 🚨 **Churn Risk** | Layer 1 (AI) | intent == 'churn_risk' OR (negative sentiment + competitor mention) | Immediate retention outreach | 🟥 Critical |
| ⚔️ **Competitor Threat** | Layer 1 (AI) | has_competitor_mention | Review competitive positioning | 🟧 High |
| ⚡ **Missed Opportunity** | Layer 2 (Rules) | Business signal detected AND no outbound response | Respond immediately | 🟥 Critical |
| 👔 **Stakeholder Entry** | Layer 2 (Rules) | New high-seniority CC in recent thread | Multi-thread the account | 🟧 High |
| 🔇 **Silent Champion** | Layer 2 (Rules) | engagement_score ≥ 50 AND no outbound 14+ days | Send personalized check-in | 🟨 Medium |
| ⏳ **Unresolved Block** | Layer 2 (Rules) | Thread awaiting_reply > 48h AND intent == 'question' | Bump thread to resolve blocker | 🟨 Medium |

---

## Database Schema (Migration 013)

```sql
-- =========================================================================
-- Sprint 3 Migration 013: AI Intelligence Layer
-- =========================================================================

-- Combined classification + entity extraction + action buckets (ONE AI pass)
CREATE TABLE IF NOT EXISTS ai_email_intelligence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email_id UUID REFERENCES emails(id) ON DELETE CASCADE,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,

    -- === CLASSIFICATION ===
    intent TEXT CHECK (intent IN (
        'action_required', 'fyi_update', 'meeting_scheduling',
        'question', 'complaint', 'positive_feedback',
        'pricing_inquiry', 'feature_request', 'expansion_signal',
        'churn_risk', 'follow_up', 'introduction', 'other'
    )),
    urgency TEXT CHECK (urgency IN ('critical', 'high', 'medium', 'low', 'none')),
    sentiment TEXT CHECK (sentiment IN (
        'very_positive', 'positive', 'neutral', 'negative', 'very_negative'
    )),
    sentiment_score DECIMAL(3,2),       -- -1.0 to 1.0
    summary TEXT,                        -- 1-2 sentence summary
    suggested_action TEXT,               -- What the AM should do
    key_topics TEXT[],                   -- Themes
    confidence DECIMAL(3,2),             -- 0.0-1.0
    justification TEXT,                  -- WHY this classification (from AI)

    -- === MULTI-AXIS CLASSIFICATION (v3.2: richer signal inputs for bucket engine) ===
    action_type TEXT,                    -- What needs to happen: respond_to_inquiry, provide_quote,
                                         -- schedule_meeting, escalate_internally, send_follow_up,
                                         -- resolve_issue, acknowledge_receipt, no_action, delegate,
                                         -- prepare_document
    business_signal TEXT,                -- CRM signal: buying_intent, renewal_intent,
                                         -- expansion_interest, churn_signal, competitive_evaluation,
                                         -- budget_discussion, escalation, positive_feedback,
                                         -- negative_feedback, contract_activity, neutral
    thread_role TEXT,                    -- Conversation position: initial, reply, forward,
                                         -- auto_reply, cc_addition, internal

    -- === ENTITY EXTRACTION (same API call) ===
    competitors_mentioned TEXT[],
    products_mentioned TEXT[],
    budget_signals JSONB,               -- {amount, timeframe, context}
    buying_signals TEXT[],
    people_mentioned JSONB,             -- [{name, role, context}]
    dates_mentioned JSONB,              -- [{date, context}]
    action_items_extracted TEXT[],

    -- === BUSINESS SIGNAL FLAGS ===
    has_budget_signal BOOLEAN DEFAULT FALSE,
    has_buying_signal BOOLEAN DEFAULT FALSE,
    has_competitor_mention BOOLEAN DEFAULT FALSE,
    has_deadline BOOLEAN DEFAULT FALSE,
    business_signal_score INTEGER DEFAULT 0,  -- 0-100

    -- === ACTION BUCKETS (derived by Python engine, stored for fast queries) ===
    action_buckets JSONB DEFAULT '[]',  -- [{bucket, confidence, justification}]
    primary_bucket TEXT,                 -- Highest-confidence bucket for filtering/sorting

    -- === HUMAN FEEDBACK (trust-building) ===
    human_feedback TEXT CHECK (human_feedback IN ('correct', 'incorrect')),
    human_override_intent TEXT,
    human_override_bucket TEXT,
    feedback_at TIMESTAMPTZ,
    feedback_by UUID,

    -- === PROCESSING METADATA ===
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    processing_time_ms INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(email_id)
);

-- Classification indexes
CREATE INDEX idx_ai_intel_mailbox ON ai_email_intelligence(mailbox_id);
CREATE INDEX idx_ai_intel_intent ON ai_email_intelligence(intent);
CREATE INDEX idx_ai_intel_urgency ON ai_email_intelligence(urgency)
    WHERE urgency IN ('critical', 'high');
CREATE INDEX idx_ai_intel_sentiment ON ai_email_intelligence(sentiment);
CREATE INDEX idx_ai_intel_created ON ai_email_intelligence(created_at DESC);

-- Entity/signal indexes
CREATE INDEX idx_ai_intel_budget ON ai_email_intelligence(has_budget_signal)
    WHERE has_budget_signal = TRUE;
CREATE INDEX idx_ai_intel_buying ON ai_email_intelligence(has_buying_signal)
    WHERE has_buying_signal = TRUE;
CREATE INDEX idx_ai_intel_competitor ON ai_email_intelligence(has_competitor_mention)
    WHERE has_competitor_mention = TRUE;
CREATE INDEX idx_ai_intel_deadline ON ai_email_intelligence(has_deadline)
    WHERE has_deadline = TRUE;
CREATE INDEX idx_ai_intel_signal_score ON ai_email_intelligence(business_signal_score DESC)
    WHERE business_signal_score > 0;

-- Action bucket indexes
CREATE INDEX idx_ai_intel_primary_bucket ON ai_email_intelligence(primary_bucket)
    WHERE primary_bucket IS NOT NULL;
CREATE INDEX idx_ai_intel_feedback ON ai_email_intelligence(human_feedback)
    WHERE human_feedback IS NOT NULL;

-- v3.2: Multi-axis classification indexes
CREATE INDEX idx_ai_intel_business_signal ON ai_email_intelligence(business_signal)
    WHERE business_signal IS NOT NULL AND business_signal != 'neutral';
CREATE INDEX idx_ai_intel_action_type ON ai_email_intelligence(action_type)
    WHERE action_type IS NOT NULL AND action_type != 'no_action';
CREATE INDEX idx_ai_intel_thread_role ON ai_email_intelligence(thread_role)
    WHERE thread_role = 'auto_reply';  -- For filtering out auto-replies

GRANT SELECT, INSERT, UPDATE, DELETE ON ai_email_intelligence TO anon, authenticated;


-- Business entities aggregate
CREATE TABLE IF NOT EXISTS ai_business_entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL CHECK (entity_type IN (
        'competitor', 'product', 'person', 'company', 'technology'
    )),
    entity_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    mention_count INTEGER DEFAULT 1,
    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    associated_company_ids UUID[],
    context_snippets JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(client_id, entity_type, normalized_name)
);

CREATE INDEX idx_ai_entities_client ON ai_business_entities(client_id);
CREATE INDEX idx_ai_entities_type ON ai_business_entities(entity_type);
CREATE INDEX idx_ai_entities_mentions ON ai_business_entities(mention_count DESC);
CREATE TRIGGER update_ai_entities_updated_at BEFORE UPDATE
    ON ai_business_entities FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
GRANT SELECT, INSERT, UPDATE, DELETE ON ai_business_entities TO anon, authenticated;


-- Relationship summaries
CREATE TABLE IF NOT EXISTS ai_relationship_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID REFERENCES customer_companies(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    key_themes TEXT[],
    risk_factors TEXT[],
    opportunities TEXT[],
    recommended_actions TEXT[],
    competitors_in_play TEXT[],
    active_buying_signals TEXT[],
    upcoming_deadlines JSONB,
    active_buckets JSONB DEFAULT '[]',  -- [{bucket, count, example}]
    emails_analyzed INTEGER,
    date_range_start TIMESTAMPTZ,
    date_range_end TIMESTAMPTZ,
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_rel_company ON ai_relationship_summaries(company_id);
CREATE INDEX idx_ai_rel_client ON ai_relationship_summaries(client_id);
CREATE TRIGGER update_ai_rel_summaries_updated_at BEFORE UPDATE
    ON ai_relationship_summaries FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
GRANT SELECT, INSERT, UPDATE, DELETE ON ai_relationship_summaries TO anon, authenticated;


-- AI usage tracking
CREATE TABLE IF NOT EXISTS ai_usage_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operation TEXT NOT NULL,
    model TEXT NOT NULL,
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE SET NULL,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost_usd DECIMAL(10,6),
    processing_time_ms INTEGER,
    batch_size INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_usage_date ON ai_usage_log(created_at DESC);
CREATE INDEX idx_ai_usage_operation ON ai_usage_log(operation);
CREATE INDEX idx_ai_usage_client ON ai_usage_log(client_id);
GRANT SELECT, INSERT ON ai_usage_log TO anon, authenticated;


-- Daily digests
CREATE TABLE IF NOT EXISTS ai_daily_digests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mailbox_id UUID REFERENCES mailboxes(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
    digest_date DATE NOT NULL,
    summary TEXT NOT NULL,
    action_items JSONB DEFAULT '[]',
    key_threads JSONB DEFAULT '[]',
    highlights JSONB DEFAULT '[]',
    stats JSONB DEFAULT '{}',
    business_signals JSONB DEFAULT '[]',
    competitor_activity JSONB DEFAULT '[]',
    bucket_summary JSONB DEFAULT '{}',  -- {buying_signal: 2, churn_risk: 1, ...}
    emails_analyzed INTEGER,
    model_used TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(mailbox_id, digest_date)
);

CREATE INDEX idx_digest_mailbox_date ON ai_daily_digests(mailbox_id, digest_date DESC);
GRANT SELECT, INSERT, UPDATE, DELETE ON ai_daily_digests TO anon, authenticated;
```

### Backend Services

```
backend/src/services/
├── (existing 8 Sprint 2 services)
├── ai_client.py                    -- Shared Claude API client (Haiku + Sonnet)
├── ai_usage_tracker.py             -- Cost tracking per operation
├── ai_privacy_filter.py            -- Strip sensitive data before AI
├── ai_email_analyzer.py            -- UNIFIED: classify + extract + justify (ONE API call)
├── ai_action_bucket_engine.py      -- Derive action buckets (NO AI, pure Python)
├── ai_entity_aggregator.py         -- Roll up entities across emails
├── ai_digest_generator.py          -- Daily digest with bucket language
└── ai_relationship_summarizer.py   -- Company summaries with bucket context
```

### API Endpoints

```
# Email Intelligence
POST /api/v1/ai/analyze/{mailbox_id}              -- Run full intelligence pass
GET  /api/v1/ai/intelligence/{mailbox_id}          -- Get results (paginated, filterable)
GET  /api/v1/ai/intelligence/stats/{mailbox_id}    -- Stats breakdown

# Action Buckets
GET  /api/v1/ai/action-items/{client_id}           -- All active buckets, prioritized
GET  /api/v1/ai/action-items/{client_id}/summary   -- Bucket counts for dashboard

# Human Feedback
POST /api/v1/ai/intelligence/{email_id}/feedback   -- Submit 👍/👎 + optional override

# Business Entities
GET  /api/v1/ai/entities/{client_id}
GET  /api/v1/ai/entities/{client_id}/competitors
GET  /api/v1/ai/entities/{client_id}/opportunities

# Daily Digest
GET  /api/v1/ai/digest/{mailbox_id}
GET  /api/v1/ai/digest/{mailbox_id}/history

# Relationship Summaries
POST /api/v1/ai/relationship-summary/{company_id}
GET  /api/v1/ai/relationship-summary/{company_id}
POST /api/v1/ai/relationship-summaries/bulk/{client_id}

# Usage (Admin)
GET  /api/v1/ai/usage/costs
```

### Frontend Pages

```
/ai/digest              -- Daily digest with bucket counts header
/ai/inbox               -- Smart inbox with bucket tags + 👍/👎
/ai/opportunities       -- Business signals + competitor intelligence
/ai/usage               -- AI cost dashboard (Admin only)
+ Relationship summary + bucket badges on company detail page
+ AM comparison on analytics dashboard
+ Gap alerts (bucket-enriched) on analytics dashboard
+ Quick Insights card on main dashboard
```

---

## Week 1: Intelligence Engine + Action Buckets + Digest

### Session 1 (5h) — Infrastructure

**Day 1: Database + AI Client + Privacy Filter + Usage Tracker**

```
Read CLAUDE.md and docs/CONTINUATION_GUIDE.md for full project context.

I need to build the AI intelligence layer (Sprint 3). Start with infrastructure.

TASK 1: Create `scripts/sprint2/sprint2_migration_013_ai_layer.sql`
[Paste the full SQL from the Database Schema section above]

TASK 2: Create `backend/src/services/ai_client.py` — shared Claude API client.
Requirements:
- Use httpx AsyncClient to call https://api.anthropic.com/v1/messages
- Read ANTHROPIC_API_KEY from environment
- Support both Haiku (for email intelligence) and Sonnet (for summaries)
- Include retry logic (3 retries, exponential backoff) matching our existing
  _execute_with_retry() pattern in other services
- Return structured response: {content, input_tokens, output_tokens, model}
- Support batch mode: accept list of messages, process sequentially
  with rate limiting (10 req/sec max)
- Add cost calculation helper:
  Haiku: input=$0.80/MTok, output=$4/MTok
  Sonnet: input=$3/MTok, output=$15/MTok

TASK 3: Create `backend/src/services/ai_privacy_filter.py`
- sanitize_email_body(body: str) → str
- Strip: credit card patterns (\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})
- Strip: SSN patterns (\d{3}-\d{2}-\d{4})
- Strip: API keys/tokens (alphanumeric strings 32+ chars)
- Strip: password patterns (password/pwd followed by value)
- Keep: names, titles, company info (useful for entity extraction)
- Truncate to 500 chars after sanitization

TASK 4: Create `backend/src/services/ai_usage_tracker.py`
- log_usage(operation, model, mailbox_id, client_id, input_tokens,
  output_tokens, processing_time_ms, batch_size)
- get_usage_summary(client_id, date_range) → {total_cost, by_operation, by_model}

Follow existing patterns: Supabase sync client, _execute_with_retry(),
logging module. Add ANTHROPIC_API_KEY to backend/.env.example.
```

### Session 2 (6h) — Email Analyzer

**Day 2: Classification + Entity Extraction + Justification (ONE API call)**

This is the most important session. The prompt design is critical.

```
Read CLAUDE.md. Building the unified email intelligence service.

KEY DESIGN: One Claude API call per batch does classification AND entity
extraction AND provides justification. The email body is read ONCE.

Create `backend/src/services/ai_email_analyzer.py`:

1. analyze_batch(mailbox_id, client_id, batch_size=20) method:
   - Query unanalyzed emails (not in ai_email_intelligence)
   - Use Python-side filtering (our Supabase NULL handling pattern)
   - Call ai_privacy_filter.sanitize_email_body() on each email body
   - Batch 10 emails per Claude API call

   PROMPT TEMPLATE for Haiku:
   ```
   You are an email intelligence analyst for a B2B account management team.
   For each email, provide multi-axis classification, entity extraction,
   and justification.

   Return a JSON object for each email with:

   CLASSIFICATION:
   - intent: one of [action_required, fyi_update, meeting_scheduling,
     question, complaint, positive_feedback, pricing_inquiry,
     feature_request, expansion_signal, churn_risk, follow_up,
     introduction, other]
   - urgency: one of [critical, high, medium, low, none]
   - sentiment: one of [very_positive, positive, neutral, negative, very_negative]
   - sentiment_score: float -1.0 to 1.0
   - action_type: one of [respond_to_inquiry, provide_quote,
     schedule_meeting, escalate_internally, send_follow_up,
     resolve_issue, acknowledge_receipt, no_action, delegate,
     prepare_document]
   - business_signal: one of [buying_intent, renewal_intent,
     expansion_interest, churn_signal, competitive_evaluation,
     budget_discussion, escalation, positive_feedback,
     negative_feedback, contract_activity, neutral] or null
   - thread_role: one of [initial, reply, forward, auto_reply,
     cc_addition, internal] or null
   - summary: 1-2 sentence summary
   - suggested_action: what the account manager should do (1 sentence)
   - key_topics: array of 1-3 topic strings
   - confidence: float 0.0-1.0
   - justification: 1 sentence explaining WHY you chose this intent and
     urgency — reference specific words or patterns from the email

   ENTITY EXTRACTION:
   - competitors_mentioned: array of competitor company names (empty if none)
   - products_mentioned: array of product/service names discussed (empty if none)
   - budget_signals: {amount, timeframe, context} if budget/pricing discussed, null if not
   - buying_signals: array of buying indicators like "requesting proposal",
     "legal review", "procurement involved" (empty if none)
   - people_mentioned: [{name, role, context}] for people referenced who
     aren't sender/recipient (empty if none)
   - dates_mentioned: [{date, context}] for deadlines/timelines (empty if none)
   - action_items_extracted: specific action items from email body (empty if none)

   EMAILS:
   {emails_json}

   Return ONLY a JSON array with one object per email, in order.
   No markdown, no explanation, just the JSON array.
   ```

   POST-PROCESSING:
   a) Set boolean flags: has_budget_signal, has_buying_signal,
      has_competitor_mention, has_deadline
   b) SKIP auto-replies: if thread_role == 'auto_reply', store the row
      but do NOT assign buckets or count in business signals
   c) Compute business_signal_score (0-100):
      has_budget_signal: +30 | has_buying_signal: +25/signal (max 50)
      has_competitor_mention: +15 | has_deadline: +10
      intent is pricing_inquiry or expansion_signal: +20
      business_signal in (buying_intent, expansion_interest, renewal_intent): +15
      business_signal == 'competitive_evaluation': +10
      Cap at 100
   d) Call action_bucket_engine.derive_email_buckets() for each result
      (pass action_type + business_signal + thread_role as inputs)
   e) Set primary_bucket = highest-confidence bucket (or null)
   f) Insert into ai_email_intelligence
   g) Log usage via ai_usage_tracker

2. analyze_all_unanalyzed(mailbox_id, client_id):
   - Loop batches until done
   - After all batches: call entity_aggregator.aggregate_entities()
   - After aggregation: call action_bucket_engine.compute_relationship_buckets()
   - Return {total_analyzed, entities_found, buckets_assigned}

3. get_intelligence(mailbox_id, filters):
   - Filters: intent, urgency, sentiment, primary_bucket, has_budget_signal,
     has_buying_signal, has_competitor_mention, min_confidence, date_range
   - Join with emails for subject, sender
   - Paginated, sortable

Existing patterns: _execute_with_retry(), offset pagination with
len==0 break, logging. Handle JSON parse errors per-batch gracefully.
```

### Session 3 (5h) — Action Bucket Engine

**Day 3: Zero-Cost Intelligence Amplifier (Pure Python)**

```
Read CLAUDE.md. Build the action bucket derivation engine.

Create `backend/src/services/ai_action_bucket_engine.py`

This service translates raw AI results + Sprint 2 data into human-readable
Action Buckets. It makes ZERO Claude API calls — pure Python rules.

IMPORTANT: Emails with thread_role='auto_reply' are NEVER assigned buckets.

BUCKET DEFINITIONS (8 types, 2 categories):

EMAIL-LEVEL (from ai_email_intelligence per row):
- buying_signal: has_buying_signal OR has_budget_signal
  OR business_signal IN ('buying_intent', 'expansion_interest', 'renewal_intent')
  OR action_type == 'provide_quote'
  confidence: AI confidence + 0.1 boost (explicit signals are reliable)
- expansion_signal: intent == 'expansion_signal'
  OR business_signal == 'expansion_interest'
  confidence: AI confidence directly
- churn_risk: intent == 'churn_risk'
  OR business_signal IN ('churn_signal', 'competitive_evaluation')
  OR (sentiment in negative/very_negative AND has_competitor_mention)
  confidence: AI confidence if intent/signal match, 0.65 if inferred
- competitor_threat: has_competitor_mention
  OR business_signal == 'competitive_evaluation'
  confidence: AI confidence directly

RELATIONSHIP-LEVEL (from Sprint 2 data + ai_email_intelligence cross-reference):
- silent_champion: contact.engagement_score >= 50 AND days_since_outbound >= 14
  confidence: 0.85 (rule-based, high reliability)
- stakeholder_entry: new high-seniority CC (director/vp/c_level from
  customer_contacts.seniority_level) appeared in a thread in last 7 days
  that previously had lower-seniority participants only
  OR thread_role == 'cc_addition' AND contact seniority >= director
  confidence: 0.80
- unresolved_block: thread_status.status == 'awaiting_reply' AND
  open_duration_seconds > 172800 (48h) AND last inbound email's
  intent == 'question' (from ai_email_intelligence)
  confidence: 0.90
- missed_opportunity: email has business_signal_score > 0 AND
  no outbound email in that thread after the signal email
  confidence: 0.90

Methods:
1. derive_email_buckets(intel_row: dict) → list[{bucket, confidence, justification}]
   Called per-row during analyze_batch post-processing.
   Uses: intent, sentiment, has_*_signal flags, action_type, business_signal, thread_role
   SKIP if thread_role == 'auto_reply' (return empty list)

2. compute_relationship_buckets(client_id, mailbox_id) → list[{bucket, confidence,
   justification, contact_id?, company_id?, thread_id?, email_id?}]
   Called once after full analysis completes. Queries Sprint 2 tables:
   - customer_contacts (engagement_score, seniority_level, last_outbound_at)
   - thread_status (status, open_duration_seconds)
   - email_response_metrics (status)
   - ai_email_intelligence (intent, business_signal_score)

3. get_action_items(client_id, min_confidence=0.5) → prioritized list of all
   active buckets across both categories, sorted by:
   a) Severity (critical > high > medium)
   b) Confidence DESC
   c) Date DESC
   Returns: [{bucket, label, icon, color, action_text, confidence,
     justification, company_name, contact_name, email_subject, email_id,
     source: 'email'|'relationship'}]

4. get_bucket_summary(client_id) → {buying_signal: 3, churn_risk: 1, ...}
   Quick counts for dashboard display.

BUCKET METADATA (include in module):
BUCKET_CONFIG = {
    'buying_signal':      {'label': 'Buying Signal',      'icon': '💰', 'color': 'green',  'severity': 'critical', 'action': 'Trigger a proposal or sales follow-up'},
    'expansion_signal':   {'label': 'Expansion Signal',   'icon': '📈', 'color': 'blue',   'severity': 'critical', 'action': 'Schedule an upsell or strategy call'},
    'churn_risk':         {'label': 'Churn Risk',         'icon': '🚨', 'color': 'red',    'severity': 'critical', 'action': 'Immediate retention outreach required'},
    'competitor_threat':  {'label': 'Competitor Threat',  'icon': '⚔️', 'color': 'red',    'severity': 'high',     'action': 'Review competitive positioning'},
    'missed_opportunity': {'label': 'Missed Opportunity', 'icon': '⚡', 'color': 'red',    'severity': 'critical', 'action': 'Business signal with no response — act now'},
    'stakeholder_entry':  {'label': 'Stakeholder Entry',  'icon': '👔', 'color': 'purple', 'severity': 'high',     'action': 'Multi-thread the account'},
    'silent_champion':    {'label': 'Silent Champion',    'icon': '🔇', 'color': 'orange', 'severity': 'medium',   'action': 'Send personalized check-in'},
    'unresolved_block':   {'label': 'Unresolved Block',   'icon': '⏳', 'color': 'yellow', 'severity': 'medium',   'action': 'Bump thread to resolve blocker'},
}
```

### Session 4 (6h) — Entity Aggregator + API Router

**Day 4: Entity Roll-Up + All 15 API Endpoints**

```
Read CLAUDE.md. Build entity aggregation and ALL AI API endpoints.

PART 1: Create `backend/src/services/ai_entity_aggregator.py`

1. aggregate_entities(client_id, mailbox_id)
   Called after analyze_all_unanalyzed completes.
   Logic:
   a) Query ai_email_intelligence WHERE has_competitor_mention OR
      has_buying_signal OR products_mentioned IS NOT NULL OR
      people_mentioned IS NOT NULL
   b) For each email's entities:
      - competitors_mentioned → entity_type='competitor'
      - products_mentioned → entity_type='product'
      - people_mentioned → entity_type='person'
   c) Normalize names (lowercase, trim, strip "Inc"/"LLC"/"Corp")
   d) Upsert into ai_business_entities:
      ON CONFLICT: INCREMENT mention_count, UPDATE last_seen_at,
      APPEND to context_snippets (keep last 10), APPEND company_id
   e) Return {competitors: N, products: N, people: N, total: N}

2. get_entities(client_id, filters) — paginated, sorted by mention_count

3. get_competitor_landscape(client_id) — type=competitor, mentions>=2,
   with associated companies and context

4. get_opportunity_signals(client_id, mailbox_id) —
   ai_email_intelligence WHERE business_signal_score > 0,
   joined with emails + customer_companies, sorted by score DESC

PART 2: Create `backend/src/routers/ai.py` with ALL endpoints:

INTELLIGENCE:
1. POST /api/v1/ai/analyze/{mailbox_id}
   Body: {client_id, batch_size?: 20}
   Triggers analyze_all_unanalyzed in background thread

2. GET /api/v1/ai/intelligence/{mailbox_id}
   Query params: intent, urgency, sentiment, primary_bucket,
   action_type, business_signal, thread_role,
   has_budget_signal, has_buying_signal, has_competitor_mention,
   min_signal_score, min_confidence, page, page_size, sort_by,
   sort_order, date_from, date_to
   Include action_buckets and justification in response

3. GET /api/v1/ai/intelligence/stats/{mailbox_id}
   Include bucket_counts + by_action_type + by_business_signal in response

ACTION BUCKETS:
4. GET /api/v1/ai/action-items/{client_id}?min_confidence=0.5
5. GET /api/v1/ai/action-items/{client_id}/summary

HUMAN FEEDBACK:
6. POST /api/v1/ai/intelligence/{email_id}/feedback
   Body: {feedback: "correct"|"incorrect", override_intent?, override_bucket?}

ENTITIES:
7. GET /api/v1/ai/entities/{client_id}
8. GET /api/v1/ai/entities/{client_id}/competitors
9. GET /api/v1/ai/entities/{client_id}/opportunities

Register in main.py. Follow analytics.py patterns exactly.

REMINDERS:
- int() cast for numeric Supabase filters
- lowercase 'true'/'false' for booleans
- _execute_with_retry pattern
- nullsfirst=False for DESC sorts
```

### Session 5 (5h) — Digest Service

**Day 5: Bucket-Aware Daily Digest**

```
Read CLAUDE.md. Build the daily digest generator.

Create `backend/src/services/ai_digest_generator.py`:

1. generate_digest(mailbox_id, client_id, date=today):
   - Check cache first → return if exists
   - Query emails for date
   - Query ai_email_intelligence for those emails
   - Query thread_status for active threads
   - Query email_response_metrics for pending responses
   - Call action_bucket_engine.get_bucket_summary(client_id) for counts

   Prompt for Sonnet:
   ```
   You are an executive assistant creating a daily email briefing.
   Be concise, prioritized, and ACTION-ORIENTED.

   Use these action categories when describing items:
   - 💰 Buying Signal: customer showing purchase intent
   - 📈 Expansion Signal: customer wants to grow usage
   - 🚨 Churn Risk: customer showing signs of leaving
   - ⚔️ Competitor Threat: competitor being discussed
   - 🔇 Silent Champion: engaged customer gone quiet
   - ⏳ Unresolved Block: question waiting 48+ hours
   - ⚡ Missed Opportunity: business signal with no response yet

   TODAY'S ACTIVITY:
   - Emails received: {count} | Sent: {count}
   - Action buckets detected: {bucket_summary counts}
   - Open threads: {count} | Overdue: {count}

   BUSINESS SIGNALS:
   {list from ai_email_intelligence where business_signal_score > 0}

   EMAIL DETAILS:
   [For each email: subject, from/to, intent, urgency, summary,
    action buckets assigned, entities if any]

   Generate JSON:
   1. summary: 2-3 sentences. Lead with most critical action buckets.
      Example: "You have 2 Buying Signals and 1 Churn Risk to address today.
      Acme Corp discussed a $50K Q3 budget, while Beta Inc mentioned a competitor."
   2. action_items: [{email_id, action, priority (1-5), contact_name, bucket}]
      Emails with action buckets get priority 1-2.
   3. key_threads: [{thread_id, subject, status, one_line_summary}]
   4. highlights: [{type, description, email_id, bucket?}]
   5. business_signals: [{type, description, email_id, company_name}]
   6. competitor_activity: [{competitor, context, email_id}]

   Return ONLY the JSON.
   ```

   - Compute bucket_summary from action items
   - Store in ai_daily_digests
   - Log usage

2. get_digest(mailbox_id, date) → cached or null
3. get_digest_or_generate(mailbox_id, client_id, date)

Add to routers/ai.py:
10. GET /api/v1/ai/digest/{mailbox_id}?date=YYYY-MM-DD
11. GET /api/v1/ai/digest/{mailbox_id}/history
```

**Week 1 Exit Criteria:**
- [ ] `POST /api/v1/ai/analyze/{mailbox_id}` triggers analysis and populates ai_email_intelligence
- [ ] ai_email_intelligence rows have: classification, entities, justification, action_buckets, primary_bucket
- [ ] v3.2: action_type, business_signal, thread_role populated on every row
- [ ] v3.2: auto_reply emails stored but never assigned action buckets
- [ ] Action bucket engine derives email-level + relationship-level buckets
- [ ] Bucket engine uses business_signal + action_type for richer derivation
- [ ] `GET /api/v1/ai/action-items/{client_id}` returns prioritized bucket list
- [ ] Daily digest generates with bucket language ("2 Buying Signals today")
- [ ] ai_usage_log tracks costs for every API call
- [ ] Privacy filter strips sensitive data before Claude sees email bodies

---

## Week 2: Dashboard Integration + Opportunities

### Session 6 (6h) — Digest + Smart Inbox Frontend

**Day 6: The Two Core Frontend Pages**

```
Read CLAUDE.md. Build digest page and smart inbox with action bucket UI.

IMPORTANT UI PATTERN — Confidence-based display:
  confidence >= 0.8  → Full colored tag with icon: "💰 Buying Signal"
  confidence 0.5-0.8 → Muted outline tag: "💰 Buying Signal · Review"
  confidence < 0.5   → Not displayed

Create shared components first:

`frontend/src/components/ai/ActionBucketTag.tsx`
- Props: {bucket: string, confidence: number, justification?: string}
- Renders colored Ant Design Tag per confidence threshold
- Tooltip on hover shows justification text
- Returns null if confidence < 0.5

`frontend/src/components/ai/FeedbackButtons.tsx`
- Props: {emailId: string, currentFeedback?: string, onFeedback: fn}
- Renders 👍 👎 buttons, highlighted if already given
- On 👎: show small dropdown for override intent/bucket

PAGE 1: `frontend/src/pages/ai/digest.tsx`
- TOP: Date selector + mailbox selector
- BUCKET SUMMARY BAR: Horizontal row of bucket count badges
  "💰 2 | 🚨 1 | 🔇 3 | ⏳ 2" — clicking any filters action items below
- HERO: Digest summary text (2-3 sentences, large)
- BUSINESS SIGNALS: Gold/amber cards with entity details
- ACTION ITEMS: List with ActionBucketTag on each + priority badge
- KEY THREADS: Cards with status badges
- HIGHLIGHTS: Color-coded cards
- STATS ROW: emails in/out, response time, total signals

PAGE 2: `frontend/src/pages/ai/inbox.tsx`
- TOP: Mailbox selector + "Analyze New Emails" button
- FILTER BAR: Bucket filter chips + intent/urgency/sentiment filters
  + confidence threshold slider
- TABLE:
  | Bucket(s) | Urgency | Subject | From | Sentiment | Summary | Date |
  Rows with business signals get subtle highlight

- DETAIL DRAWER (on row click):
  Section 1: Email headers
  Section 2: "AI Intelligence" card
    - Action Buckets (full-size tags with justification)
    - Intent + urgency + sentiment badges
    - v3.2: Action Type badge (e.g., "Provide Quote", "Schedule Meeting")
    - v3.2: Business Signal badge (e.g., "Buying Intent", "Competitive Evaluation")
    - v3.2: Thread Role indicator (e.g., "Initial Contact", "Reply", "Auto-Reply")
    - Suggested Action (boxed, prominent)
    - Key Topics as tags
    - Confidence meter
    - Justification text (italic)
  Section 3: "Business Entities" (if any)
    - Competitors, products, budget, buying signals, people, deadlines
  Section 4: Full email body
  Section 5: Feedback row — "Was this analysis helpful?" 👍 👎

Create `frontend/src/services/aiService.ts` following analyticsService.ts.
Add routes. Add "AI Intelligence" section to sidebar.
```

### Session 7 (5h) — Relationship Summary Service

**Day 7: Company Intelligence with Bucket Context**

```
Read CLAUDE.md. Build AI relationship summarizer.

Create `backend/src/services/ai_relationship_summarizer.py`:

1. generate_summary(company_id, client_id, mailbox_id):
   - Query company info, contacts, emails (90 days), threads, response metrics
   - Query ai_email_intelligence for this company's emails
   - Query action buckets for this company

   Prompt for Sonnet:
   ```
   You are a CRM analyst. Provide an executive relationship summary.

   COMPANY: {name}
   CONTACTS: {list with names, roles, seniority, engagement scores}
   METRICS: Score: {}/100 | Status: {} | Health: {}
   Response time: {} | Frequency: {}/month ({trend})
   Open threads: {} | Dropped: {}

   AI-DETECTED PATTERNS (last 90 days):
   - Active action buckets: {e.g., "2 Buying Signals, 1 Competitor Threat"}
   - Intent distribution: {counts}
   - Sentiment trend: {by month}
   - Business signals: competitors: {}, budgets: {}, buying indicators: {}

   RECENT THREADS (last 10): [subject, status, intent, sentiment]

   Generate JSON:
   1. summary: 3 sentences. Reference specific action buckets detected.
      Example: "Acme Corp is an active account with 2 recent Buying Signals
      around their Q3 expansion. However, a Competitor Threat was detected
      when they mentioned evaluating alternatives. Recommend scheduling an
      executive review to solidify the relationship."
   2. key_themes: 3-5
   3. risk_factors: 0-3 (reference competitor threats, churn risks)
   4. opportunities: 0-3 (reference buying signals, expansion signals)
   5. recommended_actions: 1-3 specific steps

   Return ONLY JSON.
   ```

   - Store with active_buckets populated, cache 7 days

2. get_summary(company_id)
3. bulk_generate(client_id, mailbox_id, top_n=20)

Add to routers/ai.py:
12. POST /api/v1/ai/relationship-summary/{company_id}
13. GET /api/v1/ai/relationship-summary/{company_id}
14. POST /api/v1/ai/relationship-summaries/bulk/{client_id}
```

### Session 8 (6h) — Company Detail Enhancement

**Day 8: AI Intelligence Cards on Company Pages**

```
Read CLAUDE.md. Enhance company detail page with AI + bucket intelligence.

Modify `frontend/src/pages/analytics/company-detail.tsx`:

ADD TOP CARD: "RELATIONSHIP INTELLIGENCE" (gradient background):
- 3-sentence summary text
- Active Bucket Row: ActionBucketTag components for active buckets
  "This company has: 💰 Buying Signal  ⚔️ Competitor Threat"
- Key Themes as Tags
- Risk Factors (red) / Opportunities (green) as Alert items
- Recommended Actions as numbered list
- "Generated {date}" + "Refresh" button

ADD SECOND CARD: "BUSINESS SIGNALS":
- Competitors (tags with mention count)
- Buying signals (highlighted list)
- Budget discussions (amount + timeframe)
- Deadlines (timeline)
- "View all signals →" → filtered /ai/inbox for this company

If no data: "Generate AI Summary" / "Run AI Analysis" buttons.

Use aiService.ts methods:
- getRelationshipSummary(companyId)
- generateRelationshipSummary(companyId)
- getCompanyIntelligence(companyId) — filter by company
```

### Session 9 (5h) — Opportunities Page

**Day 9: Business Signal Discovery (5 Tabs)**

```
Read CLAUDE.md. Build the business opportunities/signals page.

Create `frontend/src/pages/ai/opportunities.tsx`

TAB 1: "Action Items" (primary view)
  Uses GET /api/v1/ai/action-items/{client_id}?min_confidence=0.5
  | Bucket | Company | Contact | Description | Confidence | Action | Date |
  ActionBucketTag components, confidence bars, detail drawers

TAB 2: "Active Opportunities"
  Emails with business_signal_score > 0
  | Score | Company | Subject | Signals | Buckets | Date |

TAB 3: "Competitor Intelligence"
  GET /api/v1/ai/entities/{client_id}/competitors
  | Competitor | Mentions | Companies Discussing | Last Mentioned |

TAB 4: "Budget Discussions"
  Emails with has_budget_signal=true
  | Company | Amount | Timeframe | Context | Date |

TAB 5: "Entity Tracker"
  All entities from GET /api/v1/ai/entities/{client_id}
  | Entity | Type | Mentions | Companies | First Seen | Last Seen |

Add to sidebar: "AI Intelligence" → "Opportunities"
```

### Session 10 (6h) — AM Comparison + Gap Alerts

**Day 10: Business Owner Views (Bucket-Enriched)**

```
Read CLAUDE.md. Build AM comparison and gap alerts.

PART 1: AM COMPARISON
Backend: GET /api/v1/analytics/account-manager-comparison/{client_id}
Per-mailbox stats:
- Standard: mailbox_name, total_companies, total_contacts, total_emails_30d,
  avg_response_time, sla_compliance_pct, open/dropped_thread_count,
  avg_engagement_score
- AI metrics: analyzed_email_count, bucket_counts, avg_sentiment_score,
  unresolved_blocks_count, missed_opportunities_count

Frontend: Comparison table + bar charts on analytics dashboard.
Admin and Client Manager roles only.

PART 2: GAP ALERTS (bucket-enriched)
Backend: GET /api/v1/analytics/communication-gaps/{client_id}

Alert types (using bucket names for visual consistency):
1. missed_opportunity (RED): Business signal + no response
2. churn_risk (RED): AI churn intent or negative sentiment + competitor
3. ignored (RED): 3+ unanswered inbound
4. competitor_threat (ORANGE): Competitor mention + declining engagement
5. silent_champion (ORANGE): High engagement + gone quiet 14+ days
6. unresolved_block (YELLOW): Thread waiting 48h+ with question intent
7. sentiment_declining (YELLOW): Avg sentiment < -0.3 over 30 days
8. single_contact (BLUE): Only 1 contact at company

Each alert returns: {company_name, alert_type, bucket, severity,
label, icon, color, action_text, details, related_email_id, confidence}

Frontend: "Gap Alerts" card on analytics dashboard using ActionBucketTag.
Top 10, "View All" link. Clicking → company detail.
```

**Week 2 Exit Criteria:**
- [ ] Digest page renders with bucket summary bar + action items + signals
- [ ] Smart inbox shows bucket tags with confidence thresholds applied
- [ ] 👍/👎 feedback buttons work and update ai_email_intelligence
- [ ] Relationship summaries generate with bucket context language
- [ ] Company detail page shows AI intelligence + business signals cards
- [ ] Opportunities page shows all 5 tabs with real data
- [ ] AM comparison shows per-mailbox stats with AI metrics
- [ ] Gap alerts surface bucket-enriched warnings on analytics dashboard

---

## Week 3: Polish, Connect, Deploy

### Session 11 (5h) — Navigation + Usage Page + Cross-Linking

**Day 11: Wire the Full Experience**

```
Read CLAUDE.md. Connect all AI features and build usage page.

1. Sidebar navigation:
   "AI Intelligence" section:
   - 📋 Daily Digest → /ai/digest
   - 📬 Smart Inbox → /ai/inbox
   - 💡 Opportunities → /ai/opportunities
   - 💰 AI Usage → /ai/usage (admin only)

2. Main dashboard — "Quick Insights" card:
   - Bucket summary bar: "💰 2 | 🚨 1 | 🔇 3"
   - Digest first 2 sentences + "Read More →"
   - Gap alert count + critical urgency count

3. Cross-linking:
   - Digest action items → /ai/inbox with email selected
   - Opportunity signals → company detail
   - Gap alerts → company detail
   - Company detail "View signals" → /ai/inbox?company={id}

4. /ai/usage page (admin only):
   - Month total cost (big number)
   - Bucket impact: "AI detected 47 Buying Signals across 3,200 emails (cost: $3.20)"
   - Cost by operation (pie chart)
   - Cost trend (line chart, 30 days)
   - Cost per mailbox (table)
   - Feedback stats: "Users confirmed 89% of classifications correct"

Add endpoint:
15. GET /api/v1/ai/usage/costs?client_id=X&date_from=Y&date_to=Z
    Returns: {total_cost, by_operation, by_model, by_day, by_mailbox,
    feedback_stats: {total, correct, incorrect, correct_pct}}
```

### Session 12 (4h) — Integration Testing

**Day 12: End-to-End Verification**

```
Read CLAUDE.md. Test the complete AI intelligence + action bucket flow.

Create `scripts/test_ai_pipeline.py`:
a) Pick a mailbox
b) Run intelligence analysis on 50 emails
c) Verify ai_email_intelligence has entries WITH:
   - justification populated, action_buckets populated, primary_bucket set
   - v3.2: action_type, business_signal, thread_role populated
   - v3.2: auto_reply emails have empty action_buckets (never bucketed)
d) Check entity extraction: count competitors, products, signals
e) Verify ai_business_entities populated
f) Check action bucket engine:
   - Get action items — verify email-level + relationship-level buckets
   - Verify confidence thresholds (all 0.0-1.0)
   - Check bucket summary counts
g) Generate digest — verify bucket language
h) Generate relationship summary — verify active_buckets
i) Submit feedback (1 correct, 1 incorrect) — verify columns updated
j) Check ai_usage_log — verify cost entries
k) Check gap alerts — verify bucket-enriched alerts
l) Print summary:
   Emails: N | Buckets: {type: count} | Entities: {type: count}
   Cost: $X.XX | Feedback: N

Verify ALL 15 API endpoints return valid responses.

Error handling checks:
- Claude API down → retry 3x with backoff
- Empty email body → skip, log warning
- JSON parse failure → skip batch, log error, continue
- Company with no emails → empty summary gracefully
- All low confidence → no buckets shown (correct)
```

### Session 13 (3h) — Production Deploy

**Day 13: Deploy to Railway**

```
PRODUCTION DEPLOYMENT CHECKLIST:

Environment:
□ Railway: ANTHROPIC_API_KEY set in production
□ Railway: ANTHROPIC_API_KEY set in staging (if applicable)
□ Railway: No hardcoded localhost in new code

Database:
□ Run Migration 013 on production Supabase
□ Verify all 5 tables created + indexes + triggers
□ Verify RLS grants (anon, authenticated)

Smoke Test (production):
□ Run scripts/test_ai_pipeline.py on 50 production emails
□ Verify all 15 API endpoints respond (200 OK)
□ Verify frontend pages load: /ai/digest, /ai/inbox, /ai/opportunities, /ai/usage
□ Verify sidebar navigation shows AI Intelligence section
□ Verify Quick Insights card on main dashboard

Cost Approval:
□ Run cost projection: 26K emails × ~$0.001 = ~$26 initial run
□ Get business owner sign-off before triggering full analysis
□ Confirm monthly budget: ~$16/month for 30K emails ongoing

Monitoring:
□ AI usage dashboard live and showing real-time costs
□ Error logs accessible for Claude API failures / retries
□ ai_usage_log tracking every API call

Documentation:
□ CLAUDE.md updated with Sprint 3 section
□ CONTINUATION_GUIDE.md updated with Sprint 3 complete status
□ TODO.md — Sprint 3 items checked off
□ CHANGELOG entry created
```

### Day 14 (2h) — Buffer

Reserve for bug fixes, UI polish, or any session that ran over estimate.

**Week 3 Exit Criteria:**
- [ ] All pages connected via sidebar navigation with correct cross-links
- [ ] Main dashboard shows Quick Insights with bucket counts
- [ ] AI usage page shows cost breakdown and feedback stats
- [ ] Integration test passes end-to-end on production data
- [ ] Deployed to Railway with ANTHROPIC_API_KEY configured
- [ ] Migration 013 live on production database
- [ ] Documentation updated (CLAUDE.md, CONTINUATION_GUIDE, TODO, CHANGELOG)
- [ ] Business owner approved initial analysis cost (~$26)

---

## Claude Code Best Practices

### Before Every Session
```
"Read CLAUDE.md and docs/CONTINUATION_GUIDE.md for project context.
I'm working on [specific task]. Don't modify files outside of [scope]."
```

### Project-Specific Gotchas
```
REMINDERS:
- Supabase NULL: Python-side filtering, NOT .neq() on nullable columns
- Supabase pagination: break on len(batch)==0, NOT len < PAGE_SIZE
- Supabase booleans: lowercase strings 'true'/'false'
- Supabase sort: nullsfirst=False to push NULLs to end
- Batch limits: max 100 per update, 500 per .in_() filter
- Float params: cast to int() before .gte()/.lte() on INTEGER columns
- Frontend: apiClient.ts only, no nested retries
- Frontend: onChangeComplete for sliders
- Ant Design v5 patterns only
- Ports: backend 8000, frontend 3001
```

### Session Sizing

| Task | Sessions | Notes |
|------|----------|-------|
| New backend service | 1 (5-6h) | Full spec + prompt template |
| API router | 1 (6h) | Reference analytics.py |
| Frontend page | 1-2 (5-6h) | Structure first, polish second |
| Shared component | Part of page session | ActionBucketTag, FeedbackButtons |
| Bug fix | 1 short (1-2h) | Specific error + file |
| Cross-wiring | 1 (5h) | List all touchpoints |

### Conversation Management
- /compact after files >200 lines
- New conversation after each week
- /compact before new feature area within a week

---

## Cost Projections

### Per-Email Cost

```
v3.2 Unified Pass (classify + entities + justification + multi-axis):
  Input:  ~200 tokens/email (body + metadata)
  Output: ~228 tokens/email (v3.1 fields + action_type + business_signal + thread_role)
  Total:  ~$0.00107/email with Haiku

vs v3.1: +$0.00003/email for 3 new classification axes (~8 extra tokens)
vs separate passes: saves 27% cost, 50% latency
```

### Monthly Estimate (30K emails, 1 mailbox)

| Operation | Model | Frequency | Monthly Cost |
|-----------|-------|-----------|-------------|
| Email Intelligence (unified) | Haiku | 30K/month | ~$10.70 |
| Action Bucket Engine | None | After analysis | $0.00 |
| Entity Aggregation | None | After analysis | $0.00 |
| Daily Digest | Sonnet | 30/month | ~$1.44 |
| Relationship Summary | Sonnet | 100/month | ~$3.90 |
| **Total** | | | **~$16.04/month** |

### Performance Targets

| Operation | Target |
|-----------|--------|
| Analyze 1 email batch (10) | <3s |
| Analyze 30K emails | ~75 min |
| Derive action buckets (all) | <5s (pure Python) |
| Generate digest | <20s |
| Relationship summary | <25s |
| Action items page load | <3s (pre-computed) |

---

## Appendix A: Client ROI & Pricing Context

### Cost Per Client

| Item | Cost |
|------|------|
| Initial email analysis (26K existing) | ~$26 one-time |
| Monthly ongoing (30K new emails) | ~$16/month |
| Annual per client | ~$218/year |

### Value Delivered

| Metric | Estimate |
|--------|----------|
| AM time saved on email triage | ~2h/week |
| At $150/hr loaded AM salary | $15,600/year saved |
| ROI at $218/year cost | ~71x |
| Buying signals surfaced (est.) | 5-15/month per client |
| Churn risks caught proactively | Previously invisible |

### Post-Launch Success KPIs

| Metric | Target | Measurement |
|--------|--------|-------------|
| Buying Signals detected | 5+/month per client | action-items endpoint |
| Classification accuracy | 85%+ user-confirmed correct | human feedback data |
| AM daily digest engagement | 80%+ daily usage | page view analytics |
| Analysis cost per client | <$20/month | AI usage dashboard |
| System uptime | 99%+ | Railway metrics |

---

## Implementation Status (as of March 3, 2026)

### Overall Progress: Week 1 COMPLETE | Week 2 PARTIAL (Frontend only)

**Sessions 1-6 are fully implemented.** The backend intelligence engine, action bucket engine, digest service, and all 4 frontend pages are built and functional. Sessions 7-13 (relationship summaries, company AI cards, AM comparison, gap alerts, integration testing, production deploy) are **not yet started**.

---

### Backend Services — ALL 7 BUILT ✅

| Service | File | Status | Notes |
|---------|------|--------|-------|
| AI Client | `backend/src/services/ai_client.py` | ✅ Built | Haiku ($0.80/$4.00/MTok) + Sonnet ($3.00/$15.00/MTok), rate limiting (10 req/s), retry (3 attempts), daily budget $2, monthly $16 |
| Privacy Filter | `backend/src/services/ai_privacy_filter.py` | ✅ Built | Strips credit cards, SSN, API keys, JWT, passwords, signatures. MAX_BODY_LENGTH=500 |
| Usage Tracker | `backend/src/services/ai_usage_tracker.py` | ✅ Built | Logs every AI operation with tokens, cost, latency to `ai_usage_log` |
| Email Analyzer | `backend/src/services/ai_email_analyzer.py` | ✅ Built | Claude Haiku, BATCH_SIZE=10, 12 intent categories, 5 urgency levels, entity extraction, pre-filtering (skips spam/marketing/auto-reply) |
| Action Bucket Engine | `backend/src/services/ai_action_bucket_engine.py` | ✅ Built | 8 bucket types (4 email-level + 4 relationship-level), pure Python, zero AI cost |
| Entity Aggregator | `backend/src/services/ai_entity_aggregator.py` | ✅ Built | Rolls up per-email entities into aggregate tracking in `ai_business_entities` |
| Digest Generator | `backend/src/services/ai_digest_generator.py` | ✅ Built | Claude Sonnet, generates daily digest with bucket language, action items, highlights |

### API Router — 19 ENDPOINTS BUILT ✅

| File | Endpoints | Status |
|------|-----------|--------|
| `backend/src/routers/ai.py` | 19 endpoints | ✅ Built |
| `backend/src/routers/rules.py` | 4 endpoints | ✅ Built |

**AI Router endpoints:** analyze, intelligence (paginated), intelligence stats, action items, action items summary, feedback, entities, competitors, opportunities, digest, digest history, relationship summary (POST/GET), bulk relationship summaries, usage costs, usage controls, budget, analysis health

### Backend Models — COMPLETE ✅

| File | Contents | Status |
|------|----------|--------|
| `backend/src/models/ai.py` | Pydantic models for all AI request/response types | ✅ Built |
| `backend/src/models/rules.py` | Pydantic models for email rules | ✅ Built |

### Email Rules Service — COMPLETE ✅

| File | Purpose | Status |
|------|---------|--------|
| `backend/src/services/email_rules_service.py` | CRUD for unified email rules | ✅ Built |

---

### Frontend — 4 INTELLIGENCE PAGES BUILT ✅

| Page | Route | File | Status | Features |
|------|-------|------|--------|----------|
| Smart Inbox | `/intelligence/inbox` | `frontend/src/pages/intelligence/inbox.tsx` | ✅ Built | Bucket filter chips, intent/urgency/sentiment filters, confidence slider, detail drawer with AI intelligence card, feedback buttons, "Analyze New Emails" trigger |
| Daily Digest | `/intelligence/digest` | `frontend/src/pages/intelligence/digest.tsx` | ✅ Built | Date picker, bucket summary bar, hero summary, action items list, key threads, highlights, business signals, stats row |
| Opportunities | `/intelligence/opportunities` | `frontend/src/pages/intelligence/opportunities.tsx` | ✅ Built | 4 tabs: Action Items, Opportunities, Competitors, Entities. Bucket tags, confidence bars, detail views |
| Usage & Monitoring | `/intelligence/usage` | `frontend/src/pages/intelligence/usage.tsx` | ✅ Built | Admin controls (enable/disable, budget), cost breakdown charts, per-mailbox usage, feedback stats, analysis health metrics |

### Frontend Components — 2 SHARED COMPONENTS BUILT ✅

| Component | File | Status |
|-----------|------|--------|
| ActionBucketTag | `frontend/src/components/ai/ActionBucketTag.tsx` | ✅ Built | Confidence-gated display (≥0.8 full, 0.5-0.8 muted, <0.5 hidden), tooltip justification |
| FeedbackButtons | `frontend/src/components/ai/FeedbackButtons.tsx` | ✅ Built | 👍/👎 buttons with structured feedback + override intent/bucket |

### Frontend Services & Types — COMPLETE ✅

| File | Status | Details |
|------|--------|---------|
| `frontend/src/services/aiService.ts` | ✅ Built | 7 API groups, 16 endpoint wrappers, TTL cache, in-flight deduplication |
| `frontend/src/services/rulesService.ts` | ✅ Built | Email rules CRUD service |
| `frontend/src/types/ai.ts` | ✅ Built | 13 enums (IntentType, UrgencyLevel, SentimentType, ActionType, BusinessSignal, ThreadRole, ActionBucket, etc.), comprehensive interfaces |

### Frontend — Email Rules Page ✅

| Page | Route | File | Status |
|------|-------|------|--------|
| Email Rules | `/analytics/email-rules` | `frontend/src/pages/analytics/email-rules.tsx` | ✅ Built | Production-ready rules management UI |

---

### NOT YET IMPLEMENTED

| Session | Planned Deliverable | Status |
|---------|-------------------|--------|
| Session 7 | Relationship Summary Service (`ai_relationship_summarizer.py`) | ❌ Not started |
| Session 8 | Company detail page AI cards | ❌ Not started |
| Session 9 | Opportunities page Tab 5 (Budget Discussions) | ❌ Not started (4 of 5 tabs done) |
| Session 10 | AM Comparison + Gap Alerts (bucket-enriched) | ❌ Not started |
| Session 11 | Main dashboard Quick Insights card + cross-linking | ❌ Not started |
| Session 12 | Integration testing (`test_ai_pipeline.py`) | ❌ Not started |
| Session 13 | Production deployment + documentation | ❌ Not started |

---

### Known Issues (Must Fix Before Continuing)

**Issue 1: Email analysis processes age-old emails**
- `ai_email_analyzer.py` has no date filter — fetches ALL unanalyzed emails regardless of age
- **Fix:** Add `date_from`/`date_to` params, default to last 7 days
- **Files:** `ai_email_analyzer.py`, `ai.py` router, frontend analysis trigger

**Issue 2: Daily Digest considers old emails + no Weekly Digest**
- Digest should only process emails within its time window (1 day or 7 days)
- **Fix:** Add `digest_type` param (`daily` | `weekly`), filter by `sent_date`
- **Files:** `ai_digest_generator.py`, `ai.py` router, frontend digest page

**Issue 3: AI processing cost too high**
- Current: ~$0.001/email with BATCH_SIZE=10
- **Fix:** Increase batch 10→20, reduce body 500→300 chars, skip trivial/forward-only emails
- **Target:** 50%+ cost reduction
- **Files:** `ai_email_analyzer.py`, `ai_privacy_filter.py`

---

### Week 1 Exit Criteria Status

- [x] `POST /api/v1/ai/analyze/{mailbox_id}` triggers analysis and populates ai_email_intelligence
- [x] ai_email_intelligence rows have: classification, entities, justification, action_buckets, primary_bucket
- [x] action_type, business_signal, thread_role populated on every row
- [x] auto_reply emails stored but never assigned action buckets
- [x] Action bucket engine derives email-level + relationship-level buckets
- [x] Bucket engine uses business_signal + action_type for richer derivation
- [x] `GET /api/v1/ai/action-items/{client_id}` returns prioritized bucket list
- [x] Daily digest generates with bucket language ("2 Buying Signals today")
- [x] ai_usage_log tracks costs for every API call
- [x] Privacy filter strips sensitive data before Claude sees email bodies

### Week 2 Exit Criteria Status

- [x] Digest page renders with bucket summary bar + action items + signals
- [x] Smart inbox shows bucket tags with confidence thresholds applied
- [x] 👍/👎 feedback buttons work and update ai_email_intelligence
- [ ] Relationship summaries generate with bucket context language — **NOT BUILT**
- [ ] Company detail page shows AI intelligence + business signals cards — **NOT BUILT**
- [x] Opportunities page shows 4 of 5 tabs with real data (Budget Discussions tab missing)
- [ ] AM comparison shows per-mailbox stats with AI metrics — **NOT BUILT**
- [ ] Gap alerts surface bucket-enriched warnings on analytics dashboard — **NOT BUILT**

### Week 3 Exit Criteria Status

- [ ] All pages connected via sidebar navigation with correct cross-links — **PARTIAL** (sidebar has Intelligence section, cross-linking not wired)
- [ ] Main dashboard shows Quick Insights with bucket counts — **NOT BUILT**
- [x] AI usage page shows cost breakdown and feedback stats
- [ ] Integration test passes end-to-end on production data — **NOT BUILT**
- [ ] Deployed to Railway with ANTHROPIC_API_KEY configured — **NOT DEPLOYED**
- [ ] Migration 013 live on production database — **NOT VERIFIED**
- [ ] Documentation updated — **IN PROGRESS**
- [ ] Business owner approved initial analysis cost — **NOT DONE**

---

## Appendix B: Updated CLAUDE.md Section (Copy Into Your CLAUDE.md)

```markdown
### Sprint 3 — AI Semantic Intelligence (In Progress)

**Three-Layer Architecture:**
- Layer 1: Per-Email AI Intelligence (Claude Haiku, ONE call)
- Layer 2: Relationship Pattern Detection (Python rules, NO AI)
- Layer 3: Action-First Presentation (confidence thresholds + feedback)

**AI Services:**
- `ai_client.py` — Shared Claude API client (Haiku + Sonnet, retry, rate limiting)
- `ai_privacy_filter.py` — Strip sensitive data before AI calls
- `ai_email_analyzer.py` — Unified classify + extract + justify (Haiku, 10/batch)
  Multi-axis: intent + action_type + business_signal + thread_role + urgency + sentiment
- `ai_action_bucket_engine.py` — 8 action buckets from AI + Sprint 2 data ($0 cost)
- `ai_entity_aggregator.py` — Cross-email entity tracking (pure DB)
- `ai_digest_generator.py` — Daily digest with bucket language (Sonnet)
- `ai_relationship_summarizer.py` — Company summaries with bucket context (Sonnet)
- `ai_usage_tracker.py` — Cost tracking per operation/model/mailbox

**8 Action Buckets (2 categories):**
- Email-level (from AI): Buying Signal, Expansion Signal, Churn Risk, Competitor Threat
- Relationship-level (from rules): Silent Champion, Stakeholder Entry, Unresolved Block, Missed Opportunity
- Confidence display: ≥0.8 full tag, 0.5-0.8 "Review" tag, <0.5 hidden
- Human feedback: 👍/👎 on every classification, stored for prompt tuning

**AI API Endpoints** at `/api/v1/ai/`:
- Intelligence (3): trigger, list, stats
- Action Buckets (2): items, summary
- Feedback (1): submit feedback
- Entities (3): all, competitors, opportunities
- Digest (2): get/generate, history
- Relationship (3): generate, get, bulk
- Usage (1): costs + feedback stats

**Key Patterns:**
- ONE API call per email batch (classify + extract + justify)
- Multi-axis classification: intent, action_type, business_signal, thread_role, urgency, sentiment
- Auto-replies (thread_role='auto_reply') never get action buckets
- Privacy filter strips sensitive data before Claude sees it
- Action buckets derived in Python, not by AI (zero marginal cost)
- Confidence thresholds prevent AI fatigue
- Budget: ~$16/month for 30K emails
```

---

## Appendix C: All Files Created/Modified

### New Files (Sprint 3)

**Backend Services (8 new):**
```
backend/src/services/ai_client.py
backend/src/services/ai_usage_tracker.py
backend/src/services/ai_privacy_filter.py
backend/src/services/ai_email_analyzer.py
backend/src/services/ai_action_bucket_engine.py
backend/src/services/ai_entity_aggregator.py
backend/src/services/ai_digest_generator.py
backend/src/services/ai_relationship_summarizer.py
```

**Backend Router (1 new):**
```
backend/src/routers/ai.py              -- 15 endpoints
```

**Frontend Pages (4 new):**
```
frontend/src/pages/ai/digest.tsx
frontend/src/pages/ai/inbox.tsx
frontend/src/pages/ai/opportunities.tsx
frontend/src/pages/ai/usage.tsx
```

**Frontend Components (2 new):**
```
frontend/src/components/ai/ActionBucketTag.tsx
frontend/src/components/ai/FeedbackButtons.tsx
```

**Frontend Services (1 new):**
```
frontend/src/services/aiService.ts
```

**Database (1 new):**
```
scripts/sprint2/sprint2_migration_013_ai_layer.sql  -- 5 tables
```

**Scripts (1 new):**
```
scripts/test_ai_pipeline.py
```

### Modified Files

```
backend/src/routers/analytics.py       -- +2 endpoints (AM comparison, gap alerts)
backend/src/main.py                    -- Register ai router
backend/.env.example                   -- +ANTHROPIC_API_KEY
frontend/src/pages/analytics/company-detail.tsx  -- +AI intelligence cards
frontend/src/pages/analytics/dashboard.tsx       -- +gap alerts, AM comparison
frontend/src/pages/dashboard.tsx                 -- +Quick Insights card
frontend/src/components/Layout.tsx               -- +AI Intelligence sidebar
docs/CLAUDE.md                         -- +Sprint 3 section
docs/CONTINUATION_GUIDE.md             -- +Sprint 3 status
docs/TODO.md                           -- Check off completed items
docs/CHANGELOG.md                      -- Sprint 3 entry
```

---

## Appendix D: Multi-Axis Classification Design (v3.2)

### Why Multi-Axis Instead of Single Label

v3.1 classified each email with a single `intent` from 13 options. This loses information:

```
Email: "We're comparing your pricing with Competitor X before our Q3 budget meeting"

v3.1 output:
  intent = "pricing_inquiry"           ← All you know

v3.2 output:
  intent          = "pricing_inquiry"  ← What they're asking about
  action_type     = "provide_quote"    ← What YOU need to do
  business_signal = "competitive_evaluation"  ← CRM-relevant signal
  thread_role     = "initial"          ← First contact (high priority)
  ← Now the bucket engine knows: buying_signal + competitor_threat + high priority
```

### The 3 Axes Added (and Why These Specifically)

**1. `action_type`** (10 values) — Answers "what do I do next?"
Transforms vague `suggested_action` free text into a structured, filterable enum.
AMs can filter inbox by "needs quote" vs "needs meeting" vs "no action needed."

**2. `business_signal`** (11 values) — Answers "what does this mean for the deal?"
Separate from `intent` because one email can have intent="question" but
signal="buying_intent." The bucket engine uses this for much more precise
buying/churn/expansion detection.

**3. `thread_role`** (6 values) — Answers "where does this email sit in the conversation?"
Critical for filtering: auto-replies should never trigger action buckets.
Initial outreach emails are higher priority than mid-thread replies.
CC additions can signal stakeholder entry.

### What We Deliberately Did NOT Add

| Dimension | Why Skipped |
|-----------|------------|
| Communication Source (customer/prospect/vendor) | Sprint 2 already knows this from email domain → company → relationship type |
| Contact Role (decision maker, influencer) | Sprint 2's `seniority_level` on customer_contacts handles this |
| Event Type (meeting request, invoice) | Overlaps with intent — "meeting_scheduling" already captures this |
| Priority (separate from urgency) | Already have 5-level `urgency` field |
| Tone sub-categories (formal, sarcastic) | Unreliable with Haiku at batch scale. 5-level sentiment is sufficient |
| 30 intent sub-types | More options = lower accuracy. 13 intents is the sweet spot |
| Custom/company tags | Requires admin config UI. Phase 2 feature |

### Cost of Multi-Axis

3 new single-value enum fields = ~8 extra output tokens per email.
At Haiku rates ($4/MTok output): $0.000032/email.
At 30K emails/month: +$0.96/month. Negligible for the intelligence gained.

