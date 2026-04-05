"""
AI Insights Engine — On-demand per-entity AI analysis (Sprint 3).

Provides "Analyze" button functionality on company/contact/thread detail pages.
Uses LangChain with the cheap model (Gemini free tier or Haiku) for fast,
per-entity insights. Results cached 24h.

Endpoints:
    GET /v1/ai/insights/company/{company_id}
    GET /v1/ai/insights/contact/{contact_id}
    GET /v1/ai/insights/thread/{thread_id}
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage

from .langchain_core import get_cheap_llm, get_model_config
from ..utils.number_format import get_client_currency_code, format_currency

logger = logging.getLogger(__name__)

# Cache TTL
CACHE_TTL_HOURS = 24

# System prompts per entity type
COMPANY_INSIGHT_PROMPT = """You are a business intelligence analyst. Analyze this company's relationship health based on email communication patterns and business data.

Return JSON with:
{
  "health_summary": "2-3 sentence assessment of this relationship",
  "revenue_risk": "low" | "medium" | "high" | "unknown",
  "key_observations": ["observation 1", "observation 2", "observation 3"],
  "recommended_actions": ["action 1", "action 2"],
  "engagement_trend": "improving" | "stable" | "declining" | "unknown"
}

Be factual. Base analysis on the data provided. Never invent data."""

CONTACT_INSIGHT_PROMPT = """You are a business intelligence analyst. Analyze this contact's engagement and importance based on email patterns and business data.

Return JSON with:
{
  "engagement_summary": "2-3 sentence assessment of this contact",
  "importance_level": "critical" | "high" | "medium" | "low",
  "key_observations": ["observation 1", "observation 2"],
  "follow_up_suggestion": "specific recommended next step",
  "engagement_trend": "improving" | "stable" | "declining" | "unknown"
}

Be factual. Never invent data."""

THREAD_INSIGHT_PROMPT = """You are a business intelligence analyst. Analyze this email thread to assess deal probability, risk, and recommended next steps.

Return JSON with:
{
  "thread_summary": "2-3 sentence summary of the thread",
  "deal_probability": number 0-100 or null if not deal-related,
  "risk_level": "low" | "medium" | "high" | "none",
  "key_signals": ["signal 1", "signal 2"],
  "recommended_action": "specific next step for the account manager"
}

Be factual. Never invent data."""


class AIInsightsEngine:
    """Generate on-demand AI insights for companies, contacts, and threads."""

    def __init__(self, supabase_client, client_id: Optional[str] = None):
        self._supabase = supabase_client
        self._client_id = client_id

    async def get_company_insight(self, company_id: str, force: bool = False) -> Optional[dict]:
        """Generate or return cached AI insight for a company."""
        # Check cache first
        if not force:
            cached = self._get_cached_insight("company", company_id)
            if cached:
                return cached

        # Gather context
        context = self._gather_company_context(company_id)
        if not context:
            return None

        # Generate insight
        from .ai_prompt_loader import get_prompt, PROMPT_KEY_INSIGHT_COMPANY
        prompt = get_prompt(self._supabase, PROMPT_KEY_INSIGHT_COMPANY, COMPANY_INSIGHT_PROMPT, self._client_id)
        result = self._generate_insight(prompt, context, "company", company_id)
        return result

    async def get_contact_insight(self, contact_id: str, force: bool = False) -> Optional[dict]:
        """Generate or return cached AI insight for a contact."""
        if not force:
            cached = self._get_cached_insight("contact", contact_id)
            if cached:
                return cached

        context = self._gather_contact_context(contact_id)
        if not context:
            return None

        from .ai_prompt_loader import get_prompt, PROMPT_KEY_INSIGHT_CONTACT
        prompt = get_prompt(self._supabase, PROMPT_KEY_INSIGHT_CONTACT, CONTACT_INSIGHT_PROMPT, self._client_id)
        return self._generate_insight(prompt, context, "contact", contact_id)

    async def get_thread_insight(self, thread_id: str, force: bool = False) -> Optional[dict]:
        """Generate or return cached AI insight for a thread."""
        if not force:
            cached = self._get_cached_insight("thread", thread_id)
            if cached:
                return cached

        context = self._gather_thread_context(thread_id)
        if not context:
            return None

        from .ai_prompt_loader import get_prompt, PROMPT_KEY_INSIGHT_THREAD
        prompt = get_prompt(self._supabase, PROMPT_KEY_INSIGHT_THREAD, THREAD_INSIGHT_PROMPT, self._client_id)
        return self._generate_insight(prompt, context, "thread", thread_id)

    def _get_cached_insight(self, entity_type: str, entity_id: str) -> Optional[dict]:
        """Check for a recent cached insight."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
            result = self._supabase.table("relationship_context_cache").select(
                "ai_signals_summary, computed_at"
            ).eq("company_id" if entity_type == "company" else "company_id", entity_id).gte(
                "computed_at", cutoff
            ).limit(1).execute()

            # For now use relationship_context_cache for companies only
            # Contacts and threads use a simpler approach
            if entity_type == "company" and result.data:
                cached = result.data[0].get("ai_signals_summary")
                if cached and isinstance(cached, dict) and cached.get("_ai_insight"):
                    return cached["_ai_insight"]
        except Exception:
            pass
        return None

    def _gather_company_context(self, company_id: str) -> Optional[str]:
        """Gather all context for a company insight."""
        try:
            # Company profile
            company = self._supabase.table("customer_companies").select(
                "client_id, company_name, industry, engagement_score, total_emails, total_inbound, total_outbound, "
                "contact_count, decision_maker_count, first_contact_date, last_contact_date, "
                "qb_customer_type, qb_tier, qb_total_revenue, qb_invoiced_ty, qb_invoiced_ly, "
                "qb_growth_90d, qb_days_since_last_invoice, qb_account_manager"
            ).eq("id", company_id).single().execute()

            if not company.data:
                return None

            c = company.data

            # Active threads
            threads = self._supabase.table("thread_status").select(
                "subject, status, last_message_at, message_count"
            ).eq("customer_company_id", company_id).order(
                "last_message_at", desc=True
            ).limit(5).execute()

            # Recent AI signals — ai_email_intelligence has no company column;
            # resolve via emails.customer_company_id first
            _email_ids_res = self._supabase.table("emails").select("id").eq(
                "customer_company_id", company_id
            ).order("sent_date", desc=True).limit(100).execute()
            _email_ids = [r["id"] for r in (_email_ids_res.data or [])]
            if _email_ids:
                signals = self._supabase.table("ai_email_intelligence").select(
                    "primary_bucket, intent, urgency, sentiment, business_signal_score"
                ).in_("email_id", _email_ids).eq(
                    "processing_status", "completed"
                ).order("created_at", desc=True).limit(20).execute()
            else:
                class _Empty:
                    data = []
                signals = _Empty()

            # Load per-client currency code
            currency_code = get_client_currency_code(self._supabase, c.get("client_id"))

            # Build context string
            parts = [f"Company: {c['company_name']}"]
            if c.get("qb_customer_type"):
                parts.append(f"Customer Type: {c['qb_customer_type']}")
            if c.get("qb_tier"):
                parts.append(f"Tier: {c['qb_tier']}")
            if c.get("qb_total_revenue"):
                parts.append(f"Total Revenue: {format_currency(c['qb_total_revenue'], currency_code, include_code=True)}")
                if c.get("qb_invoiced_ty") is not None and c.get("qb_invoiced_ly") is not None:
                    parts.append(f"This Year: {format_currency(c['qb_invoiced_ty'], currency_code, include_code=True)} | Last Year: {format_currency(c['qb_invoiced_ly'], currency_code, include_code=True)}")
            if c.get("qb_days_since_last_invoice") is not None:
                parts.append(f"Days Since Last Order: {c['qb_days_since_last_invoice']}")
            parts.append(f"Engagement Score: {c.get('engagement_score', 'N/A')}/100")
            parts.append(f"Total Emails: {c.get('total_emails', 0)} (in: {c.get('total_inbound', 0)}, out: {c.get('total_outbound', 0)})")
            parts.append(f"Contacts: {c.get('contact_count', 0)} | Decision Makers: {c.get('decision_maker_count', 0)}")

            if threads.data:
                parts.append(f"\nActive Threads ({len(threads.data)}):")
                for t in threads.data:
                    parts.append(f"  - [{t.get('status', '?')}] {t.get('subject', 'No subject')} ({t.get('message_count', 0)} msgs)")

            if signals.data:
                bucket_counts = {}
                for s in signals.data:
                    b = s.get("primary_bucket")
                    if b:
                        bucket_counts[b] = bucket_counts.get(b, 0) + 1
                if bucket_counts:
                    parts.append(f"\nAI Signals (last 20 emails): {bucket_counts}")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"Failed to gather company context: {e}")
            return None

    def _gather_contact_context(self, contact_id: str) -> Optional[str]:
        """Gather context for a contact insight."""
        try:
            contact = self._supabase.table("customer_contacts").select(
                "full_name, email_address, job_title, company_name, seniority_level, "
                "is_decision_maker, engagement_score, total_emails_sent, total_emails_received, "
                "first_contacted_at, last_contacted_at, reply_rate, "
                "qb_quotes_count, qb_last_quote_date, qb_contact_recency_days"
            ).eq("id", contact_id).single().execute()

            if not contact.data:
                return None

            c = contact.data
            parts = [
                f"Contact: {c.get('full_name', 'Unknown')} ({c.get('email_address', '')})",
                f"Company: {c.get('company_name', 'Unknown')}",
                f"Title: {c.get('job_title', 'Unknown')} | Seniority: {c.get('seniority_level', 'Unknown')}",
                f"Decision Maker: {'Yes' if c.get('is_decision_maker') else 'No'}",
                f"Engagement: {c.get('engagement_score', 'N/A')}/100",
                f"Emails Sent: {c.get('total_emails_sent', 0)} | Received: {c.get('total_emails_received', 0)}",
                f"Reply Rate: {c.get('reply_rate', 'N/A')}",
            ]
            if c.get("qb_quotes_count"):
                parts.append(f"QB Quotes: {c['qb_quotes_count']}")
            if c.get("qb_last_quote_date"):
                parts.append(f"Last Quote: {c['qb_last_quote_date']}")

            return "\n".join(parts)

        except Exception as e:
            logger.error(f"Failed to gather contact context: {e}")
            return None

    def _gather_thread_context(self, thread_id: str) -> Optional[str]:
        """Gather context for a thread insight."""
        try:
            # Get thread status
            thread = self._supabase.table("thread_status").select(
                "subject, status, message_count, last_message_at, "
                "qb_customer_type, qb_customer_tier"
            ).eq("thread_id", thread_id).single().execute()

            # Get thread emails (last 5)
            emails = self._supabase.table("emails").select(
                "subject, sender_email, sender_name, sent_date, is_outbound, body_text"
            ).eq("thread_id", thread_id).order(
                "sent_date", desc=True
            ).limit(5).execute()

            parts = []
            if thread.data:
                t = thread.data
                parts.append(f"Thread: {t.get('subject', 'No subject')}")
                parts.append(f"Status: {t.get('status', 'unknown')} | Messages: {t.get('message_count', 0)}")
                if t.get("qb_customer_type"):
                    parts.append(f"Customer Type: {t['qb_customer_type']} | Tier: {t.get('qb_customer_tier', '?')}")

            if emails.data:
                parts.append(f"\nRecent Emails ({len(emails.data)}):")
                for e in reversed(emails.data):  # chronological order
                    direction = "OUT" if e.get("is_outbound") else "IN"
                    sender = e.get("sender_name") or e.get("sender_email", "?")
                    body = (e.get("body_text") or "")[:200]
                    parts.append(f"  [{direction}] {sender}: {body}")

            return "\n".join(parts) if parts else None

        except Exception as e:
            logger.error(f"Failed to gather thread context: {e}")
            return None

    def _generate_insight(self, system_prompt: str, context: str, entity_type: str, entity_id: str) -> Optional[dict]:
        """Call LLM and parse JSON response."""
        try:
            # Apply client model settings so we use the configured model (not hardcoded default)
            if self._supabase and self._client_id:
                from .ai_email_analyzer import _apply_client_model_settings
                _apply_client_model_settings(self._supabase, self._client_id)

            llm = get_cheap_llm(temperature=0.1)

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=context),
            ]

            response = llm.invoke(messages)
            content = response.content

            # Parse JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content.strip())
            result["_entity_type"] = entity_type
            result["_entity_id"] = entity_id
            result["_generated_at"] = datetime.now(timezone.utc).isoformat()
            result["_model"] = "cheap"

            # Log usage
            usage = getattr(response, "usage_metadata", None)
            if usage:
                logger.info(
                    f"AI insight generated for {entity_type}/{entity_id}: "
                    f"{usage.get('input_tokens', 0)} in, {usage.get('output_tokens', 0)} out"
                )

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Insight JSON parse failed for {entity_type}/{entity_id}: {e}")
            return {"error": "Failed to parse AI response", "_entity_type": entity_type}
        except Exception as e:
            logger.error(f"Insight generation failed for {entity_type}/{entity_id}: {e}")
            return {"error": str(e), "_entity_type": entity_type}
