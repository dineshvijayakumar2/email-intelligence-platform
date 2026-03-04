# Sprint 3: AI Semantic Intelligence — Implementation Plan

## Context

**Problem:** The platform processes 26K+ emails through a 13-step extraction pipeline producing contacts, companies, engagement scores, threads, and communication patterns — all rule-based. Users see *data* but not *intelligence*. They can't answer: "Which accounts are about to churn?", "Where are buying signals?", or "What needs my attention today?"

**Goal:** Transform from a data dashboard into an intelligence platform by adding a three-layer AI system that classifies emails, detects business signals, derives action buckets, and presents action-oriented insights — all while keeping costs under $16/month for 30K emails.

**Starting point:** Sprint 2 fully complete. 13-step pipeline, 30 analytics endpoints, 8 analytics pages, admin data view — all production-tested.

---

## Architecture: Three-Layer Intelligence Model

```
Layer 1: Per-Email AI (Claude Haiku, ~$0.001/email)
  ai_email_analyzer.py → ai_email_intelligence table
  ONE API call per batch: classify + extract entities + justify + multi-axis

Layer 2: Action Bucket Engine (Pure Python, $0 cost)
  ai_action_bucket_engine.py → action_buckets in ai_email_intelligence
  8 buckets derived from AI results + Sprint 2 engagement/thread/seniority data

Layer 3: Action-First Presentation (Frontend)
  Confidence thresholds: >=0.8 full tag, 0.5-0.8 "Review" tag, <0.5 hidden
  Human feedback: thumbs up/down on every classification
```

### Key Architectural Decisions

1. **Official `anthropic` Python SDK** — handles retries, rate limiting, typed responses. Cleaner than hand-rolling HTTP calls.
2. **AI is a separate trigger, NOT part of the 13-step extraction pipeline** — AI has per-email cost, users trigger explicitly. Extraction pipeline stays untouched.
3. **No modifications to existing Sprint 2 services** — AI reads from Sprint 2 tables but writes exclusively to new `ai_*` tables. Zero risk of breaking production.
4. **New `scripts/sprint3/` directory** for migrations — clean separation.
5. **Route prefix: `/api/v1/ai/`** (backend) and **`/intelligence/`** (frontend routes).

### Prompt Design Principles (All 3 Prompts)

- **Output = pure JSON** — no markdown, no explanation, no extra keys
- **Explicit enum values** — every allowed value listed in the prompt
- **Null over guessing** — "return null if uncertain" reduces hallucination ~20-30%
- **Nested entities** — `entities: {competitors, budget_signal, ...}` prevents flat field chaos
- **Short summaries** — reduces output tokens and cost
- **Explicit anti-hallucination** — "Do not hallucinate competitors/budgets"
- **No business logic in prompts** — LLM classifies, Python computes scores and buckets
- **Concise instructions** — more tokens in prompt does NOT mean better accuracy
- **Guard layer** — `clean_llm_output()` strips markdown fences before JSON parse, then Pydantic validates

### Production Engineering Principles (Embedded Throughout)

These are woven into every session — not bolted on after:

- **Strict schema enforcement** — Pydantic validation of every LLM response. Retry once on validation failure, then reject. Never insert partial data.
- **Idempotent processing** — `processing_status` field (pending/processing/completed/failed), safe to re-run.
- **Version everything** — `prompt_version`, `scoring_version`, `bucket_engine_version` stored per row for full traceability.
- **Store raw AI output** — `raw_ai_response JSONB` for debugging, prompt iteration, compliance.
- **Graceful degradation** — If Claude API is down, emails keep flowing, intelligence marked pending, UI doesn't crash.
- **Per-item batch resilience** — One malformed email never kills a batch. Fail per-item, log, continue.
- **Deterministic post-processing** — All business logic in Python, never inside LLM prompts.
- **Confidence gating** — Prevents AI fatigue and builds user trust.
- **Structured feedback** — Store *what* was wrong (intent/bucket/sentiment) + correct value, not just "incorrect".
- **Monitoring** — Track failure rates, parse errors, cost spikes, bucket distribution drift.

---

## Implementation Sessions (13 Sessions, Backend-First)

### Session 1: Database Migration + AI Infrastructure (5h)
**Goal:** Create all AI tables and foundational services

#### Database — `scripts/sprint3/sprint3_migration_013_ai_layer.sql`

5 tables with indexes, triggers, RLS grants. Based on v3.2 plan schema WITH these production additions:

**`ai_email_intelligence`** — additional columns beyond v3.2:
```sql
-- IDEMPOTENT PROCESSING (safe re-runs)
processing_status TEXT DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
processed_at TIMESTAMPTZ,
error_message TEXT,                    -- Why it failed (if failed)

-- VERSION TRACKING (full traceability)
prompt_version TEXT,                   -- e.g., 'v1.0', 'v1.1' — know which prompt produced this
scoring_version TEXT,                  -- business_signal_score algorithm version
bucket_engine_version TEXT,            -- bucket derivation logic version

-- RAW AI OUTPUT (debugging + compliance)
raw_ai_response JSONB,                -- Full Claude response, never modified
```

**`ai_usage_log`** — additional columns:
```sql
error_type TEXT,                       -- 'json_parse', 'validation', 'api_timeout', 'rate_limit'
retry_count INTEGER DEFAULT 0,
success BOOLEAN DEFAULT TRUE,
prompt_version TEXT,
```

**`ai_email_intelligence` feedback columns** — enhanced:
```sql
-- STRUCTURED FEEDBACK (know what was wrong)
human_feedback TEXT CHECK (human_feedback IN ('correct', 'incorrect')),
feedback_field TEXT,                   -- Which field was wrong: 'intent', 'bucket', 'sentiment', 'urgency'
human_override_intent TEXT,
human_override_bucket TEXT,
human_override_sentiment TEXT,
feedback_note TEXT,                    -- Free-text user explanation
feedback_at TIMESTAMPTZ,
feedback_by UUID,
```

All 5 tables + indexes as defined in v3.2 plan (lines 111-331 of `docs/AI_MVP_PLAN_v3.2_DEFINITIVE.md`), with additions above.

#### Backend Services

1. **`backend/src/services/ai_client.py`** — Shared Claude API wrapper
   - Uses `anthropic` Python SDK
   - Two model configs: Haiku (email intelligence) and Sonnet (digests/summaries)
   - `call_haiku(system_prompt, user_message)` → `{content, input_tokens, output_tokens, model, raw_response}`
   - `call_sonnet(system_prompt, user_message)` → same structure
   - Cost calculation helper (Haiku: $0.80/$4 per MTok, Sonnet: $3/$15 per MTok)
   - Rate limiting: 10 req/sec max via `time.sleep()` between calls
   - Retry: 3 attempts with exponential backoff (matching `_execute_with_retry()` pattern)
   - **Graceful degradation**: on API failure after retries → return `None`, caller marks row as `failed`

2. **`backend/src/services/ai_privacy_filter.py`** — Sanitize before AI
   - `sanitize_email_body(body: str) -> str`
   - Strip: credit card patterns, SSN, API keys (32+ char alphanumeric), password patterns
   - **Extended**: Strip OAuth tokens, JWT-like strings (`eyJ...`), Bearer tokens
   - **Extended**: Strip email signatures (detect `--` separator, strip everything after)
   - Keep: names, titles, company info (useful for entity extraction)
   - Truncate to 500 chars after sanitization

3. **`backend/src/services/ai_usage_tracker.py`** — Cost tracking
   - `log_usage(operation, model, mailbox_id, client_id, input_tokens, output_tokens, processing_time_ms, batch_size, success, error_type, retry_count, prompt_version)`
   - `get_usage_summary(client_id, date_range)` → total_cost, by_operation, by_model, failure_rate, avg_latency
   - `get_monitoring_stats(client_id)` → parse_failure_rate, api_failure_rate, avg_retry_count, cost_per_1000_emails

#### Config Changes
- Add `ANTHROPIC_API_KEY` to `backend/.env.example`
- Add `anthropic` to `backend/requirements.txt`

**Exit criteria:** Migration runs cleanly, 5 tables created with all production columns. `ai_client.py` makes a test Haiku call. Privacy filter strips extended patterns. Usage tracker writes to `ai_usage_log` with error tracking fields.

---

### Session 2: Email Analyzer — The Core Intelligence Engine (6h)
**Goal:** Build the unified email classification + entity extraction service with strict validation and production-grade prompts

#### Create `backend/src/services/ai_email_analyzer.py`

**Constants at module level:**
```python
PROMPT_VERSION = "v1.0"
SCORING_VERSION = "v1.0"
BATCH_SIZE = 10  # emails per Claude call
```

#### Production-Grade Prompt Templates

**SYSTEM PROMPT (stored as constant):**
```
You are a structured email intelligence engine for a B2B account management platform.

Your task is to analyze business emails and return STRICT JSON.

You must:
- Follow the schema exactly.
- Use only the allowed enum values.
- Return null if uncertain.
- Never invent entities.
- Never guess missing data.
- Never include markdown.
- Never include explanations.
- Return only a valid JSON array.

If the email does not contain enough information for a field, return null or an empty array.
Do not add fields not defined in the schema.
```

**USER PROMPT TEMPLATE (formatted per batch):**
```
Analyze the following emails.
For each email, return one JSON object with the following schema:

{
  "email_id": string,
  "intent": one of ["action_required", "fyi_update", "meeting_scheduling", "question",
    "complaint", "positive_feedback", "pricing_inquiry", "feature_request",
    "expansion_signal", "churn_risk", "follow_up", "introduction", "other"],
  "urgency": one of ["critical", "high", "medium", "low", "none"],
  "sentiment": one of ["very_positive", "positive", "neutral", "negative", "very_negative"],
  "sentiment_score": number between -1.0 and 1.0,
  "action_type": one of ["respond_to_inquiry", "provide_quote", "schedule_meeting",
    "escalate_internally", "send_follow_up", "resolve_issue", "acknowledge_receipt",
    "no_action", "delegate", "prepare_document"],
  "business_signal": one of ["buying_intent", "renewal_intent", "expansion_interest",
    "churn_signal", "competitive_evaluation", "budget_discussion", "escalation",
    "positive_feedback", "negative_feedback", "contract_activity", "neutral"] or null,
  "thread_role": one of ["initial", "reply", "forward", "auto_reply",
    "cc_addition", "internal"] or null,
  "summary": short 1-2 sentence factual summary,
  "suggested_action": one short sentence describing what the account manager should do,
  "key_topics": array of 1-3 short strings,
  "confidence": number between 0.0 and 1.0,
  "justification": one short sentence referencing specific words or phrases from the
    email that justify the intent and urgency,
  "entities": {
    "competitors_mentioned": array of company names,
    "products_mentioned": array of product/service names,
    "budget_signal": {"amount": string or null, "timeframe": string or null,
      "context": string or null} or null,
    "buying_signals": array of short phrases from the email indicating buying intent,
    "people_mentioned": [{"name": string, "role": string or null, "context": string}],
    "dates_mentioned": [{"date": string, "context": string}],
    "action_items_extracted": array of short action items explicitly mentioned
  }
}

Rules:
- Do not hallucinate competitors.
- Do not hallucinate budget amounts.
- Only extract information explicitly present.
- If no entities exist, return empty arrays.
- If no budget signal exists, return null.

EMAILS:
{emails_json}

Return ONLY a JSON array in the same order as input.
```

**Note on multi-axis fields:** `action_type`, `business_signal`, and `thread_role` are included in the prompt (from v3.2 design) because the bucket engine depends on them for precise derivation. Added ~8 extra tokens/email (~$0.000032/email).

#### Strict JSON Guard Layer (before Pydantic validation)

```python
def clean_llm_output(text: str) -> str:
    """Strip markdown fences and whitespace before JSON parsing."""
    text = text.strip()
    if text.startswith("```"):
        # Extract content between first and second ```
        parts = text.split("```")
        text = parts[1] if len(parts) >= 2 else text
        # Remove optional language tag (e.g., "json")
        if text.startswith("json"):
            text = text[4:]
    return text.strip()
```

#### Pydantic Validation Models (strict, per-item)

```python
class EntityExtraction(BaseModel):
    competitors_mentioned: list[str] = []
    products_mentioned: list[str] = []
    budget_signal: Optional[dict] = None  # {amount, timeframe, context}
    buying_signals: list[str] = []
    people_mentioned: list[dict] = []     # [{name, role, context}]
    dates_mentioned: list[dict] = []      # [{date, context}]
    action_items_extracted: list[str] = []

class EmailClassificationResult(BaseModel):
    """Validates each email's AI output. LLM response MUST match this exactly."""
    email_id: str
    intent: Literal["action_required", "fyi_update", "meeting_scheduling", "question",
                     "complaint", "positive_feedback", "pricing_inquiry", "feature_request",
                     "expansion_signal", "churn_risk", "follow_up", "introduction", "other"]
    urgency: Literal["critical", "high", "medium", "low", "none"]
    sentiment: Literal["very_positive", "positive", "neutral", "negative", "very_negative"]
    sentiment_score: confloat(ge=-1.0, le=1.0)
    action_type: Literal["respond_to_inquiry", "provide_quote", "schedule_meeting",
                          "escalate_internally", "send_follow_up", "resolve_issue",
                          "acknowledge_receipt", "no_action", "delegate", "prepare_document"]
    business_signal: Optional[Literal["buying_intent", "renewal_intent", "expansion_interest",
                                       "churn_signal", "competitive_evaluation", "budget_discussion",
                                       "escalation", "positive_feedback", "negative_feedback",
                                       "contract_activity", "neutral"]] = None
    thread_role: Optional[Literal["initial", "reply", "forward", "auto_reply",
                                   "cc_addition", "internal"]] = None
    summary: constr(max_length=500)
    suggested_action: constr(max_length=300)
    key_topics: list[str]
    confidence: confloat(ge=0.0, le=1.0)
    justification: str
    entities: EntityExtraction = EntityExtraction()
```

#### Processing Flow

**`analyze_batch(mailbox_id, client_id, batch_size=20)`:**
1. Query unanalyzed emails (WHERE NOT EXISTS in ai_email_intelligence, or processing_status = 'pending')
2. Mark batch as `processing_status = 'processing'`
3. Sanitize with `ai_privacy_filter.sanitize_email_body()`
4. Send 10 emails per Claude Haiku call
5. **Parse + validate per item:**
   - `clean_llm_output()` → strip markdown fences
   - `json.loads()` → parse JSON array
   - Per item: `EmailClassificationResult.model_validate()` → Pydantic strict validation
   - On validation fail for an item: **retry once** with just that item
   - If still fails: mark email as `failed`, log `error_type='validation'`, continue
   - **Never insert partial/invalid data**
6. Store `raw_ai_response` JSONB on every row (success or fail)
7. Post-process valid results (all in Python, never in prompts):
   - Set boolean flags from `entities`: `has_budget_signal = entities.budget_signal is not None`, etc.
   - Skip auto-replies (`thread_role == 'auto_reply'`) for bucket assignment
   - Compute `business_signal_score` (0-100) from weighted flags
   - Derive email buckets via bucket engine
   - Set `primary_bucket`
8. Insert into `ai_email_intelligence` with `processing_status='completed'`, `prompt_version`, `scoring_version`
9. Log usage (including error_type, retry_count, success flag)

**`analyze_all_unanalyzed(mailbox_id, client_id)`:**
- Loop batches until done
- After completion: entity aggregation → relationship bucket computation
- Return `{total_analyzed, total_failed, entities_found, buckets_assigned}`

**`get_intelligence(mailbox_id, filters)`:**
- Filterable by: intent, urgency, sentiment, primary_bucket, action_type, business_signal, has_*_signal, min_confidence, date_range, processing_status
- Join with emails for subject, sender
- Paginated, sortable

**Graceful degradation**: If Claude API is completely down, all emails in batch marked `failed` with `error_type='api_unavailable'`. Can be re-processed later. UI shows "Analysis pending" instead of crashing.

**Exit criteria:** Analyze 50 test emails → rows have classification + nested entities + raw_ai_response + prompt_version. Pydantic rejects invalid items. Failed items logged separately. Auto-replies have empty action_buckets. Re-running is safe (idempotent).

---

### Session 3: Action Bucket Engine (5h)
**Goal:** Zero-cost intelligence amplifier — pure Python rules

#### Create `backend/src/services/ai_action_bucket_engine.py`

**Module-level constants:**
```python
BUCKET_ENGINE_VERSION = "v1.0"

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

**`derive_email_buckets(intel_row)`** — per-email, called during post-processing
**`compute_relationship_buckets(client_id, mailbox_id)`** — reads Sprint 2 tables (no modifications)
**`get_action_items(client_id, min_confidence=0.5)`** — prioritized list
**`get_bucket_summary(client_id)`** — {bucket: count}

All bucket assignments store `bucket_engine_version` for traceability.

**Exit criteria:** Bucket derivation produces both email-level and relationship-level buckets. Summary returns non-zero counts. Version tracked.

---

### Session 4: Entity Aggregator + AI API Router + Pydantic Models (6h)
**Goal:** Entity roll-up + all 15+ API endpoints + response models

#### Create `backend/src/services/ai_entity_aggregator.py`
- `aggregate_entities()` — roll up from ai_email_intelligence → ai_business_entities
- `get_entities()`, `get_competitor_landscape()`, `get_opportunity_signals()`

#### Create `backend/src/models/ai.py` — Pydantic request/response models
- Follow `analytics.py` patterns (enums + typed models)
- Include models for: intelligence results, bucket items, entities, feedback, digest, summaries, usage stats

#### Create `backend/src/routers/ai.py` — 15 endpoints
- Pattern: global `_supabase`, `init_ai_router(supabase_client)` function
- Router prefix: `/ai`, tags: `["ai-intelligence"]`

**Endpoints:**
```
# Intelligence (3)
POST /ai/analyze/{mailbox_id}              — trigger analysis (BackgroundTasks)
GET  /ai/intelligence/{mailbox_id}          — list results (paginated, filterable)
GET  /ai/intelligence/stats/{mailbox_id}    — stats breakdown

# Action Buckets (2)
GET  /ai/action-items/{client_id}           — prioritized bucket list
GET  /ai/action-items/{client_id}/summary   — bucket counts

# Human Feedback (1) — structured feedback
POST /ai/intelligence/{email_id}/feedback   — {feedback, feedback_field, override_intent, override_bucket, override_sentiment, note}

# Entities (3)
GET  /ai/entities/{client_id}
GET  /ai/entities/{client_id}/competitors
GET  /ai/entities/{client_id}/opportunities

# (Digest + Relationship + Usage endpoints added in Sessions 5, 8, 11)
```

#### Register in `backend/main.py`
```python
from src.routers.ai import router as ai_router, init_ai_router
init_ai_router(supabase)
app.include_router(ai_router, prefix="/api/v1")
```

**Exit criteria:** All 9 initial endpoints return valid responses. POST analyze triggers background analysis. Feedback stores structured override data.

---

### Session 5: Digest Generator (5h)
**Goal:** Daily digest with bucket-aware language

#### Create `backend/src/services/ai_digest_generator.py`

**SYSTEM PROMPT:**
```
You are an executive assistant generating a concise daily email intelligence briefing.

Be action-oriented, prioritized, and factual.
Do not exaggerate.
Do not invent missing data.
Return STRICT JSON only.
```

**USER PROMPT TEMPLATE:**
```
Generate a daily email intelligence digest.

CONTEXT:
- Emails received: {in_count}
- Emails sent: {out_count}
- Open threads: {open_threads}
- Overdue threads: {overdue_threads}
- Bucket summary: {bucket_summary_json}

BUSINESS SIGNAL EMAILS:
{top_signal_emails_json}

RECENT HIGH PRIORITY EMAILS:
{priority_emails_json}

Return JSON with this schema:

{
  "summary": 2-3 concise sentences prioritizing the most critical buckets first,
  "action_items": [
    {"email_id": string, "priority": integer 1-5, "bucket": string or null,
     "action": short action sentence, "contact_name": string or null}
  ],
  "highlights": [
    {"type": string, "description": short factual description, "email_id": string or null}
  ]
}

Rules:
- Prioritize churn_risk and buying_signal first.
- Do not exceed 3 sentences in summary.
- Do not repeat raw email text.
- Do not include markdown.
- Return JSON only.
```

**Methods:**
- `generate_digest(mailbox_id, client_id, date)` — Sonnet call, store `raw_ai_response`, validate with Pydantic
- `get_digest(mailbox_id, date)` — cache-first
- `get_digest_or_generate(mailbox_id, client_id, date)`
- Compute `bucket_summary` from action bucket engine (Python-side, not in prompt)

**Add 2 endpoints to router:**
- GET `/ai/digest/{mailbox_id}?date=YYYY-MM-DD`
- GET `/ai/digest/{mailbox_id}/history`

**Exit criteria:** Digest generated with bucket-prioritized summary. Pydantic validates response. Cache works. History returns past digests.

---

### Session 6: Frontend Service + Shared Components + Smart Inbox (6h)
**Goal:** Frontend service layer and primary intelligence inbox page

#### Create `frontend/src/services/aiService.ts`
- Follow `analyticsService.ts` pattern: TTL cache, in-flight dedup, error fallbacks
- API prefix: `/v1/ai`

#### Create `frontend/src/types/ai.ts`
- TypeScript interfaces mirroring `backend/src/models/ai.py`

#### Create shared components
- `frontend/src/components/ai/ActionBucketTag.tsx` — confidence-based colored tag with justification tooltip
- `frontend/src/components/ai/FeedbackButtons.tsx` — thumbs up/down with structured override (what field was wrong + correct value)

#### Create `frontend/src/pages/intelligence/inbox.tsx`
- Mailbox selector + "Analyze New Emails" button
- Filter bar: bucket chips, intent/urgency/sentiment dropdowns, confidence slider (`onChangeComplete`)
- Table with bucket tags, urgency, subject, sender, sentiment, summary, date
- Detail drawer: classification, multi-axis badges, entities, suggested action, raw AI justification, feedback
- **All business logic server-side** — frontend only displays structured output + applies confidence thresholds

#### Register in `frontend/src/App.tsx`
- Add `/intelligence/*` routes with `<ProtectedRoute>`

#### Update `frontend/src/components/layout.tsx`
- Add "Intelligence" menu section: Inbox, Digest, Opportunities, Usage (admin only)
- Add page titles for all new routes

**Exit criteria:** Inbox loads, displays analyzed emails with bucket tags, drawer shows full intelligence, feedback submits structured data.

---

### Session 7: Digest Frontend Page (5h)
**Goal:** Daily digest page with bucket summary bar

#### Create `frontend/src/pages/intelligence/digest.tsx`
- Date selector + mailbox selector
- Bucket summary bar (clickable badges)
- Hero digest summary
- Business signals cards, action items with bucket tags, key threads, stats row

**Exit criteria:** Digest page renders with real data, bucket bar interactive, action items link to inbox.

---

### Session 8: Relationship Summary Service + Company Detail (6h)
**Goal:** AI relationship summaries + company page enhancement

#### Create `backend/src/services/ai_relationship_summarizer.py`

**SYSTEM PROMPT:**
```
You are a CRM intelligence analyst generating executive-level relationship summaries.

Be concise, analytical, and factual.
Use the provided data only.
Return STRICT JSON only.
```

**USER PROMPT TEMPLATE:**
```
Generate a relationship intelligence summary.

COMPANY: {company_name}

METRICS:
- Engagement score: {score}
- Response time: {response_time}
- Email frequency: {frequency}
- Open threads: {open_threads}

CONTACTS: {contacts_with_roles}

ACTIVE BUCKETS: {bucket_counts}

RECENT INTENTS: {intent_distribution}

BUSINESS SIGNALS: {business_signals_summary}

Return JSON:
{
  "summary": 3 concise analytical sentences,
  "risk_factors": array of short phrases,
  "opportunities": array of short phrases,
  "recommended_actions": array of short action steps
}

Rules:
- Reference active buckets in summary if present.
- Do not invent data.
- Do not exceed 3 sentences in summary.
- Return JSON only.
```

**Methods:**
- `generate_summary()` — Sonnet call, Pydantic validate, store `raw_ai_response`, `active_buckets`, cache 7 days
- `get_summary()`, `bulk_generate()`

#### Add 3 endpoints to `backend/src/routers/ai.py`
- POST/GET `/ai/relationship-summary/{company_id}`
- POST `/ai/relationship-summaries/bulk/{client_id}`

#### Enhance `frontend/src/pages/analytics/company-detail.tsx`
- ADD "Relationship Intelligence" card: summary, bucket tags, themes, risks/opportunities, actions, refresh
- ADD "Business Signals" card: competitors, buying signals, budgets, deadlines
- Fallback: "Generate AI Summary" button when no data

**Exit criteria:** Company detail shows AI cards. Generate/refresh works. Bucket tags styled by confidence.

---

### Session 9: Opportunities Page (5h)
**Goal:** Business signal discovery with 5 tabs

#### Create `frontend/src/pages/intelligence/opportunities.tsx`
- Tab 1: Action Items (prioritized buckets)
- Tab 2: Active Opportunities (business_signal_score > 0)
- Tab 3: Competitor Intelligence (entity type=competitor, mentions >= 2)
- Tab 4: Budget Discussions (has_budget_signal)
- Tab 5: Entity Tracker (all entities)

**Exit criteria:** All 5 tabs render with real data. Sorting and filtering work.

---

### Session 10: AM Comparison + Gap Alerts (6h)
**Goal:** Business owner views enriched with AI intelligence

#### Backend — Add to `backend/src/routers/analytics.py` (2 endpoints)
- GET `/analytics/account-manager-comparison/{client_id}` — per-mailbox stats + AI metrics
- GET `/analytics/communication-gaps/{client_id}` — 8 alert types with bucket visual consistency

#### Frontend — Enhance `frontend/src/pages/analytics/dashboard.tsx`
- "Gap Alerts" card with ActionBucketTag, top 10, "View All"
- AM comparison table + bar charts (admin/client_manager only)

**Exit criteria:** Gap alerts show bucket-enriched warnings. AM comparison includes AI metrics.

---

### Session 11: Usage Page + Cross-Linking + Dashboard + Monitoring (5h)
**Goal:** Wire full experience, add monitoring dashboard

#### Create `frontend/src/pages/intelligence/usage.tsx` (admin only)
- Month total cost (big number)
- Bucket impact summary
- Cost by operation (pie), cost trend (line, 30 days), cost per mailbox (table)
- Feedback stats: accuracy rate from user confirmations
- **Monitoring panel**: parse failure rate, API failure rate, avg retry count, bucket distribution (detect drift)

#### Backend — Add to `backend/src/routers/ai.py`
- GET `/ai/usage/costs` → total_cost, by_operation, by_model, by_day, by_mailbox, feedback_stats
- GET `/ai/usage/monitoring` → failure_rates, parse_errors, distribution_stats, cost_per_1000

#### Dashboard — Enhance `frontend/src/pages/dashboard.tsx`
- "Quick Insights" card: bucket summary bar, digest excerpt, gap alert count

#### Cross-linking
- Digest action items → `/intelligence/inbox`
- Opportunity signals → company detail
- Gap alerts → company detail
- Company detail "View signals" → `/intelligence/inbox?company={id}`

**Exit criteria:** All pages connected. Dashboard shows Quick Insights. Usage page shows cost + monitoring data. Cross-links work.

---

### Session 12: Integration Testing + Evaluation Dataset (4h)
**Goal:** End-to-end verification + baseline accuracy measurement

#### Create `scripts/test_ai_pipeline.py`
- Trigger analysis on 50 emails
- Verify: classification, entities, raw_ai_response, prompt_version, processing_status
- Verify: auto-replies have empty action_buckets
- Verify: failed items logged with error_type
- Verify: entity aggregation in ai_business_entities
- Verify: bucket engine produces email + relationship buckets
- Generate digest → verify bucket language
- Generate relationship summary → verify active_buckets
- Submit structured feedback → verify fields stored
- Check ai_usage_log → cost, error tracking, retry counts
- Test all 17+ API endpoints → 200 OK
- **Idempotency check**: re-run analysis → no duplicates, failed items retried
- Print: emails analyzed, failed, bucket counts, entity counts, total cost, failure rate

#### Create `scripts/sprint3/evaluation_dataset.py`
- Select 100-200 diverse emails (mix of intents, urgencies, companies)
- Run AI analysis on them
- Export results as CSV for manual review
- Track: precision of churn/buying signal buckets, false positive rate
- This becomes the baseline for prompt tuning

**Exit criteria:** Test script passes. All endpoints respond. Idempotent re-run safe. Evaluation dataset exported.

---

### Session 13: Production Deploy + Documentation (3h)
**Goal:** Deploy to Railway, update all docs

**Deployment checklist:**
- Set `ANTHROPIC_API_KEY` in Railway
- Run Migration 013 on production Supabase
- Verify 5 tables + indexes + RLS
- Run `test_ai_pipeline.py` on 50 production emails
- Verify all endpoints (200 OK)
- Verify all frontend pages load
- Check monitoring dashboard for healthy metrics

**Documentation:**
- `docs/CLAUDE.md` — Sprint 3 section
- `docs/CONTINUATION_GUIDE.md` — Sprint 3 complete status
- `docs/TODO.md` — Check off items

---

## Complete File Manifest

### New Files (20)

**Backend Services (8):**
- `backend/src/services/ai_client.py`
- `backend/src/services/ai_usage_tracker.py`
- `backend/src/services/ai_privacy_filter.py`
- `backend/src/services/ai_email_analyzer.py`
- `backend/src/services/ai_action_bucket_engine.py`
- `backend/src/services/ai_entity_aggregator.py`
- `backend/src/services/ai_digest_generator.py`
- `backend/src/services/ai_relationship_summarizer.py`

**Backend Router + Models (2):**
- `backend/src/routers/ai.py` (17+ endpoints)
- `backend/src/models/ai.py`

**Frontend Pages (4):**
- `frontend/src/pages/intelligence/inbox.tsx`
- `frontend/src/pages/intelligence/digest.tsx`
- `frontend/src/pages/intelligence/opportunities.tsx`
- `frontend/src/pages/intelligence/usage.tsx`

**Frontend Components (2):**
- `frontend/src/components/ai/ActionBucketTag.tsx`
- `frontend/src/components/ai/FeedbackButtons.tsx`

**Frontend Service + Types (2):**
- `frontend/src/services/aiService.ts`
- `frontend/src/types/ai.ts`

**Database (1):**
- `scripts/sprint3/sprint3_migration_013_ai_layer.sql`

**Scripts (2):**
- `scripts/test_ai_pipeline.py`
- `scripts/sprint3/evaluation_dataset.py`

### Modified Files (9)
- `backend/main.py` — Import + register ai_router
- `backend/requirements.txt` — Add `anthropic`
- `backend/.env.example` — Add `ANTHROPIC_API_KEY`
- `backend/src/routers/analytics.py` — +2 endpoints (AM comparison, gap alerts)
- `frontend/src/App.tsx` — Add `/intelligence/*` routes
- `frontend/src/components/layout.tsx` — Add Intelligence sidebar + page titles
- `frontend/src/pages/analytics/company-detail.tsx` — AI intelligence cards
- `frontend/src/pages/analytics/dashboard.tsx` — Gap alerts + AM comparison
- `frontend/src/pages/dashboard.tsx` — Quick Insights card

---

## Critical Patterns (MUST follow in all new code)

### Supabase
1. **NULL handling:** `neq('col', 'val')` excludes NULLs — use Python-side filtering
2. **Pagination:** `offset += len(batch)`, break on `len(batch) == 0`
3. **Booleans:** Lowercase `'true'`/`'false'` strings
4. **No .or_():** Use Python-side filtering
5. **Batch limits:** 100/update, 500 IDs per `.in_()`
6. **Retry:** `_execute_with_retry()` for SSL 525, 502-504
7. **Float params:** Cast to `int()` before `.gte()` on INTEGER columns

### AI-Specific
8. **Validate every LLM response** with Pydantic before inserting
9. **Store raw_ai_response** on every row
10. **Track versions** (prompt, scoring, bucket engine) on every row
11. **Per-item failure** — one bad email never kills the batch
12. **Graceful degradation** — AI down = pending status, not crash
13. **No business logic in prompts** — LLM classifies, Python decides
14. **Frontend displays only** — no AI interpretation client-side

---

## Verification Plan

**Per-session:** Backend → curl/httpie test + DB verification. Frontend → page load + console check.

**End-to-end (Session 12):**
1. Analyze 50 emails → ai_email_intelligence with all fields + raw_ai_response
2. Verify failed items: error_type, processing_status='failed'
3. Re-run analysis → idempotent (no duplicates, failed items retried)
4. Bucket engine → email-level + relationship-level buckets
5. Digest → bucket summary language
6. Relationship summary → active_buckets
7. Structured feedback → feedback_field + override stored
8. Usage log → cost + error_type + retry_count
9. Monitoring → failure rates, distribution stats
10. All 17+ endpoints → 200 OK
11. All frontend pages → no console errors
12. Cross-links → correct navigation
13. Evaluation dataset → baseline accuracy exported
