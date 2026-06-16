# Carbon8 — Cross-Sell Opportunities & Outreach Timing

**Date:** 9 June 2026
**Scope:** Top 50 customers by revenue. QuickBase purchase history is ground truth; email interaction supplies the contact, framing, and timing.
**Method:** find products a customer doesn't buy that similar customers reliably do (market basket), identify the value contact and timing from email history, and verify each gap against actual purchase history before listing it.

---

## Headline

The biggest accounts are not the cross-sell opportunity.

Of the top 50 customers by revenue, only 13 have a product gap. The other 37 already buy the full set of capabilities their purchase profile predicts — including all six seven-figure accounts (Artis, HH Global, The Property Agency, Maui Jim, Public House, Urban Purveyor).

The whales are saturated — retention and volume plays, not cross-sell. Cross-sell lives in the mid-market, where the gaps are real. This tells the AMs where not to spend cross-sell effort as much as where to.

---

## How a recommendation is built

Three legs, all required:

1. **Product** — across all 3,458 customers, which capabilities are bought together. A gap is only flagged when a customer's existing purchases strongly predict a capability they're missing (measured by lift and support).
2. **Contact** — who drives won business at the account, from email history.
3. **Timing** — whether they're overdue relative to their own ordering pattern.

Each gap is then checked against actual purchase history to confirm it's real.

---

## Three recommendations

All three: customers who buy Soft Cover Books or Wide Format but have never ordered Hard Cover Books, where similar customers reliably do.

### MED-EL Implant Systems — Hard Cover Books
- ~37% of Soft Cover Books buyers also buy Hard Cover Books (409 customers, lift 1.69). MED-EL buys Soft Cover Books, zero Hard Cover Books.
- Contact: `clare.tamas@medel.com` — $134K won, active in May.
- Framing: execution-led — position as an add-on to current production runs.
- Timing: orders every ~14 days; quiet for 85 (past their p90 gap of ~65) — slowing.

### Meriton — Hard Cover Books
- Same rule. Meriton buys Soft Cover Books, zero Hard Cover Books.
- Contact: `jahleenm@meriton.com.au` — $125K won. Last active ~7 months ago — confirm still the right contact.
- Framing: execution-led.
- Timing: orders every ~5 days; quiet for 31 (past their p90 gap of ~18) — slowing.

### Emily Ziz Style Studio — Hard Cover Books
- ~32% of Wide Format buyers also buy Hard Cover Books (489 customers, lift 1.48). Emily Ziz buys Wide Format, zero Hard Cover Books.
- Contact: `emma@emilyziz.com` — $147K won, 82% strike rate, active in May.
- Framing: execution-led.
- Timing: orders every ~5 days; quiet for 28 (past their p90 gap of ~12) — slowing.

These rest on broad patterns (400+ customers) but modest per-customer conversion — about a third of similar customers add Hard Cover Books, not a majority. Real gaps, lower-probability bets.

---

## Needs verification before use: two Embellishment recommendations

The engine also flagged **Embellishment** for Geoff Letchford Photography and Studio Odea. Both have zero orders in the standalone Embellishment capability — but both apply embellishment finishes (Hot Foil, Spot UV, Deboss) within their other jobs, recorded under a different QuickBase field.

So the question for these two is a business one we can't answer from the data: **is "standalone Embellishment" a distinct service they could buy, or just a finish they already apply inside existing jobs?** If the former, it's a real upsell. If the latter, it isn't a gap at all. Needs a view from someone who knows how Carbon8 sells embellishment before either goes to the customer.

---

## Cut from the list

13 candidates surfaced; the rest were cut, including the two highest-revenue ones — high revenue didn't rescue a missing leg:

| Customer | Revenue | Reason |
|---|---|---|
| Public House Management | $590K | No email grounding; dormant ~2.6 years |
| Freedom | $400K | Only 4 won email threads — too little to ground framing |
| Delivery | $285K | No value contact identified |
| Pacific Blue Health | $234K | No email grounding; dormant ~4.4 years |
| Centuria | $203K | Pattern too thin (62-customer rule) |
| ACS | $175K | No email grounding |
| Sullivan Strumpf | $161K | No email grounding; on track (no timing trigger) |
| Momento Pro | $115K | In liquidation; dormant |

---

## Note on timing figures

Timing here uses each customer's own ordering distribution, not a simple average. The platform screens still use the older average-based calculation, which over-flags high-frequency accounts as overdue. Where a figure here differs from the platform, the figure here is the corrected one; porting the fix into the platform is a small follow-up.

---

## Limits and next step

- Capability is measured at a coarse 8-category level. The Embellishment case shows this taxonomy can diverge from how the business thinks about its work; a product-group-level version (hundreds of items) would be more granular and would resolve that ambiguity.
- The communication framing per customer is currently directional.

**Next:** the most direct lever on AM performance is analysing how each AM writes, thread by thread, and what approach works for which customer type. This engine answers what to offer, to whom, when; that analysis answers how to say it.

---

*Figures from QuickBase order history and email interaction data; no platform-display metrics used. Gaps verified against actual purchase history at the company grain.*
