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
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROMPT_KEY_AGENT_CHAT = "agent_chat"
MAX_HISTORY = 20  # Max conversation turns to keep

AGENT_SYSTEM_PROMPT = """You are an AI assistant for the Email Intelligence Platform, helping Account Managers at a B2B commercial printing company understand and act on their customer data.

You have access to these tools:
- lookup_company_detail: Look up a company's profile, engagement score, QB financials, and account manager
- lookup_contact_history: Look up a contact's profile and their last 10 emails
- lookup_thread_messages: Read the full conversation in an email thread
- lookup_quote_detail: Look up quote details including value, status, and linked jobs
- semantic_search_emails: Search emails by meaning — find emails about topics, concerns, or contexts
- semantic_search_operations: Search production operations by meaning — find what products/services were ordered

GUIDELINES:
- Be concise and actionable. Lead with the answer, then provide supporting detail.
- Use specific numbers, names, and dates from the data. Never fabricate data.
- If you don't have enough information, say so and suggest what to look up.
- Format responses with markdown for readability (bold key facts, use bullet lists).
- Focus on business impact: revenue at risk, engagement trends, overdue follow-ups.
- When multiple tools could help, use the most relevant one first.

TONE: Professional, consultative — like a knowledgeable colleague helping an AM prepare for calls and prioritize follow-ups."""


ALL_TOOLS = [
    lookup_company_detail,
    lookup_contact_history,
    lookup_thread_messages,
    lookup_quote_detail,
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

    # Create agent
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

    model_config = get_model_config("sonnet")
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
