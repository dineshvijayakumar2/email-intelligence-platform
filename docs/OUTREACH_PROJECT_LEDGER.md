# Outreach Project Ledger — operational tracking

> **Single source of truth for the Next-Best-Outreach workstream.** Update status here as items move. Tactical day-to-day ledger; strategic plan lives in `BUCKET_LIST_JUNE_2026.md`.
>
> Status: 🔜 next / 🔄 running / ✅ done / ⏸ held / 📌 parked
> Numbering: prompts are prefixed by day (11.x = 11 Jun, 12.x = 12 Jun, 13.x = 13 Jun).
> Last updated: 15 June 2026 (~01:30 IST — ALL 6 AM docs SENT + Jeff email sent. Tracking responses. Next-activity plan at bottom.)

---

## ⚡ SHIPPED (15 Jun ~01:00 IST) — all 6 AM docs generated + SENT. Now tracking rep responses.

**Decision:** Dinesh chose to SEND all six now (fail-fast > wait-for-perfection) — rep ground-truth on THIS deck beats another polish cycle against guesses. Defensible: the deck is verified-correct (capability layer durable, filter validated, cadence fixed, ranking confirmed not mis-selecting); "fast" applies to framing/presentation judgment, not unverified data.

**What went out (`docs/data-insights/`, filenames `outreach_<am>_15-06-2026.docx`):** Nic 18 cards (13HC/3WF/1Design/1SC, 24 major accts) · Linda 14 (11HC/2Design/1SC, 30 accts, 2 smart-catch shifts) · **Ehab 14 (12HC/1WF/1SC, 26 accts — carries the deck's ONLY "Not pitched" [Performance Frontiers] + the MED-EL smart-catch = best industry-logic showcase)** · Kenneth 3 (2HC/1Emb, 12) · Mary 1 (1HC, 6, no-mailbox note) · Peter 0 (major-accounts-only + no-mailbox note).

**Final fixes after first Nic/Linda gen (all in, all validated):** plain-language timing (no p50/p90); cadence corrected (same-fortnight bursts collapsed into one "occasion", propagated into ranking too — Next Printing spurious #1-overdue → in-cadence); 12-mo revenue shown (was all-time); doubled-label bugs fixed (Fits/Not-pitched); "-1 days ago" fixed (reference date bumped to 2026-06-15); **15 cash/internal/test buckets excluded** (incl. former card #29 Cash Account-Kenneth); date-stamped AU filenames. Validator refreshed: CHECK 2 15/15 PASS / 0 FAIL, CHECK 1 = 0 Embellishment pitches. Baseline `outreach_cards_50_preocc.json`.

**Jeff email: SENT** — brief version. Covered: QB capability-tag root cause (department conflation), the platform correction layer (op-level, alongside QB, recomputes on sync) + own-classifier mis-tags caught, the 4 feedback verdicts (cello confirmed+fixed / within-job confirmed / HC→WF checked+kept / AM-basis switched to recent job manager), industry-fit grounding (the furniture/medical examples), and the Hard-Cover-is-real heads-up.

**WATCH IN RESPONSES (this is the fail-fast signal):**
- Does the Hard-Cover framing hold? Multiple "why all hardcover again" → opening note didn't carry it, fix is STRUCTURAL (sub-heading grouping HC cards under restated rationale), not wording. Engagement with cards → framing worked.
- Do the "smart catch"/"not pitched" lines read as intelligence or get skipped? Ehab's reaction is the tell.
- Does the feedback column (Makes sense/Already buys/Wrong) get used? That IS the ground truth validating or flagging the approach.

**Post-Monday platform items (logged, NOT done):** see NEXT-ACTIVITY PLAN below.

---

## 📋 NEXT-ACTIVITY PLAN (set 15 Jun ~01:30, for the days ahead)

**Posture: the next move is REACTIVE, not proactive.** The docs + Jeff email are out. The highest-value input now is rep/Jeff RESPONSE — don't pre-build against guesses. Triage on what comes back, then pick from the queue below.

### A. Response-driven (do when feedback lands) — TOP PRIORITY
- **Triage rep feedback** against the 3 watch-points (HC framing held? smart-catch read as intelligence? feedback column used?). Capture each AM's reactions — this is the ground truth the whole approach is validated against.
- **If "why all hardcover" recurs** → structural fix: sub-heading that groups HC cards under a restated one-line rationale (not a wording tweak).
- **If a rep marks cards "wrong"/"already buys"** → that's a data signal; trace whether it's a gap-detection miss or a real data error before changing logic.
- **Jeff reply** → depends what he asks; be ready to walk through the HC→WF evidence or the correction-layer mechanics.

### B. Platform-hardening follow-ons (proactive, NOT blocked on feedback; pick when there's a clear runway)
- **B1 — Deck-ranking occasion-cadence consistency.** Propagate occasion-based cadence into `RPC_GAPS` so ranking + display use one definition. Diagnostic showed 0 deck cards mis-selected today, so this is consistency/hygiene, not a correctness fix. Will re-rank + re-select on next regen (~2-3 boundary swaps).
- **B2 — WAVE-2 vector re-embed.** Only `vector_service:583` bakes capability into embedding text; targeted re-embed of ~8-10k cello/fuse ops (NOT 631k), index-churn-dominated. Confirm first whether anything in a live user-facing path reads the vector layer for capability meaning (deck path is SQL-only, so low urgency).
- **B3 — 13.5-UI: surface the correction layer.** Reuse the Intelligence-Config classifier-rules page to show QB-formula value vs corrected + rule + rationale; the keyword rules (now config-driven) become UI-visible. Makes the correction client-manageable, not buried. Guardrail: re-runnable verify after edits.
- **B4 — Config/UI completion of keyword rules.** (Pairs with B3.) Keyword rules are config-driven in code but not yet UI-editable — the schema/UI extension flagged in 13.7 Decision 2.

### C. Coverage / breadth follow-ons (proactive, lower urgency)
- **C1 — 13.4 full-base industry enrichment.** Vocab-collapse (merge synonym buckets checked vs check-4 buying behaviour) → switch gate to defensible-match → re-run to ~85% → classify the full ~12,600 with provenance columns. The 13.2 spend already added 34 confident labels across the 648 active; this extends to the long tail. Strengthens platform, not deck-Monday-critical.
- **C2 — Writeback the 42 approved 13.2 labels** if not already persisted to `industry_enriched` (confirm Part-A of the combined pass actually wrote them; the migration 125 column exists).

### D. The OTHER track (parked during the deck sprint, still real)
- **AM Coaching (the flagship feature).** Latency prerequisite done (mig 122, all 7 mailboxes backfilled). Was paused for the cards/industry sprint. When the deck thread quiets, this is the next big build — structural v1 on the 4 mailbox AMs with fairness caveats, Mary/Peter on a separate QB-outcome track. Content features (intent/sentiment/Q3-substance) gated on fresh extraction.

**Recommended sequence when work resumes:** (1) triage whatever feedback arrived [A], (2) if quiet, B1 (cheap consistency win) or pick up the Coaching track [D] as the next flagship. Hold B2/B3/C/13.4 until either feedback demands them or there's a clear platform-hardening window.

---

---

## ACTIVE — Industry-aware redirect (Jeff's Fri email; no rush, Monday) + corrected deck

**Jeff's Friday strategic redirect:** dig deeper, find AI/semi-AI insights that give recommendations; look closer BY INDUSTRY and growth areas. His example: a furniture company won't make casebound books — market-basket can't know who a customer *is*. = the ceiling of pure-statistical cross-sell. Deadline OFF (team back Monday). Acknowledged by email ("dig through more over the weekend, get back with concrete results").

- **13.1 (was 12.6-corr3) — Clean bidirectional capability reclassification — ✅ DONE (deck-level Corr3; superseded as a PLATFORM fix by 13.7).** The single holistic fix that ended the whack-a-mole at the deck level; 13.7 makes it a platform-persistent classifier correction. Per the 12.6-audit `TRUE` taxonomy:
  > Build Correction 3: a single bidirectional op-name reclassification of `qb_capability_tag`, fixing the two polluted capabilities (Embellishment, Hard Cover Books) in one pass — leave the other six untouched. Move celloglaze/film-lamination/matte/gloss/laminate/laser OUT of Embellishment → Specialty Finishing; "Fuse back to back" OUT of Hard Cover → Specialty; perfect-bind/saddle-stitch OUT of Hard Cover → Soft Cover; "Hand Foil/Deboss" OUT of Hard Cover → Embellishment; AND reclaim genuine embellishment mis-filed under Hard Cover + genuine casebind mis-filed under Soft Cover (the bidirectional part — lifts Embellishment to ~15.3%, not 7.8%). Recompute the full rule set; expect ~37 balanced rules (HardCover→WideFormat 84%/2.26, HardCover→SoftCover 75%/2.77), no single pathological category. Verify borderline routing (Proofing→Design, preflight→WideFormat, section-sewing→SoftCover, Display) doesn't move any surviving rule; no card pitches Display off its inflated 100%. Output corrected `outreach_cards_50.json` + change summary. Keep baselines. **Then HOLD — don't regenerate docs/send until the industry-layer decision (13.3).**
  - **On return, check:** (1) balanced ~37-rule mix, not another single dominant category; (2) Embellishment ~15% not 7.8% (confirms the bidirectional reclaim fired); (3) borderline routing calls moved no surviving rule + no Display-100% card; (4) cards changed/dropped count vs what reps already have.

- **13.2 (was 12.9-enrich) — Classify the 116 active customers — 🔄 RUNNING (14 Jun, on POST-13.7 clean capability inputs).** The Monday deliverable only needs the 116 active, order-history-rich "Not Selected" customers. Classify with the classifier on clean `capability_tags` (via `caps_for_op`) → produce a human-reviewable list (`industry_116_review.json`, sorted low-conf-first; Dinesh reviews all 116, ~1hr) → industry-enriched active set for Monday, validated by human eyes not a gate metric. **WRITES NOTHING to `qb_customers` until Dinesh approves** (read-only review artifact). 13-bucket vocab + abstention. On `main`, no new branches.
  - **⚠️ REGEN REQUIREMENT (Claude Code flag, 14 Jun — lock in):** `_outreach_cards_50.py` currently does its OWN inline `CAP_LATERAL` cello/fuse correction. Now that the classifier is authoritative + `capability_tags` is clean/live, the deck regen MUST remove the inline CAP_LATERAL and read the corrected column (`caps_for_op`) instead — else deck + platform drift (two sources of capability truth, defeats 13.7). **Do this AS PART OF the single final regen that also applies the 13.3 industry filter — NOT a separate capability-only regen now** (avoid two regens; the first would be a half-deck missing the industry layer Jeff asked for).

- **13.3 (was 12.9-design) — Industry filter layer — 🔜 (after 13.2).** Pure design first (uses 12.9-pre check-4 buying profiles). For each statistically-suggested pitch, check vs the customer's industry buying-profile; suppress mismatches (furniture/casebound fix), flag strong fit. **FILTER (suppress) first, NOT generative.** Show suppression reason on filtered cards (rep-transparent). **Merge-discipline carried from the diag:** only collapse buckets that ALSO buy similarly (check-4) — confused-but-buy-differently = better classification, not merging (else the filter loses a distinction it needs).

- **13.4 — Vocab-collapse + full-base enrichment — 📌PLATFORM follow-on (NOT Monday-critical).** Collapse synonym/overlap buckets (Trade Printers+Print Broker; govt-health/govt-education rule; Retail-vs-Creative for design-led brands; Advertising/Corporate/Creative cluster) — each merge checked against check-4 buying behaviour. Relabel the clear QB errors (James Creative Agency, Studio Odea both mislabelled "Property"). Switch the gate metric to **defensible-match** not exact-match (labels themselves disagree ~10%). Then re-run gate to confirm ~85%+, classify full 12,600 with provenance columns. Strengthens the platform; do after the Monday deliverable lands.

- **13.5 — Platform correction layers — ✅ DESIGN DONE + DECISION SETTLED; build greenlit.** Doc: `docs/design/CORRECTION_LAYERS_DESIGN.md` (no DB writes yet; migrations 123-126 written but NOT applied). Finding that drove it: Correction 3 (13.1) cleaned the DECK ONLY — reclassification lives in `_outreach_cards_50.py` ephemeral RPCs, dies with the run; production `qb_capability_tag` still polluted, every platform consumer (`_caps_for_op`, `get_capability_rhythm`, big-accounts, future coaching) still reads dirty.
  - **OWNERSHIP DECISION (settled):** capability assignment stays in **QB** (Jeff moved it to QB formula fields; the platform's 597-rule classifier was made INACTIVE). Platform corrects DOWNSTREAM via a `true_capability` layer — accepting the perpetual-correction tradeoff consciously. NOT reactivating the classifier (don't step on Jeff's formula-ownership).
  - **Shape (Layer 3 principle):** QB-synced field = read-only source; correction in adjacent platform-owned column w/ provenance; definition stored AS DATA in a table (not migration/script logic); recompute on sync, re-runnable.
  - **Layer 1 — capability:** `true_capability`/`true_capability_source`/`true_capability_at` on `qb_operations` (beside, never overwriting, `qb_capability_tag`). Definition in a `capability_taxonomy` table. Recompute hooks the existing sync post-`enrich_operations()`; taxonomy-version bump → full recompute (like reclassify). §10.12 gate: must reproduce 242 Embellishment / 183 Hard Cover / the clean rule set before any consumer switches.
  - **FORMULA OBTAINED (13 Jun) — changes the dimension + REVERSES the map decision.** The QB `Capability_Tag` formula keys on **`Department`** (primary; `Operation`/`Machine`/`Job Title` secondary), NOT op-name keywords. So pollution is a *department-level* mis-route, and the formula is *legible*. Reading it, cello does NOT obviously route to Embellishment — and the formula header says **"UPDATED"** (Case Making box/packaging disambiguation added). **Map-dimension decision REVERSED:** exact-op-name-map was my earlier lean (from the dormant classifier screenshot); now that (a) the formula keys on department and (b) the audit's *validated* correction is **keyword**-based on op-names (`cello`/`laminat`/`fuse`), KEYWORD is right here — it fits the pollution's actual shape (recurring substrings across many op-names) and fails SAFER (a new "soft-touch cello mount" is caught by keyword, missed by an exact map). Rationale to document: the formula routes at *department* granularity (too coarse to separate cello from foil within a dept); the correction refines at *operation* granularity — doing what the formula structurally can't. Drop `'classifier'` from the source enum (dormant).
  - **⚠️ GATING INCONSISTENCY → 13.6 must run before build.** Audit found cello→Embellishment + Fuse-back→Hard Cover, but (1) the current formula doesn't obviously route cello to Embellishment, (2) the formula is "UPDATED", (3) ops table was FULL-SYNCED 2 days ago. These can't all hold — the live data may already be cleaner than the audit (which ran on possibly-older-formula data). **Do NOT build the correction until 13.6 confirms the pollution still exists in current data.**
  - **Layer 2 — industry** (absorbs 13.2+13.4): `industry_enriched`/`industry_source`/`industry_enriched_at` on `qb_customers`; vocab+adjacency as tables; coverage=ALL tiered by provenance; enrich-on-sync = ENQUEUE + background worker (not LLM inline in sync path); full-base write gated on vocab-collapse clearing ~85% defensible-match; 116-active human-reviewed write ships first for Monday.
  - **Consumer switch (Q4, wave 1 must / wave 2 deferred):** wave 1 = `_caps_for_op`, `recompute_affinities`, `get_capability_rhythm`, `strategic_context_builder`, cards engine, big-accounts, future coaching → `true_capability`. Wave 2 (deferred, costed separately) = embedding consumers (vector_service, hybrid_retriever, langchain_tools) — switching forces re-embed. Transitional `COALESCE(true_capability, qb_capability_tag)` during backfill. **Watch:** until wave-2, embeddings carry polluted caps — confirm Monday path / fit-selection don't lean on vector layer for capability meaning (cards engine uses SQL path, likely fine).
  - **Build order:** Layer 1 (capability) lands FIRST → 13.2 (116 classify) reads clean capability profiles → 13.3 (fit-selection, resolves the 32-HC monotony via industry-fit, not an arbitrary cap).
  - **13.5-UI — surface the correction layer in the frontend (reuse the INACTIVE classifier-rules page) — NOT Monday-critical, platform-completeness follow-on.** Makes the correction layer MANAGED not buried: client-manageable rules, visible + auditable, with the existing Reclassify/Cache action as the recompute trigger. Show per op/capability: QB-formula value vs corrected `true_capability` + the rule + its `note` rationale (show the rules' EFFECT, not just a list). **Guardrails:** (1) clearly distinguish LIVE correction rules from the DORMANT 597 classifier rules so no one edits dead logic — retire/label the old ones; (2) if rules become UI-editable, the §10.12 verify (reproduce 242/183) must be re-runnable + visible after any edit, so a well-meaning UI change can't silently re-pollute — reclassify-and-verify loop visible, not fire-and-forget. Same pattern later for the industry vocab/adjacency tables. **Sequence: AFTER the Layer 1 backend is built + verified + feeding Monday's deck — does not block Monday.**

- **13.6 — Targeted formula↔data reconciliation audit — ✅ DONE. Verdict (a): pollution CURRENT, build the correction as designed (keyword-level).** Output `reconcile_pollution.json`. Root cause = **department conflation**, not bad op-tagging: the formula routes by `Department`, and cello lives in a combined department literally named `Post-print finishing/embellishment` (bundles cello+foil) → whole dept tagged Embellishment → cello inherits it (6,590/6,590 cello-Emb ops from that one dept). Hard Cover same via `Case-making, gluing` (fuse+casebind bundled, 90% of fuse ops → HC). **Structural implication: NO department-level fix can separate cello from foil (shared dept by construction) → op-name keyword granularity is REQUIRED → validates the Layer-1 keyword-rules design.** Magnitude reproduces audit to the digit (588/77.7%); >97% of pollution in the RAW formula tag (classifier fallback adds only ~3%) → correction targets the tag. Jeff's "Case Making disambiguation" formula update did NOT touch the polluting paths — data is fresh (synced today) and still polluted. **13.5 Layer-1 build now UNBLOCKED + greenlit.**
  - **Memory update queued:** sharpen `feedback_qb_capability_tag_pollution.md` with the routing-department root cause (mechanism = dept conflation; op-name granularity structurally required; exact depts/magnitudes; "Case Making update did NOT fix it" so nobody wrongly assumes resolved).

- **13.7 — Layer 1 build = REACTIVATE + CORRECT the existing classifier (Option 3, supersedes the design doc's new-layer approach) — 🔜 BUILD NEXT, greenlit.** Code read (13 Jun) revealed the platform's classifier is NOT dead — `backend/src/services/capability_classifier.py` is a complete op-name-granular system: exact-tuple match on 597 rules from `client_taxonomy_config` + keyword fallback, with `classify()` / `reclassify_all()` / the Intelligence-Config UI / the `batch_update_classifications` RPC all already built. **Linchpin: `qb_operations` ALREADY has two separate columns** — `qb_capability_tag` (QB formula, synced, polluted) and `capability_tags` (classifier output, platform-owned). The provenance separation you wanted EXISTS. Current `_caps_for_op` (recommendation_engine.py:32) logic = **QB-tag-wins, classifier-as-fallback** — which is why pollution flows in. So Option 3 reuses existing infra instead of building a parallel `true_capability` layer.
  - **The fix has 3 parts:** (1) **complete the classifier's keyword rules** — they have the SAME cello gap (Embellishment kw = foil/scodix/spot-uv/varnish/emboss; no cello/fuse). Add cello/laminat/matte/gloss/soft-touch/velvet/anti-scuff→Specialty; fuse/mount→Specialty; perfect-bind/saddle/section-sew→Soft Cover. Edit BOTH `_KEYWORD_RULES` (code default) AND `client_taxonomy_config` classifier_rules for Carbon8 (the live UI-edited source); also fix any exact-match seed tuples that map these ops to the wrong tag (exact wins over keyword). (2) **§10.12 gate** — run corrected classifier over all Carbon8 ops, must reproduce **242 Embellishment / 183 Hard Cover** + ~37 rules BEFORE any consumer switch. (3) **invert precedence** in `_caps_for_op` + `get_capability_rhythm`(:233,268) + strategic_context_builder(:709) + cards engine + big-accounts → classifier-wins-when-it-has-an-opinion, QB-tag fallback. Lockstep (docstring says these must match); shared helper if practical. **Embedding consumers (vector_service, hybrid_retriever, langchain_tools) = WAVE 2, do NOT switch (re-embed cost).**
  - **Step 0 (confirm before writing, abort if false):** both columns separate on `qb_operations` ✓(strongly implied); classifier NOT currently called during QB sync (genuinely dormant, no double-tag); full grep of capability-precedence call sites with line numbers.
  - **Step 4:** wire classifier into sync (reclassify after ops-sync) so new ops get corrected tags going forward — platform-not-one-shot. Confirm idempotent.
  - **Discipline:** branch, no prod writes until Step-2 gate passes; report after Step 0 and Step 2 before proceeding. `qb_capability_tag` stays untouched read-only source.
  - **Supersedes:** `CORRECTION_LAYERS_DESIGN.md` Layer 1 (new `true_capability` column + new `capability_taxonomy` table) is REPLACED by reuse-the-classifier. The design's *principle* (QB read-only, platform correction beside it w/ provenance, definition-as-data in `client_taxonomy_config`) HOLDS; only the implementation changes. Industry Layer 2 of that doc still stands.

- **13.7 STEP 0 FINDINGS (13 Jun) — assumption 2 FALSE, build reshaped + 2 decisions settled.**
  - ✅ Cols separate (capability_tags jsonb / qb_capability_tag text). ✅ No double-tag risk. ❌ **"classifier dormant" was FALSE:** sync DOES run it (`_classify_operations`, quickbase_sync.py:545) but it **COPIES qb_capability_tag into capability_tags** when the QB tag is present — only uses the real op-name classifier when QB tag is blank. **So the sync PROPAGATES pollution; `capability_tags` today is mostly a polluted copy, not clean classifier output.** (Shape mess too: 474k bare scalars + 157k arrays + 65k empty.) For 9,238 cello ops: 6,483 empty, ~1,705 copied-Embellishment.
  - **⇒ Inverting precedence alone fixes NOTHING** (empty cello ops fall back to polluted QB tag). **Mandatory order (§10.14 fix-the-tap-before-mopping): fix rules+tuples → `reclassify_all` (write real classifier output) → §10.12 gate → flip precedence → FIX SYNC PATH so `_classify_operations` stops copying the QB tag (else next sync re-pollutes).** The sync-path fix is REQUIRED for durability, not optional follow-up.
  - **Exact-tuple traps (exact match wins over keyword; `(none)` short-circuits keyword fallback):** ~13 tuples must be fixed — 3 fuse→HardCover (`Fuse back to back`×2, `Fuse or mounting`), 4 varnish→Embellishment (SwissQ varnish, should be WideFormat), 6 `(none)` cello tuples in dept `Coating`. High-volume cello (6,590 ops, `Post-print finishing/embellishment`) NOT in seed → new keyword rule catches it. Current `_KEYWORD_RULES` also wrong: varnish under Emb, case-bind→SoftCover, no cello/laminat/matte/gloss/fuse/mount rules.
  - **WAVE-1 sites confirmed (5):** `_caps_for_op`(recommendation_engine.py:32, canonical), inline capability_breakdown(:716 QB-only), `get_contact_capability_profile`(customer_analytics:267), `get_capability_rhythm`(customer_analytics:552), strategic_context_builder:709 (**QB-only, filters qb_capability_tag IS NOT NULL** — biggest change). WAVE-2 (defer, re-embed): vector_service:583, hybrid_retriever:384, langchain_tools:434.
  - **DECISION 1 (settled): precedence = classifier-OVERRIDES, QB-FILLS-GAPS.** Classifier wins where it has an opinion (foil→Emb, cello→Specialty, fuse→Specialty, casebind→HC); QB tag fills generic ops where classifier has no rule (Printing/Guillotine). **⚠️ §10.12 GATE MUST verify against THIS composed precedence (classifier+QB-fallback), NOT classifier-only — else it measures the wrong path vs what consumers read.**
  - **DECISION 2 (settled): config-driven keyword rules = FOLD IN (proper end-state, satisfies definition-as-data fully + lights up 13.5-UI).** Refined sequencing so it doesn't risk the Monday spine: keyword rules in CODE first → pass gate → ship clean caps (Monday-critical spine); migrate keyword rules into config + UI-editable as the immediately-following step. **Whichever path, the gate runs on the FINAL shipping path, not an intermediate.** (Corrects earlier ledger note: "classifier config rules ARE definition-as-data" was only half-true — exact tuples in config, keyword rules in code; this decision closes that gap.)
  - **Status: ✅ 13.7 CLOSED (14 Jun) — capability layer fully done + durable + pushed (commits 4bfe282→8c139b8, migrations 123+124).** Steps 0-5 all complete & verified on live. See execution + closeout blocks below.
  - **CLOSEOUT (14 Jun):** Step 4 precedence flipped across all 5 WAVE-1 sites via shared `capability_resolution.caps_for_op` (classifier-wins/QB-fills-gaps); strategic_context_builder filter (`qb_capability_tag IS NOT NULL`) REMOVED so classifier-only ops are visible — verified via Architectus (old deck "Emb 49%"=cello → now correctly Specialty, no Emb). Step 5 sync fixed: `_classify_operations` writes classifier-only via mig-123 RPC, mig-124 NULL sentinel so syncs classify only NEW rows (not the 413k legit empties); re-pollution path closed (verified `Matt cello`→Specialty through the actual sync method, idempotent 0-row 2nd pass). **WAVE-2 resolved:** only `vector_service:583` needs anything (bakes tag into embedding text); `hybrid_retriever`/`langchain_tools` read the live column at query-time = already corrected. **Deck path is SQL-only for capability meaning → split-brain does NOT reach Monday.** WAVE-2 = targeted ~8-10k re-embed (not 631k), index-churn-dominated, safe-deferred (in bucket list). Display label spelling (`Display / Installation` vs QB `Display/Installation`) — fixing now to close clean (one-word change + Display reclassify).

- **13.7 EXECUTION (13 Jun, eve) — branch `feature/capability-classifier-layer1`.**
  - ✅ **Steps 1-2 DONE, §10.12 GATE PASSED (vs the AUDIT, not the deck's 242).** Step 1: corrected `_KEYWORD_RULES` (cello/laminate/matte/gloss/fuse/mount→Specialty; section/oversew→Soft Cover; removed varnish→Emb + case-bind→Soft Cover bugs), made keyword rules config-driven (loaded from `client_taxonomy_config.classifier_rules→config_data['keyword_rules']`, code fallback); fixed **35 mis-curated exact tuples** (Emb 47→37, HC 34→17) — dominant = **`Printing` on `LED UV Printer - SwissQ` mis-tagged Embellishment (307 co, 1,969 ops)** = bulk of the 457→335 gap; also Hand Lay→SwissQ, Oversewn/Manual-Section→HC→SoftCover, D-ring/Book-Ribbon→Specialty, fuse→Specialty, SwissQ varnish→WideFormat, 6 `(none)` Coating cello tuples.
  - **GATE RESULT (dry-run, read-only): Emb 15.2%/335 (audit 15.3%), HC 8.4%/186 (audit 8.3%) — within 0.1pp; full rule set reproduces (Emb↔HC lift 3.87 vs 3.96, HC→WF/HC→SC/Emb→SC+WF all match).** **KEY METHOD CALL (settled): gate retargeted from the deck's scoped 242 → the audit's unscoped 335.** Justified: the classifier is QB-blind/unscoped = structurally the AUDIT's TRUE methodology, NOT the deck's scoped CAP_LATERAL; reproducing 242 would require coupling the classifier back to the QB tag, defeating independent correction. Validated as an HONEST pass (not overfitting): difference is methodological-scoping not tuning, the FULL rule set matched, HC 183 matches BOTH scoped+unscoped (convergence case), tuples fixed on their own merits. Two benign non-pollution divergences documented: Design 86 vs 94 / Flat Sheets 89.8 vs 85.5 (generic prepress/print ops stay `(none)`→QB-fallback, not keyword-promoted); **Display label spelling bug to fix (`Display / Installation` vs QB's `Display/Installation`).**
  - ✅ **Step 3a DONE (live write):** `client_taxonomy_config` → **v4** (35 corrected tuples + config-driven keyword_rules). `qb_capability_tag` UNTOUCHED.
  - 🔄 **Step 3b reclassify RUNNING** — rewriting `capability_tags` as pure classifier output for all ~631k Carbon8 ops (also normalizes the 474k-scalar/157k-array/65k-empty shape mess). Healthy/steady (~366 rows/sec). **SAFE even if interrupted: no consumer reads classifier-primary yet (all WAVE-1 still read qb_capability_tag first), so a half-rewritten column changes ZERO production behavior; reclassify is idempotent.**
  - 📋 **Step 3c verify STAGED — the hard checkpoint. Confirm THREE things on the LIVE written column (not just script-returned):** (a) row count covers all ~631k (not a stunted partial — the latency-recompute lesson), (b) string/array shape normalized, (c) gate numbers reproduce on the live column (Emb 15.3%/HC 8.3%). **All three clean → PAUSE for review before the consumer-precedence flip.**
  - **REMAINING (all consumer/durability-affecting, gated on review): Step 4** flip WAVE-1 precedence (5 sites) → classifier-overrides via shared helper; **Step 5** fix sync path (`_classify_operations`) to stop copying the QB tag (REQUIRED — else next sync re-pollutes); fix the Display label spelling; document the two benign divergences in the §10.12 record.
  - **Resume detail:** `project_capability_classifier_layer1.md` (locked decisions, 5 WAVE-1 sites, sync-path fix, divergences). Code edits (`capability_classifier.py`, `capability_classifier_data.json`) on the branch.
  - **Memory still queued:** `feedback_qb_capability_tag_pollution.md` — now TWO pollution sources to record: QB department-conflation AND the classifier's own mis-curated seed tuples (e.g. Printing→Embellishment), the second of which the original audit never saw (the gate caught it).

- **13.1-open — deck balance (32 Hard Cover) — NOT a bug, design choice.** Corr3's single genuine `Embellishment→Hard Cover` rule (lift 4.71) + premium emb-buyers dominating the top-50 → 32 HC pitches. Each card individually valid (clean gap, real high-lift). Resolved by 13.3's industry-fit re-ranking (premium Luxury → HC fits/keep; Retail/Hospitality → demote HC, surface fitting 2nd-best), NOT a hard pitch-cap. Downstream of the platform layers, so resolved after they land.

- **13.8 — Extend big-accounts to top 100 + opportunity-surfacing check — 🔜 part of the post-13.7 deck regeneration (runs on CORRECTED data, NOT now on polluted tags).** Tests the hypothesis: did big accounts with a real gap get cut by the rank-50 opportunity cutoff? Two cuts:
  - **Big-accounts view → top 100 by trailing-12mo revenue** (was top 40), per AM, with saturation status. Fuller reference list; folds into each per-AM doc (see deliverable structure below).
  - **Opportunity-surfacing check:** of the top 100 BY REVENUE, how many have a genuine POST-correction gap, and where do they rank in the OPPORTUNITY ordering? A big account with a real gap ranked 51–100 = the case Dinesh suspected (big customer sat just outside the bounded top-50 and wasn't surfaced). If found → argues for extending the deck beyond 50 OR a dedicated "big accounts WITH real gaps" cut that guarantees they surface regardless of opportunity-rank cutoff. **The sharper answer to Linda's "are the big ones maxed out?": not just "mostly yes" but "yes except these N, which are big AND have room — here they are."**
  - **Discipline:** only meaningful on POST-13.7 corrected capabilities — pollution inflated gaps (a phantom rank-60 gap on polluted data may vanish when clean, or a real gap may be revealed that pollution masked). Do NOT run on current tags.

- **DELIVERABLE FORMAT (decided 13 Jun) — per-AM docs, two sections each:**
  - **(1) Opportunities** — corrected, industry-grounded cards. Each card shows BOTH reasonings side by side: "Pattern" (clean stats, post-13.7) AND "Fits their business" (industry layer, 13.3), PLUS a "Not pitched" line showing the suppressed pitch + why (e.g. "Hard Cover suggested by numbers but retail/design firms don't print casebound — set aside"). **The visible suppression reason is what DEMONSTRATES the breakthrough to Jeff — the intelligence is invisible if you only show kept pitches.** Industry reasoning MADE VISIBLE = Jeff's explicit ask. (Card layout sketched/visualized 13 Jun.)
  - **(2) Your major accounts** — top accounts by 12mo revenue (now top 100) with saturation status. **Saturated/retention accounts framed ACTIVELY** ("$420k, buys your full range, no gap — retention relationship, protect it") NOT as empty/failed opportunity cards (a blank pitch field reads as "system has nothing for my biggest client"). Has-real-gap big accounts become opportunity cards.
  - Feedback column throughout (rep validation = ground truth).
  - **Each card's 3 feeds must be real & clean:** Pattern←clean rules (post-13.7), Fits-business←industry buying-profile (12.9-pre check-4), Timing←cadence (the Freedom-Furniture-validated signal). A card is only as honest as its feeds → 13.7 gates everything.
  - **13.3 spec addition:** fit-selection must RETAIN + surface the suppressed candidate with its reason (first-class output), not silently drop it — the "Not pitched" line needs it.

- **Monday deliverable = clean stats (13.1/13.7) + industry-grounding (13.2 + 13.3) on the Layer-1 clean-capability foundation, shipped as the two-section per-AM docs above.** The answer to Jeff's redirect. **Approach INTACT.** Honest tradeoff: full platform-layer build > what Monday strictly needs — for Monday the selection logic + capability taxonomy must be written as engine/pipeline components (not one-shot scripts) even if industry enrichment is semi-manual, so they don't get buried.

---

## ACTIVE — AM Coaching (the flagship feature)

Two-audience design: (1) a management comparison report for Jeff + Kenneth (client manager) — "honest analysis", NOT a score/rank; (2) per-AM sharable coaching insights. **Groundwork-first: do not build the comparison report until data quality/evenness is confirmed.** The comparison goes to management about named people, so uneven data = unfair characterisation. Caveats will be built into the final report (not presented as final truth).

- **12.3 — AM coaching DATA-READINESS audit — ✅ DONE.** Output `am_coaching_readiness.json`, generator `_am_coaching_readiness.py`.
  - **Readiness:** Nic/Linda/Ehab/Kenneth = email-READY for a STRUCTURAL layer (caveats: uneven CV 1.1–3.1; Ehab ~3wk stale; **Nic latency population only 7.5%** vs 45–58% others — resolve before using latency). Mary/Peter = NOT-EMAIL-READY *by construction* (no mailbox) → separate QB-outcome track.
  - **Features:** structural (initiation, cadence, depth, latency*, resolution*) buildable NOW, no LLM. Content (intent-mix 53% catch-all, sentiment 0.1%, buying-signal/topics ~0%, tone, Q3-substance) ALL gated on fresh extraction (pilot first §10.12).
  - **Key insight:** relationship-account AMs won't separate on volume/cadence → **response-substance (Q3) is their unlock**, not more structural metrics.
  - **§10.13 traps caught:** (1) `thread_status` only carries mailbox_id for Linda's legacy box (86% NULL) — would have fabricated "no thread data" for Nic/Ehab/Kenneth; fixed via `canonical_thread_id`. (2) "hello@ 144K" memory stale → actually 44,153; full corpus 198,479, zero null-mailbox. Memory corrected.
  - **LAUNCH-SCOPE DECISION (now answered by data):** structural v1 on the 4 mailbox AMs WITH comparison-fairness caveats; Mary/Peter separate QB-outcome track. NOT all-six (Mary/Peter email-absent forever), NOT wait. **But CV unevenness + Nic latency gap mean "ready" = data-exists, not yet fair-to-compare head-to-head — resolve before the comparison report.**

- **12.3-open — Nic latency population check** — is `email_response_metrics` under-computed for Nic's mailbox (would make him look artificially unresponsive = unfair) vs genuine long-tail low-reply? Resolve before latency enters any comparison.

- **FUTURE PLAY (parked, good idea, NOT now): sandwich per-AM coaching insights into a doc-send to the AMs.** Vehicle is sound, timing is wrong: (a) data not fair-to-compare yet (CV unevenness, Nic latency gap); (b) collides with the cello-correction message (two credibility hits at once); (c) only structural features exist today, and relationship AMs need Q3-substance not structural. Revisit once data is fair + content features extracted. Coaching ships as its own deliberate deliverable, not riding a correction.

- **Likely groundwork (parked, may need promoting):** Finer-intent reclassification (the 53% catch-all) — content-feature prerequisite. Mailbox re-auth (Ehab stale, + Kenneth/Jeff/hello@) — evenness. Substance/tone extraction pass — deeper content. **NOTE: Jeff's "use recent job manager not customer-AM" (12.4.5) also governs coaching attribution.**

---

## DONE — 12 June

- ✅ **12.9-enrich-diag — 57% gate decomposed (3 causes, vocabulary dominant).** (1) **Vocabulary = dominant:** strict 56.1% → adjacency-tolerant 84.1% (+28pts), ~90% with more overlaps found (Healthcare↔Government, Education↔Government, Retail↔Creative, Property↔NFP). Most "error" = non-separable buckets, not classifier wrong. (2) **Classifier error = small (~4%):** ~4/112 genuine, all generic-name over-indexing (Koala→Corporate but furniture; Odd Culture→Creative but hospitality; Maui Jim/Krama Yoga). Few-shot fixable. (3) **QB-label noise = real (§10.13 on the validation set itself):** of 19 real disagreements, classifier-right/QB-wrong=2 (James Creative Agency, Studio Odea both mislabelled "Property"), QB-right=4, ambiguous=13 → "trusted" 1,912 carry ~10% label-error/subjectivity, so true classifier accuracy materially >56% and the 85% exact-match bar was partly unfair. **Verdict: vocab-collapse (primary) + ground-truth-cleanup (secondary); classifier-tune smallest. Monday path = enrich just the 116 active + human-review, independent of the 12,600 base.** → carried into 13.2/13.3/13.4.
- ✅ **12.7 — Latency recompute (all 7 mailboxes, 0 errors; Nic 1,001→8,431) + contact-rollup fixed (mig 122: direction-split + uncapped server-side UPDATE, 4,123 contacts) + documented (DATABASE_DESIGN.md §13). Committed + pushed (6167fa4).** Coaching latency prerequisite satisfied (read `email_response_metrics` directly).
- ✅ **12.6 / 12.6-validate / 12.6-audit** — regeneration (cello fix, recency-AM, big-accounts view: top tier saturated, 8/40 real gap); Hard Cover = next cello caught (26% genuine); **full capability audit: only 2/8 tags polluted, cross-sell real-but-OBSCURED not thin, 37 clean balanced rules.**
- ✅ **12.4 — Reps' feedback verified** (cello CONFIRMED 63→16%, within-job CONFIRMED, hardcover→WF REFUTED 72% real, recency-AM CONFIRMED). Substantive reply SENT.
- ✅ **12.2b — Jeff's reply handled + 3 accounts reassigned.** Verified assignment used `qb_operations.am_customer` (mode), agrees with field #16 on 47/50. Kenneth narrow miss (~#48; caught "Cash Account" junk bucket #12 §10.13). Reassigned Jet+Forsight→Nic, Jefferies→Ehab. Reply SENT + clean docs SENT.
- ✅ **12.1 / 12.1b / 12.1c** — Nathan/Daniel docs + bug isolation; Kalani cleared; tier labels unified (37/7/6); docx polish.
- ✅ **12.2 — Email to Jeff SENT with 6 docs.** Reps' feedback incoming = ground truth (→ now 12.4).
- ✅ **`EMAIL_DRAFTING_GUIDE.md`** created (outside repo; plain-words note added).

---

## DONE — 11 June (the cards deliverable)

- ✅ **11.17** Per-AM Word docs. `card_am_assignment.json`. Double-scaling bug caught+fixed.
- ✅ **11.16** PDF deliverable. **11.15** Full-50 reference doc (re-tiered 37/7/6). **11.14** Confidence-spread read. **11.4** Card validation (finish-trap 17/30 fixed). **11.1** Cards finalized.

---

## NEXT PHASE — after the urgent + coaching groundwork

- **Intent-lifecycle rollup (won/lost feature)** — overlaps coaching content-features.
- **Daily/periodic platform refresh** of the cards — promised to Jeff. Railway cron. Depends on mailbox freshness.
- **Draft-ready outreach** — drafted emails into AM drafts folders, human-approve-send. Promised to Jeff.

---

## DOCS / TRACKING

- **DATA_ANALYSIS_GUIDELINES.md** — current through 10.14. Dinesh maintains.
- **OUTREACH_PROJECT_LEDGER.md** (this file) — canonical tactical tracker.
- **BUCKET_LIST_JUNE_2026.md** — strategic plan.
- **EMAIL_DRAFTING_GUIDE.md** — outside the repo (Claude can't reach it).

---

## BLOCKED / WAITING ON OTHERS

- **Mailbox re-auth — Ehab, Kenneth, Jeff, hello@ (OAuth expired).** Self-heals once owners reconnect; can't be server-triggered. Relevant to coaching evenness. In Jeff's hands.

---

## PARKED

- Regex repoint of AI-Link-Refs backfill · DB RAM-hit 82.71% · Thread-intent rollup unbuilt · Nic 2025-H1 holes · Hello v2 first-touch signal · Orphan-row cleanup · Finer-intent reclassification pilot (NOW a coaching prerequisite) · Prod deploy of QB-sync commits · 384 stale rows · client_id tagging · Mary re Q711314 · Rare ID dead-batch · QB-side dedup note to Jeff.

---

## DONE — earlier

- ✅ QB operations sync overflow (mig 119) + dropped rows recovered (630,798) + pagination `.order()`.
- ✅ Nic mailbox backfill (10.9b) 17.8%→84%; certification closed.
- ✅ Trash `folder_trash` pre-filter leak fixed at source.
- ✅ Four-mailbox readiness audit (11.2).
- ✅ Revenue-defense analysis, saturation finding, sequence-engine null (→ onboarding finding), feature audit.
