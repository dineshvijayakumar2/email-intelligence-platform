"""
LangChain Tools — Supabase-backed tools for the strategic digest agent.

Provides @tool-decorated functions that the LangGraph ReAct agent can invoke
to dig deeper into specific companies, contacts, threads, or quotes when
the pre-built context isn't sufficient.

Initialization:
    from .langchain_tools import init_langchain_tools
    init_langchain_tools(supabase_client)

All tools return formatted strings (not dicts) so the LLM can consume them
directly without JSON parsing.
"""

import logging
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level Supabase client (same init pattern as ai_usage_tracker)
# ---------------------------------------------------------------------------
_supabase = None


def init_langchain_tools(supabase_client):
    """Initialize the module-level Supabase client for all tools."""
    global _supabase
    _supabase = supabase_client
    logger.info("LangChain tools initialized with Supabase client")


def _get_client():
    """Get the Supabase client, raising if not initialized."""
    if _supabase is None:
        raise RuntimeError(
            "LangChain tools not initialized — call init_langchain_tools() first"
        )
    return _supabase


def _execute_with_retry(query_builder, max_retries: int = 3, base_delay: float = 2.0):
    """Execute a Supabase query with retry for transient errors."""
    import time

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return query_builder.execute()
        except Exception as e:
            last_error = e
            error_str = str(e)
            is_transient = any(kw in error_str for kw in [
                'SSL handshake failed', '525', '502', '503', '504',
                'Connection reset', 'Connection refused', 'timed out',
                'ECONNRESET', 'ETIMEDOUT', 'ConnectionTerminated',
            ])
            if is_transient and attempt < max_retries:
                import time
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Transient error (attempt {attempt + 1}), retrying in {delay}s"
                )
                time.sleep(delay)
                continue
            raise
    raise last_error


# ---------------------------------------------------------------------------
# Tool: Company Detail
# ---------------------------------------------------------------------------
@tool
def lookup_company_detail(company_name: str) -> str:
    """Look up full company profile by name from customer_companies and qb_customers.
    Returns company details including engagement score, tier, revenue, and account manager.
    Use this when you need deeper context about a specific company."""

    client = _get_client()
    lines = [f"=== Company Detail: {company_name} ==="]

    # 1. Search customer_companies (ilike for fuzzy match)
    try:
        resp = _execute_with_retry(
            client.table("customer_companies")
            .select("*")
            .ilike("company_name", f"%{company_name}%")
            .limit(5)
        )
        companies = resp.data or []
    except Exception as e:
        logger.error(f"lookup_company_detail — customer_companies query failed: {e}")
        companies = []

    if not companies:
        lines.append("No matching company found in customer_companies.")
    else:
        for c in companies:
            lines.append(f"\nCompany: {c.get('company_name', 'N/A')}")
            lines.append(f"  ID: {c.get('id')}")
            lines.append(f"  Domain: {c.get('domain', 'N/A')}")
            lines.append(f"  Industry: {c.get('industry', 'N/A')}")
            lines.append(f"  Customer Type: {c.get('customer_type', 'N/A')}")
            lines.append(f"  Engagement Score: {c.get('engagement_score', 'N/A')}")
            lines.append(f"  Email Count: {c.get('email_count', 0)}")
            lines.append(f"  Contact Count: {c.get('contact_count', 0)}")
            lines.append(f"  Last Activity: {c.get('last_activity_date', 'N/A')}")
            lines.append(f"  Created: {c.get('created_at', 'N/A')}")

    # 2. Search qb_customers for financial/tier data
    try:
        resp = _execute_with_retry(
            client.table("qb_customers")
            .select("*")
            .ilike("customer_name", f"%{company_name}%")
            .limit(5)
        )
        qb_customers = resp.data or []
    except Exception as e:
        logger.error(f"lookup_company_detail — qb_customers query failed: {e}")
        qb_customers = []

    if qb_customers:
        lines.append("\n--- Quickbase Financial Data ---")
        for qb in qb_customers:
            lines.append(f"  Customer: {qb.get('customer_name')}")
            lines.append(f"  Tier: {qb.get('customer_tier', 'N/A')}")
            lines.append(f"  Status: {qb.get('customer_status', 'N/A')}")
            lines.append(f"  Account Manager: {qb.get('account_manager', 'N/A')}")
            lines.append(f"  Total Invoiced: ${qb.get('total_invoiced', 0)}")
            lines.append(f"  Invoiced This Year: ${qb.get('invoiced_ty', 0)}")
            lines.append(f"  Invoiced Last Year: ${qb.get('invoiced_ly', 0)}")
            lines.append(f"  Invoiced Last 90d: ${qb.get('invoiced_l90d', 0)}")
            lines.append(f"  Growth 90d: {qb.get('growth_90d', 'N/A')}%")
            lines.append(f"  Cadence Score: {qb.get('cadence_score', 'N/A')}")
            lines.append(f"  Days Since Last Invoice: {qb.get('days_since_last_invoice', 'N/A')}")
    else:
        lines.append("\nNo Quickbase customer data found.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: Contact History
# ---------------------------------------------------------------------------
@tool
def lookup_contact_history(contact_email: str) -> str:
    """Look up contact profile and recent email history by email address.
    Returns contact details and the last 10 emails involving this contact.
    Use this when you need context about a specific person's communication."""

    client = _get_client()
    lines = [f"=== Contact History: {contact_email} ==="]

    # 1. Look up contact record
    try:
        resp = _execute_with_retry(
            client.table("customer_contacts")
            .select("*")
            .eq("email", contact_email)
            .limit(1)
        )
        contacts = resp.data or []
    except Exception as e:
        logger.error(f"lookup_contact_history — contacts query failed: {e}")
        contacts = []

    if contacts:
        c = contacts[0]
        lines.append(f"  Name: {c.get('first_name', '')} {c.get('last_name', '')}")
        lines.append(f"  Company ID: {c.get('customer_company_id', 'N/A')}")
        lines.append(f"  Role: {c.get('role', 'N/A')}")
        lines.append(f"  Contact Type: {c.get('contact_type', 'N/A')}")
        lines.append(f"  Engagement Score: {c.get('engagement_score', 'N/A')}")
        lines.append(f"  Email Count: {c.get('email_count', 0)}")
        lines.append(f"  Last Activity: {c.get('last_activity_date', 'N/A')}")
    else:
        lines.append("  No contact record found.")

    # 2. Recent emails (last 10)
    try:
        resp = _execute_with_retry(
            client.table("emails")
            .select("id,subject,from_address,to_addresses,date,is_outbound")
            .or_(
                f"from_address.ilike.%{contact_email}%,"
                f"to_addresses.ilike.%{contact_email}%"
            )
            .order("date", desc=True)
            .limit(10)
        )
        emails = resp.data or []
    except Exception as e:
        logger.error(f"lookup_contact_history — emails query failed: {e}")
        emails = []

    if emails:
        lines.append(f"\n--- Recent Emails ({len(emails)}) ---")
        for em in emails:
            direction = "OUT" if em.get("is_outbound") else "IN"
            lines.append(
                f"  [{direction}] {em.get('date', 'N/A')[:10]} | "
                f"{em.get('subject', '(no subject)')}"
            )
    else:
        lines.append("\n  No recent emails found.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: Thread Messages
# ---------------------------------------------------------------------------
@tool
def lookup_thread_messages(thread_id: str) -> str:
    """Look up all emails in a thread by thread_id.
    Returns a chronological summary of the thread conversation.
    Use this when you need to understand the full context of a discussion."""

    client = _get_client()
    lines = [f"=== Thread: {thread_id} ==="]

    try:
        resp = _execute_with_retry(
            client.table("emails")
            .select("id,subject,from_address,to_addresses,date,is_outbound,body_preview")
            .eq("thread_id", thread_id)
            .order("date", desc=False)
            .limit(50)
        )
        emails = resp.data or []
    except Exception as e:
        logger.error(f"lookup_thread_messages — query failed: {e}")
        return f"Error looking up thread {thread_id}: {e}"

    if not emails:
        lines.append("No emails found for this thread ID.")
        return "\n".join(lines)

    lines.append(f"Thread has {len(emails)} message(s)")
    lines.append(f"Subject: {emails[0].get('subject', '(no subject)')}")
    lines.append("")

    for i, em in enumerate(emails, 1):
        direction = "SENT" if em.get("is_outbound") else "RECEIVED"
        from_addr = em.get("from_address", "unknown")
        date_str = em.get("date", "N/A")[:16]
        subject = em.get("subject", "(no subject)")
        preview = em.get("body_preview", "")
        # Truncate preview to 200 chars
        if preview and len(preview) > 200:
            preview = preview[:200] + "..."

        lines.append(f"  [{i}] {direction} | {date_str} | From: {from_addr}")
        lines.append(f"       Subject: {subject}")
        if preview:
            lines.append(f"       Preview: {preview}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: Quote Detail
# ---------------------------------------------------------------------------
@tool
def lookup_quote_detail(quote_no: str) -> str:
    """Look up a Quickbase quote by quote number, including linked job details.
    Returns quote value, status, contact, and any associated job information.
    Use this when you need details about a specific quote or proposal."""

    client = _get_client()
    lines = [f"=== Quote Detail: {quote_no} ==="]

    # 1. Look up quote
    try:
        resp = _execute_with_retry(
            client.table("qb_quotes")
            .select("*")
            .eq("quote_no", quote_no)
            .limit(5)
        )
        quotes = resp.data or []
    except Exception as e:
        logger.error(f"lookup_quote_detail — qb_quotes query failed: {e}")
        return f"Error looking up quote {quote_no}: {e}"

    if not quotes:
        lines.append("No quote found with this number.")
        return "\n".join(lines)

    for q in quotes:
        lines.append(f"  Quote No: {q.get('quote_no')}")
        lines.append(f"  AM: {q.get('quote_am_name', 'N/A')}")
        lines.append(f"  Sell (ex tax): ${q.get('sell_ex_tax', 0)}")
        lines.append(f"  Date Created: {q.get('date_created', 'N/A')}")
        lines.append(f"  Date Accepted: {q.get('date_accepted', 'N/A')}")
        lines.append(f"  Category: {q.get('category', 'N/A')}")
        lines.append(f"  Contact: {q.get('contact_name', 'N/A')} ({q.get('contact_email', 'N/A')})")
        lines.append(f"  Has Job: {q.get('has_job', False)}")
        lines.append(f"  Job No: {q.get('job_no', 'N/A')}")
        lines.append(f"  Quantity: {q.get('quantity', 'N/A')} | Kinds: {q.get('kinds', 'N/A')}")

        # 2. Look up linked job if exists
        job_no = q.get("job_no")
        if job_no:
            try:
                job_resp = _execute_with_retry(
                    client.table("qb_jobs")
                    .select("*")
                    .eq("job_no", job_no)
                    .limit(1)
                )
                jobs = job_resp.data or []
            except Exception as e:
                logger.error(f"lookup_quote_detail — qb_jobs query failed: {e}")
                jobs = []

            if jobs:
                j = jobs[0]
                lines.append(f"\n  --- Linked Job: {job_no} ---")
                lines.append(f"    Status: {j.get('job_status', 'N/A')}")
                lines.append(f"    Retail Sale: ${j.get('retail_sale', 0)}")
                lines.append(f"    Invoiced Margin: ${j.get('invoiced_margin', 0)}")
                lines.append(f"    Margin %: {j.get('margin_pct', 'N/A')}%")
                lines.append(f"    Accepted Date: {j.get('accepted_date', 'N/A')}")
                lines.append(f"    Due Date: {j.get('due_date', 'N/A')}")
                lines.append(f"    Rush Level: {j.get('factory_rush_level', 'N/A')}")
                lines.append(f"    Pieces: {j.get('pieces_ordered', 'N/A')} | Kinds: {j.get('kinds_ordered', 'N/A')}")

    return "\n".join(lines)


# ===========================================================================
# Semantic Search Tools (Sprint 4 S4.4 — requires pgvector + embeddings)
# ===========================================================================

@tool
def semantic_search_emails(query: str) -> str:
    """Search email intelligence records semantically.

    Use this when you need to find emails about a specific topic, customer concern,
    or business context that can't be found by exact name matching.

    Args:
        query: Natural language search query (e.g. "delayed delivery complaints",
               "wide format printing quote follow-up")

    Returns:
        Formatted list of matching emails with subject, summary, intent, and similarity score.
    """
    import asyncio
    from .vector_service import VectorService

    client = _get_client()
    vs = VectorService(client)

    try:
        results = asyncio.get_event_loop().run_until_complete(
            vs.search_emails(query, threshold=0.6, limit=8)
        )
    except RuntimeError:
        # Already in async context — use thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            results = pool.submit(
                lambda: asyncio.run(vs.search_emails(query, threshold=0.6, limit=8))
            ).result()
    except Exception as e:
        logger.error(f"semantic_search_emails failed: {e}")
        return f"Semantic search failed: {e}"

    if not results:
        return f"No emails found matching '{query}'"

    lines = [f"Found {len(results)} emails matching '{query}':\n"]
    for r in results:
        lines.append(f"  Subject: {r.get('email_subject', 'N/A')}")
        lines.append(f"  Summary: {r.get('ai_summary', 'N/A')}")
        lines.append(f"  Intent: {r.get('intent', 'N/A')} | Urgency: {r.get('urgency', 'N/A')}")
        lines.append(f"  Similarity: {r.get('similarity', 0):.2f}")
        lines.append("")
    return "\n".join(lines)


@tool
def semantic_search_operations(query: str) -> str:
    """Search QB operations (production/finishing/outsource records) semantically.

    Use this when you need to find what products/services a company has ordered,
    what capabilities have been used, or search for specific production processes.

    Args:
        query: Natural language search query (e.g. "embellishment foil stamping",
               "wide format banner printing", "soft cover book binding")

    Returns:
        Formatted list of matching operations with name, department, machine,
        customer, capability tags, and similarity score.
    """
    import asyncio
    from .vector_service import VectorService

    client = _get_client()
    vs = VectorService(client)

    try:
        results = asyncio.get_event_loop().run_until_complete(
            vs.search_operations(query, threshold=0.6, limit=10)
        )
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            results = pool.submit(
                lambda: asyncio.run(vs.search_operations(query, threshold=0.6, limit=10))
            ).result()
    except Exception as e:
        logger.error(f"semantic_search_operations failed: {e}")
        return f"Semantic search failed: {e}"

    if not results:
        return f"No operations found matching '{query}'"

    lines = [f"Found {len(results)} operations matching '{query}':\n"]
    for r in results:
        tags = r.get('capability_tags', [])
        tag_str = ', '.join(tags) if isinstance(tags, list) and tags else 'unclassified'
        lines.append(f"  Operation: {r.get('operation_name', 'N/A')}")
        lines.append(f"  Dept: {r.get('department', 'N/A')} | Machine: {r.get('machine', 'N/A')}")
        lines.append(f"  Customer: {r.get('customer_name', 'N/A')}")
        lines.append(f"  Capabilities: {tag_str} | Type: {r.get('row_type', 'N/A')}")
        lines.append(f"  Similarity: {r.get('similarity', 0):.2f}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 7: Portfolio Summary — aggregate account health
# ---------------------------------------------------------------------------

@tool
def portfolio_summary() -> str:
    """Get a high-level summary of the account portfolio.

    Returns total accounts, engagement breakdown, revenue summary, and
    accounts not contacted recently. Use this to answer questions like
    "how is our portfolio doing?" or "how many accounts are at risk?".

    Returns:
        Portfolio health summary with key metrics
    """
    sb = _get_client()
    try:
        # Fetch all companies with key metrics
        all_companies = []
        offset = 0
        while True:
            resp = sb.table('customer_companies').select(
                'company_name, engagement_score, last_contact_date, '
                'total_emails, contact_count, '
                'qb_total_revenue, qb_tier, qb_growth_90d, qb_days_since_last_invoice'
            ).range(offset, offset + 999).execute()
            rows = resp.data or []
            all_companies.extend(rows)
            if len(rows) == 0:
                break
            offset += len(rows)

        if not all_companies:
            return "No companies found in the portfolio."

        from datetime import datetime, timedelta
        now = datetime.utcnow()
        cutoff_90 = (now - timedelta(days=90)).isoformat()
        cutoff_30 = (now - timedelta(days=30)).isoformat()

        total = len(all_companies)
        with_revenue = [c for c in all_companies if c.get('qb_total_revenue')]
        total_revenue = sum(float(c.get('qb_total_revenue') or 0) for c in all_companies)
        avg_engagement = sum(c.get('engagement_score') or 0 for c in all_companies) / max(total, 1)

        # Contact recency
        not_contacted_90d = sum(1 for c in all_companies
                                if c.get('last_contact_date') and str(c['last_contact_date']) < cutoff_90)
        not_contacted_30d = sum(1 for c in all_companies
                                if c.get('last_contact_date') and str(c['last_contact_date']) < cutoff_30)
        no_contact_date = sum(1 for c in all_companies if not c.get('last_contact_date'))

        # Engagement tiers
        high_eng = sum(1 for c in all_companies if (c.get('engagement_score') or 0) >= 70)
        med_eng = sum(1 for c in all_companies if 30 <= (c.get('engagement_score') or 0) < 70)
        low_eng = sum(1 for c in all_companies if (c.get('engagement_score') or 0) < 30)

        lines = [
            f"PORTFOLIO SUMMARY ({total} accounts)",
            f"",
            f"Revenue: ${total_revenue:,.0f} total across {len(with_revenue)} accounts with QB data",
            f"Avg Engagement Score: {avg_engagement:.0f}/100",
            f"",
            f"Engagement: {high_eng} high (70+), {med_eng} medium (30-69), {low_eng} low (<30)",
            f"",
            f"Contact Recency:",
            f"  Not contacted in 90+ days: {not_contacted_90d} accounts",
            f"  Not contacted in 30+ days: {not_contacted_30d} accounts",
            f"  No contact date recorded: {no_contact_date} accounts",
        ]
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"portfolio_summary failed: {e}")
        return f"Failed to get portfolio summary: {e}"


# ---------------------------------------------------------------------------
# Tool 8: Account Ranking — top/bottom accounts by metric
# ---------------------------------------------------------------------------

@tool
def account_ranking(metric: str, limit: int = 10) -> str:
    """Rank accounts by a specific metric. Returns the top N accounts.

    Use this to answer questions like "top 5 customers by revenue",
    "which accounts are most at risk", "who hasn't been contacted recently",
    "accounts with highest engagement".

    Args:
        metric: One of: "revenue", "engagement", "growth",
                "days_since_contact", "days_since_invoice", "email_volume"
        limit: Number of accounts to return (default 10, max 25)

    Returns:
        Ranked list of accounts with key metrics
    """
    sb = _get_client()
    limit = min(limit, 25)

    # Map metric to sort column and direction
    METRIC_MAP = {
        'revenue': ('qb_total_revenue', True),
        'engagement': ('engagement_score', True),
        'growth': ('qb_growth_90d', True),
        'days_since_contact': ('last_contact_date', False),  # oldest first
        'days_since_invoice': ('qb_days_since_last_invoice', True),  # highest days first
        'email_volume': ('total_emails', True),
    }

    if metric not in METRIC_MAP:
        return f"Unknown metric '{metric}'. Use one of: {', '.join(METRIC_MAP.keys())}"

    sort_col, desc = METRIC_MAP[metric]

    try:
        query = sb.table('customer_companies').select(
            'company_name, engagement_score, total_emails, contact_count, '
            'last_contact_date, qb_total_revenue, qb_tier, qb_growth_90d, '
            'qb_days_since_last_invoice, qb_account_manager'
        )

        # Filter out nulls for the sorted column
        if sort_col in ('qb_total_revenue', 'qb_growth_90d', 'qb_days_since_last_invoice'):
            query = query.not_.is_(sort_col, 'null')
        if sort_col == 'last_contact_date' and not desc:
            query = query.not_.is_('last_contact_date', 'null')

        query = query.order(sort_col, desc=desc).limit(limit)
        result = query.execute()

        companies = result.data or []
        if not companies:
            return f"No accounts found for metric '{metric}'."

        from datetime import datetime
        now = datetime.utcnow()

        lines = [f"TOP {len(companies)} ACCOUNTS BY {metric.upper().replace('_', ' ')}:\n"]
        for i, c in enumerate(companies, 1):
            name = c.get('company_name', 'Unknown')
            revenue = c.get('qb_total_revenue')
            eng = c.get('engagement_score') or 0
            tier = c.get('qb_tier') or '-'
            growth = c.get('qb_growth_90d')
            last_contact = c.get('last_contact_date')
            emails = c.get('total_emails') or 0
            am = c.get('qb_account_manager') or '-'

            days_since = ''
            if last_contact:
                try:
                    lcd = datetime.fromisoformat(str(last_contact).replace('Z', '+00:00')).replace(tzinfo=None)
                    days_since = f" ({(now - lcd).days}d ago)"
                except Exception:
                    pass

            line = f"  {i}. {name}"
            if revenue is not None:
                line += f" | ${float(revenue):,.0f}"
            line += f" | Eng: {eng}"
            if growth is not None:
                line += f" | Growth: {float(growth):+.1f}%"
            line += f" | {emails} emails"
            if days_since:
                line += f" | Last contact{days_since}"
            line += f" | Tier: {tier} | AM: {am}"
            lines.append(line)

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"account_ranking failed: {e}")
        return f"Failed to rank accounts: {e}"
