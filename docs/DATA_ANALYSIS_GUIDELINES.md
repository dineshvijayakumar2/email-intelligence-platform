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
- **Same rule for ad-hoc QuickBase pulls:** `skip/top` paging without `sortBy` is
  unstable across pages. Sort by Record ID# (`sort_by=[{"fieldId": 3, "order": "ASC"}]`)
  — unique and immutable on every QB table. (The production sync now does this by
  default; a missing sort here is what made the 2026-06-10 `qb_operations` backfill
  untrustworthy.)

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

### 9.1 `qb_operations` count reconciliation — the cache is intentionally smaller than QB

Don't treat `count(qb_operations) < QB Operations total` as a sync gap. The sync
applies a **`T-Cancelled` prefilter** (`sync_operations` drops every record whose
`production_status = 'T-Cancelled'`). Reconciliation (2026-06-10):

| | rows |
|---|---:|
| QB Operations table (raw, what the QB report shows) | 683,366 |
| Less `T-Cancelled` (excluded by the sync prefilter) | −53,043 |
| **Expected in `qb_operations`** | **630,323** |
| Actual live count (incl. stale stragglers) | 630,707 |

- The cache holds **630,707**, i.e. ~384 *more* than the 630,323 valid set. Those
  extras are rows cached earlier that have since become `T-Cancelled` or been deleted
  in QB; the upsert-only sync never purges them. So expect the live count to drift a
  few hundred above the valid total until a delete-aware reconciliation runs.
- When reconciling an analysis count against QB, **always exclude `T-Cancelled`**
  on the QB side first (`{'21'.EX.'T-Cancelled'}`), or compare against 630,323 — not 683,366.
- `profit_pct` is unbounded `NUMERIC` (migration 119). Do **not** assume it sits in
  any bounded range; QB emits values in the millions of percent when cost ≈ 0. Treat
  it as a display field, not an aggregation input (a mean/sum is dominated by these
  near-zero-cost outliers and is meaningless) — see [BEST_PRACTICES.md](BEST_PRACTICES.md).

---

## 10. Building reports and client-facing documents

Hard-won learnings from the Next-Best-Outreach card set (50 cards, six per-AM Word
docs, a master markdown/PDF). Apply these when turning an analysis into a deliverable.
Generator scripts and JSON outputs are the reproducible source: `_outreach_cards_50.py`,
`_validate_cards_50.py`, `_assign_am.py`, `_gen_am_docs.py`, `_retier_master.py`,
`_gen_master_pdf.py`, `_check_outsidesix_touch.py` (all read-only, throwaway).

### 10.1 No long dashes in generated output

Avoid em / en dashes (`—` `–`) in any document handed to a person. Use a plain hyphen,
colon, or parentheses instead. The trap: they leak in from two places, so fixing only
your own f-strings is not enough. They also arrive inside **data** you render (e.g. the
timing label stored in the cards JSON is `"due soon - 142d ..."` with an em dash). Run a
**sanitize pass over every rendered string**, not just literals:
- docx: walk every run in `doc.paragraphs` **and** every table cell's paragraphs, replace
  `— – ―` with `-` (see `_gen_am_docs._sanitize_doc`).
- markdown: a global `replace("—","-")` on the whole text before rendering to PDF.
- Write the guidance section dash-free too, or you contradict yourself.

### 10.2 One canonical scale for percentages (the "4760%" bug)

Decide whether a field is a **fraction** (`0.72`) or a **percent** (`72.1`) and never mix.
We stored `front.confidence = 72.1` (percent) and `factors.confidence = 0.72` (fraction);
a generator multiplied the percent by 100 again and printed **4760%** - and, worse,
mis-tiered every card because `47.6 >= 0.50` is always true. Rule: do math on the fraction,
format `* 100` exactly once at display, and **sanity-check outputs for impossible values**
(no confidence > 100%; the only legitimate 3-digit token is `100%`).

### 10.3 Tier on confidence AND lift (lift-aware), never confidence alone

A 92%-confidence / lift-1.0 recommendation is **near-universal** (almost everyone buys it),
which is weak, not strong. Canonical tiers used across all outreach docs:
`Strong = conf >= 50% AND lift >= 1.5`; `Moderate = conf >= 35% AND lift >= 1.3`; else `Weak`.
High confidence with lift near 1 means "broadly popular product," not "targeted gap."

### 10.4 One definition and one label set across a document family

When the same data ships as several documents (per-AM docx + master md + master PDF), a
cross-reference must place each customer in the **same tier in every document**. Matching
the *counts* is not enough - the *labels* and the *definition* must agree (we had the master
calling the bottom tier "Low-signal" while the per-AM docs called it "Weak", so the same
customer read as two different tiers). Verify by joining every document on customer name and
asserting **zero tier mismatches** before hand-out.

### 10.5 Do not let raw revenue swamp a composite score

An opportunity score of `conf x lift x revenue x timing` with **raw** revenue (roughly a
1000x dynamic range) collapses the ranking back to "top by revenue" and buries small,
high-confidence, well-timed accounts. Dampen revenue (`log10`) so confidence / lift / timing
can actually move the order, and **store the raw factors on every row** so the ranking can be
re-derived or re-weighted without re-running the pull.

### 10.6 Two-sided cards: action on the front, audit trail on the back

Structure each recommendation as `{front, back}`: the front is the glanceable action (what
to pitch, to whom, with what context, at what timing, plus the headline confidence); the back
carries the evidence (the rule's conf / support / lift / base-rate, the zero-order gap
confirmation, the contact's won-value and engagement, the order dates behind the timing). The
back lets a reviewer spot-check any card without re-running the analysis.

### 10.7 Confirm a "gap" is genuinely zero at company grain

Before pitching a cross-sell, verify the customer has **zero** orders in it under the
corrected definition - not merely below the rule-mining threshold. Use qb-OR-classifier
(§5.1) for capability presence, and for a standalone-Embellishment pitch also check the
`qb_embellishment_tag` finish signal (a customer who foils / embosses within other jobs
already does embellishment - the Geoff Letchford trap). A capability with 1 job is not a
clean gap; err toward "already has it."

### 10.8 AM attribution: the QuickBase owner is not always the email-relationship owner

Assign an account to an AM by the **mode of `am_customer`** over its operations (do not guess;
flag no-AM, AM-outside-the-known-set, and split ownership separately). But the QB owner can be
an AM with no mailbox while the real email thread runs through a different, mailbox-enabled AM.
To find who can actually action a card, map `emails.mailbox_id -> mailboxes.user_id ->
user_profiles.name` and take the **plurality mailbox-AM** (exclude the shared `hello@` box and
non-AM boxes like Production). Example: Jefferies' QB owner has no mailbox, but 55 of 59 of its
emails sit in Ehab's mailbox - so Ehab owns the relationship.

### 10.9 Document tooling on this machine (Windows)

- `python-docx` works for `.docx`. There is **no pandoc, LibreOffice, or wkhtmltopdf**, and the
  Windows-Store Python sandbox **cannot read the skills-plugin directory** under
  `AppData\Roaming\Claude\...` (so the docx skill's `soffice.py` / `validate.py` are
  unreachable - `os.path.exists` returns False). For markdown -> PDF use **`xhtml2pdf`**
  (pure-python): `markdown.markdown(text, extensions=["tables",...])` then `pisa.CreatePDF`.
- Client `.docx`: portrait A4, tight (0.5in) margins; small (8pt) table font when a table has
  many columns. Validate by round-tripping with `python-docx` and checking the zip + XML
  well-formedness (the sandbox blocks the skill validator).
- The Windows console is cp1252: wrap stdout (`io.TextIOWrapper(sys.stdout.buffer, "utf-8")`)
  before printing `≥`, `·`, em dashes, etc., or the script crashes mid-run. Do **not** wrap
  stdout twice (importing a second module that also wraps closes the buffer).

### 10.10 Verify every artifact before hand-out

Reconcile counts (all N accounted for, none duplicated or missing across the document set),
scan for impossible values, round-trip-open each file, and de-dash. Keep the generator scripts
and the JSON outputs (`outreach_cards_50.json`, `card_am_assignment.json`, etc.) as the
reproducible record so any number on a card traces back to a row.

### 10.11 Push heavy aggregates server-side, with a raised statement timeout

Do not pull 600K operation rows to the client. Aggregate in a throwaway jsonb-returning RPC
(dropped at the end) and add `SET statement_timeout = '240s'` to the function - the
`service_role` default timeout is short and silently kills a multi-minute full-base scan with
`57014 canceling statement due to statement timeout`. Cache the one expensive egress pull
(e.g. pool emails) to a local JSON and refill it incrementally (§7, §8).

### 10.12 Pilot a cheap slice before an expensive run; validate a new code path against a known-good one

The most repeated win of this project was spending a few cents to avoid a wrong expensive run.
Concrete instances: a feared $400 reclassification turned out to cost ~$36 once a 300-email
pilot measured the real per-email cost; that same pilot exposed a driver that silently dropped
~80% of a batch (an output-token-cap requeue the fast path ignored) before it ran on 58K. Rules:
- For any run that costs real money or hours, pilot on a small representative slice first,
  measure actual cost/throughput, and extrapolate. Do not trust the headline row count as the
  cost basis (most of it may be legitimately pre-filtered).
- When you replace a slow path with a faster one (e.g. an id-driven batch instead of the
  orchestrator), the pilot validated the slow path, so re-validate the fast path against the
  known-good output on a small sample before scaling. A fast path can quietly drop, re-order,
  or under-enrich rows the slow path handled.
- Put a hard cost-abort in long runs (stop if actual spend trends past ~1.3x the estimate) and
  checkpoint per batch so an interruption resumes cleanly without double-spend.

### 10.13 Distinguish a definitional blind spot from a code bug

Several of the worst issues were not bugs: the code ran correctly on a wrong definition, so
nothing threw and tests passed. Examples: a `folder_trash` pre-filter that silently excluded
~20K real customer emails (folder location was treated as a proxy for irrelevance, but AMs
delete resolved-but-real mail to Trash); `qb_capability_tag` being ~40% NULL so a "gap" was
really a tagging hole (§5.1); standalone-Embellishment "gaps" that were finishes-within-jobs
(§10.7). These are invisible to normal testing because the pipeline is behaving as written.
Defenses:
- When a number looks surprisingly clean or surprisingly large, spot-check the raw rows behind
  it (read 20-30 actual records), not just the aggregate.
- Be suspicious of any single field used as a proxy for a business concept (folder = irrelevant,
  one tag = capability presence). Confirm the proxy against a second signal.
- A correct computation on the wrong population is still wrong. Validate the population (what is
  included / excluded and why), not only the math.

### 10.14 Order-of-operations and idempotency for backfills

When reprocessing data through a pipeline, the trigger and the order matter:
- A code change to a pre-filter does not by itself reprocess already-skipped rows; they stay
  `processing_status='skipped'` until explicitly reset. Fix the filter first, then reset, or
  the next sync re-skips what you just reset (mop after fixing the tap, not before).
- Idempotency protects spend: rows already `completed` / `skipped` are not re-fetched, so a
  filter change is safe to ship without triggering a surprise reprocess; the reset is the
  deliberate, separately-gated step.
- Run backfills as a resumable server-side worker (survives restarts / sleep), not a local
  script babysat across a session; report progress from durable DB state (row counts), not an
  in-process counter that resets on restart.

---

## 11. Running an LLM-scored analysis (API keys + provider)

When an ad-hoc analysis needs an LLM (e.g. scoring email content, classifying, judging), the
keys and the call path are NOT what you'd guess. Learned on the Tier-B content-quality pilot
(15.3); reference scripts `scripts/db/_tier_b_pilot_{sample,score,analyze}.py`.

### 11.1 Provider: use OpenAI (gpt-4o). Anthropic is out of credits; Gemini is not preferred
- The team uses the **OpenAI** credits. The `ANTHROPIC_API_KEY` is **out of credits** (direct
  calls return 400 "credit balance too low"), and Gemini is not the chosen route. Default to
  `gpt-4o` for judgment-quality work, `gpt-4o-mini` for cheap/bulk.
- **Never silently fall back** to another model/provider on failure — raise, or record the item
  as failed and exclude it (never fabricate a score). See `BEST_PRACTICES.md` / the no-fallback rule.

### 11.2 Keys live (base64) in `system_settings`, NOT in `.env`
- The API keys are **not** in `backend/.env.development` / `.env.production`. They are stored
  **base64-encoded, per-client** in `system_settings` (keys `api_key_openai`, `api_key_anthropic`,
  `api_key_google`).
- Hydrate them into env the same way the platform does, before building the LLM:
  ```python
  from supabase import create_client
  from src.services.ai_email_analyzer import _load_client_api_keys
  sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
  _load_client_api_keys(sb, CARBON8)   # decodes -> os.environ["OPENAI_API_KEY"] etc.
  ```
  (DB creds come from `.env.production`; `ANTHROPIC_API_KEY`/`GOOGLE_GENAI_API_KEY` are also in
  `.env.development` but are NOT the OpenAI key — that one only comes from the DB.)

### 11.3 Call `get_llm` directly, not the budget-gated `AIClient`
- For a one-off analysis, build the model with
  `from src.services.langchain_core import get_llm; llm = get_llm("gpt4o", temperature=0.0)`
  and invoke with `[SystemMessage(...), HumanMessage(...)]`. Read tokens from
  `resp.usage_metadata` and compute cost yourself (gpt-4o ≈ $2.50/$10.00 per 1M in/out).
- **Avoid the production `AIClient` path** (`call_for_task`/`call_cheap`): it enforces a per-tenant
  **daily budget gate** (default $2/day) that will block your run mid-way, and its spend lookups
  read `ai_usage_log`. A one-off script calling `get_llm` directly does **not** write
  `ai_usage_log` or any production table — keep it that way for read-only pilots.

### 11.4 Pilot discipline carries over (§10.12)
- Smoke-test on ~4 items first to confirm the key, model, and JSON parsing work and to measure
  real per-item cost before the full run (200 blind-scored threads cost **$0.86** on gpt-4o).
- Make the scorer **resumable** (skip items already in the output JSON) and **strict-JSON**
  (extract `{...}`, repair with `json_repair`, validate ranges; on failure exclude + count, never
  fabricate). For validation work, keep the LLM **blind** to the label it's being validated against.

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
