"""
AI Entity Aggregator — Roll up entities from per-email to aggregate tracking.

Reads from ai_email_intelligence (competitors, products, people extracted per email)
and upserts into ai_business_entities (aggregate counts, context snippets).

Also provides query methods for competitor landscape and opportunity signals.
"""

import time
import logging
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class AIEntityAggregator:
    """Aggregates entities from per-email intelligence into business entity tracking."""

    def __init__(self, supabase_client):
        self.client = supabase_client

    @staticmethod
    def _execute_with_retry(query_builder, max_retries: int = 3, base_delay: float = 2.0):
        """Execute a Supabase query with retry for transient errors."""
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return query_builder.execute()
            except Exception as e:
                last_error = e
                error_str = str(e)
                is_transient = any(keyword in error_str for keyword in [
                    'SSL handshake failed', '525', '502', '503', '504',
                    'Connection reset', 'Connection refused', 'timed out',
                    'JSON could not be generated', 'ECONNRESET', 'ETIMEDOUT', 'ConnectionTerminated', 'PROTOCOL_ERROR', 'SEND_HEADERS', 'StreamInput', 'state 5',
                ])
                if is_transient and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Transient Supabase error (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay}s: {error_str[:200]}"
                    )
                    time.sleep(delay)
                    continue
                raise
        raise last_error

    # ------------------------------------------------------------------
    # Aggregate entities from intel rows → ai_business_entities
    # ------------------------------------------------------------------
    def aggregate_entities(
        self,
        mailbox_id: str,
        client_id: Optional[str] = None,
    ) -> dict:
        """
        Scan all completed ai_email_intelligence rows and roll up
        entity mentions into ai_business_entities.

        Returns: {"competitors": int, "products": int, "people": int, "total_upserted": int}
        """
        if not client_id:
            # Look up client_id from mailbox
            resp = self._execute_with_retry(
                self.client.table("mailboxes")
                .select("client_id")
                .eq("id", mailbox_id)
                .range(0, 0)
            )
            data = resp.data or []
            client_id = data[0]["client_id"] if data else None

        if not client_id:
            logger.error("Cannot aggregate entities without client_id")
            return {"competitors": 0, "products": 0, "people": 0, "total_upserted": 0}

        # Fetch all intel rows with entity data
        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("email_id,competitors_mentioned,products_mentioned,"
                        "people_mentioned,processed_at")
                .eq("mailbox_id", mailbox_id)
                .eq("processing_status", "completed")
                .range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            all_rows.extend(batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        # Build aggregate maps: {normalized_name: {count, contexts, first_seen, last_seen}}
        entity_map = {}  # (entity_type, normalized) -> data

        for row in all_rows:
            ts = row.get("processed_at") or datetime.utcnow().isoformat()

            # Competitors
            for comp in (row.get("competitors_mentioned") or []):
                if not comp or not comp.strip():
                    continue
                key = ("competitor", comp.strip().lower())
                self._merge_entity(entity_map, key, comp.strip(), ts)

            # Products
            for prod in (row.get("products_mentioned") or []):
                if not prod or not prod.strip():
                    continue
                key = ("product", prod.strip().lower())
                self._merge_entity(entity_map, key, prod.strip(), ts)

            # People
            for person in (row.get("people_mentioned") or []):
                if isinstance(person, dict):
                    name = (person.get("name") or "").strip()
                    if not name:
                        continue
                    key = ("person", name.lower())
                    context = person.get("context", "")
                    self._merge_entity(entity_map, key, name, ts, context)

        # Upsert into ai_business_entities
        counts = {"competitor": 0, "product": 0, "person": 0}
        for (entity_type, normalized), data in entity_map.items():
            try:
                self._execute_with_retry(
                    self.client.table("ai_business_entities")
                    .upsert({
                        "client_id": client_id,
                        "mailbox_id": mailbox_id,
                        "entity_type": entity_type,
                        "entity_name": data["name"],
                        "normalized_name": normalized,
                        "mention_count": data["count"],
                        "first_seen_at": data["first_seen"],
                        "last_seen_at": data["last_seen"],
                        "context_snippets": data["contexts"][-10:],  # Keep last 10
                    }, on_conflict="client_id,entity_type,normalized_name")
                )
                counts[entity_type] = counts.get(entity_type, 0) + 1
            except Exception as e:
                logger.error(f"Failed to upsert entity {entity_type}/{normalized}: {e}")

        total = sum(counts.values())
        logger.info(
            f"Entity aggregation: {counts.get('competitor', 0)} competitors, "
            f"{counts.get('product', 0)} products, {counts.get('person', 0)} people"
        )
        return {
            "competitors": counts.get("competitor", 0),
            "products": counts.get("product", 0),
            "people": counts.get("person", 0),
            "total_upserted": total,
        }

    @staticmethod
    def _merge_entity(
        entity_map: dict,
        key: tuple,
        display_name: str,
        timestamp: str,
        context: str = "",
    ):
        """Merge an entity mention into the aggregate map."""
        if key not in entity_map:
            entity_map[key] = {
                "name": display_name,
                "count": 0,
                "contexts": [],
                "first_seen": timestamp,
                "last_seen": timestamp,
            }
        entry = entity_map[key]
        entry["count"] += 1
        entry["last_seen"] = max(entry["last_seen"], timestamp)
        entry["first_seen"] = min(entry["first_seen"], timestamp)
        if context and context not in entry["contexts"]:
            entry["contexts"].append(context)

    # ------------------------------------------------------------------
    # Helper: get email IDs within a sent_date range
    # ------------------------------------------------------------------
    def _get_email_ids_in_date_range(
        self, mailbox_id: str, date_from: str = None, date_to: str = None
    ) -> Optional[set]:
        """Get email IDs from the emails table within a sent_date range.

        Returns None if no date filtering needed, empty set if no emails match.
        """
        if not date_from and not date_to:
            return None

        query = self.client.table("emails").select("id").eq("mailbox_id", mailbox_id)
        if date_from:
            query = query.gte("sent_date", date_from)
        if date_to:
            query = query.lte("sent_date", date_to)

        all_ids = set()
        offset = 0
        while True:
            resp = self._execute_with_retry(query.range(offset, offset + 499))
            batch = resp.data or []
            all_ids.update(e["id"] for e in batch)
            if len(batch) == 0:
                break
            offset += len(batch)

        return all_ids

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------
    def get_entities(
        self,
        client_id: str,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get aggregated entities, optionally filtered by type."""
        query = (
            self.client.table("ai_business_entities")
            .select("*")
            .eq("client_id", client_id)
            .order("mention_count", desc=True)
        )
        if entity_type:
            query = query.eq("entity_type", entity_type)

        resp = self._execute_with_retry(query.range(0, limit - 1))
        return resp.data or []

    def get_competitor_landscape(self, client_id: str) -> dict:
        """
        Get competitor analysis: top competitors by mentions,
        plus count of accounts where they appear.
        """
        competitors = self.get_entities(client_id, entity_type="competitor", limit=50)
        total_mentions = sum(c.get("mention_count", 0) for c in competitors)

        # Count unique companies affected (from associated_company_ids)
        all_companies = set()
        for comp in competitors:
            company_ids = comp.get("associated_company_ids") or []
            all_companies.update(company_ids)

        return {
            "competitors": competitors,
            "total_mentions": total_mentions,
            "accounts_affected": len(all_companies),
        }

    def get_opportunity_signals(
        self,
        client_id: str,
        mailbox_id: str,
        limit: int = 50,
        date_from: str = None,
        date_to: str = None,
    ) -> list[dict]:
        """
        Get emails with high business signals (buying intent, budget, expansion).
        These are the top opportunities to pursue.
        Date-scoped via email sent_date when date_from/date_to provided.
        """
        # Date filter: get valid email IDs in range
        email_id_set = self._get_email_ids_in_date_range(mailbox_id, date_from, date_to)
        if email_id_set is not None and not email_id_set:
            return []

        # Fetch intel rows with high signal scores
        all_rows = []
        offset = 0
        PAGE_SIZE = 500
        while True:
            resp = self._execute_with_retry(
                self.client.table("ai_email_intelligence")
                .select("email_id,business_signal,business_signal_score,"
                        "confidence,summary,budget_signals,buying_signals,"
                        "has_budget_signal,has_buying_signal")
                .eq("mailbox_id", mailbox_id)
                .eq("processing_status", "completed")
                .gt("business_signal_score", "0")
                .order("business_signal_score", desc=True)
                .range(offset, offset + PAGE_SIZE - 1)
            )
            batch = resp.data or []
            # Apply date filter
            if email_id_set is not None:
                batch = [r for r in batch if r.get("email_id") in email_id_set]
            all_rows.extend(batch)
            if len(resp.data or []) == 0 or len(all_rows) >= limit:
                break
            offset += len(resp.data or [])

        all_rows = all_rows[:limit]

        # Enrich with email data
        email_ids = [r["email_id"] for r in all_rows if r.get("email_id")]
        email_lookup = {}
        if email_ids:
            for i in range(0, len(email_ids), 500):
                chunk = email_ids[i:i + 500]
                resp = self._execute_with_retry(
                    self.client.table("emails")
                    .select("id,subject,sender_email,sent_date")
                    .in_("id", chunk)
                )
                for e in (resp.data or []):
                    email_lookup[e["id"]] = e

        results = []
        for row in all_rows:
            email = email_lookup.get(row.get("email_id"), {})
            results.append({
                "email_id": row.get("email_id"),
                "email_subject": email.get("subject", ""),
                "email_sender": email.get("sender_email", ""),
                "email_date": email.get("sent_date"),
                "signal_type": row.get("business_signal", ""),
                "confidence": float(row.get("confidence") or 0),
                "summary": row.get("summary", ""),
                "budget_signal": row.get("budget_signals"),
                "buying_signals": row.get("buying_signals") or [],
                "business_signal_score": int(row.get("business_signal_score") or 0),
            })

        return results


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_entity_aggregator: Optional[AIEntityAggregator] = None


def init_entity_aggregator(supabase_client) -> AIEntityAggregator:
    """Initialize the global entity aggregator."""
    global _entity_aggregator
    _entity_aggregator = AIEntityAggregator(supabase_client)
    return _entity_aggregator


def get_entity_aggregator() -> Optional[AIEntityAggregator]:
    """Get the initialized entity aggregator instance."""
    return _entity_aggregator
