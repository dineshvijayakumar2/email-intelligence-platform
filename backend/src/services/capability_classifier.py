"""
Capability Classifier — Maps QB Operations (dept, op, machine) → capability tags + flags.

Resolution order:
  1. Exact match on (dept_norm, op_norm, machine_norm) from loaded rules
  2. Keyword fallback for unknown tuples (catches new operations after backfill)
  3. Returns empty tags + no flags if nothing matches (unclassified)

Rules are loaded from client_taxonomy_config (config_type='classifier_rules').
On first use for a client, Carbon8 defaults are auto-seeded from
capability_classifier_data.json so the UI immediately shows editable rules.

Cache: In-memory per client_id, invalidated when config version changes.
"""

import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Defaults ────────────────────────────────────────────────────────────────
# 8 MVP capability tags with display metadata
DEFAULT_CAPABILITY_TAGS = [
    {"tag_id": "flat_sheets",        "name": "Flat Sheets",          "color": "#3B82F6", "description": "Sheetfed offset and digital flat print"},
    {"tag_id": "soft_cover_books",   "name": "Soft Cover Books",     "color": "#10B981", "description": "Perfect binding, saddle stitch, saddle sewn, wire binding"},
    {"tag_id": "hard_cover_books",   "name": "Hard Cover Books",     "color": "#8B5CF6", "description": "Casebinding, section sewing, oversewing"},
    {"tag_id": "wide_format",        "name": "Wide Format",          "color": "#F59E0B", "description": "WF print, laminating, mounting"},
    {"tag_id": "embellishment",      "name": "Embellishment",        "color": "#EC4899", "description": "Foil, spot UV, varnish, digital foil, embossing"},
    {"tag_id": "specialty_finishing","name": "Specialty Finishing",  "color": "#EF4444", "description": "Zund, laser cut, die cut"},
    {"tag_id": "design_services",    "name": "Design Services",      "color": "#6366F1", "description": "Design, artwork, pre-press"},
    {"tag_id": "display_install",    "name": "Display / Installation","color": "#14B8A6", "description": "Display, signage, installation"},
]

DEFAULT_RUSH_SETTINGS = {
    "am_rush_pattern": "RUSH: Approx",          # operation_name prefix for am_rush
    "rush_pct_threshold": 30,                    # % of jobs that are rush → surface in recommendations
    "gap_count_threshold": 3,                    # factory_rush without am_rush count → surface in recommendations
}

# Keyword fallback rules: if no exact match, check these keywords in (dept+op+machine)
_KEYWORD_RULES = [
    (["wide format", "wf print", "wf lam", "wf mount"], "Wide Format"),
    (["foil", "scodix", "spot uv", "varnish", "emboss", "digital foil"], "Embellishment"),
    (["perfect bind", "saddle stitch", "saddle sewn", "wire bind", "case bind", "section sew", "oversew"], "Soft Cover Books"),
    (["casebind", "casebinding", "section sewing", "oversewing"], "Hard Cover Books"),
    (["zund", "laser cut", "die cut"], "Specialty Finishing"),
    (["design", "artwork", "pre-press", "prepress"], "Design Services"),
    (["display", "install", "signage"], "Display / Installation"),
    (["sheetfed", "offset", "litho", "digital print", "indigo", "vdp", "variable data"], "Flat Sheets"),
]

# ── In-memory cache ──────────────────────────────────────────────────────────
# client_id → {version: int, rules: dict, tags: list}
_cache: dict[str, dict] = {}

_DATA_FILE = os.path.join(os.path.dirname(__file__), "capability_classifier_data.json")


def _normalize(text: Optional[str]) -> str:
    """Lowercase + collapse whitespace for fuzzy matching."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.lower().strip())


def _load_seed_data() -> list[dict]:
    """Load the 597-tuple Carbon8 classifier data from JSON file."""
    try:
        with open(_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load classifier seed data: {e}")
        return []


def _build_lookup(rules: list[dict]) -> dict:
    """Build normalized (dept, op, machine) → {tag, granular_tags, flags, row_type} lookup."""
    lookup = {}
    for r in rules:
        key = (
            _normalize(r.get("dept")),
            _normalize(r.get("op")),
            _normalize(r.get("machine")),
        )
        lookup[key] = {
            "tag":          r.get("tag"),           # MVP tag or None
            "granular_tags": r.get("granular_tags", []),  # Phase 2A sub-tags
            "flags":        r.get("flags", []),
            "row_type":     r.get("row_type"),
        }
    return lookup


def _seed_defaults(supabase_client, client_id: str) -> None:
    """Seed capability_tags and classifier_rules into client_taxonomy_config for a new client."""
    seed_rules = _load_seed_data()
    # Add granular_tags field if missing (future-proof for Phase 2A)
    for r in seed_rules:
        r.setdefault("granular_tags", [])

    configs = [
        {
            "client_id":   client_id,
            "config_type": "capability_tags",
            "config_data": {"tags": DEFAULT_CAPABILITY_TAGS},
            "version":     1,
            "description": "8 MVP capability tags — auto-seeded",
        },
        {
            "client_id":   client_id,
            "config_type": "classifier_rules",
            "config_data": {"rules": seed_rules},
            "version":     1,
            "description": f"Classifier rules — {len(seed_rules)} tuples auto-seeded from Carbon8 taxonomy",
        },
        {
            "client_id":   client_id,
            "config_type": "rush_settings",
            "config_data": DEFAULT_RUSH_SETTINGS,
            "version":     1,
            "description": "Rush detection settings — auto-seeded",
        },
    ]
    for cfg in configs:
        try:
            supabase_client.table("client_taxonomy_config").upsert(
                cfg, on_conflict="client_id,config_type"
            ).execute()
        except Exception as e:
            logger.debug(f"Seed skipped for {cfg['config_type']}: {e}")

    logger.info(f"Auto-seeded capability taxonomy for client {client_id} ({len(seed_rules)} classifier rules)")


def _load_client_rules(supabase_client, client_id: str) -> dict:
    """Load classifier rules + version from DB for a client. Seeds defaults if absent."""
    try:
        result = supabase_client.table("client_taxonomy_config").select(
            "config_type, config_data, version"
        ).eq("client_id", client_id).in_(
            "config_type", ["classifier_rules", "capability_tags", "rush_settings"]
        ).execute()

        rows = {r["config_type"]: r for r in (result.data or [])}

        if "classifier_rules" not in rows:
            _seed_defaults(supabase_client, client_id)
            # Re-fetch after seeding
            result = supabase_client.table("client_taxonomy_config").select(
                "config_type, config_data, version"
            ).eq("client_id", client_id).in_(
                "config_type", ["classifier_rules", "capability_tags", "rush_settings"]
            ).execute()
            rows = {r["config_type"]: r for r in (result.data or [])}

        rules_row = rows.get("classifier_rules", {})
        rules_list = (rules_row.get("config_data") or {}).get("rules", [])
        version = rules_row.get("version", 1)

        return {
            "version": version,
            "lookup": _build_lookup(rules_list),
            "rush_pattern": (
                (rows.get("rush_settings", {}).get("config_data") or {})
                .get("am_rush_pattern", DEFAULT_RUSH_SETTINGS["am_rush_pattern"])
            ),
        }
    except Exception as e:
        logger.error(f"Failed to load classifier rules for client {client_id}: {e}")
        return {"version": 0, "lookup": {}, "rush_pattern": DEFAULT_RUSH_SETTINGS["am_rush_pattern"]}


def _get_client_state(supabase_client, client_id: str) -> dict:
    """Return cached classifier state, refreshing if version changed in DB."""
    cached = _cache.get(client_id)

    # Check if DB version is newer than cached version
    try:
        ver_result = supabase_client.table("client_taxonomy_config").select(
            "version"
        ).eq("client_id", client_id).eq("config_type", "classifier_rules").limit(1).execute()
        db_version = (ver_result.data or [{}])[0].get("version", 0) if ver_result.data else 0
    except Exception:
        db_version = cached["version"] if cached else 0

    if not cached or cached["version"] != db_version:
        state = _load_client_rules(supabase_client, client_id)
        _cache[client_id] = state
        return state

    return cached


# ── Public API ───────────────────────────────────────────────────────────────

def classify(
    supabase_client,
    client_id: str,
    dept: Optional[str],
    op: Optional[str],
    machine: Optional[str],
    operation_name: Optional[str] = None,
) -> dict:
    """
    Classify one operation row.

    Returns:
        {
            "capability_tags": ["Wide Format"],      # MVP tags (list)
            "granular_tags":   [],                   # Phase 2A sub-tags
            "has_coating":     False,
            "has_sewing":      False,
            "has_outsource_component": False,
            "am_rush":         False,
            "row_type":        "internal",           # or None
        }
    """
    state = _get_client_state(supabase_client, client_id)
    lookup = state["lookup"]
    rush_pattern = state["rush_pattern"]

    # Exact match
    key = (_normalize(dept), _normalize(op), _normalize(machine))
    match = lookup.get(key)

    if not match:
        # Keyword fallback on combined text
        combined = f"{dept or ''} {op or ''} {machine or ''}".lower()
        for keywords, tag in _KEYWORD_RULES:
            if any(kw in combined for kw in keywords):
                match = {"tag": tag, "granular_tags": [], "flags": [], "row_type": None}
                break

    tags = []
    granular_tags = []
    flags = []
    row_type = None

    if match:
        if match.get("tag"):
            tags = [match["tag"]]
        granular_tags = match.get("granular_tags") or []
        flags = match.get("flags") or []
        row_type = match.get("row_type")

    # am_rush: pattern match on operation_name (field 9 in QB)
    # Use operation_name if provided, otherwise fall back to op
    name_to_check = operation_name or op or ""
    am_rush = name_to_check.startswith(rush_pattern)

    return {
        "capability_tags":          tags,
        "granular_tags":            granular_tags,
        "has_coating":              "has_coating" in flags,
        "has_sewing":               "has_sewing" in flags,
        "has_outsource_component":  "has_outsource_component" in flags,
        "am_rush":                  am_rush,
        "row_type":                 row_type,
    }


def reclassify_all(supabase_client, client_id: str) -> int:
    """
    Re-classify all qb_operations rows for a client using current rules.
    Called when rules are updated via the Intelligence Config UI.
    Does NOT re-fetch from QB — operates on already-synced rows.

    Returns: number of rows updated
    """
    # Force reload of rules from DB
    _cache.pop(client_id, None)
    state = _get_client_state(supabase_client, client_id)
    lookup = state["lookup"]
    rush_pattern = state["rush_pattern"]

    logger.info(f"[Classifier] Starting reclassify_all for client {client_id} ({len(lookup)} rules loaded)")

    # Fetch all operations in batches
    total_updated = 0
    offset = 0
    batch_size = 500

    while True:
        result = supabase_client.table("qb_operations").select(
            "id, department, operation_name, machine"
        ).eq("client_id", client_id).range(offset, offset + batch_size - 1).execute()

        rows = result.data or []
        if not rows:
            break

        for row in rows:
            dept    = row.get("department")
            op      = row.get("operation_name")
            machine = row.get("machine")

            key = (_normalize(dept), _normalize(op), _normalize(machine))
            match = lookup.get(key)

            if not match:
                combined = f"{dept or ''} {op or ''} {machine or ''}".lower()
                for keywords, tag in _KEYWORD_RULES:
                    if any(kw in combined for kw in keywords):
                        match = {"tag": tag, "granular_tags": [], "flags": [], "row_type": None}
                        break

            tags = [match["tag"]] if match and match.get("tag") else []
            granular_tags = (match.get("granular_tags") or []) if match else []
            flags = (match.get("flags") or []) if match else []
            row_type = match.get("row_type") if match else None
            am_rush = (op or "").startswith(rush_pattern)

            try:
                supabase_client.table("qb_operations").update({
                    "capability_tags":         tags,
                    "has_coating":             "has_coating" in flags,
                    "has_sewing":              "has_sewing" in flags,
                    "has_outsource_component": "has_outsource_component" in flags,
                    "am_rush":                 am_rush,
                    "row_type":                row_type,
                }).eq("id", row["id"]).execute()
                total_updated += 1
            except Exception as e:
                logger.warning(f"[Classifier] Failed to update operation {row['id']}: {e}")

        offset += len(rows)
        if len(rows) < batch_size:
            break

        if offset % 5000 == 0:
            logger.info(f"[Classifier] reclassify_all progress: {total_updated} updated...")

    logger.info(f"[Classifier] reclassify_all complete: {total_updated} operations updated for client {client_id}")
    return total_updated


def invalidate_cache(client_id: Optional[str] = None) -> None:
    """Invalidate in-memory classifier cache. Call after updating rules via API."""
    if client_id:
        _cache.pop(client_id, None)
    else:
        _cache.clear()
