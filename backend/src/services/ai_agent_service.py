"""
AI Chat Agent Service — Conversational Q&A over the email intelligence platform.

Uses LangGraph ReAct agent with 6 tools (company lookup, contact history,
thread messages, quote detail, semantic search for emails + operations).

Usage:
    result = await agent_chat(supabase, client_id, "What's the status of Acme Corp?", [])
"""

import asyncio
import time
import logging
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from .langchain_core import get_strategic_llm, get_model_config
from .langchain_tools import (
    init_langchain_tools,
    lookup_company_detail,
    lookup_contact_history,
    lookup_thread_messages,
    lookup_quote_detail,
    semantic_search_emails,
    semantic_search_operations,
    portfolio_summary,
    account_ranking,
    search_emails,
    search_contacts,
    thread_overview,
    company_analytics,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROMPT_KEY_AGENT_CHAT = "agent_chat"
MAX_HISTORY = 20  # Max conversation turns to keep

AGENT_SYSTEM_PROMPT = """You are an AI assistant for the Email Intelligence Platform — a B2B commercial printing company's customer intelligence system. You help Account Managers understand their customer portfolio, find insights in email data, and take action on opportunities and risks.

## YOUR TOOLS (use them proactively — don't say "I can't", use a tool instead)

**Portfolio & Rankings:**
- `portfolio_summary` — Overall portfolio health: account counts, engagement, revenue, dormant accounts
- `account_ranking(metric, limit)` — Top/bottom accounts by: revenue, engagement, growth, days_since_contact, days_since_invoice, email_volume

**Email Intelligence:**
- `search_emails(query_type, value, limit)` — Find emails by: "recent", "urgent", "sender:<email>", "intent:<type>", "company:<name>", "signal:<type>", "unresponded"
- `semantic_search_emails(query)` — Natural language search across all emails (vector similarity)

**Company Deep-Dive:**
- `lookup_company_detail(company_name)` — Profile, engagement, QB financials, account manager
- `company_analytics(company_name, analysis)` — Strike rate, seasonality, ordering rhythm, contact capabilities. Use analysis="all" for full picture or "strike_rate"/"seasonality"/"rhythm"/"capabilities" for specific

**Contacts:**
- `search_contacts(filter_type, value, limit)` — Find contacts: "decision_makers", "company:<name>", "role:<role>", "low_engagement", "inactive", "all"
- `lookup_contact_history(contact_email)` — Contact profile + last 10 emails

**Threads:**
- `thread_overview(filter_type, company_name)` — "summary" (status counts), "overdue", "active", "company" (for specific company)
- `lookup_thread_messages(thread_id)` — Full thread conversation

**Production/Operations:**
- `semantic_search_operations(query)` — Search QB operations by product/service/capability
- `lookup_quote_detail(quote_no)` — Quote details + linked jobs

## GUIDELINES
- **Always use tools** to answer questions. Never guess or say "I don't have access". If unsure which tool, start with the most likely one.
- **Chain tools**: Use portfolio_summary first for overview, then drill into specific accounts with company_analytics or lookup_company_detail.
- **Be specific**: Use real numbers, names, dates, and dollar amounts from tool results. Bold key facts.
- **Be actionable**: End with specific recommendations — who to call, what to discuss, when to follow up.
- **Format well**: Use markdown — **bold** for key facts, bullet lists for data, headers for sections.
- **Business focus**: Revenue at risk, engagement trends, overdue responses, ordering pattern changes, cross-sell opportunities.

## TONE
Professional, consultative — like a knowledgeable colleague helping an AM prepare for calls, prioritize accounts, and spot opportunities."""


ALL_TOOLS = [
    # Portfolio-level analytics
    portfolio_summary,
    account_ranking,
    # Email & thread tools
    search_emails,
    thread_overview,
    # Contact tools
    search_contacts,
    # Company deep-dive tools
    lookup_company_detail,
    company_analytics,
    # Individual record lookups
    lookup_contact_history,
    lookup_thread_messages,
    lookup_quote_detail,
    # Semantic search
    semantic_search_emails,
    semantic_search_operations,
]


async def agent_chat(
    supabase_client,
    client_id: str,
    message: str,
    conversation_history: list[dict],
) -> dict:
    """Run a single chat turn with the ReAct agent.

    Args:
        supabase_client: Initialized Supabase client
        client_id: Client UUID for scoping tool queries
        message: User's new message
        conversation_history: Previous turns [{role: "user"|"assistant", content: str}]

    Returns:
        {response, tools_used, model, input_tokens, output_tokens, cost_usd, processing_time_ms}
    """
    t0 = time.time()

    # Initialize tools with Supabase client
    init_langchain_tools(supabase_client)

    # Apply client's model preferences
    from .ai_email_analyzer import _apply_client_model_settings
    _apply_client_model_settings(supabase_client, client_id)

    # Load configurable prompt (DB override → hardcoded default)
    from .ai_prompt_loader import get_prompt
    system_prompt = get_prompt(supabase_client, PROMPT_KEY_AGENT_CHAT,
                               AGENT_SYSTEM_PROMPT, client_id)

    # Build message history (limit to last N turns)
    messages = []
    history = conversation_history[-MAX_HISTORY:] if len(conversation_history) > MAX_HISTORY else conversation_history
    for entry in history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    # Add the new user message
    messages.append(HumanMessage(content=message))

    # Create agent — uses the per-client strategic model (may be Gemini, GPT-4o, etc.)
    from .langchain_core import _default_strategic_model
    active_model_name = _default_strategic_model
    llm = get_strategic_llm(temperature=0.2)
    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=system_prompt,
    )

    # Run with retry
    agent_result = None
    raw_content = None
    _transient_codes = {'383', '429', '500', '502', '503', '504',
                         'rate', 'quota', 'overload', 'timeout', 'unavailable'}

    for _attempt in range(3):
        try:
            agent_result = await agent.ainvoke({"messages": messages})
            final_message = agent_result["messages"][-1]
            # Extract text from content — may be str or list of content blocks
            content = final_message.content
            if isinstance(content, str):
                raw_content = content
            elif isinstance(content, list):
                # LangChain returns [{type: 'text', text: '...'}, ...] blocks
                raw_content = '\n'.join(
                    block.get('text', '') if isinstance(block, dict) else str(block)
                    for block in content
                    if isinstance(block, dict) and block.get('type') == 'text' or isinstance(block, str)
                )
            else:
                raw_content = str(content)
            break
        except Exception as _e:
            _err = str(_e).lower()
            _is_transient = any(c in _err for c in _transient_codes)
            if _is_transient and _attempt < 2:
                _wait = 5 * (2 ** _attempt)
                logger.warning(f"Agent attempt {_attempt + 1}/3 failed: {str(_e)[:120]}, retrying in {_wait}s")
                await asyncio.sleep(_wait)
                continue
            # Fallback to direct LLM call (no tools)
            logger.warning(f"Agent failed after {_attempt + 1} attempts: {_e}. Falling back to direct LLM.")
            direct_messages = [
                SystemMessage(content=system_prompt),
                *messages,
            ]
            direct_response = await llm.ainvoke(direct_messages)
            fb_content = direct_response.content
            if isinstance(fb_content, str):
                raw_content = fb_content
            elif isinstance(fb_content, list):
                raw_content = '\n'.join(
                    block.get('text', '') if isinstance(block, dict) else str(block)
                    for block in fb_content
                    if isinstance(block, dict) and block.get('type') == 'text' or isinstance(block, str)
                )
            else:
                raw_content = str(fb_content)
            agent_result = {"messages": [direct_response]}
            break

    if not raw_content:
        raw_content = "I'm sorry, I wasn't able to process your request. Please try again."

    # Extract tool usage from agent messages
    tools_used = []
    if agent_result:
        for msg in agent_result["messages"]:
            msg_type = type(msg).__name__
            if msg_type == "ToolMessage":
                tools_used.append({
                    "tool_name": getattr(msg, "name", "unknown"),
                    "tool_output_preview": (msg.content[:200] + "...") if len(msg.content) > 200 else msg.content,
                })
            elif msg_type == "AIMessage" and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    tools_used.append({
                        "tool_name": tc.get("name", "unknown"),
                        "tool_input": str(tc.get("args", {}))[:200],
                    })

    # Deduplicate — keep unique tool invocations
    seen = set()
    unique_tools = []
    for t in tools_used:
        key = t.get("tool_name", "") + t.get("tool_input", "")
        if key not in seen:
            seen.add(key)
            unique_tools.append(t)

    # Calculate tokens and cost
    total_input_tokens = 0
    total_output_tokens = 0
    if agent_result:
        for msg in agent_result["messages"]:
            usage = getattr(msg, "usage_metadata", None)
            if usage:
                total_input_tokens += usage.get("input_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)

    model_config = get_model_config(active_model_name)
    cost = round(
        (total_input_tokens / 1_000_000) * model_config["cost_input_per_mtok"]
        + (total_output_tokens / 1_000_000) * model_config["cost_output_per_mtok"],
        6,
    )

    processing_time_ms = int((time.time() - t0) * 1000)

    # Log usage
    try:
        supabase_client.table("ai_usage_log").insert({
            "client_id": client_id,
            "operation": "agent_chat",
            "model": model_config.get("model", "sonnet"),
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "estimated_cost_usd": cost,
            "processing_time_ms": processing_time_ms,
            "batch_size": 1,
            "success": True,
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to log agent usage: {e}")

    logger.info(f"Agent chat: {total_input_tokens}+{total_output_tokens} tokens, "
                f"${cost}, {len(unique_tools)} tools, {processing_time_ms}ms")

    return {
        "response": raw_content,
        "tools_used": unique_tools,
        "model": model_config.get("model_id", "sonnet"),
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "cost_usd": cost,
        "processing_time_ms": processing_time_ms,
    }
