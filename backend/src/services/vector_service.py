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
_cached_provider = None              # Track which provider the cached model is for


def _resolve_provider(client_id: str = None) -> str:
    """Resolve embedding provider: in-memory override > DB (client-scoped) > 'google'."""
    if _embedding_provider_override:
        return _embedding_provider_override
    if not client_id:
        # No client_id — try to read from the _last_client_id used
        client_id = _last_client_id
    if client_id:
        try:
            from ..database.supabase_client import SupabaseClient
            sb = SupabaseClient.get_client(use_service_key=True)
            resp = sb.table('system_settings').select('value').eq(
                'key', 'embedding_provider'
            ).eq('client_id', client_id).limit(1).execute()
            if resp.data and resp.data[0].get('value'):
                provider = resp.data[0]['value'].lower()
                logger.info(f"Embedding provider from DB: {provider} (client={client_id})")
                return provider
        except Exception as e:
            logger.warning(f"Could not read embedding_provider from DB: {e}")
    return "google"


# Track the last client_id used for embedding — so embed_texts() can
# resolve the correct provider even when called without client context.
_last_client_id: str | None = None


def _resolve_api_key(provider: str, client_id: str = None) -> str | None:
    """Resolve API key: DB (base64-encoded, per-client) > env var."""
    import base64

    # Try DB first (same source as the AI Usage page API Keys section)
    if client_id:
        try:
            from ..database.supabase_client import SupabaseClient
            sb = SupabaseClient.get_client(use_service_key=True)
            db_key_name = 'api_key_openai' if provider == 'openai' else 'api_key_google'
            resp = sb.table('system_settings').select('value').eq(
                'key', db_key_name
            ).eq('client_id', client_id).limit(1).execute()
            if resp.data and resp.data[0].get('value'):
                decoded = base64.b64decode(resp.data[0]['value']).decode()
                if decoded:
                    logger.info(f"API key for {provider} loaded from DB (client={client_id})")
                    return decoded
        except Exception as e:
            logger.debug(f"Could not read {provider} API key from DB: {e}")

    # Fall back to env vars
    if provider == 'openai':
        return os.getenv('OPENAI_API_KEY')
    else:
        return (
            os.getenv('GOOGLE_GENAI_API_KEY')
            or os.getenv('GOOGLE_API_KEY')
            or os.getenv('GOOGLE_GENERATIVE_AI_API_KEY')
        )


def _get_embedding_model(client_id: str = None):
    """Lazy-init embedding model. Provider from in-memory override > DB > 'google'.

    Returns a LangChain Embeddings instance (Google or OpenAI).
    Both produce 768-dim vectors compatible with pgvector.
    """
    global _embedding_model_cache, _last_client_id, _cached_provider
    if client_id:
        _last_client_id = client_id

    provider = _resolve_provider(client_id)

    # Return cached model only if provider hasn't changed
    if _embedding_model_cache is not None and _cached_provider == provider:
        return _embedding_model_cache
    # Provider changed — clear cache and reinitialize
    if _embedding_model_cache is not None and _cached_provider != provider:
        logger.info(f"Embedding provider changed from {_cached_provider} to {provider} — reinitializing")
        _embedding_model_cache = None

    # Resolve API key: DB (base64-encoded) > env var
    api_key = _resolve_api_key(provider, client_id)

    if provider == "openai":
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError:
            raise RuntimeError(
                "langchain-openai package not installed but embedding_provider is set to 'openai'. "
                "Either install langchain-openai or change the embedding provider to 'google' in AI Usage settings."
            )

        if not api_key:
            raise RuntimeError("OpenAI API key not found — set it in the AI Usage page or OPENAI_API_KEY env var")

        _embedding_model_cache = OpenAIEmbeddings(
            model=OPENAI_EMBEDDING_MODEL,
            openai_api_key=api_key,
            dimensions=EMBEDDING_DIMS,
        )
        _cached_provider = 'openai'
        logger.info(f"Embedding provider: OpenAI ({OPENAI_EMBEDDING_MODEL}, {EMBEDDING_DIMS} dims)")
    else:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        if not api_key:
            raise RuntimeError("Google API key not found — set it in the AI Usage page or GOOGLE_GENAI_API_KEY env var")

        _embedding_model_cache = GoogleGenerativeAIEmbeddings(
            model=GOOGLE_EMBEDDING_MODEL,
            google_api_key=api_key,
            output_dimensionality=EMBEDDING_DIMS,
        )
        _cached_provider = 'google'
        logger.info(f"Embedding provider: Google ({GOOGLE_EMBEDDING_MODEL}, {EMBEDDING_DIMS} dims)")

    return _embedding_model_cache


# ---------------------------------------------------------------------------
def reset_embedding_model(provider: str = None):
    """Clear the cached embedding model and set the new provider explicitly."""
    global _embedding_model_cache, _embedding_provider_override, _cached_provider
    _embedding_model_cache = None
    _cached_provider = None
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


async def embed_texts(texts: list[str], client_id: str = None) -> list[list[float]]:
    """Embed a list of texts using configured embedding provider.

    Returns list of 768-dim float vectors, one per input text.
    Handles batching + rate limit retries for both Google and OpenAI.
    """
    model = _get_embedding_model(client_id)
    all_embeddings: list[list[float]] = []
    batch_count = 0

    # Detect actual provider from the model instance (not the config —
    # config may say 'openai' but model fell back to Google if langchain-openai is missing)
    model_class = type(model).__name__
    is_openai = 'OpenAI' in model_class

    # OpenAI supports large batches (up to 2048) — use 500 to stay safe
    # Google has stricter quota limits — keep small batches
    api_batch_size = 500 if is_openai else EMBED_BATCH_SIZE
    base_delay = 1 if is_openai else EMBED_DELAY_SECONDS

    for i in range(0, len(texts), api_batch_size):
        batch = texts[i:i + api_batch_size]

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
                    logger.info(f"[Vector] Rate limited ({'openai' if is_openai else 'google'}), waiting {wait}s (attempt {attempt + 1}/5)")
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
        if i + api_batch_size < len(texts):
            if was_rate_limited:
                cooldown = 10 if is_openai else 30
            elif batch_count % 5 == 0:
                cooldown = 2 if is_openai else 15
            else:
                cooldown = 0.5 if is_openai else base_delay
            await asyncio.sleep(cooldown)

    return all_embeddings


async def embed_query(text: str, client_id: str = None) -> list[float]:
    """Embed a single query text. Uses embed_query (optimised for retrieval queries)."""
    model = _get_embedding_model(client_id)
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
        self, client_id: str, batch_size: int = 500, limit: int | None = None,
        on_progress: "callable | None" = None,
    ) -> dict:
        """Embed all un-embedded emails for a client.

        Reads directly from the `emails` table — no dependency on AI analysis.
        Builds embed text from: subject + body_text (truncated) + sender.
        Stores embedding on the `emails` table.

        Args:
            on_progress: Optional callback(stage: str, delta_processed: int,
                delta_failed: int) invoked after each DB chunk write succeeds or
                fails. Stage is always "embedding_emails" from this method.
        """
        from ..database.supabase_client import retry_async
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
                embeddings = await embed_texts(texts, client_id)
                # Filter out None entries (skipped due to rate limits)
                valid = [(i, e) for i, e in zip(ids, embeddings) if e is not None]
                if not valid:
                    total_skipped += len(ids)
                else:
                    v_ids, v_embs = zip(*valid)
                    v_ids, v_embs = list(v_ids), list(v_embs)
                    total_skipped += len(ids) - len(v_ids)
                    # Write to DB in chunks — HNSW indexes are dropped during
                    # bulk reembed (restored after), so 100 rows is fast.
                    # For non-reembed callers, indexes are present so keep lower.
                    DB_CHUNK = 100
                    for ci in range(0, len(v_ids), DB_CHUNK):
                        chunk_ids = v_ids[ci:ci + DB_CHUNK]
                        chunk_embs = v_embs[ci:ci + DB_CHUNK]
                        try:
                            # Wrap in async retry so transient socket errors
                            # (WinError 10035, ReadError, etc.) don't drop the
                            # whole chunk. Previously these were caught and the
                            # 100 emails were silently skipped.
                            await retry_async(
                                lambda cids=chunk_ids, cembs=chunk_embs: self._db(
                                    lambda: self._sb.rpc(
                                        "batch_update_embeddings_emails", {
                                            "p_ids": cids,
                                            "p_embeddings": self._vecs_to_pg(cembs),
                                        }).execute()
                                ),
                                label="batch_update_embeddings_emails",
                            )
                            total_embedded += len(chunk_ids)
                            if on_progress:
                                try:
                                    on_progress("embedding_emails", len(chunk_ids), 0)
                                except Exception as pe:
                                    logger.warning(f"[Vector] on_progress raised: {pe}")
                        except Exception as e:
                            logger.warning(f"Batch chunk failed ({len(chunk_ids)} emails) after retries: {e}")
                            total_skipped += len(chunk_ids)
                            if on_progress:
                                try:
                                    on_progress("embedding_emails", 0, len(chunk_ids))
                                except Exception as pe:
                                    logger.warning(f"[Vector] on_progress raised: {pe}")

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
                embeddings = await embed_texts(texts, client_id)
                DB_CHUNK = 100
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
                embeddings = await embed_texts(texts, client_id)
                DB_CHUNK = 100
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
        result = await self._db(lambda: self._sb.rpc("search_emails", params).execute())
        return result.data or []

    async def search_companies(
        self, query: str, client_id: str | None = None,
        threshold: float = 0.65, limit: int = 10,
        date_from: str | None = None, date_to: str | None = None,
    ) -> list[dict]:
        """Semantic search over companies, optionally bounded by date range."""
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
        result = await self._db(lambda: self._sb.rpc("search_companies", params).execute())
        return result.data or []

    async def search_operations(
        self, query: str, client_id: str | None = None,
        threshold: float = 0.65, limit: int = 10,
    ) -> list[dict]:
        """Semantic search over QB operations."""
        query_emb = await embed_query(query, client_id)
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
        cancel_check: "callable | None" = None,
        on_progress: "callable | None" = None,
    ) -> dict:
        """Bootstrap / re-embed entities for a client. Returns combined stats.

        Args:
            limit: Max records to embed per table. Pass small value (e.g. 10) for local testing.
            tables: Which tables to embed. Default: ["emails", "companies", "operations"].
            cancel_check: Callable returning True if job should stop.
            on_progress: Optional callback(stage: str, delta_processed: int,
                delta_failed: int) invoked at table boundaries AND from inside
                embed_emails_batch after each chunk write. Safe to pass None.
        """
        self._cancel_check = cancel_check or (lambda: False)
        if tables is None:
            tables = ["emails", "companies", "operations"]

        logger.info(f"[Vector] Starting reembed for client {client_id}, tables={tables}" + (f" (limit={limit})" if limit else ""))

        # Map friendly names to actual table names for BulkIndexManager
        table_map = {'emails': 'emails', 'companies': 'customer_companies', 'operations': 'qb_operations'}
        db_tables = [table_map[t] for t in tables if t in table_map]

        from ..database.bulk_index_manager import BulkIndexManager
        manager = BulkIndexManager(self._sb)

        skip = {"embedded": 0, "skipped": 0, "elapsed_s": 0}

        def _safe_progress(stage: str, delta_processed: int = 0, delta_failed: int = 0):
            if on_progress is None:
                return
            try:
                on_progress(stage, delta_processed, delta_failed)
            except Exception as pe:
                logger.warning(f"[Vector] on_progress raised at stage={stage}: {pe}")

        # BulkIndexManager handles drop → yield → recreate (including HNSW with extended timeout)
        _safe_progress("dropping_indexes")
        async with manager.async_bulk_operation(db_tables, row_count=999999):
            _safe_progress("embedding_emails")
            emails = (await self.embed_emails_batch(
                client_id, limit=limit, on_progress=on_progress
            )) if "emails" in tables else skip
            if self._cancel_check():
                logger.info(f"[Vector] Stopped after emails ({emails['embedded']} embedded)")
                return {"emails": emails, "companies": skip, "operations": skip,
                        "total_embedded": emails["embedded"]}

            _safe_progress("embedding_companies")
            companies = await self.embed_companies(client_id, limit=limit) if "companies" in tables else skip
            if "companies" in tables:
                _safe_progress("companies_done", companies.get("embedded", 0), companies.get("skipped", 0))
            if self._cancel_check():
                logger.info(f"[Vector] Stopped after companies ({companies['embedded']} embedded)")
                return {"emails": emails, "companies": companies, "operations": skip,
                        "total_embedded": emails["embedded"] + companies["embedded"]}

            _safe_progress("embedding_operations")
            operations = await self.embed_operations(client_id, limit=limit) if "operations" in tables else skip
            if "operations" in tables:
                _safe_progress("operations_done", operations.get("embedded", 0), operations.get("skipped", 0))

            _safe_progress("recreating_indexes")
        # async with exit — indexes recreated here by BulkIndexManager

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
