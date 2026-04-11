"""
Hybrid Retriever — Phase 2 Retrieval Infrastructure

A single `retrieve(query, filters)` interface that:
1. Parses temporal expressions from the query
2. Runs vector (semantic) + BM25 (keyword) search in parallel
3. Applies recency decay to similarity scores
4. Fuses results via Reciprocal Rank Fusion (RRF)
5. Returns a ranked mix of emails, companies, and operations

Usage:
    retriever = HybridRetriever(supabase_client)
    results = await retriever.retrieve(
        query="what did we discuss with Acme last quarter",
        client_id="...",
        sources=["emails", "companies"],
        limit=20,
    )
"""

import asyncio
import math
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Literal

from .temporal_query_parser import parse_temporal_query

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class RetrievalResult:
    """A single retrieval result from any source."""
    id: str
    source_type: Literal["email", "company", "operation"]
    score: float                     # Final fused score (0–1 range)
    title: str                       # Subject / company name / operation name
    snippet: str = ""                # Contextual snippet
    metadata: dict = field(default_factory=dict)  # Source-specific fields

    # Individual component scores for debugging/tuning
    vector_score: float = 0.0
    keyword_score: float = 0.0
    recency_score: float = 1.0


@dataclass
class RetrievalResponse:
    """Full retrieval response."""
    results: list[RetrievalResult]
    query: str                       # Original query
    cleaned_query: str               # Query with temporal expressions stripped
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    total_vector_hits: int = 0
    total_keyword_hits: int = 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Reciprocal Rank Fusion constant (higher = less aggressive rank penalty)
RRF_K = 60

# Recency decay: score = exp(-DECAY_RATE * days_since_email)
# At 30 days → 0.95, at 90 days → 0.86, at 365 days → 0.69
RECENCY_DECAY_RATE = 0.001

# Weights for vector vs keyword in the final score (before RRF)
VECTOR_WEIGHT = 0.65
KEYWORD_WEIGHT = 0.35


# ---------------------------------------------------------------------------
# Hybrid Retriever
# ---------------------------------------------------------------------------

class HybridRetriever:
    """
    Hybrid retrieval with vector search, BM25 keyword search,
    reciprocal rank fusion, and time-aware ranking.
    """

    def __init__(self, supabase_client):
        self._sb = supabase_client

    async def retrieve(
        self,
        query: str,
        client_id: Optional[str] = None,
        sources: Optional[list[str]] = None,
        limit: int = 20,
        vector_threshold: float = 0.55,
        keyword_limit: int = 30,
        vector_limit: int = 30,
        reference_date: Optional[date] = None,
    ) -> RetrievalResponse:
        """
        Main retrieval interface.

        Args:
            query: Natural language search query
            client_id: Filter to a specific client
            sources: List of sources to search ("emails", "companies", "operations").
                     Defaults to all three.
            limit: Max results to return after fusion
            vector_threshold: Minimum cosine similarity for vector search
            keyword_limit: Max results from keyword search per source
            vector_limit: Max results from vector search per source
            reference_date: Date for resolving temporal expressions (default: today)

        Returns:
            RetrievalResponse with fused, ranked results
        """
        if sources is None:
            sources = ["emails", "companies", "operations"]

        # Step 1: Parse temporal expressions
        parsed = parse_temporal_query(query, reference_date)
        logger.info(
            f"Temporal parse: has_temporal={parsed.has_temporal}, "
            f"date_from={parsed.date_from}, date_to={parsed.date_to}, "
            f"cleaned='{parsed.cleaned_query}'"
        )

        # Step 2: Run searches in parallel
        tasks = []
        task_labels = []

        if "emails" in sources:
            tasks.append(self._search_emails_vector(
                parsed.cleaned_query, client_id, vector_threshold, vector_limit,
                parsed.date_from, parsed.date_to,
            ))
            task_labels.append("email_vector")

            tasks.append(self._search_emails_keyword(
                parsed.cleaned_query, client_id, keyword_limit,
                parsed.date_from, parsed.date_to,
            ))
            task_labels.append("email_keyword")

        if "companies" in sources:
            tasks.append(self._search_companies_vector(
                parsed.cleaned_query, client_id, vector_threshold, vector_limit,
                parsed.date_from, parsed.date_to,
            ))
            task_labels.append("company_vector")

        if "operations" in sources:
            tasks.append(self._search_operations_vector(
                parsed.cleaned_query, client_id, vector_threshold, vector_limit,
            ))
            task_labels.append("operation_vector")

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Step 3: Collect results by ID
        results_by_id: dict[str, RetrievalResult] = {}
        vector_ranks: dict[str, int] = {}   # id → rank in vector results
        keyword_ranks: dict[str, int] = {}  # id → rank in keyword results
        total_vector = 0
        total_keyword = 0

        for label, result in zip(task_labels, raw_results):
            if isinstance(result, Exception):
                logger.warning(f"Search failed for {label}: {result}")
                continue

            is_keyword = "keyword" in label
            source_type = label.split("_")[0]

            for rank, item in enumerate(result):
                item_id = str(item.get("id", ""))
                if not item_id:
                    continue

                if is_keyword:
                    total_keyword += 1
                    keyword_ranks[item_id] = rank + 1
                else:
                    total_vector += 1
                    vector_ranks[item_id] = rank + 1

                if item_id not in results_by_id:
                    results_by_id[item_id] = self._build_result(item, source_type)

                # Update component scores
                r = results_by_id[item_id]
                if is_keyword:
                    r.keyword_score = max(r.keyword_score, item.get("rank_score", 0))
                else:
                    r.vector_score = max(r.vector_score, item.get("similarity", 0))

        # Step 4: Apply recency decay
        today = reference_date or date.today()
        for r in results_by_id.values():
            sent_str = r.metadata.get("sent_date") or r.metadata.get("last_contact_date")
            if sent_str:
                try:
                    sent_date = datetime.fromisoformat(sent_str.replace("Z", "+00:00")).date()
                    days_ago = (today - sent_date).days
                    r.recency_score = math.exp(-RECENCY_DECAY_RATE * max(days_ago, 0))
                except (ValueError, TypeError):
                    pass

        # Step 5: Reciprocal Rank Fusion
        for item_id, r in results_by_id.items():
            v_rank = vector_ranks.get(item_id)
            k_rank = keyword_ranks.get(item_id)

            rrf_score = 0.0
            if v_rank:
                rrf_score += VECTOR_WEIGHT / (RRF_K + v_rank)
            if k_rank:
                rrf_score += KEYWORD_WEIGHT / (RRF_K + k_rank)

            # Multiply by recency decay
            r.score = rrf_score * r.recency_score

        # Step 6: Sort and limit
        ranked = sorted(results_by_id.values(), key=lambda r: r.score, reverse=True)[:limit]

        return RetrievalResponse(
            results=ranked,
            query=query,
            cleaned_query=parsed.cleaned_query,
            date_from=parsed.date_from,
            date_to=parsed.date_to,
            total_vector_hits=total_vector,
            total_keyword_hits=total_keyword,
        )

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    async def _search_emails_vector(
        self, query: str, client_id: Optional[str],
        threshold: float, limit: int,
        date_from: Optional[str], date_to: Optional[str],
    ) -> list[dict]:
        """Semantic vector search over emails."""
        try:
            from .vector_service import embed_query
            query_emb = await embed_query(query, client_id)
            params: dict = {
                "query_embedding": query_emb,
                "match_threshold": threshold,
                "match_count": limit,
                "p_client_id": client_id,
            }
            if date_from:
                params["p_date_from"] = date_from
            if date_to:
                params["p_date_to"] = date_to
            result = self._sb.rpc("search_emails", params).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Email vector search failed: {e}")
            return []

    async def _search_emails_keyword(
        self, query: str, client_id: Optional[str], limit: int,
        date_from: Optional[str], date_to: Optional[str],
    ) -> list[dict]:
        """BM25-style keyword search over emails using tsvector."""
        try:
            params: dict = {
                "p_query": query,
                "p_limit": limit,
            }
            if client_id:
                params["p_client_id"] = client_id
            if date_from:
                params["p_date_from"] = date_from
            if date_to:
                params["p_date_to"] = date_to
            result = self._sb.rpc("keyword_search_emails", params).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Email keyword search failed: {e}")
            return []

    async def _search_companies_vector(
        self, query: str, client_id: Optional[str],
        threshold: float, limit: int,
        date_from: Optional[str], date_to: Optional[str],
    ) -> list[dict]:
        """Semantic vector search over companies."""
        try:
            from .vector_service import embed_query
            query_emb = await embed_query(query, client_id)
            params: dict = {
                "query_embedding": query_emb,
                "match_threshold": threshold,
                "match_count": limit,
                "p_client_id": client_id,
            }
            if date_from:
                params["p_date_from"] = date_from
            if date_to:
                params["p_date_to"] = date_to
            result = self._sb.rpc("search_companies", params).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Company vector search failed: {e}")
            return []

    async def _search_operations_vector(
        self, query: str, client_id: Optional[str],
        threshold: float, limit: int,
    ) -> list[dict]:
        """Semantic vector search over QB operations."""
        try:
            from .vector_service import embed_query
            query_emb = await embed_query(query, client_id)
            result = self._sb.rpc("search_operations", {
                "query_embedding": query_emb,
                "match_threshold": threshold,
                "match_count": limit,
                "p_client_id": client_id,
            }).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Operations vector search failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Result building
    # ------------------------------------------------------------------

    def _build_result(self, item: dict, source_type: str) -> RetrievalResult:
        """Convert a raw search result into a RetrievalResult."""
        item_id = str(item.get("id", ""))

        if source_type == "email":
            return RetrievalResult(
                id=item_id,
                source_type="email",
                score=0.0,
                title=item.get("subject") or "(no subject)",
                snippet=f"From: {item.get('sender_name') or item.get('sender_email', '?')}",
                metadata={
                    "sender_email": item.get("sender_email"),
                    "sender_name": item.get("sender_name"),
                    "sent_date": item.get("sent_date"),
                    "is_outbound": item.get("is_outbound"),
                },
            )
        elif source_type == "company":
            return RetrievalResult(
                id=item_id,
                source_type="company",
                score=0.0,
                title=item.get("company_name") or "(unknown company)",
                snippet=f"Industry: {item.get('industry') or '-'} | Tier: {item.get('qb_tier') or '-'}",
                metadata={
                    "industry": item.get("industry"),
                    "qb_tier": item.get("qb_tier"),
                    "qb_total_revenue": item.get("qb_total_revenue"),
                    "email_domains": item.get("email_domains"),
                    "last_contact_date": None,  # Not in search_companies return
                },
            )
        elif source_type == "operation":
            return RetrievalResult(
                id=item_id,
                source_type="operation",
                score=0.0,
                title=item.get("operation_name") or item.get("customer_name") or "(unknown op)",
                snippet=f"Dept: {item.get('department') or '-'} | Machine: {item.get('machine') or '-'}",
                metadata={
                    "department": item.get("department"),
                    "machine": item.get("machine"),
                    "customer_name": item.get("customer_name"),
                    "capability_tags": item.get("capability_tags"),
                    "row_type": item.get("row_type"),
                },
            )
        else:
            return RetrievalResult(
                id=item_id,
                source_type="email",
                score=0.0,
                title=str(item.get("subject") or item.get("company_name") or item_id),
            )
