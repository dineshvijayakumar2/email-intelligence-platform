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
