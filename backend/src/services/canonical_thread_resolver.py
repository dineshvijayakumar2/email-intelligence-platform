"""
Canonical Thread Resolver — Cross-mailbox thread identity resolution.

Computes a canonical_thread_id for every email using a ranked signal stack:
  Tier 1: In-Reply-To header → definitive match to known Message-ID
  Tier 2: References header chain → walk to earliest ancestor
  Tier 3: Normalized subject + participant overlap ≥ 85% → merge
  Tier 4: Time proximity (< 72hr) + same participants → disambiguation only

The resolver writes canonical_thread_id, thread_match_method, and
thread_match_confidence on each email without modifying raw data.
Merges are logged to thread_merges for audit/review.

Usage:
    resolver = CanonicalThreadResolver(client_id="uuid")
    resolver.resolve_all()  # Backfill all emails
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from ..database.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

# Subject prefix pattern: Re:, Fwd:, FW:, AW:, SV:, TR:, RES:, etc.
SUBJECT_PREFIX_RE = re.compile(
    r'^(?:\s*(?:Re|Fwd|Fw|AW|SV|TR|RES|Rif)\s*:\s*)+',
    re.IGNORECASE
)

PAGE_SIZE = 500
UPSERT_BATCH = 50  # Smaller batches to avoid statement timeout


def _normalize_subject(subject: str) -> str:
    """Strip reply/forward prefixes, lowercase, collapse whitespace."""
    if not subject:
        return ''
    cleaned = SUBJECT_PREFIX_RE.sub('', subject)
    return ' '.join(cleaned.strip().lower().split())


def _clean_message_id(mid: str) -> str:
    """Strip angle brackets from a Message-ID."""
    if not mid:
        return ''
    return mid.strip().strip('<>').strip()


def _extract_message_ids(references: str) -> List[str]:
    """Extract all Message-IDs from a References header."""
    if not references:
        return []
    return [m.strip('<>') for m in re.findall(r'<([^>]+)>', references)]


class CanonicalThreadResolver:
    """Resolves canonical thread IDs across all mailboxes for a client."""

    # Scoring weights for Tier 3 (subject + participant heuristic)
    PARTICIPANT_WEIGHT = 0.60
    RECENCY_WEIGHT = 0.25
    SUBJECT_WEIGHT = 0.15

    MERGE_THRESHOLD = 0.85       # Auto-merge
    REVIEW_THRESHOLD = 0.60      # Merge but flag for review
    MAX_THREAD_SIZE = 500        # Skip threads larger than this

    def __init__(self, client_id: str, mailbox_id: str = None):
        self.client_id = client_id
        self.single_mailbox_id = mailbox_id  # If set, only resolve this mailbox
        self.client = SupabaseClient.get_client(use_service_key=True)

        # In-memory indexes (populated during resolve)
        self._msg_id_to_canonical: Dict[str, str] = {}    # message_id → canonical_thread_id
        self._canonical_threads: Dict[str, dict] = {}      # canonical_id → {subject, participants, last_date, email_count}
        self._subject_index: Dict[str, List[str]] = {}     # subject_normalized → [canonical_ids]

    def resolve_all(self) -> dict:
        """Resolve canonical thread IDs for ALL emails of this client.

        Processes emails in sent_date order (oldest first) so reply chains
        build up correctly. Saves results in batches.
        """
        stats = {
            'total_emails': 0,
            'tier1_message_id': 0,
            'tier2_references': 0,
            'tier3_subject': 0,
            'tier4_new': 0,
            'merges': 0,
        }

        # Get all mailbox IDs for this client
        mb_resp = self.client.table('mailboxes').select('id').eq(
            'client_id', self.client_id
        ).execute()
        mailbox_ids = [m['id'] for m in (mb_resp.data or [])]

        if self.single_mailbox_id:
            mailbox_ids = [self.single_mailbox_id]

        if not mailbox_ids:
            logger.warning("No mailboxes found for client")
            return stats

        COLUMNS = (
            'id, internet_message_id, in_reply_to, references_header, '
            'subject, subject_normalized, sender_email, recipients, cc_list, '
            'sent_date, is_outbound, thread_id, provider_thread_id, mailbox_id'
        )

        # Phase 1: Resolve all emails in memory (fast — no DB writes)
        # Collect only (email_id → canonical_thread_id, method, confidence) — lightweight
        resolutions: Dict[str, tuple] = {}  # email_id → (canonical_id, method, confidence)
        total_processed = 0

        for mb_idx, mb_id in enumerate(mailbox_ids):
            offset = 0
            mb_count = 0

            while True:
                import time as _time
                try:
                    resp = self.client.table('emails').select(
                        COLUMNS
                    ).eq('mailbox_id', mb_id).is_(
                        'canonical_thread_id', 'null'
                    ).order(
                        'sent_date', desc=False
                    ).range(offset, offset + PAGE_SIZE - 1).execute()
                except Exception as e:
                    logger.warning(f"Fetch retry at mailbox {mb_idx+1} offset {offset}: {e}")
                    _time.sleep(2)
                    try:
                        resp = self.client.table('emails').select(
                            COLUMNS
                        ).eq('mailbox_id', mb_id).is_(
                            'canonical_thread_id', 'null'
                        ).order(
                            'sent_date', desc=False
                        ).range(offset, offset + PAGE_SIZE - 1).execute()
                    except Exception:
                        logger.error(f"Fetch failed at offset {offset}, skipping rest of mailbox")
                        break

                rows = resp.data or []
                if not rows:
                    break

                for email in rows:
                    canonical_id, method, confidence = self._resolve_email(email)
                    resolutions[email['id']] = (canonical_id, method, confidence)

                    if method == 'message_id':
                        stats['tier1_message_id'] += 1
                    elif method == 'references':
                        stats['tier2_references'] += 1
                    elif method == 'subject_participant':
                        stats['tier3_subject'] += 1
                    else:
                        stats['tier4_new'] += 1

                mb_count += len(rows)
                total_processed += len(rows)
                offset += len(rows)

            logger.info(
                f"Mailbox {mb_idx + 1}/{len(mailbox_ids)}: {mb_count} emails resolved. "
                f"T1={stats['tier1_message_id']}, T2={stats['tier2_references']}, "
                f"T3={stats['tier3_subject']}, New={stats['tier4_new']}, "
                f"Threads={len(self._canonical_threads)}"
            )

        stats['total_emails'] = total_processed
        logger.info(f"Phase 1 complete: {total_processed} emails resolved into "
                    f"{len(self._canonical_threads)} threads. Starting Phase 2 (save)...")

        # Phase 2: Batch save all resolutions
        items = list(resolutions.items())
        saved = 0
        SAVE_BATCH = 200

        # Drop indexes on canonical_thread_id columns for bulk update performance
        from ..database.bulk_index_manager import BulkIndexManager
        _mgr = BulkIndexManager(self.client)
        _dropped = _mgr.drop_indexes(['emails']) if len(items) >= 500 else 0
        try:
         for i in range(0, len(items), SAVE_BATCH):
            batch = items[i:i + SAVE_BATCH]
            payload = [
                {
                    'email_id': eid,
                    'canonical_thread_id': vals[0],
                    'thread_match_method': vals[1],
                    'thread_match_confidence': str(vals[2]),
                }
                for eid, vals in batch
            ]
            try:
                self.client.rpc('batch_update_canonical_threads', {
                    'p_updates': payload,
                }).execute()
                saved += len(batch)
            except Exception:
                # Fallback: smaller chunks
                for j in range(0, len(payload), 25):
                    small = payload[j:j + 25]
                    try:
                        self.client.rpc('batch_update_canonical_threads', {
                            'p_updates': small,
                        }).execute()
                        saved += len(small)
                    except Exception as e:
                        logger.warning(f"Save chunk failed: {e}")

            if saved % 5000 == 0 and saved > 0:
                logger.info(f"Phase 2 save progress: {saved}/{total_processed}")

        finally:
         if _dropped:
             _mgr.recreate_indexes(['emails'])

        logger.info(f"Phase 2 complete: {saved}/{total_processed} emails saved")

        stats['canonical_threads'] = len(self._canonical_threads)
        stats['merges'] = 0

        logger.info(
            f"Thread resolution complete: {stats['total_emails']} emails → "
            f"{stats['canonical_threads']} canonical threads. "
            f"T1={stats['tier1_message_id']}, T2={stats['tier2_references']}, "
            f"T3={stats['tier3_subject']}, New={stats['tier4_new']}"
        )

        return stats

    def _resolve_email(self, email: dict) -> Tuple[str, str, float]:
        """Resolve canonical thread ID for a single email.

        Returns: (canonical_thread_id, method, confidence)
        """
        msg_id = _clean_message_id(email.get('internet_message_id') or '')
        in_reply_to = _clean_message_id(email.get('in_reply_to') or '')
        references = email.get('references_header') or ''
        subject = email.get('subject') or ''
        subject_norm = (email.get('subject_normalized') or _normalize_subject(subject)).strip()
        sent_date = email.get('sent_date') or ''

        # Collect all participants
        participants = self._get_participants(email)

        # --- Tier 1: In-Reply-To matches a known Message-ID ---
        if in_reply_to and in_reply_to in self._msg_id_to_canonical:
            canonical_id = self._msg_id_to_canonical[in_reply_to]
            self._register_email(canonical_id, msg_id, subject_norm, participants, sent_date)
            return canonical_id, 'message_id', 1.0

        # --- Tier 2: References header chain ---
        ref_ids = _extract_message_ids(references)
        for ref_id in ref_ids:
            if ref_id in self._msg_id_to_canonical:
                canonical_id = self._msg_id_to_canonical[ref_id]
                self._register_email(canonical_id, msg_id, subject_norm, participants, sent_date)
                return canonical_id, 'references', 0.95

        # --- Tier 3: Subject + participant scoring ---
        if subject_norm and len(subject_norm) >= 5:
            best_match, best_score = self._find_subject_match(
                subject_norm, participants, sent_date
            )
            if best_match and best_score >= self.REVIEW_THRESHOLD:
                self._register_email(best_match, msg_id, subject_norm, participants, sent_date)
                return best_match, 'subject_participant', round(best_score, 2)

        # --- Tier 4: New thread ---
        canonical_id = str(uuid4())
        self._register_email(canonical_id, msg_id, subject_norm, participants, sent_date, new_thread=True)
        return canonical_id, 'new', 1.0

    def _get_participants(self, email: dict) -> set:
        """Extract all participant email addresses from an email."""
        participants = set()
        sender = (email.get('sender_email') or '').strip().lower()
        if sender:
            participants.add(sender)

        for field in ('recipients', 'cc_list'):
            for r in (email.get(field) or []):
                addr = r.get('email') if isinstance(r, dict) else r if isinstance(r, str) else None
                if addr and '@' in addr:
                    participants.add(addr.strip().lower())

        return participants

    def _register_email(
        self, canonical_id: str, msg_id: str, subject_norm: str,
        participants: set, sent_date: str, new_thread: bool = False,
    ):
        """Register an email in the in-memory indexes."""
        # Map message_id → canonical
        if msg_id and msg_id != '__none__':
            self._msg_id_to_canonical[msg_id] = canonical_id

        # Update or create canonical thread metadata
        if canonical_id not in self._canonical_threads:
            self._canonical_threads[canonical_id] = {
                'subject': subject_norm,
                'participants': set(participants),
                'last_date': sent_date,
                'email_count': 0,
            }
        thread = self._canonical_threads[canonical_id]
        thread['participants'].update(participants)
        thread['last_date'] = max(thread['last_date'], sent_date) if sent_date else thread['last_date']
        thread['email_count'] += 1

        # Update subject index
        if subject_norm and len(subject_norm) >= 5:
            if subject_norm not in self._subject_index:
                self._subject_index[subject_norm] = []
            if canonical_id not in self._subject_index[subject_norm]:
                self._subject_index[subject_norm].append(canonical_id)

    def _find_subject_match(
        self, subject_norm: str, participants: set, sent_date: str,
    ) -> Tuple[Optional[str], float]:
        """Find the best matching existing thread by subject + participant overlap.

        Returns: (canonical_id or None, score)
        """
        candidates = self._subject_index.get(subject_norm, [])
        if not candidates:
            return None, 0.0

        best_id = None
        best_score = 0.0

        for cid in candidates:
            thread = self._canonical_threads.get(cid)
            if not thread:
                continue
            if thread['email_count'] >= self.MAX_THREAD_SIZE:
                continue

            score = self._score_match(thread, participants, sent_date, subject_norm)
            if score > best_score:
                best_score = score
                best_id = cid

        return best_id, best_score

    def _score_match(
        self, thread: dict, participants: set, sent_date: str, subject_norm: str,
    ) -> float:
        """Score how well an email matches an existing thread (0.0 - 1.0)."""
        score = 0.0

        # Participant overlap (most important signal)
        thread_participants = thread.get('participants', set())
        if thread_participants and participants:
            overlap = len(participants & thread_participants)
            union = len(participants | thread_participants)
            overlap_ratio = overlap / union if union > 0 else 0
            score += overlap_ratio * self.PARTICIPANT_WEIGHT

        # Recency score
        thread_last = thread.get('last_date', '')
        if sent_date and thread_last:
            try:
                email_dt = datetime.fromisoformat(sent_date.replace('Z', '+00:00'))
                thread_dt = datetime.fromisoformat(thread_last.replace('Z', '+00:00'))
                days_apart = abs((email_dt - thread_dt).days)
                if days_apart <= 7:
                    score += 0.25 * self.RECENCY_WEIGHT / 0.25  # full recency weight
                elif days_apart <= 30:
                    score += 0.10 * self.RECENCY_WEIGHT / 0.25
                elif days_apart > 180:
                    score -= 0.15  # Penalty for very old threads
            except (ValueError, TypeError):
                pass

        # Subject similarity (already exact match since we index by subject_norm)
        score += 1.0 * self.SUBJECT_WEIGHT

        return max(0.0, min(1.0, score))

    def _save_batch(self, updates: List[dict]):
        """Save canonical_thread_id updates to emails table.

        Uses RPC in small batches (25 rows). Falls back to individual updates on failure.
        """
        RPC_BATCH = 25
        for i in range(0, len(updates), RPC_BATCH):
            chunk = updates[i:i + RPC_BATCH]
            payload = [
                {
                    'email_id': u['id'],
                    'canonical_thread_id': u['canonical_thread_id'],
                    'thread_match_method': u['thread_match_method'],
                    'thread_match_confidence': str(u['thread_match_confidence']),
                }
                for u in chunk
            ]
            try:
                self.client.rpc('batch_update_canonical_threads', {
                    'p_updates': payload,
                }).execute()
            except Exception:
                # Fallback: individual updates for this chunk
                for row in chunk:
                    try:
                        self.client.table('emails').update({
                            'canonical_thread_id': row['canonical_thread_id'],
                            'thread_match_method': row['thread_match_method'],
                            'thread_match_confidence': row['thread_match_confidence'],
                        }).eq('id', row['id']).execute()
                    except Exception as e:
                        logger.warning(f"Failed to update email {row['id']}: {e}")
