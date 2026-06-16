# Industry-Fit Filter (Task 13.3) — Design Spec

> Purpose: make cross-sell recommendations business-sensible by checking each
> statistically-suggested pitch against the customer's industry buying-profile.
> This is the piece that answers Jeff's redirect ("the recs need to know who the
> customer is" / a furniture company won't print casebound books).
>
> FILTER, not generative: it suppresses/demotes implausible pitches and surfaces
> the reason. It does NOT invent pitches the statistics didn't find.
>
> Reads CORRECTED capabilities (post-13.7). A card is only as honest as its feeds.

## Core data: per-industry buying profiles (from industry_data_assessment.json, check 4)

% of each industry that buys each capability. Source = 12-mo order history,
the same assessment validated at ~24/25 reliability.

| Industry | FlatSheet | SoftCover | HardCover | WideFmt | Embel | Specialty | Design | Display |
|---|---|---|---|---|---|---|---|---|
| Property & Real Estate | 98 | 51 | **32** | 55 | **25** | 98 | 77 | 4 |
| Trade Printers | 98 | 64 | **28** | 46 | 16 | 98 | 95 | 1 |
| Industrial & Mfg | 89 | 32 | 13 | 50 | 3 | 95 | 76 | 5 |
| Corporate & Professional | 95 | 28 | 13 | 38 | 8 | 97 | 82 | 3 |
| Government & NFP | 96 | 56 | 9 | 42 | 4 | 100 | 76 | 4 |
| Healthcare & Medical | 96 | 31 | 8 | 31 | 8 | 96 | 92 | 0 |

(Retail/Hospitality/Luxury/Education/Creative/Advertising: from the verdict —
Property/Luxury high on hardcover+embellishment; Retail/Hospitality high on
wide-format+display; Education/Govt high on soft-cover, low embellishment.
Use each industry's own row from the assessment when wiring; fill any missing
industries by reading their profile block in industry_data_assessment.json.)

## Key insight: only a FEW capabilities discriminate

Universal (every industry 76-100%): **Flat Sheets, Specialty Finishing, Design
Services.** These carry NO industry signal — NEVER filter on them.

Discriminating (wide industry spread): **Hard Cover (8-32%), Embellishment
(3-25%), Wide Format (31-55%).** The filter acts ONLY on these.

The natural break is clean: industries that buy Hard Cover sit at 28-32%; those
that don't sit at 8-13%. Same for Embellishment (25% vs 3-8%). The thresholds
below fall in the real gap, they are not tuned cutoffs.

## The filter logic

For each statistically-suggested pitch (capability C, customer in industry I):

1. **GUARDRAIL FIRST — never contradict observed behavior.** If the customer
   ALREADY BUYS C (in their own order history), the pitch is not an
   industry-fit question at all — keep it, no suppression, no industry caveat.
   (Bloomberg is Corporate AND buys Hard Cover; that's a real buyer, not a
   furniture/casebound error. The filter shapes NEW pitches only.)

2. **If C is a universal capability** (Flat Sheets / Specialty / Design):
   keep, make no industry-fit claim. (No signal to act on.)

3. **If C is discriminating** (Hard Cover / Embellishment / Wide Format), look
   up I's buying rate for C:
   - **rate >= 20% → FITS.** Keep, surface positively:
     "Fits their business: {I} firms regularly buy {C}."
   - **rate < 10% → SUPPRESS** (the furniture/casebound fix). Demote below any
     fitting candidate; surface the suppressed pitch + reason as a first-class
     output (the "Not pitched" line):
     "{C} suggested by the numbers, but {I} firms rarely buy it — set aside."
   - **10-20% → NEUTRAL.** Keep the statistical pitch, no industry claim.

4. **Re-rank** within the customer's candidate pitches: a FITS pitch outranks a
   NEUTRAL outranks a SUPPRESSED. This is what breaks the 32-Hard-Cover deck
   monotony (13.1-open) FOR A REASON — a Retail customer's Hard Cover pitch is
   demoted below their Wide Format pitch because Wide Format fits Retail and
   Hard Cover doesn't, NOT by an arbitrary pitch-type cap.

## Output contract (per card)

The filter must RETAIN and surface the suppressed candidate, not silently drop
it — the visible suppression reason is what demonstrates the breakthrough to
Jeff. Each card outputs:
  - kept_pitch + pattern_reason (clean stats, post-13.7)
  - fit_reason (industry buying-profile) OR neutral (no claim)
  - suppressed_pitch + suppression_reason  (nullable — only when one was demoted)

## What this is NOT
- NOT generative — never proposes a capability the statistics didn't surface.
- NOT a hard pitch-type cap — diversification is a side effect of fit, not a quota.
- NOT applied to universal capabilities — those carry no industry signal.
- NEVER overrides observed behavior — a customer who buys C is a buyer of C.

## Industry label source
Reads qb_customers.industry where present (the trusted 1,912), else the
13.2-enriched label (industry_enriched, high-conf only). Low-conf / no-label
customers: SKIP the filter (no industry claim either way) rather than guess —
a wrong industry suppression is worse than none (§10.13).

## Merge-discipline (carried from the enrichment diagnostic)
If/when industry buckets are collapsed (13.4), only collapse buckets that ALSO
buy similarly (check-4). Confused-but-buy-differently = keep separate; the
filter needs the distinction. E.g. Retail vs Creative may confuse the
classifier but if they buy differently they must stay separate here.
