"""
Strategic Digest Pipeline — LangChain-powered executive intelligence digest.

Hybrid architecture:
  1. LCEL chain gathers and structures context (deterministic)
  2. LangGraph ReAct agent generates strategic insights (AI, with tool access)

The agent can call lookup tools to dig deeper into specific companies,
contacts, threads, or quotes when the pre-built context is insufficient.

Usage:
    pipeline = StrategicDigestPipeline(supabase_client, client_id)
    result = await pipeline.generate(
        period_type="weekly",
        period_start=date(2026, 3, 3),
        period_end=date(2026, 3, 9),
    )
"""

import asyncio
import json
import time
import logging
from json_repair import repair_json
from datetime import date, datetime, timezone
from typing import Optional, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .langchain_core import get_strategic_llm, get_model_config
from .strategic_context_builder import StrategicContextBuilder
from .am_efficiency_analyzer import AMEfficiencyAnalyzer
from .langchain_tools import (
    lookup_company_detail,
    lookup_contact_history,
    lookup_thread_messages,
    lookup_quote_detail,
    init_langchain_tools,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROMPT_VERSION = "v2.0"
MAX_CONTEXT_TOKENS = 15_000  # Target token budget for context (~60K chars)
MAX_COMPANY_CONTEXTS = 20   # Top companies to include in context


# ---------------------------------------------------------------------------
# System prompt for the strategic digest agent
# ---------------------------------------------------------------------------
STRATEGIC_DIGEST_SYSTEM_PROMPT = """\
You are an Account Manager efficiency analyst for a B2B commercial printing company.

Your job is to help Account Managers (AMs) be more effective by analyzing:
- Email response times (business hours), communication patterns, and organisation
- Customer lifecycle health (prospect → new → active → at-risk → dormant → champion)
- Mapping QB orders and quotes to AM workload and performance
- Retention signals based on relationship cooling, unanswered emails, stalled deals

You have tools to look up deeper details on companies, contacts, threads, or quotes.
Use them when context hints at something important but lacks detail.

ANALYSIS PRIORITIES (in order):
1. AM response urgency — unanswered inbound emails, overdue threads
2. Retention risk — at-risk or dormant customers with no recent AM contact
3. Deal at risk — stalled quotes 30+ days + declining engagement
4. AM efficiency — response times in business hours, after-hours workload
5. Revenue opportunity — active customers not quoted recently
6. New relationships — first-time contacts that need qualification

CUSTOMER LIFECYCLE TIERS:
- prospect: No orders yet, or QB type = prospective
- new_customer: First order within 90 days
- active_customer: Orders within 6 months, regular communication
- at_risk: Was active, no orders 90+ days AND declining engagement
- dormant: No email + no QB activity 180+ days
- champion: High revenue (A-tier or >$100K), high engagement

OUTPUT FORMAT:
Return ONLY valid JSON with exactly these 8 keys (no markdown, no commentary):
{
  "executive_summary": "2-3 paragraph overview focused on AM efficiency and customer health",
  "relationship_health": [
    {
      "company_name": "...",
      "lifecycle_tier": "prospect|new_customer|active_customer|at_risk|dormant|champion",
      "status": "healthy|at_risk|declining|growing|new",
      "signal": "specific signal: unanswered emails / stalled quote / declining orders / etc.",
      "am_owner": "AM name handling this account",
      "recommended_action": "specific next step with timing",
      "revenue_impact_estimate": "$X or null"
    }
  ],
  "pipeline_intelligence": {
    "lifecycle_breakdown": {"prospect": 0, "new_customer": 0, "active_customer": 0, "at_risk": 0, "dormant": 0, "champion": 0},
    "active_quotes_value": 0,
    "stalled_quotes": ["company: quote details"],
    "conversion_trend": "improving|stable|declining",
    "new_relationships_this_period": ["contact @ company"]
  },
  "risk_alerts": [
    {
      "severity": "critical|high|medium",
      "type": "response_urgency|deal_at_risk|retention_risk|account_neglect",
      "description": "...",
      "affected_company": "...",
      "am_owner": "...",
      "days_overdue": 0,
      "recommended_action": "..."
    }
  ],
  "opportunities": [
    {
      "type": "revenue_opportunity|reactivation|new_relationship|deal_acceleration",
      "company_name": "...",
      "lifecycle_tier": "...",
      "description": "...",
      "estimated_value": "$X or null",
      "next_step": "..."
    }
  ],
  "competitive_landscape": {
    "competitor_mentions": ["..."],
    "price_sensitivity_signals": ["..."],
    "win_loss_insights": ["..."]
  },
  "am_performance": {
    "summary": [
      {
        "am_name": "...",
        "avg_bh_response_hours": 0,
        "after_hours_pct": 0,
        "response_rate_pct": 0,
        "revenue_attributed": 0,
        "quote_conversion_rate": 0,
        "accounts_at_risk": 0,
        "performance_note": "brief assessment"
      }
    ],
    "top_performers": ["AM name: reason"],
    "needs_attention": ["AM name: specific concern"],
    "workload_imbalance": "description or null"
  },
  "action_items": [
    {
      "priority": "urgent|high|medium",
      "signal_type": "response_urgency|deal_at_risk|retention_risk|revenue_opportunity|account_neglect",
      "action": "specific actionable step",
      "owner": "AM name",
      "company": "customer company name",
      "deadline_suggestion": "today|this week|next 48h|this month",
      "context": "brief reason with data"
    }
  ]
}

Be specific. Use actual company names, AM names, dollar amounts. Do not fabricate.
If data is missing, say so. Prioritise AMs taking action TODAY over general strategy.
"""


class StrategicDigestPipeline:
    """Generates executive-level strategic digests using LangChain + LangGraph."""

    def __init__(self, supabase_client, client_id: str):
        self.supabase = supabase_client
        self.client_id = client_id

        # Initialize tools with the Supabase client
        init_langchain_tools(supabase_client)

    async def generate(
        self,
        period_type: str,
        period_start: date,
        period_end: date,
        comparison_start: Optional[date] = None,
        comparison_end: Optional[date] = None,
        on_progress=None,
        cancel_check=None,
    ) -> dict:
        """
        Generate a strategic digest for the given period.

        Args:
            period_type: 'weekly', 'monthly', 'quarterly', 'ytd', 'custom'
            period_start: Start of analysis period
            period_end: End of analysis period
            comparison_start: Optional comparison period start (for trends)
            comparison_end: Optional comparison period end

        Returns:
            Dict with digest sections + metadata
        """
        start_time_ms = int(time.time() * 1000)
        logger.info(
            f"Strategic digest generation started: {period_type} "
            f"{period_start} to {period_end} (client={self.client_id})"
        )

        try:
            # -----------------------------------------------------------------
            # Step 1: Build context (deterministic LCEL chain)
            # -----------------------------------------------------------------
            context_builder = StrategicContextBuilder(
                self.supabase, self.client_id
            )
            loop = asyncio.get_event_loop()
            all_contexts = await loop.run_in_executor(
                None,
                lambda: context_builder.build_all_contexts(
                    lookback_months=6, on_progress=on_progress, cancel_check=cancel_check
                ),
            )

            if cancel_check and cancel_check():
                return {"status": "cancelled"}

            if on_progress:
                on_progress("am_performance", 1, 1, "Building AM efficiency snapshots…")

            # -----------------------------------------------------------------
            # Step 2: Build AM efficiency data (mailbox → user based)
            # -----------------------------------------------------------------
            am_analyzer = AMEfficiencyAnalyzer(self.supabase, self.client_id)
            am_efficiency_data = await loop.run_in_executor(
                None,
                lambda: am_analyzer.compute_all(period_start, period_end),
            )
            # Persist snapshots async (fire and forget on failure)
            try:
                await loop.run_in_executor(
                    None, lambda: am_analyzer.save_snapshots(am_efficiency_data)
                )
            except Exception as e:
                logger.warning(f"Failed to save AM efficiency snapshots: {e}")

            # -----------------------------------------------------------------
            # Step 3: Get top company contexts from cache
            # -----------------------------------------------------------------
            company_contexts = await loop.run_in_executor(
                None,
                lambda: context_builder.get_contexts_for_digest(top_n=MAX_COMPANY_CONTEXTS),
            )

            # -----------------------------------------------------------------
            # Step 4: Compile context into structured prompt
            # -----------------------------------------------------------------
            context_prompt = self._compile_context(
                all_contexts=all_contexts,
                am_performance=am_efficiency_data,
                company_contexts=company_contexts,
                period_type=period_type,
                period_start=period_start,
                period_end=period_end,
                comparison_start=comparison_start,
                comparison_end=comparison_end,
            )

            # -----------------------------------------------------------------
            # Step 5: Create LangGraph agent with tools
            # -----------------------------------------------------------------
            llm = get_strategic_llm(temperature=0.1)
            tools = [
                lookup_company_detail,
                lookup_contact_history,
                lookup_thread_messages,
                lookup_quote_detail,
            ]
            agent = create_react_agent(
                model=llm,
                tools=tools,
                prompt=STRATEGIC_DIGEST_SYSTEM_PROMPT,
            )

            if on_progress:
                on_progress("ai_analysis", 1, 1, "Running AI strategic analysis…")

            # -----------------------------------------------------------------
            # Step 6: Run agent to generate strategic analysis
            # -----------------------------------------------------------------
            agent_result = await agent.ainvoke({
                "messages": [HumanMessage(content=context_prompt)],
            })

            # Extract final message content
            final_message = agent_result["messages"][-1]
            raw_content = (
                final_message.content
                if isinstance(final_message.content, str)
                else str(final_message.content)
            )

            # -----------------------------------------------------------------
            # Step 7: Parse response into structured sections
            # -----------------------------------------------------------------
            parsed = self._parse_digest_response(raw_content)

            # -----------------------------------------------------------------
            # Step 8: Calculate token usage from agent messages
            # -----------------------------------------------------------------
            total_input_tokens = 0
            total_output_tokens = 0
            for msg in agent_result["messages"]:
                usage = getattr(msg, "usage_metadata", None)
                if usage:
                    total_input_tokens += usage.get("input_tokens", 0)
                    total_output_tokens += usage.get("output_tokens", 0)

            model_config = get_model_config("sonnet")
            cost = (
                (total_input_tokens / 1_000_000) * model_config["cost_input_per_mtok"]
                + (total_output_tokens / 1_000_000) * model_config["cost_output_per_mtok"]
            )
            cost = round(cost, 6)

            end_time_ms = int(time.time() * 1000)
            generation_time_ms = end_time_ms - start_time_ms

            # -----------------------------------------------------------------
            # Step 8: Save to ai_strategic_digests table
            # -----------------------------------------------------------------
            digest_row = {
                "client_id": self.client_id,
                "digest_date": date.today().isoformat(),
                "period_type": period_type,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "executive_summary": parsed.get("executive_summary", ""),
                "relationship_health": json.dumps(parsed.get("relationship_health", [])),
                "pipeline_intelligence": json.dumps(parsed.get("pipeline_intelligence", {})),
                "risk_alerts": json.dumps(parsed.get("risk_alerts", [])),
                "opportunities": json.dumps(parsed.get("opportunities", [])),
                "competitive_landscape": json.dumps(parsed.get("competitive_landscape", {})),
                "am_performance": json.dumps(parsed.get("am_performance", {})),
                "action_items": json.dumps(parsed.get("action_items", [])),
                "companies_analyzed": len(company_contexts),
                "contacts_analyzed": all_contexts.get("contacts_analyzed", 0),
                "emails_analyzed": all_contexts.get("emails_analyzed", 0),
                "qb_orders_included": all_contexts.get("qb_orders_included", 0),
                "qb_quotes_included": all_contexts.get("qb_quotes_included", 0),
                "model_used": model_config["model"],
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_cost_usd": cost,
                "chain_steps_completed": len(agent_result["messages"]),
                "prompt_version": PROMPT_VERSION,
                "raw_ai_responses": json.dumps({
                    "final_content": raw_content[:5000],
                    "message_count": len(agent_result["messages"]),
                }),
                "generation_time_ms": generation_time_ms,
            }

            # Add comparison period if provided
            if comparison_start:
                digest_row["comparison_period_start"] = comparison_start.isoformat()
            if comparison_end:
                digest_row["comparison_period_end"] = comparison_end.isoformat()

            try:
                self.supabase.table("ai_strategic_digests").upsert(
                    digest_row,
                    on_conflict="client_id,digest_date,period_type",
                ).execute()
                logger.info(f"Strategic digest saved for {period_type} {period_start}")
            except Exception as e:
                logger.error(f"Failed to save strategic digest: {e}")

            # -----------------------------------------------------------------
            # Step 9: Track usage via ai_usage_log
            # -----------------------------------------------------------------
            try:
                self.supabase.table("ai_usage_log").insert({
                    "operation": "strategic_digest",
                    "model": model_config["model"],
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "estimated_cost_usd": cost,
                    "processing_time_ms": generation_time_ms,
                    "batch_size": 1,
                    "success": True,
                    "client_id": self.client_id,
                    "prompt_version": PROMPT_VERSION,
                }).execute()
            except Exception as e:
                logger.error(f"Failed to log strategic digest usage: {e}")

            logger.info(
                f"Strategic digest complete: {generation_time_ms}ms, "
                f"{total_input_tokens}+{total_output_tokens} tokens, "
                f"${cost:.4f}"
            )

            return {
                **parsed,
                "_metadata": {
                    "period_type": period_type,
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "companies_analyzed": len(company_contexts),
                    "contacts_analyzed": all_contexts.get("contacts_analyzed", 0),
                    "emails_analyzed": all_contexts.get("emails_analyzed", 0),
                    "model": model_config["model"],
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cost_usd": cost,
                    "generation_time_ms": generation_time_ms,
                    "agent_steps": len(agent_result["messages"]),
                    "prompt_version": PROMPT_VERSION,
                },
            }

        except Exception as e:
            end_time_ms = int(time.time() * 1000)
            generation_time_ms = end_time_ms - start_time_ms
            logger.error(
                f"Strategic digest generation failed after {generation_time_ms}ms: {e}",
                exc_info=True,
            )

            # Log failure to usage tracker
            try:
                model_config = get_model_config("sonnet")
                self.supabase.table("ai_usage_log").insert({
                    "operation": "strategic_digest",
                    "model": model_config["model"],
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0,
                    "processing_time_ms": generation_time_ms,
                    "batch_size": 1,
                    "success": False,
                    "error_type": "pipeline_error",
                    "client_id": self.client_id,
                    "prompt_version": PROMPT_VERSION,
                }).execute()
            except Exception:
                pass

            raise

    def _compile_context(
        self,
        all_contexts: dict,
        am_performance: list,
        company_contexts: list,
        period_type: str,
        period_start: date,
        period_end: date,
        comparison_start: Optional[date],
        comparison_end: Optional[date],
    ) -> str:
        """Compile all gathered context into a structured prompt for the agent."""

        sections = []

        # Header
        sections.append(
            f"# AM Efficiency Digest Request\n"
            f"Period: {period_type.upper()} | {period_start} to {period_end}"
        )
        if comparison_start and comparison_end:
            sections.append(f"Comparison Period: {comparison_start} to {comparison_end}")

        # AM Efficiency KPIs (from AMEfficiencyAnalyzer, mailbox → user)
        sections.append("\n## Account Manager Efficiency (this period)")
        if am_performance:
            for am in am_performance:
                name = am.get("am_name") or am.get("mailbox_id", "Unknown")
                sections.append(f"\n  AM: {name}")
                bh = am.get("avg_bh_response_time_hours")
                raw = am.get("avg_response_time_hours")
                sections.append(f"    BH Response Time: {f'{bh:.1f}h' if bh else 'N/A'}"
                                 f"  (raw: {f'{raw:.1f}h' if raw else 'N/A'})")
                rr = am.get("response_rate_pct")
                sections.append(f"    Response Rate: {f'{rr:.0f}%' if rr is not None else 'N/A'}")
                ah = am.get("after_hours_email_pct")
                sections.append(f"    After-Hours Emails: {f'{ah:.0f}%' if ah is not None else 'N/A'}")
                sections.append(f"    Emails Sent: {am.get('emails_sent', 0)} | "
                                 f"Received: {am.get('emails_received', 0)}")
                rev = am.get("revenue_attributed", 0)
                if rev:
                    sections.append(f"    Revenue Attributed: ${rev:,.0f}")
                qs = am.get("quotes_sent", 0)
                qa = am.get("quotes_accepted", 0)
                qcr = am.get("quote_conversion_rate")
                if qs:
                    sections.append(f"    Quotes: {qs} sent, {qa} accepted"
                                     f"{f', {qcr:.0f}% conversion' if qcr else ''}")
        else:
            sections.append("  No AM efficiency data available for this period.")

        # Customer Lifecycle Summary
        lifecycle_counts: dict = {}
        for ctx in company_contexts:
            tier = ctx.get("lifecycle_tier") or "unknown"
            lifecycle_counts[tier] = lifecycle_counts.get(tier, 0) + 1

        sections.append("\n## Customer Lifecycle Distribution")
        for tier, count in sorted(lifecycle_counts.items()):
            sections.append(f"  {tier}: {count} companies")

        # Company contexts: prioritised (at-risk first, then champion, then active)
        sections.append(f"\n## Top {len(company_contexts)} Company Contexts")
        for i, ctx in enumerate(company_contexts, 1):
            company_name = ctx.get("company_name", "Unknown")
            tier = ctx.get("lifecycle_tier", "unknown")
            am_name = ctx.get("am_name") or ctx.get("account_manager") or "Unassigned"
            sections.append(f"\n### {i}. {company_name}  [{tier.upper()}]  AM: {am_name}")

            if ctx.get("customer_tier"):
                sections.append(f"  QB Tier: {ctx['customer_tier']}")
            if ctx.get("engagement_trajectory"):
                sections.append(f"  Engagement: {ctx['engagement_trajectory']}")

            # Financial
            fin = ctx.get("qb_financial_summary") or {}
            if fin.get("invoiced_ty") or fin.get("total_revenue"):
                rev_ty = fin.get("invoiced_ty") or 0
                rev_ly = fin.get("invoiced_ly") or 0
                days = fin.get("days_since_last_invoice")
                sections.append(f"  Revenue TY: ${rev_ty:,.0f} | LY: ${rev_ly:,.0f}"
                                 + (f" | {days}d since last order" if days else ""))
                open_q = fin.get("open_quotes_count", 0)
                open_v = fin.get("open_quotes_total", 0)
                if open_q:
                    sections.append(f"  Open Quotes: {open_q} (${open_v:,.0f} total)")

            # Communication health
            comm = ctx.get("communication_health") or {}
            if comm.get("avg_response_hours") is not None or comm.get("avg_bh_response_hours") is not None:
                bh_r = comm.get("avg_bh_response_hours")
                sections.append(f"  BH Response Time: {f'{bh_r:.1f}h' if bh_r else 'N/A'}"
                                 f"  | Responses: {comm.get('total_responses', 0)}")

            # AI signals
            signals = ctx.get("ai_signals_summary") or {}
            if signals:
                dist = signals.get("bucket_distribution") or {}
                sig_parts = [f"{k}:{v}" for k, v in dist.items() if v and k not in ("unknown", "")]
                if sig_parts:
                    sections.append(f"  Signals: {', '.join(sig_parts[:5])}")
                if signals.get("escalation_count"):
                    sections.append(f"  ⚠ Escalations: {signals['escalation_count']}")

            # Active threads
            threads_data = ctx.get("active_threads_summary") or {}
            if isinstance(threads_data, dict) and threads_data.get("active_count"):
                overdue = threads_data.get("overdue_count", 0)
                sections.append(f"  Threads: {threads_data['active_count']} active"
                                 + (f", {overdue} OVERDUE" if overdue else ""))
                for t in (threads_data.get("threads") or [])[:2]:
                    sections.append(f"    - {t.get('subject', 'N/A')[:80]}")

            # Key contacts
            contacts = ctx.get("key_contacts") or []
            if contacts:
                names = [
                    f"{c.get('name') or 'Unknown'} ({c.get('role', 'N/A')}, score={c.get('engagement_score', 0)})"
                    for c in contacts[:3]
                ]
                sections.append(f"  Key Contacts: {'; '.join(names)}")

            # Token budget guard
            if len("\n".join(sections)) > MAX_CONTEXT_TOKENS * 4:
                sections.append(
                    f"\n... (truncated — {len(company_contexts) - i} more companies)"
                )
                break

        # Instruction
        sections.append(
            "\n## Instructions\n"
            "Analyse the above data and produce a strategic digest as JSON. "
            "Focus on AM actions needed TODAY or THIS WEEK. "
            "Use the lookup tools for deeper context on specific companies or threads. "
            "Prioritise: unanswered emails, stalled deals, at-risk customers. "
            "Use actual names, figures, and response time data from the context above."
        )

        return "\n".join(sections)

    def _parse_digest_response(self, raw_content: str) -> dict:
        """
        Parse the agent's JSON response into structured sections.

        Handles common LLM output issues:
        - JSON wrapped in markdown code blocks
        - Extra text before/after JSON
        - Missing keys (uses defaults)
        """
        content = raw_content.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = content.index("\n") if "\n" in content else len(content)
            content = content[first_newline + 1:]
        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        # Try to find JSON object in the content
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            content = content[json_start:json_end]

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # LLM sometimes returns single-quoted keys or trailing commas — try repair
            try:
                repaired = repair_json(content, return_objects=True)
                if isinstance(repaired, dict):
                    parsed = repaired
                else:
                    parsed = json.loads(str(repaired))
                logger.info("Digest JSON repaired successfully")
            except Exception as e2:
                logger.error(f"Failed to parse digest JSON even after repair: {e2}")
                logger.debug(f"Raw content (first 500 chars): {raw_content[:500]}")
                parsed = {
                    "executive_summary": (
                        "Digest generation completed but response parsing failed. "
                        "Raw analysis is available in metadata."
                    ),
                    "_parse_error": str(e2),
                    "_raw_content": raw_content[:2000],
                }

        # Ensure all 8 required keys exist with defaults
        defaults = {
            "executive_summary": "",
            "relationship_health": [],
            "pipeline_intelligence": {"lifecycle_breakdown": {}, "active_quotes_value": 0,
                                       "stalled_quotes": [], "conversion_trend": "stable",
                                       "new_relationships_this_period": []},
            "risk_alerts": [],
            "opportunities": [],
            "competitive_landscape": {"competitor_mentions": [], "price_sensitivity_signals": [],
                                       "win_loss_insights": []},
            "am_performance": {"summary": [], "top_performers": [], "needs_attention": [],
                                "workload_imbalance": None},
            "action_items": [],
        }
        for key, default in defaults.items():
            if key not in parsed:
                parsed[key] = default

        return parsed
