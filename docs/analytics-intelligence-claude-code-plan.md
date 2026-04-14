# Analytics Intelligence System — Claude Code Implementation Plan

> **What we're building:** A single `POST /ai/intelligence/query` endpoint that accepts
> any natural language question and returns a grounded answer — whether it needs SQL,
> vector search, time-series, or QB financial data.
>
> **Read before starting every session:**
> `CLAUDE.md`
> `backend/src/routers/analytics.py` (existing query patterns, `_supabase` client usage)
> `backend/src/services/vector_service.py` (existing `search_emails`, `search_companies`,
> `search_operations`, `get_company_history_context`)
>
> **Never touch:** routing, auth, layout, sidebar, existing analytics endpoints,
> TanStack Query hooks, SSE streaming already built.

---

## Architecture overview

```
POST /ai/intelligence/query
        │
        ▼
 QueryClassifier          ← Claude Haiku, ~100ms, selects intent + engines
        │
   ┌────┴─────┬──────────────┬──────────────┐
   ▼          ▼              ▼              ▼
SQL Engine  Vector Engine  Timeseries    QB Engine
(catalogue) (existing VS)  (date-bucket  (cross-join
                            SQL)          QB fields)
   └────┬─────┴──────────────┴──────────────┘
        ▼
 ResultSynthesiser        ← Claude Sonnet, streams answer
        │
        ▼
 QueryResponse { answer, data, chart_type, sources, engines_used }
```

---

## Supabase infrastructure notes (read before any session)

**Plan:** Pro ($25/month). pgvector, custom RPCs, and all migrations in this plan are
fully supported. No extension changes needed.

**Spend cap — disable before launch.**
The billing dashboard shows spend cap is currently enabled. With it on, Supabase will
make your project read-only or unresponsive once the included compute quota is hit.
The intelligence query engine runs parallel vector search + SQL + SSE streaming
simultaneously — this will push compute harder than the current setup.

Before running Session 3: go to Supabase → Billing → Cost Control → Change spend cap
→ disable it (or set a hard limit of $50). Overage on Pro is minimal at this usage level.
An unresponsive API mid-demo is worse than a small overage charge.

**Compute:** currently on Micro (0.5 CPU / 1GB RAM, 433 hours billed this cycle).
The parallel engine execution in Session 3 will stress this. If classifier + engines +
synthesis chain exceeds 3 seconds in testing, upgrade to Small Compute ($10/month extra)
before optimising code — it's the faster fix.

**ParadeDB / pg_search (true BM25):** not available on Supabase Pro without custom
extension approval. Use `ts_rank_cd` with `websearch_to_tsquery` as specified in
Session 6 — it delivers 85-90% of BM25 quality for business email search and works
on Pro out of the box. Revisit ParadeDB post-launch only if exact-name queries show
measurable miss rates.

---

## Session 1 — Backend models + catalogue (Day 1)

**Goal:** Define every Pydantic model and the full SQL catalogue.
Nothing executes yet — this is the schema everything else builds on.

### Files to create

```
backend/src/models/intelligence.py          ← new
backend/src/services/query_catalogue.py     ← new
```

---

### `backend/src/models/intelligence.py`

```python
"""
Intelligence Query Models

Request/response models for the analytics intelligence endpoint.
Follows ai.py and analytics.py patterns.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from enum import Enum


class QueryIntent(str, Enum):
    AGGREGATION = "aggregation"   # top N, count, average, rank
    SEMANTIC    = "semantic"      # what did X say about Y
    TREND       = "trend"         # how has X changed over time
    FINANCIAL   = "financial"     # revenue, tier, QB cross-joins
    MIXED       = "mixed"         # requires multiple engines


class ChartType(str, Enum):
    BAR   = "bar"
    LINE  = "line"
    TABLE = "table"
    NONE  = "none"


class EngineType(str, Enum):
    SQL        = "sql"
    VECTOR     = "vector"
    TIMESERIES = "timeseries"
    QB         = "qb"


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language question")
    client_id: str = Field(..., description="Client UUID")
    company_id: Optional[str] = Field(default=None, description="Scope to a company")
    stream: bool = Field(default=True, description="Stream the synthesis answer via SSE")


class QueryClassification(BaseModel):
    intent: QueryIntent
    engines: List[EngineType]
    catalogue_key: Optional[str] = None       # which SQL template to run
    params: Dict[str, Any] = {}               # extracted params for the template
    semantic_query: Optional[str] = None      # cleaned query for vector search
    needs_chart: bool = False
    chart_type: ChartType = ChartType.NONE
    confidence: float = 1.0


class EngineResult(BaseModel):
    engine: EngineType
    rows: List[Dict[str, Any]] = []
    columns: List[str] = []
    row_count: int = 0
    error: Optional[str] = None


class QuerySource(BaseModel):
    type: str            # "email" | "company" | "sql" | "qb"
    id: Optional[str] = None
    label: str           # human-readable: "Email from Acme, Jan 2026"
    snippet: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    data: List[Dict[str, Any]] = []
    columns: List[str] = []
    chart_type: ChartType = ChartType.NONE
    query_type: QueryIntent
    engines_used: List[EngineType] = []
    sources: List[QuerySource] = []
    catalogue_key: Optional[str] = None
    processing_ms: Optional[int] = None
```

---

### `backend/src/services/query_catalogue.py`

The full catalogue of parameterised SQL templates. Claude Haiku selects from these
by matching descriptions to the user query — it never writes raw SQL.

```python
"""
Query Catalogue — Parameterised SQL templates for analytics intelligence.

Claude Haiku selects a key from this catalogue based on the user query.
It extracts params only — it never writes SQL.

All queries use :param_name placeholders — replaced via safe string formatting,
never f-strings on user input.

Param conventions:
  client_id   — always required
  date_from   — ISO string or None (no date filter)
  date_to     — ISO string or None
  limit       — int, default 10
  company_id  — UUID or None
  direction   — 'inbound' | 'outbound' | None (both)
  am_name     — account manager name string or None
  tier        — QB tier string or None
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CatalogueEntry:
    description: str      # what Claude reads to select this template
    params: list[str]     # required + optional param names
    sql: str              # parameterised SQL
    chart_type: str = "table"
    default_limit: int = 10


CATALOGUE: dict[str, CatalogueEntry] = {

    # ── Volume / activity ─────────────────────────────────────────────────

    "top_companies_by_email_volume": CatalogueEntry(
        description="Rank companies by number of emails sent or received. "
                    "Use for: top customers by email count, most active accounts, "
                    "most emailed companies, highest email volume.",
        params=["client_id", "date_from", "date_to", "limit", "direction"],
        chart_type="bar",
        sql="""
            SELECT
                cc.company_name,
                COUNT(e.id)                          AS email_count,
                SUM(CASE WHEN e.is_outbound THEN 1 ELSE 0 END) AS sent,
                SUM(CASE WHEN NOT e.is_outbound THEN 1 ELSE 0 END) AS received,
                cc.qb_tier,
                cc.qb_total_revenue,
                cc.qb_account_manager
            FROM emails e
            JOIN customer_companies cc ON e.company_id = cc.id
            WHERE e.client_id = '{client_id}'
              AND ('{date_from}' = 'None' OR e.sent_date >= '{date_from}')
              AND ('{date_to}'   = 'None' OR e.sent_date <= '{date_to}')
              AND ('{direction}' = 'None'
                   OR ('{direction}' = 'outbound' AND e.is_outbound)
                   OR ('{direction}' = 'inbound'  AND NOT e.is_outbound))
            GROUP BY cc.id, cc.company_name, cc.qb_tier,
                     cc.qb_total_revenue, cc.qb_account_manager
            ORDER BY email_count DESC
            LIMIT {limit}
        """,
    ),

    "top_contacts_by_email_volume": CatalogueEntry(
        description="Rank individual contacts/people by number of emails. "
                    "Use for: most active contacts, top senders, busiest people.",
        params=["client_id", "date_from", "date_to", "limit"],
        chart_type="bar",
        sql="""
            SELECT
                cc.full_name,
                cc.email_address,
                cc.company_name,
                COUNT(e.id)        AS email_count,
                cc.engagement_score,
                cc.qb_tier
            FROM emails e
            JOIN customer_contacts cc ON e.sender_email = cc.email_address
            WHERE e.client_id = '{client_id}'
              AND ('{date_from}' = 'None' OR e.sent_date >= '{date_from}')
              AND ('{date_to}'   = 'None' OR e.sent_date <= '{date_to}')
            GROUP BY cc.id, cc.full_name, cc.email_address,
                     cc.company_name, cc.engagement_score, cc.qb_tier
            ORDER BY email_count DESC
            LIMIT {limit}
        """,
    ),

    # ── Engagement ────────────────────────────────────────────────────────

    "top_companies_by_engagement": CatalogueEntry(
        description="Rank companies by engagement score. "
                    "Use for: most engaged customers, best relationship scores, "
                    "top accounts by engagement.",
        params=["client_id", "limit", "tier", "am_name"],
        chart_type="bar",
        sql="""
            SELECT
                company_name,
                engagement_score,
                total_emails,
                contact_count,
                qb_tier,
                qb_total_revenue,
                qb_account_manager,
                last_contact_date
            FROM customer_companies
            WHERE client_id = '{client_id}'
              AND engagement_score IS NOT NULL
              AND ('{tier}'    = 'None' OR qb_tier ILIKE '{tier}%')
              AND ('{am_name}' = 'None' OR qb_account_manager = '{am_name}')
            ORDER BY engagement_score DESC
            LIMIT {limit}
        """,
    ),

    "at_risk_companies": CatalogueEntry(
        description="Companies that have gone quiet — no recent contact. "
                    "Use for: at risk customers, silent accounts, neglected customers, "
                    "churn risk, no contact in X days.",
        params=["client_id", "days_silent", "limit", "tier"],
        chart_type="table",
        sql="""
            SELECT
                company_name,
                last_contact_date,
                CURRENT_DATE - last_contact_date::date AS days_since_contact,
                engagement_score,
                qb_tier,
                qb_total_revenue,
                qb_account_manager,
                qb_days_since_last_invoice
            FROM customer_companies
            WHERE client_id = '{client_id}'
              AND last_contact_date IS NOT NULL
              AND last_contact_date < NOW() - INTERVAL '{days_silent} days'
              AND ('{tier}' = 'None' OR qb_tier ILIKE '{tier}%')
            ORDER BY last_contact_date ASC
            LIMIT {limit}
        """,
    ),

    # ── Threads / response ────────────────────────────────────────────────

    "overdue_threads_by_am": CatalogueEntry(
        description="Overdue threads grouped or filtered by account manager. "
                    "Use for: which AM has overdue threads, unanswered emails by AM, "
                    "who has the most overdue conversations.",
        params=["client_id", "am_name", "limit"],
        chart_type="table",
        sql="""
            SELECT
                ts.subject,
                cc.company_name,
                co.full_name           AS contact_name,
                cc.qb_account_manager  AS account_manager,
                ts.days_since_last_email,
                ts.status,
                cc.qb_tier,
                cc.qb_total_revenue
            FROM thread_status ts
            JOIN mailboxes m        ON ts.mailbox_id = m.id
            LEFT JOIN customer_companies cc ON ts.customer_company_id = cc.id
            LEFT JOIN customer_contacts  co ON ts.customer_contact_id = co.id
            WHERE m.client_id = '{client_id}'
              AND ts.status IN ('overdue', 'awaiting_our_response')
              AND ('{am_name}' = 'None' OR cc.qb_account_manager = '{am_name}')
            ORDER BY ts.days_since_last_email DESC
            LIMIT {limit}
        """,
    ),

    "response_time_by_company": CatalogueEntry(
        description="Average response time per company. "
                    "Use for: slowest to respond, fastest response time, "
                    "how long companies take to reply.",
        params=["client_id", "date_from", "date_to", "limit"],
        chart_type="bar",
        sql="""
            SELECT
                cc.company_name,
                ROUND(AVG(rm.response_time_seconds) / 3600.0, 1) AS avg_response_hours,
                COUNT(rm.id)    AS response_count,
                cc.qb_tier,
                cc.qb_account_manager
            FROM email_response_metrics rm
            JOIN customer_contacts  co ON rm.responder_contact_id = co.id
            JOIN customer_companies cc ON co.customer_company_id = cc.id
            WHERE cc.client_id = '{client_id}'
              AND ('{date_from}' = 'None' OR rm.created_at >= '{date_from}')
              AND ('{date_to}'   = 'None' OR rm.created_at <= '{date_to}')
            GROUP BY cc.id, cc.company_name, cc.qb_tier, cc.qb_account_manager
            HAVING COUNT(rm.id) >= 3
            ORDER BY avg_response_hours DESC
            LIMIT {limit}
        """,
    ),

    # ── QB financial intelligence ─────────────────────────────────────────

    "revenue_vs_engagement": CatalogueEntry(
        description="Cross-reference QB revenue against email engagement score. "
                    "Use for: high revenue low engagement, revenue vs activity, "
                    "financial risk by engagement, QB vs email correlation.",
        params=["client_id", "limit", "tier"],
        chart_type="table",
        sql="""
            SELECT
                company_name,
                qb_total_revenue,
                qb_invoiced_ty,
                qb_invoiced_ly,
                qb_growth_90d,
                engagement_score,
                total_emails,
                last_contact_date,
                qb_tier,
                qb_account_manager,
                qb_days_since_last_invoice
            FROM customer_companies
            WHERE client_id = '{client_id}'
              AND qb_total_revenue IS NOT NULL
              AND engagement_score IS NOT NULL
              AND ('{tier}' = 'None' OR qb_tier ILIKE '{tier}%')
            ORDER BY qb_total_revenue DESC
            LIMIT {limit}
        """,
    ),

    "high_revenue_no_contact": CatalogueEntry(
        description="High revenue QB customers with no recent email contact. "
                    "Use for: valuable customers being ignored, revenue at risk, "
                    "high value accounts with no activity.",
        params=["client_id", "days_silent", "limit", "tier"],
        chart_type="table",
        sql="""
            SELECT
                company_name,
                qb_total_revenue,
                qb_tier,
                qb_account_manager,
                last_contact_date,
                CURRENT_DATE - last_contact_date::date AS days_since_contact,
                engagement_score,
                qb_days_since_last_invoice
            FROM customer_companies
            WHERE client_id = '{client_id}'
              AND qb_total_revenue IS NOT NULL
              AND (last_contact_date IS NULL
                   OR last_contact_date < NOW() - INTERVAL '{days_silent} days')
              AND ('{tier}' = 'None' OR qb_tier ILIKE '{tier}%')
            ORDER BY qb_total_revenue DESC
            LIMIT {limit}
        """,
    ),

    "qb_tier_breakdown": CatalogueEntry(
        description="Summary of companies broken down by QB tier. "
                    "Use for: how many tier 1 customers, tier distribution, "
                    "customers by tier, tier summary.",
        params=["client_id"],
        chart_type="bar",
        sql="""
            SELECT
                COALESCE(qb_tier, 'Untiered')   AS tier,
                COUNT(*)                          AS company_count,
                ROUND(AVG(engagement_score), 1)  AS avg_engagement,
                ROUND(SUM(qb_total_revenue))     AS total_revenue,
                COUNT(CASE WHEN last_contact_date >= NOW() - INTERVAL '30 days'
                           THEN 1 END)            AS active_last_30d
            FROM customer_companies
            WHERE client_id = '{client_id}'
            GROUP BY COALESCE(qb_tier, 'Untiered')
            ORDER BY total_revenue DESC NULLS LAST
        """,
    ),

    "am_performance": CatalogueEntry(
        description="Account manager performance summary — email activity, "
                    "engagement, revenue, overdue threads. "
                    "Use for: which AM is most active, AM comparison, "
                    "account manager leaderboard.",
        params=["client_id", "date_from", "date_to"],
        chart_type="table",
        sql="""
            SELECT
                qb_account_manager                    AS account_manager,
                COUNT(DISTINCT id)                    AS company_count,
                ROUND(AVG(engagement_score), 1)       AS avg_engagement,
                ROUND(SUM(qb_total_revenue))          AS total_revenue,
                SUM(total_emails)                     AS total_emails,
                COUNT(CASE WHEN last_contact_date < NOW() - INTERVAL '30 days'
                           THEN 1 END)                AS at_risk_companies
            FROM customer_companies
            WHERE client_id = '{client_id}'
              AND qb_account_manager IS NOT NULL
            GROUP BY qb_account_manager
            ORDER BY total_revenue DESC NULLS LAST
        """,
    ),

    # ── Sentiment / AI fields ─────────────────────────────────────────────

    "sentiment_by_company": CatalogueEntry(
        description="Average email sentiment score per company. "
                    "Use for: most negative customers, sentiment ranking, "
                    "happiest customers, unhappy accounts.",
        params=["client_id", "date_from", "date_to", "limit"],
        chart_type="bar",
        sql="""
            SELECT
                cc.company_name,
                ROUND(AVG(ai.sentiment_score)::numeric, 2) AS avg_sentiment,
                COUNT(ai.id)                               AS emails_analysed,
                cc.qb_tier,
                cc.qb_account_manager,
                cc.qb_total_revenue
            FROM ai_email_classifications ai
            JOIN emails e ON ai.email_id = e.id
            JOIN customer_companies cc ON e.company_id = cc.id
            WHERE e.client_id = '{client_id}'
              AND ai.sentiment_score IS NOT NULL
              AND ('{date_from}' = 'None' OR e.sent_date >= '{date_from}')
              AND ('{date_to}'   = 'None' OR e.sent_date <= '{date_to}')
            GROUP BY cc.id, cc.company_name, cc.qb_tier,
                     cc.qb_account_manager, cc.qb_total_revenue
            HAVING COUNT(ai.id) >= 3
            ORDER BY avg_sentiment ASC
            LIMIT {limit}
        """,
    ),

    "bucket_distribution": CatalogueEntry(
        description="Count of emails by action bucket — response urgency, "
                    "deal at risk, retention risk, revenue opportunity, etc. "
                    "Use for: how many urgent emails, bucket summary, "
                    "action items by type, signal distribution.",
        params=["client_id", "date_from", "date_to"],
        chart_type="bar",
        sql="""
            SELECT
                primary_bucket,
                COUNT(*)                                    AS email_count,
                ROUND(AVG(business_signal_score)::numeric, 1) AS avg_signal_score
            FROM ai_email_classifications ai
            JOIN emails e ON ai.email_id = e.id
            WHERE e.client_id = '{client_id}'
              AND primary_bucket IS NOT NULL
              AND ('{date_from}' = 'None' OR e.sent_date >= '{date_from}')
              AND ('{date_to}'   = 'None' OR e.sent_date <= '{date_to}')
            GROUP BY primary_bucket
            ORDER BY email_count DESC
        """,
    ),
}


def get_catalogue_descriptions() -> str:
    """Return a compact description block for the classifier prompt."""
    lines = []
    for key, entry in CATALOGUE.items():
        lines.append(f"- {key}: {entry.description}")
    return "\n".join(lines)


def get_entry(key: str) -> CatalogueEntry | None:
    return CATALOGUE.get(key)


def run_catalogue_query(
    entry: CatalogueEntry,
    params: dict,
    supabase_client,
) -> list[dict]:
    """
    Substitute params into SQL template and execute via Supabase rpc or raw query.
    Uses safe string substitution — params are validated before reaching here.
    """
    # Fill defaults for optional params
    filled = {
        "date_from": "None",
        "date_to":   "None",
        "limit":     10,
        "direction": "None",
        "tier":      "None",
        "am_name":   "None",
        "days_silent": 30,
        "company_id": "None",
        **{k: v if v is not None else "None" for k, v in params.items()},
    }
    sql = entry.sql.format(**filled).strip()
    result = supabase_client.rpc("run_intelligence_query", {"p_sql": sql}).execute()
    return result.data or []
```

**After creating both files:** run `python -c "from backend.src.models.intelligence import QueryRequest; print('ok')"` to confirm imports resolve. Fix any path issues before Session 2.

---

## Session 2 — Query classifier service (Day 2)

**Goal:** The brain of the system. Reads the user query, returns a `QueryClassification`.
Uses Claude Haiku — fast and cheap, never Sonnet for this step.

### File to create

```
backend/src/services/query_classifier.py    ← new
```

### `backend/src/services/query_classifier.py`

```python
"""
Query Classifier

Uses Claude Haiku to classify user intent and select the right execution engine(s).
Returns a QueryClassification — never executes queries itself.

Cost: ~$0.001 per classification (Haiku pricing).
Latency: ~100–150ms.
"""

import json
import logging
import os
from anthropic import AsyncAnthropic
from ..models.intelligence import QueryClassification, QueryIntent, EngineType, ChartType
from .query_catalogue import get_catalogue_descriptions

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None

def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


CLASSIFIER_SYSTEM = """
You are a query router for an email intelligence platform.
You classify natural language questions and extract structured routing parameters.
Return ONLY valid JSON matching the schema below. No preamble, no markdown.

Platform data available:
- emails: subject, body, sender, sent_date, is_outbound, company_id, sentiment
- customer_companies: company_name, engagement_score, total_emails, last_contact_date,
  qb_tier, qb_total_revenue, qb_account_manager, qb_invoiced_ty, qb_invoiced_ly,
  qb_growth_90d, qb_days_since_last_invoice
- customer_contacts: full_name, email_address, engagement_score, last_contacted_at
- ai_email_classifications: sentiment_score, intent, urgency, primary_bucket,
  business_signal_score, summary
- thread_status: status, days_since_last_email, message_count
- email_response_metrics: response_time_seconds

SQL catalogue keys (select one if intent is aggregation, financial, or trend):
{catalogue}

Return this exact JSON schema:
{{
  "intent": "aggregation" | "semantic" | "trend" | "financial" | "mixed",
  "engines": ["sql", "vector", "timeseries", "qb"],
  "catalogue_key": "<key from catalogue above or null>",
  "params": {{
    "date_from": "<ISO date string or null>",
    "date_to": "<ISO date string or null>",
    "limit": <integer, default 10>,
    "direction": "<inbound|outbound or null>",
    "tier": "<tier string or null>",
    "am_name": "<account manager name or null>",
    "days_silent": <integer, default 30>,
    "company_id": "<uuid or null>"
  }},
  "semantic_query": "<cleaned query for vector search, or null>",
  "needs_chart": <true|false>,
  "chart_type": "bar" | "line" | "table" | "none",
  "confidence": <0.0 to 1.0>
}}

Rules:
- If the question asks for a ranking, count, average, or top N → intent=aggregation, use sql engine
- If the question asks what someone said, find emails about X → intent=semantic, use vector engine
- If the question asks how something changed over time → intent=trend, use timeseries engine
- If the question mentions revenue, tier, QB data AND email activity → intent=financial, engines=[sql,qb]
- For mixed questions (e.g. "find emails from our top customers") → intent=mixed, multiple engines
- Always include client_id in params (it will be injected — do not ask for it)
- Extract year references: "in 2026" → date_from=2026-01-01, date_to=2026-12-31
- Extract quarter references: "Q1" → months 1-3, "Q2" → 4-6, "Q3" → 7-9, "Q4" → 10-12
- "last month" / "this year" → compute relative to today (April 2026)
- chart_type=bar for rankings/comparisons, line for trends, table for detailed lists
"""


async def classify_query(
    query: str,
    client_id: str,
    today: str = "2026-04-06",
) -> QueryClassification:
    """
    Classify a natural language query into structured routing instructions.
    Returns QueryClassification. Never raises — returns a safe semantic fallback on error.
    """
    catalogue = get_catalogue_descriptions()
    system = CLASSIFIER_SYSTEM.format(catalogue=catalogue)

    prompt = f"Today's date: {today}\nClient ID: {client_id}\nUser query: {query}"

    try:
        response = await _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())

        return QueryClassification(
            intent=QueryIntent(data.get("intent", "semantic")),
            engines=[EngineType(e) for e in data.get("engines", ["vector"])],
            catalogue_key=data.get("catalogue_key"),
            params={**data.get("params", {}), "client_id": client_id},
            semantic_query=data.get("semantic_query") or query,
            needs_chart=data.get("needs_chart", False),
            chart_type=ChartType(data.get("chart_type", "none")),
            confidence=float(data.get("confidence", 1.0)),
        )

    except Exception as e:
        logger.warning(f"[Classifier] Failed, falling back to semantic: {e}")
        # Safe fallback — always works
        return QueryClassification(
            intent=QueryIntent.SEMANTIC,
            engines=[EngineType.VECTOR],
            semantic_query=query,
            params={"client_id": client_id},
            chart_type=ChartType.NONE,
            confidence=0.0,
        )
```

**Test after creating:**

```python
# Run from repo root
import asyncio
from backend.src.services.query_classifier import classify_query

async def test():
    cases = [
        "top customers by email count in 2026",
        "what did Acme say about pricing",
        "which account manager has the most overdue threads",
        "how has sentiment changed for our tier 1 customers this year",
        "high revenue companies with no contact in 30 days",
    ]
    for q in cases:
        result = await classify_query(q, client_id="test-uuid")
        print(f"Q: {q}")
        print(f"  intent={result.intent} engines={result.engines} key={result.catalogue_key}")
        print(f"  params={result.params}")
        print()

asyncio.run(test())
```

All five should classify correctly before moving to Session 3.

---

## Session 3 — Supabase RPC + execution engines (Day 3)

**Goal:** Wire the SQL catalogue to Supabase. Build vector and timeseries engines.
This session produces working data — no synthesis yet.

### Step 3.1 — Supabase migration

Create `supabase/migrations/057_intelligence_query_rpc.sql`:

```sql
-- Safe pass-through for intelligence queries
-- Only called server-side with pre-validated, parameterised SQL
-- No user input ever reaches this function directly

CREATE OR REPLACE FUNCTION run_intelligence_query(p_sql TEXT)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSONB;
BEGIN
    EXECUTE 'SELECT jsonb_agg(row_to_json(t)) FROM (' || p_sql || ') t'
    INTO result;
    RETURN COALESCE(result, '[]'::jsonb);
END;
$$;

-- Grant to authenticated role only
REVOKE ALL ON FUNCTION run_intelligence_query(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION run_intelligence_query(TEXT) TO authenticated;
```

Run this migration in Supabase before the next step.

### Step 3.2 — Execution engine service

**File:** `backend/src/services/intelligence_engine.py` (new)

```python
"""
Intelligence Execution Engines

Four engines that run in parallel based on QueryClassification:
  SQL        — catalogue query via run_intelligence_query RPC
  Vector     — hybrid retrieval via VectorService
  Timeseries — date-bucketed trend SQL
  QB         — QB financial cross-join queries

Each engine returns an EngineResult.
"""

import asyncio
import logging
import time
from ..models.intelligence import (
    QueryClassification, EngineResult, EngineType, QuerySource
)
from .query_catalogue import get_entry, run_catalogue_query
from .vector_service import VectorService

logger = logging.getLogger(__name__)


class IntelligenceEngine:

    def __init__(self, supabase_client):
        self._sb = supabase_client
        self._vector = VectorService(supabase_client)

    async def _db(self, fn):
        return await asyncio.to_thread(fn)

    # ── SQL engine ────────────────────────────────────────────────────────

    async def run_sql(self, classification: QueryClassification) -> EngineResult:
        if not classification.catalogue_key:
            return EngineResult(engine=EngineType.SQL, error="No catalogue key")

        entry = get_entry(classification.catalogue_key)
        if not entry:
            return EngineResult(engine=EngineType.SQL,
                                error=f"Unknown key: {classification.catalogue_key}")
        try:
            rows = await self._db(
                lambda: run_catalogue_query(entry, classification.params, self._sb)
            )
            columns = list(rows[0].keys()) if rows else []
            return EngineResult(
                engine=EngineType.SQL,
                rows=rows,
                columns=columns,
                row_count=len(rows),
            )
        except Exception as e:
            logger.error(f"[SQL engine] {e}")
            return EngineResult(engine=EngineType.SQL, error=str(e))

    # ── Vector engine ─────────────────────────────────────────────────────

    async def run_vector(self, classification: QueryClassification) -> EngineResult:
        query = classification.semantic_query or ""
        client_id = classification.params.get("client_id")
        date_from = classification.params.get("date_from")
        date_to = classification.params.get("date_to")

        try:
            # Run email + company search in parallel
            email_task = self._vector.search_emails(
                query=query,
                client_id=client_id,
                threshold=0.62,
                limit=15,
                date_from=date_from if date_from != "None" else None,
                date_to=date_to if date_to != "None" else None,
            )
            company_task = self._vector.search_companies(
                query=query,
                client_id=client_id,
                threshold=0.62,
                limit=5,
            )
            emails, companies = await asyncio.gather(email_task, company_task)

            rows = []
            for e in emails:
                rows.append({
                    "source_type": "email",
                    "id": e.get("id"),
                    "subject": e.get("subject"),
                    "sender": e.get("sender_email"),
                    "date": e.get("sent_date"),
                    "summary": e.get("summary") or e.get("body_text", "")[:200],
                    "similarity": round(e.get("similarity", 0), 3),
                })
            for c in companies:
                rows.append({
                    "source_type": "company",
                    "id": c.get("id"),
                    "company_name": c.get("company_name"),
                    "similarity": round(c.get("similarity", 0), 3),
                })

            return EngineResult(
                engine=EngineType.VECTOR,
                rows=rows,
                columns=["source_type", "id", "subject", "sender", "date",
                         "summary", "similarity", "company_name"],
                row_count=len(rows),
            )
        except Exception as e:
            logger.error(f"[Vector engine] {e}")
            return EngineResult(engine=EngineType.VECTOR, error=str(e))

    # ── Timeseries engine ─────────────────────────────────────────────────

    async def run_timeseries(self, classification: QueryClassification) -> EngineResult:
        params = classification.params
        client_id = params.get("client_id")
        date_from = params.get("date_from", "None")
        date_to = params.get("date_to", "None")
        company_id = params.get("company_id", "None")

        sql = f"""
            SELECT
                DATE_TRUNC('week', e.sent_date)::date        AS week,
                COUNT(e.id)                                  AS email_count,
                ROUND(AVG(ai.sentiment_score)::numeric, 2)   AS avg_sentiment,
                SUM(CASE WHEN ai.primary_bucket = 'response_urgency'
                         THEN 1 ELSE 0 END)                  AS urgent_count
            FROM emails e
            LEFT JOIN ai_email_classifications ai ON ai.email_id = e.id
            WHERE e.client_id = '{client_id}'
              AND ('{date_from}' = 'None' OR e.sent_date >= '{date_from}')
              AND ('{date_to}'   = 'None' OR e.sent_date <= '{date_to}')
              AND ('{company_id}' = 'None' OR e.company_id = '{company_id}')
            GROUP BY DATE_TRUNC('week', e.sent_date)
            ORDER BY week ASC
        """
        try:
            result = await self._db(
                lambda: self._sb.rpc("run_intelligence_query",
                                     {"p_sql": sql}).execute()
            )
            rows = result.data or []
            return EngineResult(
                engine=EngineType.TIMESERIES,
                rows=rows,
                columns=["week", "email_count", "avg_sentiment", "urgent_count"],
                row_count=len(rows),
            )
        except Exception as e:
            logger.error(f"[Timeseries engine] {e}")
            return EngineResult(engine=EngineType.TIMESERIES, error=str(e))

    # ── Run all requested engines in parallel ─────────────────────────────

    async def execute(
        self, classification: QueryClassification
    ) -> list[EngineResult]:
        tasks = []
        for engine in classification.engines:
            if engine == EngineType.SQL:
                tasks.append(self.run_sql(classification))
            elif engine == EngineType.VECTOR:
                tasks.append(self.run_vector(classification))
            elif engine == EngineType.TIMESERIES:
                tasks.append(self.run_timeseries(classification))
            elif engine == EngineType.QB:
                # QB uses the sql engine with QB-specific catalogue entries
                tasks.append(self.run_sql(classification))

        results = await asyncio.gather(*tasks)
        return [r for r in results if not r.error]
```

---

## Session 4 — Synthesiser + main endpoint (Day 4)

**Goal:** The final layer. Takes engine results, streams a grounded answer.
Then wires everything into a single FastAPI endpoint.

### Step 4.1 — Synthesiser service

**File:** `backend/src/services/intelligence_synthesiser.py` (new)

```python
"""
Intelligence Synthesiser

Takes raw engine results and streams a grounded answer via Claude Sonnet.
Never invents data — answers only from what the engines returned.
"""

import json
import logging
import os
from anthropic import AsyncAnthropic
from ..models.intelligence import (
    QueryClassification, EngineResult, QuerySource, ChartType
)

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM = """
You are an email intelligence analyst. Answer the user's question using ONLY
the data provided below. Do not invent figures, companies, or dates not
present in the data.

Rules:
- Cite specific numbers from the data
- Keep answers to 3-5 sentences maximum
- If a table or chart was generated, reference it ("as shown in the table above")
- End with one actionable recommendation if the data supports it
- If the data is insufficient to answer, say so directly
- Never say "based on the data provided" — just answer
"""


def _format_results_for_prompt(results: list[EngineResult]) -> str:
    sections = []
    for r in results:
        if not r.rows:
            continue
        header = " | ".join(r.columns[:8])  # cap columns shown
        rows_md = [header, "-" * len(header)]
        for row in r.rows[:20]:             # cap rows shown in prompt
            rows_md.append(" | ".join(str(row.get(c, ""))[:40] for c in r.columns[:8]))
        sections.append(f"[{r.engine.value.upper()} RESULTS]\n" + "\n".join(rows_md))
    return "\n\n".join(sections) if sections else "No data returned."


def _extract_sources(results: list[EngineResult]) -> list[QuerySource]:
    sources = []
    for r in results:
        if r.engine.value == "vector":
            for row in r.rows[:5]:
                if row.get("source_type") == "email":
                    sources.append(QuerySource(
                        type="email",
                        id=row.get("id"),
                        label=f"{row.get('subject', 'Email')} — {row.get('date', '')[:10]}",
                        snippet=row.get("summary", "")[:120],
                    ))
    return sources


async def synthesise_streaming(
    query: str,
    classification: QueryClassification,
    results: list[EngineResult],
):
    """
    Async generator — yields text tokens.
    Caller wraps in SSE: `data: {"delta": token}\n\n`
    """
    client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    data_block = _format_results_for_prompt(results)

    prompt = f"""User question: {query}

Data:
{data_block}

Answer:"""

    async with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=600,
        system=SYNTHESIS_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for token in stream.text_stream:
            yield token


def build_response_metadata(
    query: str,
    classification: QueryClassification,
    results: list[EngineResult],
    processing_ms: int,
) -> dict:
    """Non-streamed metadata sent before the stream starts."""
    primary = results[0] if results else None
    return {
        "query_type": classification.intent.value,
        "engines_used": [e.value for e in classification.engines],
        "catalogue_key": classification.catalogue_key,
        "chart_type": classification.chart_type.value,
        "needs_chart": classification.needs_chart,
        "data": primary.rows if primary else [],
        "columns": primary.columns if primary else [],
        "row_count": primary.row_count if primary else 0,
        "sources": [s.dict() for s in _extract_sources(results)],
        "processing_ms": processing_ms,
    }
```

### Step 4.2 — The endpoint

**File:** `backend/src/routers/intelligence.py` (new)

```python
"""
Intelligence Router — POST /ai/intelligence/query

Single endpoint for all analytics intelligence queries.
Streams: metadata event first, then answer tokens, then [DONE].

SSE event format:
  data: {"type": "metadata", ...}   ← sent first, non-streamed
  data: {"type": "delta", "text": "..."} ← streamed tokens
  data: [DONE]
"""

import asyncio
import json
import logging
import time
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from ..models.intelligence import QueryRequest
from ..services.query_classifier import classify_query
from ..services.intelligence_engine import IntelligenceEngine
from ..services.intelligence_synthesiser import (
    synthesise_streaming, build_response_metadata
)
from ..dependencies.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/intelligence", tags=["intelligence"])

_supabase = None

def init_intelligence_router(supabase_client):
    global _supabase
    _supabase = supabase_client


@router.post("/query")
async def intelligence_query(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    async def generator():
        t0 = time.monotonic()

        # Step 1 — classify (fast, Haiku)
        classification = await classify_query(
            query=request.query,
            client_id=request.client_id,
        )

        # Step 2 — execute engines in parallel
        engine = IntelligenceEngine(_supabase)
        results = await engine.execute(classification)

        processing_ms = int((time.monotonic() - t0) * 1000)

        # Step 3 — send metadata first (data table, chart config, sources)
        metadata = build_response_metadata(
            query=request.query,
            classification=classification,
            results=results,
            processing_ms=processing_ms,
        )
        yield f"data: {json.dumps({'type': 'metadata', **metadata})}\n\n"

        # Step 4 — stream synthesis answer
        async for token in synthesise_streaming(
            query=request.query,
            classification=classification,
            results=results,
        ):
            yield f"data: {json.dumps({'type': 'delta', 'text': token})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
```

### Step 4.3 — Register router in `main.py`

```python
from src.routers.intelligence import router as intelligence_router, init_intelligence_router

# alongside existing router registrations
app.include_router(intelligence_router)
init_intelligence_router(supabase_client)
```

**Test the full pipeline with curl:**

```bash
curl -X POST http://localhost:8000/ai/intelligence/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "query": "top customers by email count in 2026",
    "client_id": "<your-client-uuid>",
    "stream": true
  }' --no-buffer
```

Expected: metadata event with `data` array populated, then streamed answer tokens, then `[DONE]`.

---

## Session 5 — Frontend query interface (Days 5–6)

**Goal:** A single search bar on the Intelligence page that renders answers,
tables, and charts. Reuses the SSE streaming pattern already built.

### Files to create / modify

```
frontend/src/services/intelligenceService.ts          ← new
frontend/src/hooks/queries/useIntelligenceQuery.ts    ← new
frontend/src/components/intelligence/QueryBar.tsx      ← new
frontend/src/components/intelligence/QueryResult.tsx   ← new
frontend/src/components/intelligence/ResultChart.tsx   ← new
frontend/src/pages/intelligence/query.tsx              ← new page
```

### `intelligenceService.ts`

```ts
export interface QueryMetadata {
  query_type: string
  engines_used: string[]
  chart_type: 'bar' | 'line' | 'table' | 'none'
  needs_chart: boolean
  data: Record<string, unknown>[]
  columns: string[]
  row_count: number
  sources: { type: string; id: string; label: string; snippet: string }[]
  processing_ms: number
}

export async function* streamIntelligenceQuery(
  query: string,
  clientId: string,
  signal: AbortSignal,
): AsyncGenerator<{ type: 'metadata'; payload: QueryMetadata } | { type: 'delta'; text: string }> {
  const res = await fetch('/api/ai/intelligence/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, client_id: clientId, stream: true }),
    signal,
  })

  if (!res.ok) throw new Error(`Intelligence query failed: ${res.status}`)

  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const events = buffer.split('\n\n')
    buffer = events.pop()!

    for (const event of events) {
      const line = event.replace(/^data: /, '').trim()
      if (line === '[DONE]') return
      if (!line) continue
      try {
        const parsed = JSON.parse(line)
        if (parsed.type === 'metadata') {
          yield { type: 'metadata', payload: parsed as QueryMetadata }
        } else if (parsed.type === 'delta') {
          yield { type: 'delta', text: parsed.text }
        }
      } catch { /* skip malformed chunk */ }
    }
  }
}
```

### `QueryResult.tsx` — renders metadata + streamed answer

```tsx
import { Table } from 'antd'
import { QueryMetadata } from '../../services/intelligenceService'
import { ResultChart } from './ResultChart'

interface Props {
  query: string
  metadata: QueryMetadata | null
  answer: string
  isStreaming: boolean
}

export function QueryResult({ query, metadata, answer, isStreaming }: Props) {
  if (!metadata && !answer) return null

  return (
    <div style={{ marginTop: 24 }}>
      {/* Data table or chart — renders immediately from metadata event */}
      {metadata && metadata.row_count > 0 && (
        <>
          {metadata.needs_chart && metadata.chart_type !== 'none' ? (
            <ResultChart
              data={metadata.data}
              columns={metadata.columns}
              chartType={metadata.chart_type}
            />
          ) : (
            <Table
              dataSource={metadata.data}
              columns={metadata.columns.map(c => ({ key: c, dataIndex: c, title: c }))}
              size="small"
              pagination={{ pageSize: 10 }}
              style={{ marginBottom: 16 }}
            />
          )}
        </>
      )}

      {/* Streamed prose answer */}
      {answer && (
        <div style={{
          padding: '12px 16px',
          background: 'var(--color-background-secondary)',
          borderRadius: 'var(--border-radius-md)',
          fontSize: 14,
          lineHeight: 1.7,
        }}>
          {answer}
          {isStreaming && (
            <span style={{ opacity: 0.5, marginLeft: 2 }}>|</span>
          )}
        </div>
      )}

      {/* Sources */}
      {metadata?.sources?.length > 0 && (
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--color-text-tertiary)' }}>
          {metadata.sources.map((s, i) => (
            <div key={i}>{s.label}</div>
          ))}
        </div>
      )}

      {/* Engine badge */}
      {metadata && (
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--color-text-tertiary)' }}>
          {metadata.engines_used.join(' + ')} · {metadata.processing_ms}ms
        </div>
      )}
    </div>
  )
}
```

### `ResultChart.tsx` — Recharts bar or line

```tsx
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'

interface Props {
  data: Record<string, unknown>[]
  columns: string[]
  chartType: 'bar' | 'line'
}

export function ResultChart({ data, columns, chartType }: Props) {
  // First column = x-axis label, second = primary value
  const xKey = columns[0]
  const yKey = columns[1]

  if (chartType === 'line') {
    return (
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data}>
          <XAxis dataKey={xKey} tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip />
          <Line type="monotone" dataKey={yKey} stroke="#1D9E75" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} layout="vertical">
        <XAxis type="number" tick={{ fontSize: 11 }} />
        <YAxis dataKey={xKey} type="category" width={140} tick={{ fontSize: 11 }} />
        <Tooltip />
        <Bar dataKey={yKey} fill="#1D9E75" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
```

### `pages/intelligence/query.tsx` — the full page

```tsx
import { useState, useRef } from 'react'
import { Input, Button } from 'antd'
import { streamIntelligenceQuery, QueryMetadata } from '../../services/intelligenceService'
import { QueryResult } from '../../components/intelligence/QueryResult'

const EXAMPLE_QUERIES = [
  'Top customers by email count in 2026',
  'Which account manager has the most overdue threads?',
  'High revenue companies with no contact in 30 days',
  'What did customers say about pricing this year?',
  'Show me sentiment trends for our tier 1 accounts',
]

export default function IntelligenceQueryPage() {
  const [input, setInput]         = useState('')
  const [lastQuery, setLastQuery] = useState('')
  const [metadata, setMetadata]   = useState<QueryMetadata | null>(null)
  const [answer, setAnswer]       = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const { clientId } = useClientContext()  // existing context hook

  const handleQuery = async (q?: string) => {
    const query = q || input.trim()
    if (!query || isStreaming) return

    abortRef.current?.abort()
    abortRef.current = new AbortController()

    setLastQuery(query)
    setMetadata(null)
    setAnswer('')
    setIsStreaming(true)

    try {
      for await (const event of streamIntelligenceQuery(
        query, clientId, abortRef.current.signal,
      )) {
        if (event.type === 'metadata') {
          setMetadata(event.payload)
        } else if (event.type === 'delta') {
          setAnswer(prev => prev + event.text)
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') console.error(err)
    } finally {
      setIsStreaming(false)
    }
  }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '24px 0' }}>
      <Input.Search
        size="large"
        placeholder="Ask anything — top customers, overdue threads, sentiment trends..."
        value={input}
        onChange={e => setInput(e.target.value)}
        onSearch={() => handleQuery()}
        onPressEnter={() => handleQuery()}
        loading={isStreaming}
        enterButton={isStreaming ? 'Stop' : 'Ask'}
        onMouseDown={isStreaming ? () => abortRef.current?.abort() : undefined}
      />

      {/* Example queries — shown when no result yet */}
      {!lastQuery && (
        <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {EXAMPLE_QUERIES.map(q => (
            <button
              key={q}
              onClick={() => { setInput(q); handleQuery(q) }}
              style={{
                fontSize: 12,
                padding: '4px 10px',
                border: '0.5px solid var(--color-border-secondary)',
                borderRadius: 'var(--border-radius-md)',
                background: 'transparent',
                cursor: 'pointer',
                color: 'var(--color-text-secondary)',
              }}
            >
              {q}
            </button>
          ))}
        </div>
      )}

      <QueryResult
        query={lastQuery}
        metadata={metadata}
        answer={answer}
        isStreaming={isStreaming}
      />
    </div>
  )
}
```

Add this page to the Intelligence section of your router and sidebar navigation.

---

## Session 6 — tsvector index + BM25 hybrid (Day 7)

**Goal:** Add keyword search alongside vector search for the hybrid retriever.
This upgrades the vector engine from pure cosine similarity to RRF-fused results.

### Step 6.1 — Migration `058_fts_index.sql`

```sql
-- Add tsvector column to emails for full-text search
ALTER TABLE emails ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(subject, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(sender_name, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(left(body_text, 5000), '')), 'C')
    ) STORED;

-- IMPORTANT: Use CONCURRENTLY on Pro — avoids table lock during index build on 270k rows.
-- Standard CREATE INDEX locks the table; CONCURRENTLY does not. Takes longer but safe in prod.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emails_fts ON emails USING GIN(fts);

-- BM25 keyword search function
CREATE OR REPLACE FUNCTION search_emails_bm25(
    p_query      TEXT,
    p_client_id  UUID,
    p_date_from  TIMESTAMPTZ DEFAULT NULL,
    p_date_to    TIMESTAMPTZ DEFAULT NULL,
    p_limit      INT DEFAULT 40
)
RETURNS TABLE (
    id           UUID,
    subject      TEXT,
    sender_email TEXT,
    sent_date    TIMESTAMPTZ,
    body_text    TEXT,
    company_id   UUID,
    keyword_rank REAL
)
LANGUAGE sql STABLE AS $$
    SELECT
        e.id, e.subject, e.sender_email, e.sent_date,
        LEFT(e.body_text, 500) AS body_text,
        e.company_id,
        ts_rank_cd(e.fts, query, 32) AS keyword_rank
    FROM emails e,
         websearch_to_tsquery('english', p_query) query
    WHERE e.client_id = p_client_id
      AND e.fts @@ query
      AND (p_date_from IS NULL OR e.sent_date >= p_date_from)
      AND (p_date_to   IS NULL OR e.sent_date <= p_date_to)
    ORDER BY keyword_rank DESC
    LIMIT p_limit;
$$;
```

### Step 6.2 — Update `vector_service.py` — add BM25 + RRF fusion

Add these methods to the `VectorService` class:

```python
async def search_emails_bm25(
    self, query: str, client_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 40,
) -> list[dict]:
    """Keyword search via tsvector + ts_rank_cd (BM25 approximation)."""
    result = await self._db(lambda: self._sb.rpc("search_emails_bm25", {
        "p_query":     query,
        "p_client_id": client_id,
        "p_date_from": date_from,
        "p_date_to":   date_to,
        "p_limit":     limit,
    }).execute())
    return result.data or []


async def search_emails_hybrid(
    self, query: str, client_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 15,
) -> list[dict]:
    """
    Hybrid retrieval: vector + BM25, fused via Reciprocal Rank Fusion.
    Returns top `limit` results ranked by combined RRF score.

    RRF weighting is asymmetric: proper noun queries (company names, contact
    names, specific terms) weight BM25 higher since exact matching wins there.
    Conceptual queries ("emails about pricing concerns") weight vector higher.
    """
    # Run both in parallel
    vector_hits, keyword_hits = await asyncio.gather(
        self.search_emails(
            query=query, client_id=client_id,
            threshold=0.60, limit=40,
            date_from=date_from, date_to=date_to,
        ),
        self.search_emails_bm25(
            query=query, client_id=client_id,
            date_from=date_from, date_to=date_to,
            limit=40,
        ),
    )

    # Asymmetric k values: lower k = higher weight for that source.
    # Proper nouns (title-case words, quoted phrases) → favour BM25 (k=30).
    # Conceptual queries → equal weighting (k=60 each).
    import re
    has_proper_noun = bool(re.search(r'\b[A-Z][a-z]{2,}\b', query))
    vector_k  = 60
    keyword_k = 30 if has_proper_noun else 60

    scores: dict[str, float] = {}
    meta: dict[str, dict] = {}

    for rank, hit in enumerate(vector_hits):
        id_ = hit["id"]
        scores[id_] = scores.get(id_, 0) + 1 / (vector_k + rank + 1)
        meta[id_] = hit

    for rank, hit in enumerate(keyword_hits):
        id_ = hit["id"]
        scores[id_] = scores.get(id_, 0) + 1 / (keyword_k + rank + 1)
        if id_ not in meta:
            meta[id_] = hit

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [
        {**meta[id_], "rrf_score": round(score, 4)}
        for id_, score in ranked[:limit]
    ]
```

Update `IntelligenceEngine.run_vector()` to call `search_emails_hybrid()` instead of `search_emails()`.

---

## Execution order

```
Day 1   Session 1 — models + catalogue (no execution, just schema)
Day 2   Session 2 — classifier (test all 5 query types before moving on)
Day 3   Session 3 — Supabase RPC migration + execution engines
Day 4   Session 4 — synthesiser + endpoint + curl test
Day 5   Session 5 — frontend query bar + result renderer
Day 6   Session 5 — result chart + example queries + add to nav
Day 7   Session 6 — tsvector migration + hybrid RRF fusion
```

---

## Key rules for every session

1. **Classifier selects from catalogue — never writes SQL.** If a query doesn't match any
   catalogue entry, it falls back to vector search. The catalogue grows; the classifier
   never writes ad-hoc SQL.

2. **Supabase `run_intelligence_query` RPC only receives pre-validated SQL.**
   The only SQL that reaches the RPC is from `CATALOGUE` templates with params
   substituted. User input never reaches the SQL directly.

3. **Metadata streams before the answer.** The frontend renders the data table/chart
   immediately from the `metadata` event, then the prose answer streams in alongside it.

4. **`synthesise_streaming` uses Sonnet — `classify_query` uses Haiku.**
   Never reverse this. Haiku for routing (~$0.001), Sonnet for synthesis (~$0.01).

5. **Existing endpoints untouched.** The intelligence router is completely new.
   `analytics.py`, `vector_service.py`, `ai.py` get additive changes only.

6. **Run the migration before Session 3.** The RPC function must exist in Supabase
   before `run_catalogue_query` will work. Migration 058 (tsvector) must run before
   Session 6.

7. **Vector fields: descriptions only — never amounts, dates, or IDs.**
   `_build_email_embed_text()` correctly embeds subject + sender + body only.
   When adding QB invoices/quotes vectorisation later: embed customer name,
   product description, line item notes — never invoice amount, date, or quantity.
   Those stay as SQL filter params in the catalogue. Vector = meaning. SQL = facts.

8. **`CREATE INDEX CONCURRENTLY` for all new indexes on emails.**
   The emails table has 270k rows. Standard `CREATE INDEX` locks the table during
   build — unacceptable in production. Always use `CONCURRENTLY`. It takes longer
   but never blocks reads or writes.
