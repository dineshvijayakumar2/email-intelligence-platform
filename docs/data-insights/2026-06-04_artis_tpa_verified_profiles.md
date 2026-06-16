# Verified Customer Profiles — Artis & The Property Agency

**Date:** 2026-06-04
**Analyst:** data-insights (first entry in this series)
**Scope:** Read-only. QB tables are ground truth for quotes/jobs/revenue/won-lost; email
data used as engagement/correlation signal only.
**Methodology:** `docs/DATA_ANALYSIS_GUIDELINES.md` (§0 frame, §0.2 alternative linkage,
matched-window YoY, revision-collapse, mailbox attribution).
**Sources:** `scripts/db/_profile_two_customers.py`, `_email_features_two_customers.py`,
`_quote_email_correlation.py` (all throwaway, re-runnable).

**Cutoff:** §1 quote/won/revenue figures capped at **2026-05-15** (Ehab's mailbox unsynced
~2 weeks; cutoff applied for consistency). Correlation uses full QB history windowed to the
email-covered period.

---

## Artis (C14306)

*Anchored on QB customer key 19212. AM = Ehab Kamel — mailbox unsynced ~2wk, so email
recency is understated.*

### 1. Quotes (distinct quote_no)
- 4,981 distinct quotes, 1,018 won → **20.4% strike rate**
- Total quoted $12.94M; won value **$1.56M**; **avg won deal $1,533** (high-volume, low-ticket)

### 2. Revenue trajectory (matched windows — the YoY fix)
- Matched Jan–mid-May: **2025 $180.3k → 2026 $148.3k = −17.8%**
- Trailing-12M $412.7k vs prior-12M $439.4k = **−6.1%** (softer decline than matched-window)
- Full-year history: 2021 $428k → 2022 $359k → 2023 $324k → 2024 $373k →
  **2025 $445k (+19.2%, a record)**. 2026 YTD is measured against a peak, not a clean decline.

### 3. Orders / jobs
- 1,737 jobs, **$2.24M** revenue, 2019-09-03 → 2026-05-15
- **Median reorder gap 2 days** — effectively a continuous-flow account; last order on the
  cutoff date (active)

### 4. Per-contact conversion (sharp-variance pattern — confirmed)
| Contact | quotes | won | strike | won value |
|---|--:|--:|--:|--:|
| graphics@ | 744 | 594 | **79.8%** | **$838k** |
| rowan@ | 875 | 124 | 14.2% | $212k |
| martin@ | 471 | 130 | 27.6% | $185k |
| accounts.pay@ | 2,056 | 84 | **4.1%** | $168k |
| mark@ | 767 | 69 | 9.0% | $139k |

- **53.7% of all won value flows through one contact (graphics@)** at an 80% strike rate.
- `accounts.pay@` is a **volume-sink**: CC'd on 2,056 quotes but sent only 2 emails —
  citation ≠ engagement.

### Email overlay
- 6,107 emails (2,851 in / 3,256 out), 2,042 threads
- **93% in the AM's own mailbox** (clean channel; 4% hello@, 3% other)
- graphics@ is also email-central (1,016 sent / 1,443 received / 686 threads) — the value
  contact *is* the communication hub
- AI intent: general_enquiry 2,647, job_approval 1,376, quote_request 1,174; sentiment
  overwhelmingly neutral/positive (797 positive vs 67 negative)

### Correlation (alternative linkage, windowed)
- Contact+temporal ±14d covers **70.8% of won revenue** (vs ~21.5% for Q-citation); ±30d 83.0%
- Thread-window ±14d covers 85.5% of won quotes

---

## The Property Agency (C13039)

*Anchored on QB customer key 17541. AM = Linda D'Arcy.*

### 1. Quotes (distinct quote_no)
- 913 distinct quotes, 322 won → **35.3% strike rate** (notably higher than Artis)
- Total quoted $8.83M; won value **$1.30M**; **avg won deal $4,052** (fewer, larger deals)

### 2. Revenue trajectory (matched windows)
- Matched Jan–mid-May: **2025 $170.0k → 2026 $71.7k = −57.8%**
- Trailing-12M $421.8k vs prior-12M $346.3k = **+21.8%** — trailing view is *up*,
  contradicting the matched-window drop
- Full-year history: 2022 $275k → 2023 $262k → 2024 $238k →
  **2025 $520k (+118.9%, a record blow-out)**. The 2026 "−57.8%" is almost entirely a base
  effect against an exceptional 2025.

### 3. Orders / jobs
- 475 jobs, **$1.66M** revenue, 2020-07-17 → 2026-05-14
- **Median reorder gap 4 days**; last order 1 day before cutoff (active)

### 4. Per-contact conversion (confirmed)
| Contact | quotes | won | strike | won value |
|---|--:|--:|--:|--:|
| ry@ | 433 | 177 | 40.9% | **$685k** |
| ck@ | 168 | 62 | 36.9% | $233k |
| hw@ | 64 | 27 | 42.2% | $108k |
| jk@ | 35 | 9 | 25.7% | $55k |
| mi@ | 42 | 6 | 14.3% | $42k |

- **52.5% of won value flows through ry@.** Strike rates are more even here than Artis
  (no near-zero volume-sink), but value still concentrates in one contact.

### Email overlay
- 2,422 emails (1,267 in / 1,155 out), 648 threads
- **78% own mailbox, 21% "other"** — meaningfully more off-named-channel leakage than Artis
  (mailbox-attribution caveat)
- **ck@ is the comms operator** (516 sent — highest email volume) yet ry@ carries 3× the won
  value: volume contact ≠ value contact. jk@ active very recently (last email 2026-06-03)
- AI intent: general_enquiry 1,149, job_approval 436, quote_request 311, artwork 174

### Correlation (alternative linkage, windowed)
- Contact+temporal ±14d covers **48.8% of won revenue** (vs ~23% Q-citation); ±30d 61.1%
- Thread-window ±14d covers 82.4% of won quotes

---

## Cross-cutting findings

1. **2025 was a record year for both** — Artis +19.2%, TPA +118.9%. 2026 YTD softness is
   measured against a peak; the trailing-12M view (Artis −6.1%, TPA **+21.8%**) is the fairer
   read and partly reverses the alarming matched-window drops. Never report the
   partial-vs-full-year figure alone.
2. **Value concentrates in a single contact** (~52–54% of won value through the top contact
   for both), and that contact is also the email hub. A separate high-volume contact handles
   comms/admin (`accounts.pay@`, `ck@`) but converts little or carries less value — so
   per-contact engagement must be **value-weighted, not volume-weighted**.
3. **Email is the dense signal.** Contact+temporal proximity correlates 2–3× more won revenue
   than exact Q-citation, validating the email-as-feature / QB-as-label frame (§0).

## Caveats
- Artis recency understated (Ehab ~2wk unsynced).
- TPA has 21% off-named-mailbox email (attribution noise).
- §1 quote/won figures use the 2026-05-15 cutoff; correlation uses full QB history windowed
  to the email-covered period (so quote counts differ slightly between sections by design).
