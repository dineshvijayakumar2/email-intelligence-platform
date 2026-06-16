# Outreach-50: Jeff verification findings (2026-06-12)

Read-only. Data: `scripts/db/jeff_verify.json`, recomputed from the same prelim-opportunity
logic that produced the 50 cards.

## Q1. Job-level vs customer-level ownership

Customer-level assignment (mode of `am_customer`) effectively equals job-level ownership.

- **48 of 50** customers have a **single AM across all their jobs** (clean, unambiguous).
- **2 of 50** are split across two AMs, and in both the mode picked the clear majority owner:
  - Bear Meets Eagle on Fire: Nic 11 jobs / Linda 6 (Nic 65%)
  - Beckett's Bar and Dining: Nic 19 jobs / Kalani 2 (Nic 90%)

No customer's jobs are spread evenly across AMs, so "mode" never made a coin-flip call.

## Q2. Kenneth and Peter: real books, but the accounts did not rank

| | Kenneth Beck-Pedersen | Peter Musarra |
|---|---|---|
| Companies owned (plurality `am_customer`) | **171** (appears on 189 incl. minority) | **81** (appears on 99) |
| In the scored opportunity set (>=2-job basket) | 111 | 57 |
| Of those, with a genuine cross-sell gap | **89** | **49** |
| In the top 50 | **0** (confirmed) | **0** (confirmed) |
| Has a mailbox | **Yes** (28,756 emails) | **No** |
| Best real account | Sullivan Strumpf Fine Art ($161,602, due-soon) | Shane Gibson Studio ($4,369, in-cadence) |
| Where it would rank | **~#48 of 2,174** (just outside the 50; near-miss, inside the 120 pool) | **~#98 of 2,174** (inside the pool but well below the top-50 line) |

Reading it for Jeff:

- **Kenneth narrowly missed.** His book is real (171 accounts, 89 with genuine gaps) and he
  has a mailbox, so his accounts are actionable. His single strongest, Sullivan Strumpf, would
  rank about #48 - right at the top-50 boundary, edged out on the final email-recency re-rank.
  Caveat: that rank is revenue-driven; the pitch itself is a modest 31%-confidence Hard Cover
  Books cross-sell. He is the obvious next tranche to extend the set into.
- **Peter is moderately outside.** He also has gaps (49 of 57), but his best account ranks
  ~#98 and his accounts have **no mailbox**, so they cannot be email-grounded - a structural
  reason they would not surface in this email-grounded ranking even when scored.
- **Data-quality note (why this needed a second look):** Kenneth's top raw score (#12) was the
  generic bucket "Cash Account - Kenneth", not a real prospect; "Carbon8 Fund" (#111) is
  similar. These were excluded. Without that filter, the answer would have read "Kenneth's best
  account is #12" - wrong.

## Q3. Nathan and Daniel accounts: REASSIGNED (applied)

Their QB owner has left, but the email relationship runs through a current mailbox AM, so the
3 accounts were reassigned to that owner and folded into the active AM docs (Nathan and Daniel
docs removed). Each card carries a provenance note ("QB owner X has left; assigned to you as
the email-relationship owner. Confirm before outreach.").

| Card | Account | QB owner (left) | Reassigned to | Evidence |
|---|---|---|---|---|
| #9 | Jet Technologies | Nathan Brown | **Nic** | 33 of 48 emails in Nic's mailbox |
| #25 | Jefferies | Nathan Brown | **Ehab** | 55 of 59 emails in Ehab's mailbox |
| #44 | Forsight | Daniel Hall | **Nic** | 66 of 72 emails in Nic's mailbox |

Resulting per-AM counts: Nic 15, Linda 17, Ehab 16, Mary 2 = 50. No outside-six / unassigned remain.
