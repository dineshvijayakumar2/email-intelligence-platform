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

import json
import time
import logging
from datetime import date, datetime, timezone
from typing import Optional, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .langchain_core import get_strategic_llm, get_model_config
from .strategic_context_builder import StrategicContextBuilder
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
PROMPT_VERSION = "v1.0"
MAX_CONTEXT_TOKENS = 15_000  # Target token budget for context (~60K chars)
MAX_COMPANY_CONTEXTS = 20   # Top companies to include in context


# ---------------------------------------------------------------------------
# System prompt for the strategic digest agent
# ---------------------------------------------------------------------------
STRATEGIC_DIGEST_SYSTEM_PROMPT = """\
You are an executive intelligence analyst for a B2B commercial printing company.

Your role is to analyze email communication patterns, Quickbase business data \
(quotes, jobs, revenue), and relationship health signals to produce a strategic \
digest for leadership.

You have access to tools to look up deeper details on specific companies, \
contacts, email threads, or quotes. Use them when the provided context hints \
at something important but lacks detail.

ANALYSIS PRIORITIES:
1. Revenue risk — customers going quiet, declining order frequency, negative sentiment
2. Pipeline opportunities — active quoting, expansion signals, new contacts engaging
3. AM performance gaps — slow response times, uneven workload, missed follow-ups
4. Competitive threats — mentions of competitors, price sensitivity, RFQ to multiple vendors
5. Relationship health — trajectory changes, key contact departures, escalations

OUTPUT FORMAT:
Return ONLY valid JSON with exactly these 8 keys (no markdown, no commentary):
{
  "executive_summary": "2-3 paragraph strategic overview of the period",
  "relationship_health": [
    {
      "company_name": "...",
      "status": "healthy|at_risk|declining|growing|new",
      "signal": "brief description of why",
      "recommended_action": "specific next step",
      "revenue_impact_estimate": "$X or null"
    }
  ],
  "pipeline_intelligence": {
    "active_quotes_value": 0,
    "conversion_trend": "improving|stable|declining",
    "notable_opportunities": ["..."],
    "stalled_quotes": ["..."]
  },
  "risk_alerts": [
    {
      "severity": "critical|high|medium",
      "type": "churn_risk|revenue_decline|competitive_threat|relationship_gap",
      "description": "...",
      "affected_company": "...",
      "recommended_action": "..."
    }
  ],
  "opportunities": [
    {
      "type": "upsell|cross_sell|reactivation|new_business",
      "company_name": "...",
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
    "top_performers": ["..."],
    "needs_attention": ["..."],
    "workload_imbalance": "description or null",
    "response_time_concerns": ["..."]
  },
  "action_items": [
    {
      "priority": "urgent|high|medium",
      "action": "specific actionable step",
      "owner": "AM name or 'Leadership'",
      "deadline_suggestion": "this week|next 48h|this month",
      "context": "brief reason"
    }
  ]
}

Be specific. Use actual company names, dollar amounts, and contact names from \
the data. Do not fabricate data — if you lack information, say so. Prioritize \
actionable insights over general observations.
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
            all_contexts = context_builder.build_all_contexts(lookback_months=6)

            # -----------------------------------------------------------------
            # Step 2: Build AM performance data
            # -----------------------------------------------------------------
            # Convert date objects to ISO strings; handle optional comparison dates
            comp_start_iso = comparison_start.isoformat() if comparison_start else period_start.isoformat()
            comp_end_iso = comparison_end.isoformat() if comparison_end else period_end.isoformat()
            am_performance_data = context_builder.build_am_performance(
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
                comparison_start=comp_start_iso,
                comparison_end=comp_end_iso,
            )

            # -----------------------------------------------------------------
            # Step 3: Get top company contexts from cache
            # -----------------------------------------------------------------
            company_contexts = context_builder.get_contexts_for_digest(
                top_n=MAX_COMPANY_CONTEXTS
            )

            # -----------------------------------------------------------------
            # Step 4: Compile context into structured prompt
            # -----------------------------------------------------------------
            context_prompt = self._compile_context(
                all_contexts=all_contexts,
                am_performance=am_performance_data,
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
                self.supabase.table("ai_strategic_digests").insert(digest_row).execute()
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
        am_performance: dict,
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
            f"# Strategic Digest Request\n"
            f"Period: {period_type.upper()} | {period_start} to {period_end}"
        )
        if comparison_start and comparison_end:
            sections.append(
                f"Comparison Period: {comparison_start} to {comparison_end}"
            )

        # Overall metrics
        sections.append("\n## Overall Metrics")
        metrics = all_contexts.get("overall_metrics", {})
        for key, value in metrics.items():
            sections.append(f"- {key}: {value}")

        # Company relationship contexts (top N)
        sections.append(f"\n## Top {len(company_contexts)} Company Contexts")
        for i, ctx in enumerate(company_contexts, 1):
            company_name = ctx.get("company_name", "Unknown")
            sections.append(f"\n### {i}. {company_name}")

            # Core fields
            if ctx.get("customer_tier"):
                sections.append(f"  Tier: {ctx['customer_tier']}")
            if ctx.get("account_manager"):
                sections.append(f"  AM: {ctx['account_manager']}")
            if ctx.get("engagement_trajectory"):
                sections.append(f"  Trajectory: {ctx['engagement_trajectory']}")

            # Financial
            fin = ctx.get("qb_financial_summary", {})
            if fin:
                sections.append(f"  Revenue TY: ${fin.get('invoiced_ty', 0)}")
                sections.append(f"  Revenue LY: ${fin.get('invoiced_ly', 0)}")
                sections.append(f"  Growth 90d: {fin.get('growth_90d', 'N/A')}%")

            # Communication health
            comm = ctx.get("communication_health", {})
            if comm:
                sections.append(f"  Emails (period): {comm.get('email_count', 0)}")
                sections.append(
                    f"  Avg Response Time: {comm.get('avg_response_hours', 'N/A')}h"
                )
                sections.append(
                    f"  Sentiment: {comm.get('avg_sentiment', 'N/A')}"
                )

            # AI signals
            signals = ctx.get("ai_signals_summary", {})
            if signals:
                if signals.get("churn_risk"):
                    sections.append(f"  CHURN RISK: {signals['churn_risk']}")
                if signals.get("opportunities"):
                    sections.append(f"  Opportunities: {signals['opportunities']}")

            # Active threads
            threads = ctx.get("active_threads_summary", [])
            if threads:
                sections.append(f"  Active Threads: {len(threads)}")
                for t in threads[:3]:
                    sections.append(f"    - {t.get('subject', 'N/A')}")

            # Key contacts
            contacts = ctx.get("key_contacts", [])
            if contacts:
                names = [
                    f"{c.get('name', 'N/A')} ({c.get('role', 'N/A')})"
                    for c in contacts[:3]
                ]
                sections.append(f"  Key Contacts: {', '.join(names)}")

            # Keep individual company context under budget
            if len("\n".join(sections)) > MAX_CONTEXT_TOKENS * 4:
                sections.append(
                    f"\n... (truncated — {len(company_contexts) - i} more companies)"
                )
                break

        # AM Performance
        sections.append("\n## Account Manager Performance")
        am_data = am_performance.get("am_snapshots", [])
        if am_data:
            for am in am_data:
                sections.append(f"\n  AM: {am.get('account_manager', 'N/A')}")
                sections.append(f"    Revenue: ${am.get('total_revenue', 0)}")
                sections.append(
                    f"    Revenue Change: {am.get('revenue_change_pct', 'N/A')}%"
                )
                sections.append(f"    Customers: {am.get('customer_count', 0)}")
                sections.append(
                    f"    Quote Conversion: {am.get('quote_conversion_rate', 'N/A')}%"
                )
                sections.append(
                    f"    Avg Response Time: {am.get('avg_response_time_hours', 'N/A')}h"
                )
                sections.append(f"    Emails Sent: {am.get('emails_sent', 0)}")
                sections.append(
                    f"    Retention Rate: {am.get('retention_rate', 'N/A')}%"
                )
        else:
            sections.append("  No AM performance data available.")

        # AI signal summaries
        ai_summary = all_contexts.get("ai_signal_summary", {})
        if ai_summary:
            sections.append("\n## AI Intelligence Signals (Aggregated)")
            for key, value in ai_summary.items():
                sections.append(f"  {key}: {value}")

        # Instruction
        sections.append(
            "\n## Instructions\n"
            "Analyze the above data and produce a strategic digest as JSON. "
            "Use the lookup tools if you need deeper context on any company, "
            "contact, thread, or quote mentioned above. Focus on actionable "
            "insights that leadership can act on this week."
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
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse digest JSON: {e}")
            logger.debug(f"Raw content (first 500 chars): {raw_content[:500]}")
            # Return a degraded response rather than failing entirely
            parsed = {
                "executive_summary": (
                    "Digest generation completed but response parsing failed. "
                    "Raw analysis is available in metadata."
                ),
                "_parse_error": str(e),
                "_raw_content": raw_content[:2000],
            }

        # Ensure all 8 required keys exist with defaults
        defaults = {
            "executive_summary": "",
            "relationship_health": [],
            "pipeline_intelligence": {},
            "risk_alerts": [],
            "opportunities": [],
            "competitive_landscape": {},
            "am_performance": {},
            "action_items": [],
        }
        for key, default in defaults.items():
            if key not in parsed:
                parsed[key] = default

        return parsed
