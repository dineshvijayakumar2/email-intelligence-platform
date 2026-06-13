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

# Keyword fallback rules: if no exact match, check these keywords in (dept+op+machine).
# Evaluated in ORDER — first list whose keyword is a substring wins. The order and keyword
# sets mirror the capability_tag_audit TRUE taxonomy (capability_tag_audit.json /
# reconcile_pollution.json) so the classifier reproduces the audit's clean base rates.
#
# Pollution corrections baked in here (the reason this classifier supersedes qb_capability_tag,
# which mis-routes by Department — see feedback_qb_capability_tag_pollution):
#   - cello / celloglaze / laminate / matte / gloss / soft-touch / velvet / anti-scuff /
#     varnish / scuff  → Specialty Finishing  (NOT Embellishment)
#   - fuse / fuse back to back / mount          → Specialty Finishing  (NOT Hard Cover)
#   - perfect-bind / saddle / section / oversew → Soft Cover Books      (NOT Hard Cover)
#   - genuine foil / spot-uv / emboss / deboss / scodix / hot-foil → Embellishment
#   - genuine casebind / casing / end-paper / head-and-tail / fusing-board → Hard Cover Books
# These are the CODE DEFAULT; the live source is client_taxonomy_config.classifier_rules
# config_data['keyword_rules'] (loaded per-client, falls back to this default when absent).
_KEYWORD_RULES = [
    (["foil", "scodix", "spot uv", "emboss", "deboss", "stamping die", "hot foil", "digital foil"], "Embellishment"),
    (["wide format", "wf print", "zund", "large format", "banner", "pull up", "decal", "vinyl",
      "mesh", "swissq", "laminate 6", "laminate setup", "groove cut", "eyelet", "hanging kit",
      "poles", "application tape", "top-cut", "top cut"], "Wide Format"),
    (["casebind", "casing", "text block to cover", "head & tail", "head and tail", "end paper", "fusing board"], "Hard Cover Books"),
    (["perfect bind", "saddle stitch", "saddle sew", "wire bind", "pur bind", "false cover",
      "section", "oversew", "padding", "coil bind", "spiral", "wire-o", "hand saddle"], "Soft Cover Books"),
    (["install", "signage"], "Display / Installation"),
    (["prepress", "pre-press", "artwork", "preflight", "proof", "mock-up", "mockup", "layout",
      "variable data setup", "complexity", "online setup", "internal setup", "online admin"], "Design Services"),
    (["cello", "celloglaze", "soft-touch", "soft touch", "velvet", "anti-scuff", "scuff", "varnish",
      "matt", "gloss", "fuse", "mount", "round corner", "die cut", "die-cut", "laser", "perforat",
      "nip", "d-ring", "magnet", "ribbon", "packag", "precoat", "coat", "laminat", "sleeking"], "Specialty Finishing"),
    (["sheetfed", "offset", "litho", "digital print", "indigo", "vdp", "variable data"], "Flat Sheets"),
]


def _coerce_keyword_rules(raw) -> list:
    """Normalize config-stored keyword rules to [(["kw", ...], "Tag"), ...].

    Accepts the config_data['keyword_rules'] shape — a list of dicts
    {"keywords": [...], "tag": "..."} (UI-editable) — or the code-default
    list-of-tuples shape. Returns the code default if raw is empty/invalid.
    """
    if not raw:
        return _KEYWORD_RULES
    out = []
    for r in raw:
        if isinstance(r, dict):
            kws = r.get("keywords") or []
            tag = r.get("tag")
        elif isinstance(r, (list, tuple)) and len(r) == 2:
            kws, tag = r[0], r[1]
        else:
            continue
        if tag and isinstance(kws, list) and kws:
            out.append(([str(k).lower() for k in kws], str(tag)))
    return out or _KEYWORD_RULES

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
            _normalize(r.get("dept") or r.get("department")),
            _normalize(r.get("op") or r.get("operation")),
            _normalize(r.get("machine")),
        )
        # MVP tag: accept both "tag" and "mvp_tag" field names
        mvp_tag = r.get("tag") or r.get("mvp_tag")
        if mvp_tag == "(none)":
            mvp_tag = None

        # Flags: accept both list format ["has_coating"] and boolean fields {has_coating: true}
        flags = r.get("flags", [])
        if not flags:
            for flag_name in ("has_coating", "has_sewing", "has_outsource_component", "am_rush"):
                if r.get(flag_name):
                    flags.append(flag_name)

        lookup[key] = {
            "tag":          mvp_tag,
            "granular_tags": r.get("granular_tags", []),
            "flags":        flags,
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
            "config_data": {
                "rules": seed_rules,
                # config-driven keyword fallback (UI-editable); seeded from the code default
                "keyword_rules": [{"keywords": kws, "tag": tag} for kws, tag in _KEYWORD_RULES],
            },
            "version":     1,
            "description": f"Classifier rules — {len(seed_rules)} tuples + {len(_KEYWORD_RULES)} keyword rules auto-seeded from Carbon8 taxonomy",
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
        rules_cfg = rules_row.get("config_data") or {}
        rules_list = rules_cfg.get("rules", [])
        version = rules_row.get("version", 1)

        return {
            "version": version,
            "lookup": _build_lookup(rules_list),
            # Keyword fallback rules are now config-driven (UI-editable). Falls back to the
            # corrected code default when the client config has no keyword_rules key yet.
            "keyword_rules": _coerce_keyword_rules(rules_cfg.get("keyword_rules")),
            "rush_pattern": (
                (rows.get("rush_settings", {}).get("config_data") or {})
                .get("am_rush_pattern", DEFAULT_RUSH_SETTINGS["am_rush_pattern"])
            ),
        }
    except Exception as e:
        logger.error(f"Failed to load classifier rules for client {client_id}: {e}")
        return {"version": 0, "lookup": {}, "keyword_rules": _KEYWORD_RULES,
                "rush_pattern": DEFAULT_RUSH_SETTINGS["am_rush_pattern"]}


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
        # Keyword fallback on combined text (config-driven, code default if unset)
        combined = f"{dept or ''} {op or ''} {machine or ''}".lower()
        for keywords, tag in state["keyword_rules"]:
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
    keyword_rules = state["keyword_rules"]
    rush_pattern = state["rush_pattern"]

    logger.info(f"[Classifier] Starting reclassify_all for client {client_id} ({len(lookup)} rules loaded)")

    # Fetch all operations in batches, classify in Python, write back in batch RPC
    total_updated = 0
    offset = 0
    batch_size = 500
    WRITE_CHUNK = 100  # Max rows per RPC call to avoid statement timeout

    while True:
        result = supabase_client.table("qb_operations").select(
            "id, department, operation_name, machine"
        ).eq("client_id", client_id).range(offset, offset + batch_size - 1).execute()

        rows = result.data or []
        if not rows:
            break

        # Classify all rows in this batch (pure Python, instant)
        batch_ids = []
        batch_tags = []
        batch_coating = []
        batch_sewing = []
        batch_outsource = []
        batch_rush = []
        batch_row_type = []

        for row in rows:
            dept    = row.get("department")
            op      = row.get("operation_name")
            machine = row.get("machine")

            key = (_normalize(dept), _normalize(op), _normalize(machine))
            match = lookup.get(key)

            if not match:
                combined = f"{dept or ''} {op or ''} {machine or ''}".lower()
                for keywords, tag in keyword_rules:
                    if any(kw in combined for kw in keywords):
                        match = {"tag": tag, "granular_tags": [], "flags": [], "row_type": None}
                        break

            tags = [match["tag"]] if match and match.get("tag") else []
            flags = (match.get("flags") or []) if match else []
            row_type_val = match.get("row_type") if match else None
            am_rush = (op or "").startswith(rush_pattern)

            batch_ids.append(row["id"])
            batch_tags.append(json.dumps(tags))
            batch_coating.append("has_coating" in flags)
            batch_sewing.append("has_sewing" in flags)
            batch_outsource.append("has_outsource_component" in flags)
            batch_rush.append(am_rush)
            batch_row_type.append(row_type_val)

        # Write in chunks via batch RPC — with pause to avoid starving other queries
        import time as _time
        for ci in range(0, len(batch_ids), WRITE_CHUNK):
            chunk_end = ci + WRITE_CHUNK
            try:
                supabase_client.rpc("batch_update_classifications", {
                    "p_ids": batch_ids[ci:chunk_end],
                    "p_capability_tags": batch_tags[ci:chunk_end],
                    "p_has_coating": batch_coating[ci:chunk_end],
                    "p_has_sewing": batch_sewing[ci:chunk_end],
                    "p_has_outsource_component": batch_outsource[ci:chunk_end],
                    "p_am_rush": batch_rush[ci:chunk_end],
                    "p_row_type": batch_row_type[ci:chunk_end],
                }).execute()
                total_updated += len(batch_ids[ci:chunk_end])
            except Exception as e:
                logger.warning(f"[Classifier] Batch update failed for chunk: {e}")
            # Brief pause between chunks so other Supabase queries can get through
            _time.sleep(0.1)

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
