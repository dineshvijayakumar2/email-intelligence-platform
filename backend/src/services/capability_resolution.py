"""
Single source of truth for resolving an operation's capabilities.

Layer-1 precedence (Task 13.7): the op-name CLASSIFIER (capability_tags) is the authority;
the QB formula tag (qb_capability_tag) only FILLS GAPS where the classifier has no opinion.

This inverts the previous "QB tag wins, classifier fallback" order. The QB tag mis-routes by
Department (cello->Embellishment, fuse->Hard Cover — see feedback_qb_capability_tag_pollution),
so the corrected classifier output must win wherever it has an opinion.

ALL capability-reading sites must call caps_for_op() so the precedence lives in exactly one place
and cannot drift. WAVE-2 embedding consumers (vector_service, hybrid_retriever, langchain_tools)
are intentionally NOT switched yet (re-embed cost).
"""
import json
from typing import Optional


def _parse_tags(raw) -> list:
    """Normalize the capability_tags column to a clean list[str].

    Handles the proper jsonb-array shape (post-migration-123) and, defensively, the legacy
    string / comma-separated shapes so a stray un-recast row never crashes a consumer.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            raw = [t.strip() for t in raw.split(",") if t.strip()]
    if not isinstance(raw, list):
        return []
    return [t.strip() for t in raw if isinstance(t, str) and len(t.strip()) > 1]


def caps_for_op(op: dict) -> list:
    """Capabilities for one operation row: classifier first, QB tag fills gaps.

    1. capability_tags (classifier output) — if it has any opinion, return it.
    2. else qb_capability_tag (QB formula) — fall back when the classifier is silent.
    3. else [] — neither has an opinion.

    `op` must contain 'capability_tags' and 'qb_capability_tag' (select both in the query).
    """
    tags = _parse_tags(op.get("capability_tags"))
    if tags:
        return tags
    qb = (op.get("qb_capability_tag") or "").strip()
    if qb:
        return [qb]
    return []
