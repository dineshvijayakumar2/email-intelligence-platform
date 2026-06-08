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
            .select("id, company_name, industry, engagement_score, contact_count, created_at")
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
            .select("customer_name, customer_tier, customer_status, account_manager, "
                    "total_invoiced, invoiced_ty, invoiced_ly, invoiced_l90d, "
                    "growth_90d, cadence_score, days_since_last_invoice")
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
            .select("first_name, last_name, customer_company_id, contact_type, engagement_score")
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
            .select("quote_no, quote_am_name, sell_ex_tax, date_created, date_accepted, "
                    "category, contact_name, contact_email, has_job, job_no, quantity, kinds")
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
                    .select("job_status, retail_sale, invoiced_margin, margin_pct, "
                            "accepted_date, due_date, factory_rush_level, "
                            "pieces_ordered, kinds_ordered")
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


# ---------------------------------------------------------------------------
# Tool 9: Email Search (filtered) — search by date, sender, urgency, intent
# ---------------------------------------------------------------------------

@tool
def search_emails(query_type: str, value: str = "", limit: int = 15) -> str:
    """Search and filter emails by various criteria.

    Use this when the user asks about recent emails, urgent emails, emails
    from a specific sender, emails about specific topics, or needs to find
    emails by intent/urgency.

    Args:
        query_type: One of: "recent" (latest emails), "urgent" (high/critical urgency),
                    "sender:<email>" (from specific sender), "intent:<type>" (by intent),
                    "company:<name>" (for a company), "signal:<type>" (business signals),
                    "unresponded" (awaiting our response)
        value: Additional filter value (e.g., email address, company name)
        limit: Max results (default 15, max 25)

    Returns:
        List of matching emails with subject, sender, date, urgency, intent, summary
    """
    sb = _get_client()
    limit = min(limit, 25)

    try:
        # Base query: emails + AI intelligence
        cols = ('e.id, e.subject, e.sender_email, e.sender_name, e.sent_date, '
                'e.is_outbound, ai.intent, ai.urgency, ai.summary, ai.primary_bucket, '
                'ai.business_signal, ai.action_type')

        # We need to query emails table and join with ai_email_intelligence
        # Since Supabase doesn't support JOINs directly, query both tables
        if query_type == "recent":
            resp = sb.table('emails').select(
                'id, subject, sender_email, sender_name, sent_date, is_outbound'
            ).order('sent_date', desc=True).limit(limit).execute()

        elif query_type == "company" and value:
            # Find company first
            comp = sb.table('customer_companies').select('id').ilike(
                'company_name', f'%{value}%'
            ).limit(1).execute()
            if not comp.data:
                return f"Company '{value}' not found."
            comp_id = comp.data[0]['id']
            resp = sb.table('emails').select(
                'id, subject, sender_email, sender_name, sent_date, is_outbound'
            ).eq('customer_company_id', comp_id).order('sent_date', desc=True).limit(limit).execute()

        elif query_type.startswith("sender"):
            sender = value or query_type.split(":", 1)[-1] if ":" in query_type else value
            resp = sb.table('emails').select(
                'id, subject, sender_email, sender_name, sent_date, is_outbound'
            ).ilike('sender_email', f'%{sender}%').order('sent_date', desc=True).limit(limit).execute()

        else:
            # For urgency/intent/signal/unresponded — query AI intelligence table
            ai_query = sb.table('ai_email_intelligence').select(
                'email_id, intent, urgency, summary, primary_bucket, business_signal, action_type'
            )

            if query_type == "urgent":
                ai_query = ai_query.in_('urgency', ['critical', 'high'])
            elif query_type.startswith("intent"):
                intent_val = value or query_type.split(":", 1)[-1] if ":" in query_type else value
                ai_query = ai_query.eq('intent', intent_val)
            elif query_type.startswith("signal"):
                signal_val = value or query_type.split(":", 1)[-1] if ":" in query_type else value
                ai_query = ai_query.eq('business_signal', signal_val)
            elif query_type == "unresponded":
                ai_query = ai_query.eq('action_type', 'respond_to_inquiry')
            else:
                return f"Unknown query_type '{query_type}'. Use: recent, urgent, sender, intent, company, signal, unresponded"

            ai_query = ai_query.order('created_at', desc=True).limit(limit)
            ai_resp = ai_query.execute()
            ai_data = ai_resp.data or []

            if not ai_data:
                return f"No emails found for {query_type}."

            # Fetch email details for AI results
            email_ids = [r['email_id'] for r in ai_data if r.get('email_id')]
            if not email_ids:
                return f"No emails found for {query_type}."

            resp = sb.table('emails').select(
                'id, subject, sender_email, sender_name, sent_date, is_outbound'
            ).in_('id', email_ids[:25]).execute()

            # Merge AI data with email data
            email_map = {e['id']: e for e in (resp.data or [])}
            lines = [f"Found {len(ai_data)} emails ({query_type}):\n"]
            for ai in ai_data:
                e = email_map.get(ai.get('email_id'), {})
                direction = "OUT" if e.get('is_outbound') else "IN"
                lines.append(f"  [{direction}] {e.get('subject', 'N/A')}")
                lines.append(f"  From: {e.get('sender_name', '')} <{e.get('sender_email', 'N/A')}>")
                lines.append(f"  Date: {str(e.get('sent_date', ''))[:16]}")
                lines.append(f"  Urgency: {ai.get('urgency', '-')} | Intent: {ai.get('intent', '-')}")
                lines.append(f"  Signal: {ai.get('business_signal', '-')} | Action: {ai.get('action_type', '-')}")
                if ai.get('summary'):
                    lines.append(f"  Summary: {ai['summary'][:150]}")
                lines.append("")
            return "\n".join(lines)

        # Format basic email results (no AI join)
        emails = resp.data or []
        if not emails:
            return f"No emails found for {query_type}."

        lines = [f"Found {len(emails)} emails ({query_type}):\n"]
        for e in emails:
            direction = "OUT" if e.get('is_outbound') else "IN"
            lines.append(f"  [{direction}] {e.get('subject', 'N/A')}")
            lines.append(f"  From: {e.get('sender_name', '')} <{e.get('sender_email', 'N/A')}>")
            lines.append(f"  Date: {str(e.get('sent_date', ''))[:16]}")
            lines.append("")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"search_emails failed: {e}")
        return f"Email search failed: {e}"


# ---------------------------------------------------------------------------
# Tool 10: Contact Search — find contacts by role, engagement, company
# ---------------------------------------------------------------------------

@tool
def search_contacts(filter_type: str, value: str = "", limit: int = 15) -> str:
    """Search and filter contacts across the portfolio.

    Use this to find decision makers, contacts at a company, high-engagement
    contacts, or contacts by role/seniority.

    Args:
        filter_type: One of: "decision_makers" (c-level/vp/director),
                     "company:<name>" (all contacts at a company),
                     "role:<role>" (by functional_role: executive, sales, operations, etc.),
                     "low_engagement" (engagement < 30),
                     "inactive" (no emails in 90+ days),
                     "all" (all contacts sorted by engagement)
        value: Additional filter (e.g., company name)
        limit: Max results (default 15, max 25)

    Returns:
        List of contacts with name, email, role, engagement, email counts
    """
    sb = _get_client()
    limit = min(limit, 25)
    SELECT = ('email_address, full_name, functional_role, seniority_level, '
              'is_decision_maker, engagement_score, total_emails_sent, '
              'total_emails_received, last_contacted_at, job_title, department')

    try:
        query = sb.table('customer_contacts').select(SELECT)

        if filter_type == "decision_makers":
            query = query.eq('is_decision_maker', True).order('engagement_score', desc=True)
        elif filter_type.startswith("company"):
            name = value or filter_type.split(":", 1)[-1] if ":" in filter_type else value
            comp = sb.table('customer_companies').select('id').ilike(
                'company_name', f'%{name}%'
            ).limit(1).execute()
            if not comp.data:
                return f"Company '{name}' not found."
            query = query.eq('customer_company_id', comp.data[0]['id']).order('engagement_score', desc=True)
        elif filter_type.startswith("role"):
            role = value or filter_type.split(":", 1)[-1] if ":" in filter_type else value
            query = query.eq('functional_role', role).order('engagement_score', desc=True)
        elif filter_type == "low_engagement":
            query = query.lt('engagement_score', 30).order('engagement_score', desc=False)
        elif filter_type == "inactive":
            from datetime import datetime, timedelta
            cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
            query = query.lt('last_contacted_at', cutoff).order('last_contacted_at', desc=False)
        elif filter_type == "all":
            query = query.order('engagement_score', desc=True)
        else:
            return f"Unknown filter '{filter_type}'. Use: decision_makers, company:<name>, role:<role>, low_engagement, inactive, all"

        result = query.limit(limit).execute()
        contacts = result.data or []

        if not contacts:
            return f"No contacts found for {filter_type}."

        lines = [f"Found {len(contacts)} contacts ({filter_type}):\n"]
        for c in contacts:
            name = c.get('full_name') or c.get('email_address', 'Unknown')
            email = c.get('email_address', '')
            role = c.get('functional_role', '-')
            seniority = c.get('seniority_level', '-')
            eng = c.get('engagement_score') or 0
            sent = c.get('total_emails_sent') or 0
            received = c.get('total_emails_received') or 0
            title = c.get('job_title') or ''
            dm = " [Decision Maker]" if c.get('is_decision_maker') else ""

            lines.append(f"  {name}{dm}")
            lines.append(f"  Email: {email} | Role: {role} ({seniority})")
            if title:
                lines.append(f"  Title: {title}")
            lines.append(f"  Engagement: {eng}/100 | Emails: {sent} sent, {received} received")
            lines.append("")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"search_contacts failed: {e}")
        return f"Contact search failed: {e}"


# ---------------------------------------------------------------------------
# Tool 11: Thread Overview — overdue, active, status counts
# ---------------------------------------------------------------------------

@tool
def thread_overview(filter_type: str = "summary", company_name: str = "") -> str:
    """Get email thread status overview or details.

    Use this to answer questions about overdue threads, response health,
    or thread status for a specific company.

    Args:
        filter_type: One of: "summary" (counts by status), "overdue" (overdue threads),
                     "active" (active threads), "company" (threads for a company)
        company_name: Company name (used with "company" filter)

    Returns:
        Thread status summary or list of threads
    """
    sb = _get_client()

    try:
        if filter_type == "summary":
            # Get counts by status
            all_threads = []
            offset = 0
            while True:
                resp = sb.table('thread_status').select(
                    'status, is_overdue'
                ).range(offset, offset + 999).execute()
                rows = resp.data or []
                all_threads.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            if not all_threads:
                return "No thread data available."

            from collections import Counter
            status_counts = Counter(t.get('status', 'unknown') for t in all_threads)
            overdue_count = sum(1 for t in all_threads if t.get('is_overdue'))

            lines = [f"THREAD STATUS OVERVIEW ({len(all_threads)} total threads):\n"]
            for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
                lines.append(f"  {status}: {count}")
            lines.append(f"\n  Overdue: {overdue_count}")
            return "\n".join(lines)

        elif filter_type == "overdue":
            resp = sb.table('thread_status').select(
                'subject, status, days_since_last_email, message_count, last_email_date'
            ).eq('is_overdue', True).order('days_since_last_email', desc=True).limit(20).execute()

        elif filter_type == "active":
            resp = sb.table('thread_status').select(
                'subject, status, days_since_last_email, message_count, last_email_date'
            ).in_('status', ['awaiting_reply', 'outbound_pending']).order(
                'last_email_date', desc=True
            ).limit(20).execute()

        elif filter_type == "company" and company_name:
            comp = sb.table('customer_companies').select('id').ilike(
                'company_name', f'%{company_name}%'
            ).limit(1).execute()
            if not comp.data:
                return f"Company '{company_name}' not found."
            resp = sb.table('thread_status').select(
                'subject, status, days_since_last_email, message_count, last_email_date, is_overdue'
            ).eq('customer_company_id', comp.data[0]['id']).order(
                'last_email_date', desc=True
            ).limit(20).execute()

        else:
            return f"Unknown filter '{filter_type}'. Use: summary, overdue, active, company"

        threads = resp.data or []
        if not threads:
            return f"No threads found for {filter_type}."

        lines = [f"Found {len(threads)} threads ({filter_type}):\n"]
        for t in threads:
            overdue_tag = " [OVERDUE]" if t.get('is_overdue') else ""
            lines.append(f"  {t.get('subject', 'No subject')}{overdue_tag}")
            lines.append(f"  Status: {t.get('status', '-')} | "
                        f"Messages: {t.get('message_count', 0)} | "
                        f"Days since: {t.get('days_since_last_email', '?')}")
            lines.append("")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"thread_overview failed: {e}")
        return f"Thread overview failed: {e}"


# ---------------------------------------------------------------------------
# Tool 12: Company Analytics — strike rate, seasonality, rhythm
# ---------------------------------------------------------------------------

@tool
def company_analytics(company_name: str, analysis: str = "all") -> str:
    """Get deep analytics for a specific company — strike rate, seasonality,
    ordering rhythm, and contact capabilities.

    Use this when the user asks about a company's ordering patterns, quote
    conversion rate, which contacts order what, or reorder timing.

    Args:
        company_name: Company name (partial match OK)
        analysis: One of: "all" (everything), "strike_rate" (quote conversion),
                  "seasonality" (monthly/quarterly patterns), "rhythm" (reorder intervals),
                  "capabilities" (what each contact orders),
                  "qb_tags" (QB-maintained capability/process/embellishment summary)

    Returns:
        Detailed analytics for the company
    """
    sb = _get_client()

    try:
        # Find company
        comp = sb.table('customer_companies').select('id, client_id, company_name').ilike(
            'company_name', f'%{company_name}%'
        ).limit(1).execute()
        if not comp.data:
            return f"Company '{company_name}' not found."

        company = comp.data[0]
        comp_id = company['id']
        client_id = company['client_id']

        from .customer_analytics_service import CustomerAnalyticsService
        service = CustomerAnalyticsService(sb, client_id)
        lines = [f"ANALYTICS FOR {company['company_name']}:\n"]

        analyses = [analysis] if analysis != "all" else ["strike_rate", "seasonality", "rhythm", "capabilities", "qb_tags"]

        for a in analyses:
            try:
                if a == "strike_rate":
                    data = service.get_strike_rate(comp_id, force=False)
                    total = data.get('company_total', {})
                    lines.append(f"STRIKE RATE (Quote Conversion):")
                    lines.append(f"  Total quotes: {total.get('total_quotes', 0)}")
                    lines.append(f"  Converted to jobs: {total.get('converted', 0)}")
                    lines.append(f"  Strike rate: {total.get('strike_rate_pct', 0):.1f}%")
                    by_contact = data.get('by_contact', [])[:5]
                    if by_contact:
                        lines.append(f"  Top contacts by conversion:")
                        for c in by_contact:
                            lines.append(f"    {c['contact_name']}: {c['strike_rate_pct']:.0f}% ({c['converted']}/{c['total_quotes']})")
                    lines.append("")

                elif a == "seasonality":
                    data = service.get_seasonality(comp_id, force=False)
                    peaks = data.get('peak_months', [])
                    troughs = data.get('trough_months', [])
                    lines.append(f"SEASONALITY (Ordering Patterns):")
                    lines.append(f"  Total orders: {data.get('total_orders', 0)}")
                    if peaks:
                        month_names = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                                      7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
                        lines.append(f"  Peak months: {', '.join(month_names.get(m,'?') for m in peaks)}")
                    if troughs:
                        lines.append(f"  Trough months: {', '.join(month_names.get(m,'?') for m in troughs)}")
                    monthly = data.get('monthly', [])
                    if monthly:
                        lines.append(f"  Monthly breakdown:")
                        for m in monthly:
                            lines.append(f"    {m['month_name']}: {m['order_count']} orders, ${m['revenue']:,.0f}")
                    lines.append("")

                elif a == "rhythm":
                    data = service.get_capability_rhythm(comp_id, force=False)
                    rhythms = data.get('rhythms', [])
                    alerts = data.get('alerts', [])
                    lines.append(f"ORDERING RHYTHM (Reorder Intervals):")
                    for r in rhythms:
                        status_icon = {"overdue": "!!", "due_soon": "!", "on_track": "OK"}.get(r.get('status'), "?")
                        interval = f"every {r['avg_interval_days']}d" if r.get('avg_interval_days') else "insufficient data"
                        lines.append(f"  [{status_icon}] {r['capability']}: {interval}, "
                                    f"last order {r.get('days_since_last', '?')}d ago "
                                    f"({r['order_count']} orders)")
                    if alerts:
                        lines.append(f"  ALERTS:")
                        for al in alerts:
                            lines.append(f"    {al['capability']}: {al['overdue_days']}d overdue [{al['severity']}]")
                    lines.append("")

                elif a == "capabilities":
                    data = service.get_contact_capabilities(comp_id, force=False)
                    contacts = data.get('contacts', [])[:10]
                    lines.append(f"CONTACT CAPABILITIES (Who orders what):")
                    for c in contacts:
                        caps = c.get('capabilities', [])
                        cap_str = ', '.join(f"{cap['tag']}({cap['order_count']})" for cap in caps[:5])
                        lines.append(f"  {c['contact_name']}: {cap_str}")
                    lines.append("")

                elif a == "qb_tags":
                    # QB-maintained capability/process/embellishment summary from Unique Emails
                    # FRAGILE (mixed-space ID): customer_companies.qb_customer_id may hold a
                    # customer_key_id OR a qb_record_id depending on which path wrote it. This
                    # join assumes record-id space; a key-id-stamped row resolves to nothing.
                    # Canonical, name-aware resolution is resolve_qb() in
                    # scripts/db/merge_duplicate_companies.py — the standing rule until Option A
                    # (normalize-on-write to customer_key_id) lands.
                    # Translate qb_record_id → customer_key_id (field 92) for unique email lookup
                    qb_cid_resp = sb.table('customer_companies').select('qb_customer_id').eq('id', comp_id).limit(1).execute()
                    qb_record_id = (qb_cid_resp.data[0].get('qb_customer_id') or '') if qb_cid_resp.data else ''
                    qb_cid = ''
                    if qb_record_id:
                        key_resp = sb.table('qb_customers').select('customer_key_id').eq(
                            'client_id', client_id
                        ).eq('qb_record_id', qb_record_id).limit(1).execute()
                        qb_cid = (key_resp.data[0].get('customer_key_id') or '') if key_resp.data else ''
                        if not qb_cid:
                            logger.warning(
                                "qb_customer_id=%s on company %s did not resolve to a "
                                "qb_customers row via qb_record_id space (mixed key_id/record_id "
                                "field; see resolve_qb in scripts/db/merge_duplicate_companies.py). "
                                "QB tags skipped.", qb_record_id, comp_id)
                    if not qb_cid:
                        lines.append("QB TAGS: Company not linked to QB customer")
                        lines.append("")
                    else:
                        ue_resp = sb.table('qb_unique_emails').select(
                            'email, capabilities_used, processes_used, embellishments_used'
                        ).eq('client_id', client_id).eq('qb_customer_id', qb_cid).eq('hide', False).execute()
                        all_caps, all_procs, all_emb = set(), set(), set()
                        per_contact = []
                        for r in (ue_resp.data or []):
                            email = r.get('email', '')
                            caps = [v.strip() for v in (r.get('capabilities_used') or '').split('|') if v.strip()]
                            procs = [v.strip() for v in (r.get('processes_used') or '').split('|') if v.strip()]
                            embs = [v.strip() for v in (r.get('embellishments_used') or '').split('|') if v.strip()]
                            all_caps.update(caps)
                            all_procs.update(procs)
                            all_emb.update(embs)
                            if caps or procs or embs:
                                per_contact.append({'email': email, 'caps': caps, 'procs': procs, 'embs': embs})

                        lines.append(f"QB TAGS (Maintained in QuickBase, {len(ue_resp.data or [])} emails):")
                        lines.append(f"  Capabilities: {', '.join(sorted(all_caps)) or 'none'}")
                        lines.append(f"  Processes: {', '.join(sorted(all_procs)) or 'none'}")
                        lines.append(f"  Embellishments: {', '.join(sorted(all_emb)) or 'none'}")
                        if per_contact:
                            lines.append(f"  Per contact (top 5):")
                            for pc in per_contact[:5]:
                                tags = ', '.join(pc['caps'][:3] + pc['procs'][:2] + pc['embs'][:2])
                                lines.append(f"    {pc['email']}: {tags}")
                        lines.append("")

            except Exception as e:
                lines.append(f"  [{a}]: Failed — {str(e)[:100]}")
                lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"company_analytics failed: {e}")
        return f"Company analytics failed: {e}"
