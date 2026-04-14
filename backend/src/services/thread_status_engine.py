"""
ThreadStatusEngine — compute effective thread status from timing + intent signals.

The effective status is what every downstream consumer should read:
dashboards, digests, AI agents, action bucket engine, etc. It is derived by
applying a prioritised list of override rules (loaded from the
`thread_status_override_rules` table) to the raw inputs:

  - timing_status  : the mechanical signal (awaiting_response, ongoing, ...)
  - intent         : AI-derived intent tag (complaint, pricing_inquiry, ...)
  - urgency        : AI-derived urgency (critical, high, normal, low)
  - last_is_outbound: did we send the last email? (for rules that care)

If no rule fires, effective_status == timing_status.

Design:
  - `compute_effective_status()` is a pure function. No DB, no AI, no side
    effects. Given the same inputs + rule list it always returns the same
    output. This is exhaustively unit-testable.
  - `RuleLoader` loads the rules from the database with Redis caching (60s
    TTL), matching the existing pattern in ai.py for vector_stats. Rules
    change infrequently, cache-friendly.
  - ThreadStatusEngine composes them: an instance holds loaded rules and
    exposes a one-call interface the refactored thread_tracker uses.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


# ── Data types ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OverrideRule:
    """One rule as loaded from thread_status_override_rules."""
    id: UUID
    name: str
    priority: int
    when_timing_in: tuple[str, ...] | None
    when_timing_not_in: tuple[str, ...] | None
    when_intent_in: tuple[str, ...] | None
    when_urgency_in: tuple[str, ...] | None
    effective_status_becomes: str
    reason_template: Optional[str]


@dataclass(frozen=True)
class StatusResult:
    """Output of compute_effective_status."""
    effective_status: str
    timing_status: str
    applied_rule_id: Optional[UUID]   # None if no override fired
    override_reason: Optional[str]    # rendered reason or None


# ── Pure function ──────────────────────────────────────────────────────────

def compute_effective_status(
    timing_status: str,
    intent: Optional[str],
    urgency: Optional[str],
    last_is_outbound: bool,
    rules: list[OverrideRule],
) -> StatusResult:
    """Apply override rules in priority order. First match wins.

    Pure function — no DB, no AI, no logging of state changes.

    Args:
        timing_status: raw mechanical status (e.g. 'awaiting_response')
        intent: AI-classified intent of the last email, or None
        urgency: AI-classified urgency, or None
        last_is_outbound: did the thread's last message originate from us?
        rules: all enabled rules, in priority order (ascending)

    Returns:
        StatusResult with effective_status, applied_rule_id, and reason.
    """
    # `rules` is expected in priority-ascending order (lowest priority = first).
    # The DB index on (priority) supports this; the loader sorts anyway.
    for rule in rules:
        if _rule_matches(rule, timing_status, intent, urgency, last_is_outbound):
            return StatusResult(
                effective_status=rule.effective_status_becomes,
                timing_status=timing_status,
                applied_rule_id=rule.id,
                override_reason=_render_reason(
                    rule.reason_template,
                    intent=intent,
                    urgency=urgency,
                    timing_status=timing_status,
                ),
            )

    # No rule fired — effective status == timing status.
    return StatusResult(
        effective_status=timing_status,
        timing_status=timing_status,
        applied_rule_id=None,
        override_reason=None,
    )


def _rule_matches(
    rule: OverrideRule,
    timing_status: str,
    intent: Optional[str],
    urgency: Optional[str],
    last_is_outbound: bool,  # noqa: ARG001 — reserved for future rule conditions
) -> bool:
    """A rule matches iff EVERY non-null condition passes.

    None/empty condition arrays mean "this field is not a condition for this
    rule" — trivially pass.
    """
    if rule.when_timing_in and timing_status not in rule.when_timing_in:
        return False
    if rule.when_timing_not_in and timing_status in rule.when_timing_not_in:
        return False
    if rule.when_intent_in and (intent is None or intent not in rule.when_intent_in):
        return False
    if rule.when_urgency_in and (urgency is None or urgency not in rule.when_urgency_in):
        return False
    return True


def _render_reason(
    template: Optional[str],
    *,
    intent: Optional[str],
    urgency: Optional[str],
    timing_status: str,
) -> Optional[str]:
    """Safely render the reason template. Missing keys become empty strings
    rather than raising KeyError.
    """
    if not template:
        return None
    # Map all potentially-referenced variables. Unknown {placeholders} are
    # rendered as empty strings via a defaulting dict.
    class _SafeDict(dict):
        def __missing__(self, key):  # pragma: no cover — trivial
            return ""
    return template.format_map(_SafeDict(
        intent=intent or "",
        urgency=urgency or "",
        timing_status=timing_status or "",
    ))


# ── Rule loader (DB + Redis cache) ─────────────────────────────────────────

_RULES_CACHE_KEY = "thread_status:override_rules:v1"
_RULES_CACHE_TTL_S = 60


def _tuple_or_none(value) -> tuple[str, ...] | None:
    """Normalise Postgres TEXT[] (returned as Python list by psycopg2/supabase)
    into an immutable tuple, or None for empty/null (so rule matching can
    fast-check for 'no condition set')."""
    if value is None:
        return None
    if isinstance(value, list) and len(value) == 0:
        return None
    return tuple(value)


def load_rules_from_db(supabase_client, use_cache: bool = True) -> list[OverrideRule]:
    """Load all enabled override rules from the DB, sorted by priority.

    With `use_cache=True` (default), tries Redis first — the rules table is
    read-heavy and changes are rare. Callers that need fresh rules
    (e.g. after an admin updates a rule) should pass `use_cache=False`.
    """
    if use_cache:
        cached = _read_rules_cache()
        if cached is not None:
            return cached

    try:
        # ORDER BY priority, name for deterministic tie-breaking when multiple
        # rules share a priority (first-match-wins logic depends on stable order).
        resp = supabase_client.table("thread_status_override_rules").select(
            "id, name, priority, when_timing_in, when_timing_not_in, "
            "when_intent_in, when_urgency_in, effective_status_becomes, reason_template"
        ).eq("enabled", True).order("priority").order("name").execute()
    except Exception as e:
        logger.error(f"[ThreadStatusEngine] Failed to load rules: {e}")
        return []

    rules = [
        OverrideRule(
            id=UUID(r["id"]),
            name=r["name"],
            priority=int(r["priority"]),
            when_timing_in=_tuple_or_none(r.get("when_timing_in")),
            when_timing_not_in=_tuple_or_none(r.get("when_timing_not_in")),
            when_intent_in=_tuple_or_none(r.get("when_intent_in")),
            when_urgency_in=_tuple_or_none(r.get("when_urgency_in")),
            effective_status_becomes=r["effective_status_becomes"],
            reason_template=r.get("reason_template"),
        )
        for r in (resp.data or [])
    ]

    _write_rules_cache(rules)
    logger.info(f"[ThreadStatusEngine] Loaded {len(rules)} override rules from DB")
    return rules


def _read_rules_cache() -> list[OverrideRule] | None:
    r = _get_redis()
    if r is None:
        return None
    try:
        raw = r.get(_RULES_CACHE_KEY)
        if not raw:
            return None
        parsed = json.loads(raw)
        return [
            OverrideRule(
                id=UUID(x["id"]),
                name=x["name"],
                priority=x["priority"],
                when_timing_in=tuple(x["when_timing_in"]) if x["when_timing_in"] else None,
                when_timing_not_in=tuple(x["when_timing_not_in"]) if x["when_timing_not_in"] else None,
                when_intent_in=tuple(x["when_intent_in"]) if x["when_intent_in"] else None,
                when_urgency_in=tuple(x["when_urgency_in"]) if x["when_urgency_in"] else None,
                effective_status_becomes=x["effective_status_becomes"],
                reason_template=x["reason_template"],
            )
            for x in parsed
        ]
    except Exception as e:
        logger.debug(f"[ThreadStatusEngine] cache read failed: {e}")
        return None


def _write_rules_cache(rules: list[OverrideRule]) -> None:
    r = _get_redis()
    if r is None:
        return
    try:
        payload = json.dumps([
            {
                "id": str(rule.id),
                "name": rule.name,
                "priority": rule.priority,
                "when_timing_in": list(rule.when_timing_in) if rule.when_timing_in else None,
                "when_timing_not_in": list(rule.when_timing_not_in) if rule.when_timing_not_in else None,
                "when_intent_in": list(rule.when_intent_in) if rule.when_intent_in else None,
                "when_urgency_in": list(rule.when_urgency_in) if rule.when_urgency_in else None,
                "effective_status_becomes": rule.effective_status_becomes,
                "reason_template": rule.reason_template,
            }
            for rule in rules
        ])
        r.setex(_RULES_CACHE_KEY, _RULES_CACHE_TTL_S, payload)
    except Exception as e:
        logger.debug(f"[ThreadStatusEngine] cache write failed: {e}")


def _get_redis():
    try:
        import redis
        return redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"),
                              decode_responses=True)
    except Exception:
        return None


def invalidate_rules_cache() -> None:
    """Call this after admin tunes a rule so the next evaluation picks up
    the change immediately instead of waiting up to 60s for TTL.
    """
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(_RULES_CACHE_KEY)
    except Exception:
        pass


# ── Engine composition (one-liner for thread_tracker) ──────────────────────

class ThreadStatusEngine:
    """Composes rule loading + pure function. One instance per evaluator run.

    Usage:
        engine = ThreadStatusEngine(sb)
        result = engine.evaluate(timing_status, intent, urgency, last_is_outbound)
        # result.effective_status, result.applied_rule_id, result.override_reason
    """

    def __init__(self, supabase_client, rules: Optional[list[OverrideRule]] = None):
        # Allow caller to inject rules (tests pass synthetic rules). When
        # omitted, load from DB (with Redis cache).
        self._rules = rules if rules is not None else load_rules_from_db(supabase_client)

    @property
    def rules(self) -> list[OverrideRule]:
        return self._rules

    def evaluate(
        self,
        timing_status: str,
        intent: Optional[str],
        urgency: Optional[str],
        last_is_outbound: bool = False,
    ) -> StatusResult:
        return compute_effective_status(
            timing_status=timing_status,
            intent=intent,
            urgency=urgency,
            last_is_outbound=last_is_outbound,
            rules=self._rules,
        )
