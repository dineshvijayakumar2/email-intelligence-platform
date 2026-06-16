# Per-AM Outreach Doc — Generation Spec (Monday deliverable)

> Generate per-AM docs from the regenerated deck (`outreach_cards_50.json`, post-13.7 clean
> capabilities + 13.3 industry filter) and the filter-aligned big-accounts top-100.
> START WITH NIC AND LINDA (Nic 18 cards, Linda 16). Review those two before generating the rest.
> On `main`. Reuse `_gen_am_docs.py` structure. Nothing sent.

## Why the framing matters (read before generating)
The deck is HARD-COVER-HEAVY (39/50). This is REAL, not the old cello artifact — post-13.7,
Hard Cover is the rarest capability (8.4%) so it's the most common genuine gap, and it fits the
high-revenue book/finishing industries. BUT a rep glancing at 39 hardcover cards will pattern-match
to last time's cello complaint and risk dismissing the deck. The opening note (below) exists to
pre-empt that. Without it, the deck reads as "broken again." With it, it reads as "the finding."

## Doc structure — two sections per AM

### Opening note (verbatim, top of every AM doc)
> **What changed since last time.** The previous cards over-counted some categories because of how
> product tags were stored — cello/laminate finishing was being counted as "embellishment," which
> inflated that category. That's now fixed at the platform level: every pitch below reads from
> corrected data.
>
> **You'll see a lot of Hard Cover / casebound suggestions — that's the finding, not a glitch.**
> Once the tagging was clean, hard cover turned out to be the single biggest *genuine* gap across
> your book-and-finishing customers: they already buy embellishment, soft cover and finishing, but
> haven't been sold casebound work, and customers with that exact profile take it up at 3-4x the
> base rate. Each card tells you whether the pitch **fits the customer's industry** (e.g. a property
> or trade-print client genuinely does books) or is **purely statistical** (worth a look, no industry
> signal either way). Where a strong-looking pitch *didn't* fit the customer's business, it's shown
> as **"Not pitched"** with the reason — so you can see what the system set aside and why.

### Section 1 — Opportunities (the cards)
Per card, in plain language (no jargon):
- **Customer** + industry + 12-mo revenue + who to contact (value contact, with the "pitch to value
  not volume" note where `contrast_note` flags it).
- **Pitch:** the capability.
- **Pattern** (from `gap_rationale`): "X% of customers who buy {their basket item} also buy {pitch}
  — Nx more likely than average. They buy {item} but have 0 {pitch} jobs." Use the real confidence/
  lift/base-rate numbers; never round up (honesty_guards).
- **Fits their business** (from `industry_fit.fit`): either the positive fit line OR, when neutral,
  state plainly "No strong industry signal — pitched on the statistics." DO NOT dress up a neutral
  as a fit.
- **Timing** (from `timing`): the cadence line (in-cadence / due-soon / overdue).
- **Not pitched** (from `industry_fit.not_pitched`, when present): "{suppressed pitch} suggested by
  the numbers, but {industry} firms rarely buy it ({rate}%) — set aside." Only 1 card in the current
  deck has this (Performance Frontiers); show it prominently where it appears — it's the clearest
  demonstration of the industry logic.
- **Feedback column:** Makes sense / Already buys this / Wrong — for rep validation.

### Section 2 — Your major accounts (top 100, this AM's slice)
- Each account: name, industry, 12-mo revenue, saturation status.
- **Saturated / retention** accounts framed ACTIVELY, never as a blank pitch:
  "$Xk, buys your full range, no real gap — retention relationship, protect it."
- **Has-real-gap** accounts (industry-filter-aligned — the 31 that survived, NOT the dropped MED-EL):
  surface as a mini opportunity ("big account, real gap in {pitch} that fits {industry}").
- This section answers Linda's "are the big ones maxed out?" in context: mostly yes, here's the
  exceptions with genuine room.
- **Surface the suppression as a positive where it occurred:** e.g. for Ehab's MED-EL, a line like
  "We did NOT flag Hard Cover for MED-EL — Healthcare doesn't buy casebound — even though the raw
  numbers suggested it." This is the single best demonstration that the system understands who the
  customer is. (MED-EL is Ehab's, not Nic/Linda's — include in Ehab's doc; for Nic/Linda use whatever
  suppression/shift occurred in their slice, e.g. Camilla's Design->Wide Format shift if Linda's.)

## Tone / language rules
- Plain words. No "leverage / fold / surface / grain". "Add" not "fold in".
- No em-dashes in the rep-facing text.
- Honest about neutral fits — do not inflate a statistical pitch into an industry fit.
- The numbers on every card must trace to the deck JSON (Pattern<-gap_rationale, Fits<-industry_fit,
  Timing<-timing). A card is only as honest as its feeds.

## Sequence
1. Generate NIC and LINDA docs only.
2. Dinesh reviews both — does the opening note land? do the cards read clean? is the HC concentration
   defensible on the page?
3. If yes -> generate Ehab/Kenneth (Mary/Peter have 0 cards; handle their big-accounts slice only or
   note no opportunities).
4. Nothing sent until Dinesh's final review.
