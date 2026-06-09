# Data Analysis Guidelines (Carbon8 / QB + Email Intelligence)

Hard-won learnings from QB/email coverage analysis. Read this before doing any
ad-hoc data analysis against the production Supabase so you don't relearn the
same gotchas. Companion to `DATABASE_DESIGN.md` and `HOW_IT_WORKS.md`.

---

## 0. Guiding frame — email is the FEATURE, QB is the LABEL

The single most important modelling decision for this platform:

- **Build features from EMAIL data; use QB data only as labels / targets.**
  Emails are the rich, dense, always-present signal (every customer interaction
  flows through the mailbox). QB records (quotes, jobs, revenue, won/lost) are
  the *outcome* we want to predict, explain, or correlate against.
- **Why, not the other way around:** QB↔email linkage is **incomplete and stale**
  (see §6 — actual link coverage ran ~56–62% while the linkable ceiling ~98%).
  Treating QB linkage as a *feature substrate* means every model/insight inherits
  that coverage hole and the mailbox-attribution artifacts (§2). Treating QB as a
  *target* is robust: you only need QB on the labelled subset to train/validate,
  then features computed purely from email generalize to the unlinked majority.
- **How to apply:**
  - Predictive / scoring work (win-likelihood, churn, responsiveness, deal
    health): inputs = email-derived signals (volume, cadence, initiation ratio,
    sentiment, response latency, thread length, who-emails-whom). Targets =
    QB won/lost, revenue, cycle time — joined via `thread_qb_links` only for the
    labelled rows.
  - Do **not** gate a feature on "is this quote linked?" — that throws away the
    unlinked majority. Compute the feature from email regardless; the QB join is
    only for supervision/evaluation.
  - When QB coverage looks low, that's a *labelling* limitation (fix with link
    rebuild, §6), not a reason to distrust the email features.

### 0.1 QB is the SOLE ground truth for won/lost

- A `quote_no` is won **iff** a QB revision has `has_job`/`job_no` (collapse to
  `quote_no`, §5). Won-value/revenue come from QB (`sell_ex_tax` per quote,
  `retail_sale` per job). **Nothing email-derived ever decides an outcome.**
- **Email-derived references (Q#/J# from subject/body, AI
  `extracted_references`) are a CORRELATION SIGNAL ONLY** — they answer "was this
  quote/job *created or discussed* in an email conversation?", correlated against
  the QB outcome. Never use them to decide won/lost or substitute for QB truth.
  Report linkage as "associated / recoverable", never as "won".

### 0.2 Use MULTIPLE alternative linkage methods (not just Q-numbers)

Exact Q-number citation is one **weak, biased** signal — sparse for high-volume
trade accounts and skewed by volume-sink inboxes (Artis `accounts.pay@` was CC'd
on 321 quotes but *sent only 2 emails*; its all-time linkable ceiling was ~13%).
Citation ≠ engagement. For the email↔quote/job correlation, combine:

1. **Contact-email + temporal proximity** *(primary)* — `qb_quotes.contact_email`
   (or a job's contact) participates in email (sender/recipient/cc) within ±N
   days of `date_created`/`accepted_date`. Needs no Q-number.
2. **AI intent lifecycle** — aggregate rates/lead-times of
   `ai_email_intelligence.intent` (`quote_request`, `job_approval`,
   `artwork_submission`) vs QB creations. Corroborating, not per-row.
3. **J-number citation** — extract job refs like quotes; a second exact-match
   channel specific to the won side.
4. **Thread-window association** — link a quote/job to a canonical thread when
   the customer contact is active in it within ±N days of creation.
5. **Q-number citation** — keep, but as one weak input among the above.

### 0.3 Window the correlation to the email-covered period

Email sync only covers ~2025+. All-time linkage rates are mechanically low
(Artis all-time ceiling ~13% because ~80% of its 5,066 quotes predate any email)
while the **recent-window** ceiling is ~98%. Always restrict the email↔QB
correlation to quotes/jobs dated within the email-covered window (≥ the
per-customer first-email date), or the rate measures sync history, not quoting
behaviour. Note the Ehab mailbox is unsynced for the trailing ~2 weeks, so recent
recency on Ehab's accounts (e.g. Artis) is understated.

---

## 1. Customer → Company resolution (the mis-key trap)

- **`qb_quotes.matched_company_id` is STALE / largely unpopulated. Do NOT use it**
  as the customer→company link. Relying on it silently yields "0 customers".
- **Correct path:** `qb_quotes.qb_customer_id` holds the customer *key*. Resolve it via
  `qb_customers.customer_key_id` → `qb_customers.matched_company_id`.
  Build a `key_to_company = {customer_key_id: matched_company_id}` map first
  (filter out null `matched_company_id`), then look up `str(qb_customer_id)`.
- Fall back to the quote's own `matched_company_id` only if the key lookup misses.

### 1.1 The mis-key SIGNATURE over-flags — confirm the shared-email bridge

The cheap signature for contamination — `qb_match_method='email_lookup'` **AND**
`company_name != matched QB customer_name` (case-insensitive) — is a **first-pass
filter only**. On its own it massively over-counts. When triaging a window of
suspected mis-keys, classify every hit into three buckets *before* concluding
contamination (observed split on one 95-candidate set: **12 / 1 / 82**):

1. **Cosmetic variant (NOT contamination)** — same entity, different spelling:
   spacing, case, punctuation, or a dropped suffix (`Pty/Ltd/Co/Group/Australia/
   Printing/Design/Studio/Services`). Normalize both names (lower, strip non-alnum,
   strip suffix words) and compare; equal ⇒ cosmetic. Examples: `Arup`/`Arup Pty
   Ltd`, `Sydneytheatre`/`Sydney Theatre Company`, `Stihl`/`STIHL Australia`.
2. **Email-verified-correct (NOT contamination)** — the SB company is merely
   *misnamed*, but its contacts genuinely belong to the matched QB customer.
   **Decisive test:** does any `customer_contacts.email_address` for the company
   share (case-insensitive) an entry in the matched customer's `qb_unique_emails`?
   If yes, the `email_lookup` match is **correct** — do not displace. Example:
   SB `Flintwood` (only contact `steng@virtuoso.com`) → QB `Virtuoso` (has
   `STeng@virtuoso.com`). Also catches free-provider/junk groupings
   (`y7mail.com`, `gmail.com` "companies").
3. **Genuine mis-key (contamination)** — unrelated entities, no shared-email
   bridge, and a *name-exact* unmatched QB customer exists for the SB name.
   Only these are safe to displace (re-point SB → name-exact QB X, un-match the
   squatter Y). Example: `Allens` → `HANSEN OPTOMETRIST`, `Eco Outdoor` →
   `Caitlin Mills`. Genuine clusters often share a tell (here a large
   optometry/eyecare cluster bridged by one shared contact in the old buggy path).

**Rule:** never displace on name-inequality alone. Require (a) not cosmetic after
normalization **and** (b) no SB-contact ↔ current-QB shared-email bridge **and**
(c) a name-exact unmatched QB target exists.

### 1.2 Distinguish pipeline-leak from a stale batch (timestamp clustering)

When asking "is the pipeline *still* writing mis-keys?", bucket the suspect rows by
`qb_matched_at`. The live streaming pipeline writes per-email with **distinct**
timestamps; the extraction orchestrator's resolve-companies step writes a **batch**
with one shared microsecond timestamp. If all suspects collapse onto a handful of
identical microsecond stamps that map to specific `processing_jobs`/`extraction_jobs`
runs, the contamination is **batch-historical, not a live leak** — mop up the data;
don't block on a pipeline fix. (Observed: 106 suspects collapsed onto 3 batch stamps;
the post-deploy batch produced 0 genuine mis-keys, only cosmetic/email-correct hits.)

## 2. AM (Account Manager) attribution

- **Quotes → AM:** `qb_quotes.quote_am_name`, stored **WITHOUT** the client suffix
  (e.g. `"Linda D'Arcy"`).
- **Emails → AM:** `emails.mailbox_id` → `mailboxes.user_id` → `user_profiles.name`,
  and that name **HAS** the suffix (e.g. `"Linda D'Arcy | Carbon8"`).
- Keep two name maps (`AM_QUOTE_NAME` without suffix, `AM_FULL` with suffix). The
  suffix mismatch is a classic silent-zero bug.
- A shared **`hello@` mailbox** exists. Emails for an AM's customers often land in
  `hello@` or other mailboxes rather than the AM's named mailbox — so low
  *named-mailbox* linkability can be a mailbox-attribution artifact, not
  off-channel behaviour. Always split per-customer email counts by mailbox
  (own-named / hello@ / other) before concluding "off-channel".

## 3. PostgREST pagination MUST be ordered (run-to-run instability)

- `.range(offset, offset+n-1)` pagination **without an explicit `.order()` is not
  stable across windows** — pages overlap or skip rows, so distinct counts vary
  between runs (observed: Ehab quote count swung 939 ↔ 1219 on the *same* query).
- **Always add `.order("id")`** (every table here has `id` and `created_at`) to
  every paged read. When de-duping into a set, overlaps are harmless but *skips*
  silently undercount — so the higher count across unstable runs is the more
  trustworthy one, and the fix is ordering, not picking the max.

## 4. Quote-number extraction — use the canonical extractor

- **Do not roll your own regex.** Import
  `backend/src/services/reference_extractor.py` → `extract_references(text)`.
  This is the *same* logic the linking pipeline uses, so it measures what the
  platform can actually link.
- It handles `Q######`, `Quote #N`, `QT N`; normalizes to `"Q" + digits`.
- **Caveat:** it does **not** match version-suffixed forms like `Q710349v2`
  (no `(?:v\d+)?`), so version suffixes are dropped. When comparing extracted
  Q-numbers to `quote_no`, strip the version (`^(Q\d+)`) on both sides.
- Also fold in AI-extracted refs: `ai_email_intelligence.extracted_references`
  where `type == "quote"`.

## 5. Won / revenue / linkage definitions (keep before-after comparable)

- **Won:** a `quote_no` is won if **any** revision has `has_job = true` or a
  `job_no`. Derive at `quote_no` level (collapse revisions).
- **Revenue per quote:** `max(sell_ex_tax)` across revisions — avoids
  revision double-counting. Document the method so deltas are interpretable.
- **Linked:** `quote_no` (or its version-stripped base) appears in
  `thread_qb_links.qb_reference` where `link_type = 'quote'`.

### 5.1 Capability presence — `qb_capability_tag` is ~40% NULL; use the classifier fallback

**The trap:** `qb_operations.qb_capability_tag` is **NULL on ~40% of operations**
(observed 39–46% across top customers). If you decide "does this company do capability
X?" from `qb_capability_tag` alone, you **fabricate false gaps** — i.e. you recommend a
capability the customer demonstrably already does.

- **Canonical definition of capability presence** (what the platform's
  `get_capability_rhythm` uses, so match it): `qb_capability_tag` **if present, else fall
  back to the classifier `capability_tags` array** on the same operation row. Helper:
  `recommendation_engine._caps_for_op(op)` (and the same logic in
  `customer_analytics_service.get_capability_rhythm`).
- **Worked failure (2026-06-09):** market-basket cross-sell flagged *Embellishment* as a
  gap for Geoff Letchford and Studio Odea using `qb_capability_tag` only (=0 jobs). Under
  the qb-OR-classifier definition they have **16 and 8** Embellishment jobs (debossing/
  stamping dies, hot-foil) — the recs were wrong and would have told a foiling customer
  "you don't do embellishment." Both pulled.
- **Three different "embellishment" signals exist — keep them distinct:**
  (1) `qb_capability_tag = 'Embellishment'` (the standalone product capability),
  (2) classifier `capability_tags` containing `'Embellishment'` (rules over operation_name),
  (3) `qb_embellishment_tag` (the **finish** applied within another job: Hot Foil, Spot UV,
  Deboss). A customer can be heavy on (3) and the classifier (2) while zero on (1).
- **For gap/cross-sell recs, the conservative direction is to err toward "already has"**
  (suppress the rec) — a false gap shown to a client is worse than a missed cross-sell.
  Use a small job-count floor (e.g. `> 2`) so a single spurious classifier hit (e.g. a
  generic "set-up charge" line) doesn't suppress a genuine gap.
- **Consistency rule:** any new capability metric MUST use the same definition as
  `get_capability_rhythm`, or the rhythm card and the recommendation panel will contradict
  each other on the same screen.

## 6. Coverage vs the linkable CEILING (the most important method)

`thread_qb_links` can be **stale** (not rebuilt after cleanup/ingestion). So a
"coverage drop" may be unbuilt links, not genuine loss of signal.

- Always compute **both**:
  1. **Actual coverage** = quotes whose `quote_no` is in `thread_qb_links`.
  2. **Linkable ceiling** = quotes that are linked **OR** have a Q-number present
     in any of that customer's emails (canonical extraction).
- If `ceiling ≈ baseline` but `actual << baseline`, the conclusion is
  **"links are stale, rebuild them"** — not "coverage fell".
  (Observed: Linda ceiling ~98% ≈ baseline 99.6% while actual links ~56–62%.)
- Classify **unlinked** quotes into:
  - **Q-num present (linkable)** — recoverable by a link rebuild.
  - **present-no-Qnum (quoting-convention)** — customer emails exist but never
    cite the Q-number; needs fuzzy/contextual linking, not exact-match.
  - **near-silent (off-channel)** — customer has < ~3 total emails; genuinely
    not transacting over email.
  - **unresolved** — company couldn't be resolved (see §1).

## 7. Supabase egress discipline (grace period ends 2026-06-11)

- `body_text` across ~196K emails is the heavy pull. **Cache derived artifacts**
  (e.g. `qnums_in_text`, per-company/per-mailbox counts) to a local JSON so
  iterative refinements don't re-pull the corpus.
- **Invalidate the cache whenever extraction logic changes** (e.g. swapping the
  Q-number regex) — otherwise you silently analyze stale derived data. Watch for
  a concurrent run rewriting the cache after you delete it.
- Prefer lightweight metadata pulls (ids/foreign keys, no body) separated from
  the one heavy body pull.

## 8. Connection robustness on long pulls

- Long sequential pulls hit `WinError 10054` (connection forcibly closed) around
  ~100K+ rows. Use a retry wrapper that **recreates the Supabase client** between
  attempts (transient HTTP/2 drops don't recover on the same connection).
- Reduce page size for body pulls (e.g. `BODY_PAGE = 400`) vs metadata (`1000`).
- For multi-minute scans, run in the background and poll the output file.

## 9. Fixed reference values (Carbon8)

- `client_id (Carbon8) = 241d7b99-f099-4557-96e5-212c4af10812`
- Coverage analysis window: quote `date_created` **2025-12-01 .. 2026-05-15**.
- `hello@` is a shared mailbox; named AM mailboxes are per-user.
- Reference script: `scripts/db/_coverage_reconfirm.py` (throwaway diagnostic;
  read-only). Embeds all of the above patterns.

---

## Findings snapshot (post-cleanup coverage re-confirm)

> From the definitive ordered + canonical-extraction run (window 2025-12-01..2026-05-15,
> Carbon8). Point-in-time; re-run `_coverage_reconfirm.py` to refresh.
> `won$cov%` = share of WON quote-revenue whose quote is linked (the metric that matters).

**Part 1 — Linda + Ehab (actual link coverage vs linkable ceiling)**

| AM    | quotes | linked | q-cov% | won | won$cov% | pre$% | Δ      | ceiling% |
|-------|-------:|-------:|-------:|----:|---------:|------:|-------:|---------:|
| Linda |    935 |    494 |   52.8 | 423 |     63.5 |  99.6 | -36.1  |     98.2 |
| Ehab  |  1219  |    675 |   55.4 | 397 |     71.1 |  92.0 | -20.9  |     80.6 |

- The headline "drop" is mostly **stale links**: Linda's ceiling 98.2% ≈ baseline
  99.6%, so a link rebuild recovers almost all of it. Ehab's ceiling 80.6% < 92%
  baseline — an ~11pt gap a rebuild *won't* close → some genuinely off-channel /
  no-Qnum won revenue for Ehab.

**Part 2 — linked-thread cell sizes (all ≥30, sample sufficient)**

| AM    | linked_won | linked_lost |
|-------|-----------:|------------:|
| Linda |        232 |         262 |
| Ehab  |        254 |         421 |

**Part 3 — Nic + Kenneth (low linkability: artifact vs genuine off-channel)**

| AM      | cov now | pre | own-named | hello@ | other | linkable | quoting-conv | off-channel |
|---------|--------:|----:|----------:|-------:|------:|---------:|-------------:|------------:|
| Nic     |   17.9% | 42% |     22.0% |  15.7% | 62.3% |      388 |          104 |          41 |
| Kenneth |    6.0% | 25% |     20.5% |  14.1% | 65.4% |       47 |          244 |          28 |

- **Not primarily off-channel.** Only ~22% of their customers' emails sit in the
  AM's *named* mailbox; ~62–65% are in "other" mailboxes → low named-mailbox
  linkability is largely a **mailbox-attribution artifact**, not silence.
- **Nic:** of 540 unlinked quotes, **388 have a Q-number present in email**
  (linkable by rebuild); only 41 near-silent. His low coverage is recoverable.
- **Kenneth:** different shape — only 47 linkable, but **244 are
  "quoting-convention"** (customer emails exist but never cite the Q-number).
  Exact-match linking will never catch these; needs fuzzy/contextual linking.

**Part 4 — alternative-linkage correlation (Q-citation is a FLOOR, not the ceiling)**

Q-number citation drastically undercounts email↔quote correlation. Measured on the
two profiled customers, windowed to the email-covered period (§0.3), denominator =
in-window quotes. `_quote_email_correlation.py` (metadata-only, no body egress).

| customer | Q-cite won$ ceiling | M1 contact+temporal ±14d (won$) | ±30d | M3 thread-window ±14d (won) | M2 contact-active |
|----------|--------------------:|--------------------------------:|-----:|----------------------------:|------------------:|
| Artis    |              ~21.5% |                           70.8% | 83.0%|                       85.5% |             100%  |
| TPA      |              ~23.1% |                           48.8% | 61.1%|                       82.4% |             98.9% |

- **Contact-email + temporal proximity (M1) is the right primary method** — it ties an
  email to the quote *moment* (±N days of `date_created`) and recovers 2–3× more won
  revenue than exact Q-citation. Use ±14d as primary, ±30d as a looser bound.
- **M2 (contact ever emailed) ≈ 100%** for these trade accounts → contact-level presence
  is near-universal; it's a sanity ceiling, not a discriminating signal. The *temporal*
  variant is what carries information.
- **M3 thread-window** (any company email within ±Nd of `date_created`) is a useful
  company-level proxy when `contact_email` is missing/unreliable.
- **Windowing matters:** 77.5% (Artis) / 88.3% (TPA) of all quotes fall in the
  email-covered window; the rest are pre-sync and correctly excluded — including them
  would mechanically depress every rate (the Artis all-time ~13% artifact).
- **Conclusion:** low `thread_qb_links` coverage is a *linkage/citation* limitation, not
  off-channel quoting. Build correlation features from M1/M3 (dense), use exact Q-citation
  only as a weak corroborating input — never as the correlation ceiling.

**Part 5 — proximity does NOT rescue every AM: Nic Doyle is structurally different**

Re-ran the M1 proximity method on Nic Doyle's WON quotes (`_nic_proximity_recheck.py`,
metadata-only). Unlike Artis/TPA (single large trade accounts), Nic is a **1,713-company
long tail**, and proximity recovers far less. The earlier Part-3 read ("low coverage is
recoverable by link rebuild") is incomplete for the *feature* question.

| metric (Nic, won quotes) | value |
|--------------------------|------:|
| won quotes / won$        | 4,383 / $6.30M |
| **outside email window** (company email-absent $1.31M + pre-window $1.71M) | **~48% of won$** |
| testable (in-window) won$ | $3.27M |
| Q-citation coverage (won$) | 30.8% |
| **proximity ±14d (won$)** | **45.1%** (only **1.46×** Q-cite, vs Artis 3.3× / TPA ~2×) |
| proximity ±30d (won$)    | 49.7% |
| no email even at ±30d    | 855 quotes / $1.65M — of which **711 / $1.39M are email-active companies** (genuine off-channel, not thin data) |

- **Not a hello@/attribution artifact.** Of proximity-matched emails, **81% are in Nic's own
  mailbox**, 5% hello@; only ~19% of matched won quotes rely on a non-nic@ box. The earlier
  "62% in other mailboxes" was diffuse *non-correlating* volume, not the conversion email.
- **Only modestly a citation artifact** (1.46× lift): Nic's Q-citation floor was already
  high (30.8%), so proximity adds less than it did for Artis.
- **Lesson — don't assume proximity rescues low coverage uniformly.** Recovery depends on
  *portfolio shape*. Email-dense single-account books (Artis/TPA) → email is a strong feature
  substrate. Long-tail SMB books (Nic) → ~half the won revenue is pre-sync/email-absent and a
  large in-window share has no contemporaneous email (off-channel / reorders without a fresh
  thread). Expect and **model** materially lower email-feature coverage for such AMs/segments;
  don't treat their low coverage as purely a link-rebuild problem.
