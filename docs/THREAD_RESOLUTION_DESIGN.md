# Best-in-Class Thread Resolution — Design Document

## Problem

The current thread ID assignment happens in the normalizer using `provider_thread_id` (e.g. Outlook `conversationId`). This breaks cross-mailbox threading: when Linda and Kenneth are in the same email conversation, their mailboxes produce different `provider_thread_id` values, splitting one conversation into two threads.

The current workaround — merging threads by normalized subject — is too broad (false merges on generic subjects) and too narrow (misses threads where the subject changed mid-conversation).

---

## Solution: Canonical Thread Resolution Layer

Introduce a **post-normalizer resolution step** that computes a `canonical_thread_id` using a ranked signal stack. Raw data is never modified — the resolver only writes to new columns.

### Two-Layer Thread Identity

| Field | Owner | Purpose |
|---|---|---|
| `provider_thread_id` | Email provider | First-pass hint within a single mailbox only |
| `canonical_thread_id` | Our system | Authoritative grouping used by all analytics |

---

## Signal Stack (ordered by reliability)

| Tier | Signal | Action |
|---|---|---|
| 1 | `In-Reply-To` header matches a known `Message-ID` | Definitive — assign same canonical thread, no scoring needed |
| 2 | `References` header chain contains a known `Message-ID` | Definitive — walk chain, assign earliest ancestor's thread |
| 3 | Normalized subject + participant overlap ≥ 85% confidence | Merge; flag if 60–84% for review |
| 4 | Time proximity (< 72hr) + same participants | Disambiguation only; never merge on this signal alone |

**Rule:** Never merge on a single Tier 3/4 signal alone. Require two signals to agree, or one Tier 1/2 hit.

---

## Cross-Mailbox Resolution Flow

```
email arrives (any mailbox)
       │
       ├─ Has In-Reply-To or References? ──YES──► find message by Message-ID (any mailbox)
       │                                               └─ found → assign same canonical_thread_id
       │
       ├─ Has provider_thread_id? ──YES──► find in same mailbox
       │                                       └─ found → check cross-mailbox match via Message-ID index
       │                                                       └─ match → merge threads
       │
       └─ Subject + participant scoring
               ├─ score ≥ 0.85 → merge
               ├─ score 0.60–0.84 → merge + flag for review
               └─ score < 0.60 → new canonical thread
```

---

## Scoring Logic (Tier 3)

```python
score = 0.0
score += participant_overlap_ratio * 0.60   # Most important signal
score += recency_score * 0.25               # <7d: +0.25 | <30d: +0.10 | >180d: -0.30
score += fuzzy_subject_similarity * 0.15   # After prefix stripping

# Subject normalisation: strip Re/Fwd/AW/SV/TR/RES prefixes, lowercase, collapse whitespace
```

---

## Schema Changes

```sql
-- Add to messages table
ALTER TABLE messages ADD COLUMN message_id_header     TEXT;
ALTER TABLE messages ADD COLUMN in_reply_to_header    TEXT;
ALTER TABLE messages ADD COLUMN references_headers    TEXT[];
ALTER TABLE messages ADD COLUMN canonical_thread_id   UUID;
ALTER TABLE messages ADD COLUMN thread_match_method   TEXT;   -- 'message_id' | 'references' | 'subject_participant' | 'new'
ALTER TABLE messages ADD COLUMN thread_match_confidence FLOAT;

-- Required indexes
CREATE INDEX idx_message_id_header  ON messages(message_id_header);
CREATE INDEX idx_canonical_thread   ON messages(canonical_thread_id);

-- Audit log for merges (supports review queue)
CREATE TABLE thread_merges (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_thread_id  UUID NOT NULL,
    to_thread_id    UUID NOT NULL,
    merged_at       TIMESTAMP NOT NULL DEFAULT now(),
    merge_reason    TEXT,
    confidence      FLOAT,
    reviewed        BOOLEAN DEFAULT FALSE
);
```

---

## Implementation Tasks

### 1. Normalizer — extract raw headers
- Parse and store `Message-ID`, `In-Reply-To`, `References` from Outlook/Gmail payloads
- Store `References` as an ordered array (oldest → newest)
- Run schema migration for new columns

### 2. `CanonicalThreadResolver` class
- Tier 1/2: lookup by `message_id_header` across all mailboxes
- Tier 3: subject + participant scoring with configurable thresholds
- Write `canonical_thread_id`, `thread_match_method`, `thread_match_confidence` on every message

### 3. Cross-mailbox merge handler
- On Tier 1/2 hit in a different mailbox's thread: call `merge_threads(a, b)`
- `merge_threads` reassigns all messages from the smaller thread to the larger, logs to `thread_merges`
- Idempotent — safe to re-run

### 4. Backfill existing data
- Run resolver over all historical messages in `sent_at` order
- Dry-run mode first: output merge candidates to CSV for spot-check before committing

### 5. Analytics layer update
- Replace all `GROUP BY provider_thread_id` with `GROUP BY canonical_thread_id`
- Thread view: surface `thread_match_method` and participant list for context

### 6. Review queue (optional but recommended)
- Simple admin view: messages where `thread_match_confidence` between 0.60–0.84
- Two actions: confirm merge or split into new thread
- Confirmed splits write to a `thread_split_overrides` table so re-runs don't re-merge

---

## Acceptance Criteria

- [ ] Linda and Kenneth emails in the same conversation share one `canonical_thread_id`
- [ ] Subject change mid-thread does not split the thread (References chain catches it)
- [ ] "Follow up" / "Hello" subject collisions do not false-merge across companies
- [ ] All merges are logged to `thread_merges` with confidence score
- [ ] Backfill completes without modifying raw message content
- [ ] Existing analytics queries updated to use `canonical_thread_id`
