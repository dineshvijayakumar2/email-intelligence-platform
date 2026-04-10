"""
Vector Service — Embedding + Semantic Search via pgvector (Sprint 4 S4.4).

Fully independent of AI analysis pipeline. Embeds directly from raw source tables:
  - emails (subject + body_text + sender)
  - customer_companies (name + industry + domains + QB data)
  - qb_operations (operation + dept + machine + customer + capabilities)

Supports two embedding providers (set EMBEDDING_PROVIDER env var):
  - "google" (default): Google text-embedding-004 / gemini-embedding-001 (768 dims)
  - "openai": OpenAI text-embedding-3-small (768 dims, configurable)

Both produce 768-dim vectors compatible with the existing pgvector schema.
"""

import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding model config
# ---------------------------------------------------------------------------
EMBEDDING_DIMS = 768   # Force 768 dims (pgvector HNSW/IVFFlat max = 2000)
EMBED_BATCH_SIZE = 50   # Texts per API call
EMBED_DELAY_SECONDS = 5  # Base delay between batches (Google rate limits)

# Google model
GOOGLE_EMBEDDING_MODEL = "models/gemini-embedding-001"

# OpenAI model — text-embedding-3-small supports dimensions param for 768
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

# Cache the model instance to avoid re-init on every call
_embedding_model_cache = None
_embedding_provider_override = None  # Set explicitly by reset_embedding_model()


def _get_embedding_model():
    """Lazy-init embedding model. Provider from explicit override > env var > 'google'.

    Returns a LangChain Embeddings instance (Google or OpenAI).
    Both produce 768-dim vectors compatible with pgvector.
    """
    global _embedding_model_cache
    if _embedding_model_cache is not None:
        return _embedding_model_cache

    provider = _embedding_provider_override or os.getenv("EMBEDDING_PROVIDER", "google").lower()

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY env var required for OpenAI embeddings")

        _embedding_model_cache = OpenAIEmbeddings(
            model=OPENAI_EMBEDDING_MODEL,
            openai_api_key=api_key,
            dimensions=EMBEDDING_DIMS,
        )
        logger.info(f"Embedding provider: OpenAI ({OPENAI_EMBEDDING_MODEL}, {EMBEDDING_DIMS} dims)")
    else:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        api_key = (
            os.getenv("GOOGLE_GENAI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GOOGLE_GENERATIVE_AI_API_KEY")
        )
        if not api_key:
            raise RuntimeError(
                "GOOGLE_GENAI_API_KEY (or GOOGLE_API_KEY) env var required for embeddings"
            )
        _embedding_model_cache = GoogleGenerativeAIEmbeddings(
            model=GOOGLE_EMBEDDING_MODEL,
            google_api_key=api_key,
            output_dimensionality=EMBEDDING_DIMS,
        )
        logger.info(f"Embedding provider: Google ({GOOGLE_EMBEDDING_MODEL}, {EMBEDDING_DIMS} dims)")

    return _embedding_model_cache


# ---------------------------------------------------------------------------
def reset_embedding_model(provider: str = None):
    """Clear the cached embedding model and set the new provider explicitly."""
    global _embedding_model_cache, _embedding_provider_override
    _embedding_model_cache = None
    _embedding_provider_override = provider.lower() if provider else None
    logger.info(f"Embedding model cache cleared. Provider set to: {_embedding_provider_override or 'env/default'}")


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _is_rate_limit_error(e: Exception) -> bool:
    """Check if an exception is a rate limit / availability error from any provider."""
    error_str = str(e)
    return any(kw in error_str for kw in [
        '429', 'RESOURCE_EXHAUSTED', 'RateLimitError', 'rate_limit',
        '503', 'UNAVAILABLE', 'overloaded', 'high demand',
    ])


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using configured embedding provider.

    Returns list of 768-dim float vectors, one per input text.
    Handles batching + rate limit retries for both Google and OpenAI.
    """
    model = _get_embedding_model()
    all_embeddings: list[list[float]] = []
    batch_count = 0

    # OpenAI has higher rate limits — less aggressive delays needed
    is_openai = _embedding_provider_override == "openai"
    base_delay = 1 if is_openai else EMBED_DELAY_SECONDS

    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i:i + EMBED_BATCH_SIZE]

        # Retry with exponential backoff on rate limit / availability errors
        was_rate_limited = False
        succeeded = False
        for attempt in range(5):
            try:
                batch_embeddings = await asyncio.to_thread(model.embed_documents, batch)
                all_embeddings.extend(batch_embeddings)
                succeeded = True
                break
            except Exception as e:
                if _is_rate_limit_error(e):
                    was_rate_limited = True
                    wait = base_delay * (2 ** attempt)
                    logger.info(f"[Vector] Rate limited ({_embedding_provider_override or 'google'}), waiting {wait}s (attempt {attempt + 1}/5)")
                    await asyncio.sleep(wait)
                else:
                    raise

        if not succeeded:
            logger.warning(
                f"[Vector] Skipping batch of {len(batch)} texts after 5 retries. "
                f"Embedded {len(all_embeddings)} of {len(texts)} so far."
            )
            all_embeddings.extend([None] * len(batch))
            await asyncio.sleep(60)
            continue

        batch_count += 1

        # Progressive delay strategy to stay under rate limits:
        # OpenAI: minimal delays (higher quota), Google: aggressive delays (free tier)
        if i + EMBED_BATCH_SIZE < len(texts):
            if was_rate_limited:
                cooldown = 10 if is_openai else 30
            elif batch_count % 5 == 0:
                cooldown = 2 if is_openai else 15
            else:
                cooldown = 0.5 if is_openai else base_delay
            await asyncio.sleep(cooldown)

    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """Embed a single query text. Uses embed_query (optimised for retrieval queries)."""
    model = _get_embedding_model()
    return await asyncio.to_thread(model.embed_query, text)


# ---------------------------------------------------------------------------
# VectorService class
# ---------------------------------------------------------------------------

class VectorService:
    """Orchestrates embedding + semantic search across the platform."""

    def __init__(self, supabase_client):
        self._sb = supabase_client

    async def _db(self, fn):
        """Run a blocking Supabase call in a thread to avoid blocking the event loop."""
        return await asyncio.to_thread(fn)

    @staticmethod
    def _vecs_to_pg(embeddings: list[list[float]]) -> list[str]:
        """Convert embedding float arrays to PostgreSQL vector string format."""
        return [f"[{','.join(str(v) for v in emb)}]" for emb in embeddings]

    # ── Embed: Emails (from raw emails table) ─────────────────────────────

    async def embed_emails_batch(
        self, client_id: str, batch_size: int = 200, limit: int | None = None
    ) -> dict:
        """Embed all un-embedded emails for a client.

        Reads directly from the `emails` table — no dependency on AI analysis.
        Builds embed text from: subject + body_text (truncated) + sender.
        Stores embedding on the `emails` table.
        """
        t0 = time.time()
        offset = 0
        total_embedded = 0
        total_skipped = 0

        while True:
            result = await self._db(lambda: self._sb.table("emails").select(
                "id, subject, body_text, sender_email, sender_name, is_outbound"
            ).eq("client_id", client_id).is_("embedding", "null").range(
                offset, offset + batch_size - 1
            ).execute())

            rows = result.data or []
            if not rows:
                break

            texts = []
            ids = []
            for row in rows:
                text = self._build_email_embed_text(row)
                if not text or len(text.strip()) < 10:
                    total_skipped += 1
                    continue
                texts.append(text)
                ids.append(row["id"])

            if texts:
                embeddings = await embed_texts(texts)
                # Filter out None entries (skipped due to rate limits)
                valid = [(i, e) for i, e in zip(ids, embeddings) if e is not None]
                if not valid:
                    total_skipped += len(ids)
                else:
                    v_ids, v_embs = zip(*valid)
                    v_ids, v_embs = list(v_ids), list(v_embs)
                    total_skipped += len(ids) - len(v_ids)
                    # Write to DB in small chunks to avoid statement timeout
                    DB_CHUNK = 10
                    for ci in range(0, len(v_ids), DB_CHUNK):
                        chunk_ids = v_ids[ci:ci + DB_CHUNK]
                        chunk_embs = v_embs[ci:ci + DB_CHUNK]
                        try:
                            await self._db(lambda cids=chunk_ids, cembs=chunk_embs: self._sb.rpc(
                                "batch_update_embeddings_emails", {
                                    "p_ids": cids,
                                    "p_embeddings": self._vecs_to_pg(cembs),
                                }).execute())
                            total_embedded += len(chunk_ids)
                        except Exception as e:
                            logger.warning(f"Batch chunk failed ({len(chunk_ids)} emails): {e}")
                            total_skipped += len(chunk_ids)

            offset += batch_size
            if limit and total_embedded >= limit:
                break
            if len(rows) < batch_size:
                break
            if hasattr(self, '_cancel_check') and self._cancel_check():
                logger.info(f"[Vector] Email embedding stopped by user at {total_embedded} records")
                break

            if total_embedded % 1000 == 0 and total_embedded > 0:
                logger.info(f"[Vector] Embedded {total_embedded} emails so far...")

        elapsed = round(time.time() - t0, 1)
        logger.info(
            f"[Vector] Email embedding {'stopped' if hasattr(self, '_cancel_check') and self._cancel_check() else 'complete'}: "
            f"{total_embedded} embedded, {total_skipped} skipped, {elapsed}s"
        )
        return {"embedded": total_embedded, "skipped": total_skipped, "elapsed_s": elapsed}

    def _build_email_embed_text(self, row: dict) -> str:
        """Build a text representation of an email for embedding.

        Uses raw email data — subject, body (truncated to 1000 chars), sender.
        No dependency on AI-processed fields.
        """
        parts = []
        if row.get("subject"):
            parts.append(f"Subject: {row['subject']}")
        if row.get("sender_name"):
            parts.append(f"From: {row['sender_name']}")
        elif row.get("sender_email"):
            parts.append(f"From: {row['sender_email']}")
        if row.get("is_outbound"):
            parts.append("Direction: outbound")
        # Truncate body to keep embedding focused + within model limits
        body = (row.get("body_text") or "").strip()
        if body:
            # Take first 1000 chars — enough context for semantic matching
            parts.append(body[:1000])
        return " | ".join(parts)

    # ── Embed: Companies ──────────────────────────────────────────────────

    async def embed_companies(self, client_id: str, limit: int | None = None) -> dict:
        """Embed all un-embedded companies for a client.

        Builds embed text from: company_name + industry + email_domains +
        QB enrichment fields (tier, revenue, account_manager).
        """
        t0 = time.time()
        offset = 0
        total_embedded = 0

        while True:
            result = await self._db(lambda: self._sb.table("customer_companies").select(
                "id, company_name, industry, email_domains, "
                "qb_tier, qb_total_revenue, qb_account_manager, qb_customer_type"
            ).eq("client_id", client_id).is_("embedding", "null").range(
                offset, offset + 499
            ).execute())

            rows = result.data or []
            if not rows:
                break

            texts = []
            ids = []
            for row in rows:
                text = self._build_company_embed_text(row)
                if text and len(text.strip()) >= 5:
                    texts.append(text)
                    ids.append(row["id"])

            if texts:
                embeddings = await embed_texts(texts)
                DB_CHUNK = 25
                for ci in range(0, len(ids), DB_CHUNK):
                    chunk_ids = ids[ci:ci + DB_CHUNK]
                    chunk_embs = embeddings[ci:ci + DB_CHUNK]
                    try:
                        await self._db(lambda cids=chunk_ids, cembs=chunk_embs: self._sb.rpc(
                            "batch_update_embeddings_companies", {
                                "p_ids": cids,
                                "p_embeddings": self._vecs_to_pg(cembs),
                            }).execute())
                        total_embedded += len(chunk_ids)
                    except Exception as e:
                        logger.warning(f"Batch chunk failed ({len(chunk_ids)} companies): {e}")

            offset += 500
            if limit and total_embedded >= limit:
                break
            if len(rows) < 500:
                break

        elapsed = round(time.time() - t0, 1)
        logger.info(f"[Vector] Company embedding complete: {total_embedded} embedded, {elapsed}s")
        return {"embedded": total_embedded, "elapsed_s": elapsed}

    def _build_company_embed_text(self, row: dict) -> str:
        """Build text representation of a company for embedding."""
        parts = []
        if row.get("company_name"):
            parts.append(row["company_name"])
        if row.get("industry"):
            parts.append(f"Industry: {row['industry']}")
        if row.get("email_domains"):
            domains = row["email_domains"]
            if isinstance(domains, list):
                parts.append(f"Domains: {', '.join(domains)}")
        if row.get("qb_tier"):
            parts.append(f"Tier: {row['qb_tier']}")
        if row.get("qb_customer_type"):
            parts.append(f"Status: {row['qb_customer_type']}")
        if row.get("qb_total_revenue"):
            parts.append(f"Revenue: ${row['qb_total_revenue']:,.0f}")
        if row.get("qb_account_manager"):
            parts.append(f"AM: {row['qb_account_manager']}")
        return " | ".join(parts)

    # ── Embed: Operations ─────────────────────────────────────────────────

    async def embed_operations(self, client_id: str, batch_size: int = 500, limit: int | None = None) -> dict:
        """Embed un-embedded QB operations."""
        t0 = time.time()
        total_embedded = 0
        offset = 0

        while True:
            result = await self._db(lambda: self._sb.table("qb_operations").select(
                "id, operation_name, department, machine, customer_name, "
                "capability_tags, row_type, finishing_type, "
                "qb_capability_tag, qb_process_tag, qb_machine_tier_tag, "
                "qb_row_type_tag, qb_embellishment_tag"
            ).eq("client_id", client_id).is_("embedding", "null").range(
                offset, offset + batch_size - 1
            ).execute())

            rows = result.data or []
            if not rows:
                break

            texts = []
            ids = []
            for row in rows:
                text = self._build_operation_embed_text(row)
                if text and len(text.strip()) >= 5:
                    texts.append(text)
                    ids.append(row["id"])

            if texts:
                embeddings = await embed_texts(texts)
                DB_CHUNK = 25
                for ci in range(0, len(ids), DB_CHUNK):
                    chunk_ids = ids[ci:ci + DB_CHUNK]
                    chunk_embs = embeddings[ci:ci + DB_CHUNK]
                    try:
                        await self._db(lambda cids=chunk_ids, cembs=chunk_embs: self._sb.rpc(
                            "batch_update_embeddings_operations", {
                                "p_ids": cids,
                                "p_embeddings": self._vecs_to_pg(cembs),
                            }).execute())
                        total_embedded += len(chunk_ids)
                    except Exception as e:
                        logger.warning(f"Batch chunk failed ({len(chunk_ids)} operations): {e}")

            offset += batch_size
            if limit and total_embedded >= limit:
                break
            if len(rows) < batch_size:
                break

            if total_embedded % 5000 == 0 and total_embedded > 0:
                logger.info(f"[Vector] Embedded {total_embedded} operations so far...")

        elapsed = round(time.time() - t0, 1)
        logger.info(f"[Vector] Operations embedding complete: {total_embedded} embedded, {elapsed}s")
        return {"embedded": total_embedded, "elapsed_s": elapsed}

    def _build_operation_embed_text(self, row: dict) -> str:
        """Build text representation of an operation for embedding.
        Prefers QB formula tags over classifier tags for richer embeddings."""
        parts = []
        if row.get("operation_name"):
            parts.append(row["operation_name"])
        if row.get("department"):
            parts.append(f"Dept: {row['department']}")
        if row.get("machine"):
            parts.append(f"Machine: {row['machine']}")
        if row.get("customer_name"):
            parts.append(f"Customer: {row['customer_name']}")

        # Prefer QB tags over classifier tags
        qb_cap = (row.get("qb_capability_tag") or "").strip()
        if qb_cap:
            parts.append(f"Capability: {qb_cap}")
        elif row.get("capability_tags"):
            tags = row["capability_tags"]
            if isinstance(tags, list) and tags:
                parts.append(f"Capabilities: {', '.join(tags)}")

        qb_process = (row.get("qb_process_tag") or "").strip()
        if qb_process:
            parts.append(f"Process: {qb_process}")

        qb_machine_tier = (row.get("qb_machine_tier_tag") or "").strip()
        if qb_machine_tier:
            parts.append(f"Technology: {qb_machine_tier}")

        qb_row_type = (row.get("qb_row_type_tag") or "").strip()
        if qb_row_type:
            parts.append(f"Type: {qb_row_type}")
        elif row.get("row_type"):
            parts.append(f"Type: {row['row_type']}")

        qb_emb = (row.get("qb_embellishment_tag") or "").strip()
        if qb_emb:
            parts.append(f"Embellishment: {qb_emb}")

        if row.get("finishing_type"):
            parts.append(f"Finishing: {row['finishing_type']}")
        return " | ".join(parts)

    # ── Search ────────────────────────────────────────────────────────────

    async def search_emails(
        self, query: str, client_id: str | None = None,
        threshold: float = 0.65, limit: int = 10,
        date_from: str | None = None, date_to: str | None = None,
    ) -> list[dict]:
        """Semantic search over emails, optionally bounded by date range."""
        query_emb = await embed_query(query)
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
        result = await self._db(lambda: self._sb.rpc("search_emails", params).execute())
        return result.data or []

    async def search_companies(
        self, query: str, client_id: str | None = None,
        threshold: float = 0.65, limit: int = 10,
        date_from: str | None = None, date_to: str | None = None,
    ) -> list[dict]:
        """Semantic search over companies, optionally bounded by date range."""
        query_emb = await embed_query(query)
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
        result = await self._db(lambda: self._sb.rpc("search_companies", params).execute())
        return result.data or []

    async def search_operations(
        self, query: str, client_id: str | None = None,
        threshold: float = 0.65, limit: int = 10,
    ) -> list[dict]:
        """Semantic search over QB operations."""
        query_emb = await embed_query(query)
        result = await self._db(lambda: self._sb.rpc("search_operations", {
            "query_embedding": query_emb,
            "match_threshold": threshold,
            "match_count": limit,
            "p_client_id": client_id,
        }).execute())
        return result.data or []

    # ── Composite helpers ─────────────────────────────────────────────────

    async def get_company_history_context(
        self, company_id: str, client_id: str, email_limit: int = 5
    ) -> dict:
        """Get rich context for a company: recent emails + operations profile."""
        company_result = await self._db(lambda: self._sb.table("customer_companies").select(
            "company_name, industry, qb_tier, qb_total_revenue"
        ).eq("id", company_id).single().execute())

        company = company_result.data
        if not company or not company.get("company_name"):
            return {"company": None, "recent_emails": [], "operations_profile": []}

        recent_emails = await self.search_emails(
            company["company_name"], client_id, threshold=0.6, limit=email_limit
        )
        operations = await self.search_operations(
            company["company_name"], client_id, threshold=0.6, limit=10
        )

        return {
            "company": company,
            "recent_emails": recent_emails,
            "operations_profile": operations,
        }

    async def reembed_all(
        self, client_id: str, limit: int | None = None,
        tables: list[str] | None = None,
        cancel_check: callable = None,
    ) -> dict:
        """Bootstrap / re-embed entities for a client. Returns combined stats.

        Args:
            limit: Max records to embed per table. Pass small value (e.g. 10) for local testing.
            tables: Which tables to embed. Default: ["emails", "companies", "operations"].
            cancel_check: Callable returning True if job should stop.
        """
        self._cancel_check = cancel_check or (lambda: False)
        if tables is None:
            tables = ["emails", "companies", "operations"]

        logger.info(f"[Vector] Starting reembed for client {client_id}, tables={tables}" + (f" (limit={limit})" if limit else ""))

        skip = {"embedded": 0, "skipped": 0, "elapsed_s": 0}

        emails = await self.embed_emails_batch(client_id, limit=limit) if "emails" in tables else skip
        if self._cancel_check():
            logger.info(f"[Vector] Stopped after emails ({emails['embedded']} embedded)")
            return {"emails": emails, "companies": skip, "operations": skip,
                    "total_embedded": emails["embedded"]}

        companies = await self.embed_companies(client_id, limit=limit) if "companies" in tables else skip
        if self._cancel_check():
            logger.info(f"[Vector] Stopped after companies ({companies['embedded']} embedded)")
            return {"emails": emails, "companies": companies, "operations": skip,
                    "total_embedded": emails["embedded"] + companies["embedded"]}

        operations = await self.embed_operations(client_id, limit=limit) if "operations" in tables else skip

        total = {
            "emails": emails,
            "companies": companies,
            "operations": operations,
            "total_embedded": (
                emails["embedded"] + companies["embedded"] + operations["embedded"]
            ),
        }
        logger.info(f"[Vector] Reembed complete for client {client_id}: {total}")
        return total
