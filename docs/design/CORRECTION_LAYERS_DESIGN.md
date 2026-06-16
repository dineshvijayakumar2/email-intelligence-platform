# Capability + Industry Correction Layers - Design

**Status: DESIGN ONLY. No DB writes, no migrations run. For review before build.**
Two open decisions to settle first: **Q1** (where the definition lives as data) and **Q4** (the complete consumer switch). Tradeoffs are flagged inline as `TRADEOFF`.

Author context: Correction 3 cleaned the deck only. Its reclassification lives in a throwaway script's ephemeral RPCs (`scripts/db/_outreach_cards_50.py`, the `CAP_LATERAL` string in `_tmp_card_basket`, dropped at end of run) and dies with the run. Production `qb_operations.qb_capability_tag` is still polluted, and `recommendation_engine._caps_for_op` plus every other consumer still reads the dirty tag. Industry enrichment is un-built. This doc makes both **persistent platform layers**.

---

## Layer 3 (stated first, because Layers 1 and 2 instantiate it): the standing principle

> **QB-synced fields are a read-only source of truth. Platform corrections live in adjacent
> platform-owned columns with provenance, recomputed on sync, and the definition is stored as
> data (a table) - never embedded in migration SQL or a one-shot script.**

Four invariants every correction layer must satisfy:

1. **Never overwrite the QB source.** `qb_capability_tag`, `capability_tags`, `qb_customers.industry` stay exactly as synced. Corrections go in NEW columns (`true_capability`, `industry_enriched`).
2. **Provenance on every corrected value.** A `*_source` marker records where the value came from (`qb` / classifier / `llm_high_conf` / `llm_low_conf`) so any consumer can choose how much to trust it, and so the value is auditable.
3. **Definition as data, in one canonical table.** The op-name->capability rules and the industry vocabulary/adjacency are rows in a table, not regexes pasted into a migration or a script. One source; the recompute reads it; it cannot drift between the deck script, the production engine, and the next analyst.
4. **Recompute on sync, re-runnable, never one-shot.** Both layers recompute as QB adds/changes rows (hooked into the existing sync), and both can be fully re-run when the definition (taxonomy/vocab) changes - versioned, like the existing classifier.

Everything below is two instances of this one pattern.

---

## Layer 1 - Capability normalization

> **⚠️ IMPLEMENTATION SUPERSEDED (13 Jun) — see ledger 13.7.** Code review found the platform's
> capability classifier (`backend/src/services/capability_classifier.py`) is NOT dead — it is a
> complete op-name-granular system (597 exact-tuple rules in `client_taxonomy_config` + keyword
> fallback, with `reclassify_all()`, the `batch_update_classifications` RPC, and the Intelligence-
> Config UI all already built). And `qb_operations` ALREADY has two separate columns:
> `qb_capability_tag` (QB formula, polluted) and `capability_tags` (classifier output). So the
> NEW `true_capability` column + NEW `capability_taxonomy` table proposed below are **NOT built** —
> they would duplicate existing infrastructure and create two sources of truth. **Instead (Option 3):**
> complete the existing classifier's keyword rules to cover the pollution (cello→Specialty, fuse→
> Specialty, etc.), run the §10.12 gate (reproduce 242/183), then invert `_caps_for_op` precedence
> from QB-tag-wins to classifier-wins-when-it-has-an-opinion. The classifier's `client_taxonomy_config`
> rules ARE the "definition as data" the principle below requires; the classifier column IS the
> "platform correction beside the QB source." **The Layer-3 principle and all four invariants below
> HOLD — only the column/table mechanics in this section are replaced by classifier-reuse.** The rest
> of this section is retained for the design rationale (keyword-not-exact-map, recompute-on-sync,
> provenance) which all carried into the Option-3 build. Layer 2 (industry) is unaffected.

### What it produces
On `qb_operations`, three new platform-owned columns (beside, never replacing, `qb_capability_tag` / `capability_tags`):

| column | meaning |
|---|---|
| `true_capability` TEXT | the corrected capability for this operation (one of the 8 caps) |
| `true_capability_source` TEXT | `taxonomy_in` / `taxonomy_out` / `qb` / `classifier` / `unclassified` |
| `true_capability_at` TIMESTAMPTZ | when this row was last recomputed |

`true_capability` is an **override** read: the single clean value every capability consumer should read instead of `qb_capability_tag`. It is computed as: apply the taxonomy rules to `operation_name`; if no rule matches, fall back to `qb_capability_tag`, else `capability_tags[0]`, else NULL.

### Q1 - where the definition lives as data: `capability_taxonomy`

The reclassification is **not** an exact op-name->capability map (there are ~736 distinct op-names and new ones arrive every sync). It is a small ordered set of **keyword rules** - exactly what Correction 3 / the audit `TRUE` taxonomy is. Store those rules:

```
capability_taxonomy
  id              uuid pk
  client_id       uuid null            -- NULL = global default; non-null = per-client override
  priority        int not null         -- lower = higher precedence (rule order matters)
  rule_kind       text not null        -- 'in_reclaim' | 'out_eject'
  match_pattern   text not null        -- POSIX regex tested against operation_name (~*)
  scope_tags      text[] null          -- NULL = applies to any source tag;
                                       --   for out_eject = {'Embellishment','Hard Cover Books'}
  target_capability text not null      -- one of the 8 canonical caps
  note            text                 -- human rationale (e.g. 'cello/film lamination, not embellishment')
  active          boolean not null default true
```

Seed rows reproduce Correction 3 exactly:

| priority | rule_kind | match_pattern | scope_tags | target_capability |
|---|---|---|---|---|
| 10 | in_reclaim | `(foil\|scodix\|spot uv\|emboss\|deboss\|stamp)` | NULL | Embellishment |
| 20 | in_reclaim | `(casebind\|casing\|text block to cover\|head & tail\|end paper\|fusing board)` | NULL | Hard Cover Books |
| 30 | in_reclaim | `(perfect bind\|saddle stitch\|saddle sew\|wire bind\|pur bind\|false cover\|oversew)` | NULL | Soft Cover Books |
| 40 | out_eject | `(cello\|laminat\|matte?\|gloss\|soft.?touch\|velvet\|anti.?scuff\|scuff\|varnish\|fuse\|mount\|round corner\|die.?cut\|laser\|perforat\|nip\|d-ring\|magnet\|ribbon\|packag\|precoat\|coat)` | `{Embellishment,Hard Cover Books}` | Specialty Finishing |

**The recompute is a join.** For each operation, pick the lowest-`priority` active rule whose `match_pattern` matches `operation_name` AND (`scope_tags IS NULL` OR the row's original `qb_capability_tag` = ANY(`scope_tags`)). `true_capability` = that rule's `target_capability`; if no rule matches, fall back as above. This is a lateral join to "first matching rule", expressible as a single set-based `UPDATE ... FROM` - deterministic, no app logic, no drift. The exact SQL recompute is the same `CASE` that `CAP_LATERAL` already encodes, but read FROM the table rather than hard-coded.

`TRADEOFF (Q1, the main one)` - **keyword-rules-as-data vs exact-op-name-map.**
- *Keyword rules* (recommended): ~4 rows, generalize to unseen op-names, this IS what Correction 3 is, regex lives in one reviewable table. Cost: a regex in a data row is still "logic-ish"; a bad pattern silently mis-routes. Mitigation: the §10.12 verification (below) catches drift, and `note` documents intent.
- *Exact op-name map* (alternative): one row per distinct `operation_name` -> capability, fully explicit and reviewable, no regex. Cost: must be maintained for every new op-name QB invents; unseen ops fall back to the polluted `qb_capability_tag` until someone adds a row - i.e. silent re-pollution. For ~736 names growing over time this is a standing maintenance tax.
- *Recommendation*: keyword rules, because the recompute-is-a-join requirement and the "can't drift" requirement are both satisfied and it matches the validated Correction 3. Keep the door open to pin specific high-volume op-names with exact rows (a `match_pattern` that is an anchored exact string) when a keyword proves too blunt.

`TRADEOFF` - **global vs per-client taxonomy.** The existing classifier rules are per-client (`client_taxonomy_config.client_id`). Carbon8 is the only live client. Recommend `client_id` nullable with a global default + per-client override (NULL client_id rules apply to all; a client row overrides by priority). Matches the classifier's multi-tenant shape without forcing every client to re-author. Flagged because it is a real choice, not obvious.

`TRADEOFF` - **reuse `client_taxonomy_config` (config_type='capability_corrections', jsonb) vs a dedicated `capability_taxonomy` table.** Reuse = no new table, consistent with classifier rules. Dedicated = the recompute can `JOIN`/`~*` against real columns (jsonb rules cannot be joined as cleanly, you'd unnest in app code, which re-introduces drift). Recommend **dedicated table** specifically to keep the recompute a set-based SQL join (the stated requirement). This is the one place we deliberately do NOT reuse the existing config table.

### Q2 - recompute trigger / sync hook
The sync already has the exact hook. `quickbase_sync.py:sync_all()` (line ~224) runs `_post_sync_operations()` (line ~272) after operations are upserted, which does `match_operations_to_companies()` + `enrich_operations()` (the classifier writes `capability_tags` here via `batch_update_qb_capabilities`, chunk 100). Add one step **immediately after** `enrich_operations()`:

- **Per-sync delta recompute**: recompute `true_capability` for the operations touched this sync (the incremental delta - rows with `qb_last_modified` after `last_sync_at`, the set sync already knows). Set-based SQL `UPDATE ... FROM capability_taxonomy` over those ids. Cheap, deterministic, runs every sync so the column never goes stale as rows arrive.
- **Taxonomy-version full recompute**: a `capability_taxonomy_version` (a row in `system_settings` or a `version` max over the table). When the taxonomy changes, the version bumps and a full recompute runs over ALL operations - mirroring the existing `reclassify_all()` + `POST /intelligence-config/reclassify` pattern (a `POST /intelligence-config/recompute-true-capability` endpoint, background thread, `batch_update_*` RPC chunk 100).

So: definition change -> full recompute (explicit, like reclassify); new rows -> delta recompute (automatic, on sync). Never stale, never one-shot. (Q8 satisfied.)

### §10.12 verification (Q3) - must reproduce the known-good numbers BEFORE consumers switch
After backfill, assert the materialized layer reproduces the validated analysis (`capability_tag_audit.json` / Correction 3):
- companies with >=2 `true_capability='Embellishment'` jobs == **242** (genuine foil/emboss base);
- companies with >=2 `true_capability='Hard Cover Books'` jobs == **183** (genuine casebinding);
- recomputing the association rules off `true_capability` reproduces the **clean rule set** (HC->WF 83%/2.27, HC->SC 77%/2.74, the ~34-37 surviving rules) within tolerance.
A verification script (extends `_verify_correction3.py`) runs these as assertions; if any fails, the materialized column has diverged from the validated definition and **no consumer is switched** until it matches. This is the §10.12 gate: the persistent layer must equal the analysis it is materializing.

---

## Layer 2 - Industry enrichment

### What it produces
On `qb_customers`, three platform-owned columns (beside, never replacing, the QB-synced `industry`):

| column | meaning |
|---|---|
| `industry_enriched` TEXT | predicted industry (one of the canonical vocabulary) or NULL |
| `industry_source` TEXT | `qb` / `llm_high_conf` / `llm_low_conf` / `llm_abstain` |
| `industry_enriched_at` TIMESTAMPTZ | when enriched |

**Read logic (the effective industry):** `qb_customers.industry` if it is a usable value (not NULL, not `'Not Selected'`, not `'Small Business or Individual'`, not `'Extinct'`) -> `industry_source='qb'`; ELSE `industry_enriched` with its `industry_source`. QB stays authoritative; enrichment fills the 83% "Not Selected" gap.

### Q1 - where the definition lives as data: `industry_vocabulary` + `industry_adjacency`
```
industry_vocabulary
  id uuid pk, client_id uuid null, name text not null, display_order int,
  active boolean default true, definition_hint text   -- the per-bucket hint fed to the LLM prompt
industry_adjacency
  id uuid pk, client_id uuid null, industry_a text, industry_b text
  -- defensible-overlap pairs used by the 'defensible-match' gate metric (12.9-enrich-diag)
```
The 13 canonical industries seed `industry_vocabulary`; the overlap pairs found in 12.9-enrich-diag (Trade Printers <-> Print Broker, Advertising/Corporate/Creative, Retail <-> Creative, Healthcare/Education <-> Government, Property <-> NFP) seed `industry_adjacency`. The classifier prompt is BUILT from `industry_vocabulary` (vocab + hints), not hard-coded - so the vocab is one canonical source, and the diagnosis finding ("the vocabulary overlaps") is fixed by editing data (collapse buckets / adjust hints / add adjacency), not code.

`TRADEOFF` - the 12.9 gate is currently **failing on the existing 13-bucket vocab** (high-conf exact-match 56%, defensible-match ~84%). Storing the vocab as data is what lets us collapse buckets (the recommended fix) without a code change. **Layer 2's full-base write stays gated** (below) until a vocab revision clears ~85% defensible-match.

### Q2 - recompute trigger / sync hook
After `sync_customers()` in `sync_all()` (before/around `propagate_qb_data_to_companies()` which copies industry to `customer_companies`):
- **Incremental enrich on new unlabelled customers**: for customers synced this run whose `industry` is NULL/`Not Selected` and who have no fresh `industry_enriched`, run the LLM classifier. Cost-bounded because it is only the delta, not all 15k each sync.
- **No auto re-enrich of already-enriched rows** unless the vocab version changes (a `industry_vocab_version` bump -> background full re-enrich, like reclassify). Avoids re-paying LLM cost every sync.

`TRADEOFF` - **enrich-on-sync (LLM in the sync path) vs a separate scheduled/queued job.** Capability recompute is pure SQL and safe inline. Industry enrichment is an external paid API call; running it inside the sync transaction risks latency/failure coupling sync to OpenAI. Recommend: the sync hook **enqueues** new unlabelled customer ids; a separate background worker (same pattern as the reclassify background thread) drains the queue and calls the LLM. Sync never blocks on the API. Flagged because "recompute on sync" for Layer 2 means *enqueue on sync*, not *call-LLM-in-sync*.

### Q6 - coverage = ALL, trust = tiered; the gate
Write the **whole base** (coverage = all customers), but tier by provenance and gate the bulk write:
- the 1,912 usable QB labels stay `industry_source='qb'` (authoritative, not LLM-touched);
- LLM predictions are written for the rest; high-confidence -> `llm_high_conf`, low-confidence -> **`llm_low_conf` (written, not withheld, not promoted)**, abstentions -> `llm_abstain`.
- **Full-base write is GATED** on a vocab revision clearing the ~85% **defensible-match** gate (12.9-enrich Phase 1, adjacency-tolerant). Until then, the full LLM write does not run.
- **Monday path, ahead of the gate**: the **116 active order-history-rich** "Not Selected" customers are few enough to **human-review**; write those first (reviewed rows marked `llm_high_conf` or a `reviewed` flag), so the Monday deliverable has industry on what it needs without waiting for the full-base gate.

### Q7 - which tiers each consumer trusts
| consumer | trusts | rule |
|---|---|---|
| **fit-based pitch suppression** ("don't pitch X, wrong industry") | `qb`, `llm_high_conf` only | high stakes -> **never suppress an opportunity on `llm_low_conf` alone** |
| **fit-based positive selection / framing** | `qb`, `llm_high_conf`; `llm_low_conf` as a soft hint only | a low-conf guess can *flavour* copy, never gate inclusion |
| **industry rollups / dashboards** (`customer_industry_segments`, `industry_benchmarks` views) | all tiers, **labelled** | show coverage with a confidence breakdown; do not present low-conf as fact |
| **analytics aggregates** (per-industry buying mix) | all tiers, weight/segment by tier | report the tier mix so a low-conf-heavy industry is visibly less certain |

The standing rule: **suppression / exclusion decisions require `qb` or `llm_high_conf`; `llm_low_conf` may inform but never gates.**

---

## Q4 - Consumer migration (the switch must be COMPLETE, not partial)

Every site that reads `qb_capability_tag` / `capability_tags` for **capability meaning** must switch to `true_capability`. Enumerated from a full grep; this is the checklist:

**MUST switch (capability used to decide what a customer does):**
1. `recommendation_engine._caps_for_op` (`recommendation_engine.py:32`) - the cards/market-basket engine core. The single highest-impact switch.
2. `recommendation_engine.recompute_affinities` / `get_recommendations` product-profile read (`recommendation_engine.py:258, 290, 696-721`) - reads `qb_capability_tag` for the product profile and affinities.
3. `customer_analytics_service.get_capability_rhythm` (`customer_analytics_service.py:233, 268`) - reads `capability_tags` + `qb_capability_tag`; powers the `/customers/{id}/capability-rhythm` endpoint (`customers.py:874`).
4. `strategic_context_builder.py:709-721` - reads `qb_capability_tag` to build AI strategic context.
5. The outreach **cards/deck engine** (`scripts/db/_outreach_cards_50.py`) - replace the `CAP_LATERAL` reclassification with a plain read of `true_capability` (the script becomes a consumer of the layer, not its own private copy of the definition).
6. The **big-accounts saturation view** (`scripts/db/_big_accounts.py`) - same EFF expression -> read `true_capability`.
7. Any future **AM-coaching** capability metric - must read `true_capability` from day one (it is greenfield; do not let it copy the polluted read).

**Embedding / display consumers - `TRADEOFF`, switch but lower urgency:**
8. `vector_service.py:583-589` - bundles `qb_capability_tag` into operation embedding text.
9. `hybrid_retriever.py:384` - passes `capability_tags` in result metadata.
10. `langchain_tools.py:434-439` - formats `capability_tags` for LLM tool output.
These do not *decide* meaning, they feed text into embeddings / AI context. Switching them makes embeddings reflect clean caps, but **changing the embedded text requires re-embedding the affected operations** (real compute + cost). Recommend: switch them in a second wave, batched with the next planned re-embed, not blocking the meaning-consumers.

**Do NOT switch (not per-op capability meaning):**
- `intelligence_config.py` `capability_tags` endpoints - that is the 8-tag *display config* (the controlled vocabulary), not per-operation reads.
- `capability_classifier.py` / `quickbase_sync.py` enrich path - these WRITE `capability_tags`; they remain the upstream the taxonomy reads from. Unchanged.

**Transitional safety:** ship `true_capability` populated and verified (§10.12) FIRST; then switch consumers; during the window, a consumer reads `COALESCE(true_capability, qb_capability_tag)` so a not-yet-recomputed row degrades to the old behaviour rather than NULL. Remove the COALESCE once backfill + verification are green.

---

## Q5 - Provenance / ownership (both layers)
- **QB source fields stay read-only:** `qb_capability_tag`, `qb_customers.industry` are written ONLY by the QB sync, never by a correction layer. `capability_tags` stays owned by the classifier.
- **Platform-owned columns** (`true_capability*`, `industry_enriched*`) and **definition tables** (`capability_taxonomy`, `industry_vocabulary`, `industry_adjacency`) are platform-owned: documented via `COMMENT ON COLUMN ... IS 'platform-owned correction layer; not from QB'`, and recorded in `DATABASE_DESIGN.md`. A QB re-sync overwrites `qb_capability_tag`/`industry` (expected) and the post-sync recompute re-derives the platform columns from them - so a sync never clobbers a correction, and a correction never hides what QB actually said.

---

## Q3 - Migration + backfill plan (proposed; NOT applied)
Next free migration number is **123** (highest existing is 122). Proposed set, applied via the existing `scripts/db/_run_NNN_via_rest.py` -> `exec_sql` RPC -> `NOTIFY pgrst` flow:

1. `123_capability_true_layer.sql` - `ALTER TABLE qb_operations ADD COLUMN IF NOT EXISTS true_capability TEXT, true_capability_source TEXT, true_capability_at TIMESTAMPTZ`; `CREATE TABLE IF NOT EXISTS capability_taxonomy (...)`; GIN/btree index on `true_capability`; `COMMENT` markers.
2. `124_capability_taxonomy_seed.sql` - seed the 4 Correction-3 rules (data, not logic).
3. `125_industry_enrichment_layer.sql` - `ALTER TABLE qb_customers ADD COLUMN industry_enriched TEXT, industry_source TEXT, industry_enriched_at TIMESTAMPTZ`; `CREATE TABLE industry_vocabulary (...)`, `industry_adjacency (...)`; `COMMENT` markers.
4. `126_industry_vocab_seed.sql` - seed the 13 (or collapsed) buckets + adjacency pairs.
5. RPCs (extend the existing pattern): `batch_update_true_capability` (chunk 100) and `batch_update_industry_enriched` (chunk 100), mirroring `batch_update_qb_capabilities` / `batch_update_classifications`.

**Backfill order:** seed taxonomy -> run capability full recompute over all `qb_operations` -> **§10.12 verify (242 / 183 / clean rules)** -> only then switch capability consumers. Seed vocab -> human-review + write the **116 active** -> (gate) revise vocab to clear ~85% defensible-match -> full-base LLM write (tiered) -> switch industry consumers.

**Cost note (Layer 2):** capability recompute is free (SQL). Industry: per 12.9-enrich, full base ~$0.30-0.40 of `gpt-4o-mini`; the 116-active pass is well under $1. Cost is not the constraint; the defensible-match gate is.

---

## Decisions to settle in review (not silently picked)
1. **Q1 capability definition shape** - keyword-rules table (recommended) vs exact op-name map. Affects maintenance and new-op-name behaviour.
2. **Q1 storage** - dedicated `capability_taxonomy` table (recommended, keeps recompute a SQL join) vs reuse `client_taxonomy_config` jsonb.
3. **Global vs per-client taxonomy/vocab** - recommended nullable `client_id` (global default + per-client override).
4. **Layer 2 enrich on sync = enqueue + background worker** (recommended) vs inline LLM in the sync path.
5. **Industry vocab collapse before full write** - the 13-bucket vocab fails the 85% gate today; recommended to collapse overlapping buckets (data edit) before the full-base write, while the 116-active human-reviewed set ships for Monday regardless.
6. **Embedding consumers (vector/retriever/langchain) switch timing** - recommended second wave batched with a planned re-embed, because switching forces re-embedding cost.
