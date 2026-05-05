"""
Diagnostic: separate false positives from real sync gaps in unmatched QB references.

Unnests extracted_references JSONB from ai_email_intelligence, validates against
qb_quotes/qb_jobs, and for unmatched refs groups by digit count + occurrence frequency.

High-occurrence short refs (Q1, Q100, Q4458) = false positives from common numbers.
Uniform distribution of 5-6 digit refs = real records not in synced QB data.

Usage:
    python scripts/db/_diagnose_ref_gaps.py
"""
import os, sys, re, io
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

PAGE = 500
QB_QUOTE_MAX = 713145
QB_JOB_MAX = 461400


def fetch_paginated(table: str, select: str, filters=None, label: str = ""):
    """Generic paginated fetch with progress logging."""
    all_rows = []
    offset = 0
    while True:
        query = sb.table(table).select(select)
        if filters:
            for fn in filters:
                query = fn(query)
        resp = query.range(offset, offset + PAGE - 1).execute()
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
        print(f"  [{label}] fetched {len(all_rows)} rows...", flush=True)
    print(f"  [{label}] done: {len(all_rows)} rows total", flush=True)
    return all_rows


def fetch_all_extracted_refs():
    return fetch_paginated(
        "ai_email_intelligence", "extracted_references",
        filters=[
            lambda q: q.eq("processing_status", "completed"),
            lambda q: q.not_.is_("extracted_references", "null"),
        ],
        label="ai_email_intelligence",
    )


def fetch_valid_quotes():
    rows = fetch_paginated("qb_quotes", "quote_no", label="qb_quotes")
    return {r["quote_no"] for r in rows if r.get("quote_no")}


def fetch_valid_jobs():
    rows = fetch_paginated("qb_jobs", "job_no", label="qb_jobs")
    return {r["job_no"] for r in rows if r.get("job_no")}


def normalize_ref(ref_type: str, ref_number: str) -> str | None:
    digits = re.sub(r'[^0-9]', '', str(ref_number))
    if not digits:
        return None
    prefix = "Q" if ref_type == "quote" else "J"
    return f"{prefix}{digits}"


def main():
    print("Fetching extracted references...")
    rows = fetch_all_extracted_refs()
    print(f"  {len(rows)} classified emails with extracted_references")

    # Unnest and normalize all refs
    quote_refs: list[str] = []
    job_refs: list[str] = []

    for row in rows:
        refs_raw = row.get("extracted_references") or []
        for ref in refs_raw:
            ref_type = ref.get("type")
            ref_number = ref.get("number")
            if not ref_type or not ref_number:
                continue
            canonical = normalize_ref(ref_type, ref_number)
            if not canonical:
                continue
            if ref_type == "quote":
                quote_refs.append(canonical)
            else:
                job_refs.append(canonical)

    print(f"  {len(quote_refs)} total quote ref occurrences, {len(job_refs)} total job ref occurrences")
    print(f"  {len(set(quote_refs))} unique quote refs, {len(set(job_refs))} unique job refs")

    # Fetch valid QB records
    print("\nFetching synced QB records...")
    valid_quotes = fetch_valid_quotes()
    valid_jobs = fetch_valid_jobs()
    print(f"  {len(valid_quotes)} synced quotes, {len(valid_jobs)} synced jobs")

    # ── QUOTE ANALYSIS ──
    print("\n" + "=" * 70)
    print("QUOTE REFERENCE ANALYSIS")
    print("=" * 70)

    quote_counts = Counter(quote_refs)
    matched_quotes = {r for r in set(quote_refs) if r in valid_quotes}
    above_range = set()
    in_range_unmatched = set()
    below_min = set()

    for ref in set(quote_refs) - matched_quotes:
        digits = int(re.sub(r'[^0-9]', '', ref))
        if digits > QB_QUOTE_MAX:
            above_range.add(ref)
        elif digits < 5:
            below_min.add(ref)
        else:
            in_range_unmatched.add(ref)

    print(f"\nMatched:           {len(matched_quotes):>6} unique refs ({sum(quote_counts[r] for r in matched_quotes):>6} occurrences)")
    print(f"Above max range:   {len(above_range):>6} unique refs ({sum(quote_counts[r] for r in above_range):>6} occurrences) [hallucinated, >Q{QB_QUOTE_MAX}]")
    print(f"Below minimum:     {len(below_min):>6} unique refs ({sum(quote_counts[r] for r in below_min):>6} occurrences) [Q0-Q4]")
    print(f"In range, no match:{len(in_range_unmatched):>6} unique refs ({sum(quote_counts[r] for r in in_range_unmatched):>6} occurrences) [Q5-Q{QB_QUOTE_MAX}]")

    # Split in-range unmatched by digit count
    by_digit_count: dict[int, list[tuple[str, int]]] = {}
    for ref in in_range_unmatched:
        digits = re.sub(r'[^0-9]', '', ref)
        dc = len(digits)
        by_digit_count.setdefault(dc, []).append((ref, quote_counts[ref]))

    print(f"\n--- In-range unmatched quotes by digit count ---")
    print(f"{'Digits':<8} {'Unique':<8} {'Occurrences':<14} {'Verdict'}")
    print("-" * 55)
    for dc in sorted(by_digit_count.keys()):
        items = by_digit_count[dc]
        total_occ = sum(c for _, c in items)
        if dc <= 3:
            verdict = "LIKELY FALSE POSITIVE (short numbers)"
        elif dc == 4:
            verdict = "MIXED (could be either)"
        else:
            verdict = "LIKELY REAL GAPS (5+ digit QB refs)"
        print(f"{dc:<8} {len(items):<8} {total_occ:<14} {verdict}")

    # Top 30 unmatched by occurrence (the false-positive signal)
    print(f"\n--- Top 30 unmatched quote refs by occurrence ---")
    print(f"{'Ref':<12} {'Occ':<6} {'Digits':<8} {'Signal'}")
    print("-" * 45)
    sorted_unmatched = sorted(
        [(r, quote_counts[r]) for r in in_range_unmatched],
        key=lambda x: -x[1]
    )
    for ref, occ in sorted_unmatched[:30]:
        digits = re.sub(r'[^0-9]', '', ref)
        dc = len(digits)
        signal = "FALSE POS" if dc <= 3 else ("MIXED" if dc == 4 else "REAL GAP")
        print(f"{ref:<12} {occ:<6} {dc:<8} {signal}")

    # Sample of 5+ digit unmatched (the real gaps)
    long_unmatched = sorted(
        [(r, quote_counts[r]) for r in in_range_unmatched if len(re.sub(r'[^0-9]', '', r)) >= 5],
        key=lambda x: -x[1]
    )
    if long_unmatched:
        print(f"\n--- Top 20 likely-real gap quotes (5+ digits, in range) ---")
        print(f"{'Ref':<12} {'Occ':<6} {'Digits'}")
        print("-" * 30)
        for ref, occ in long_unmatched[:20]:
            digits = re.sub(r'[^0-9]', '', ref)
            print(f"{ref:<12} {occ:<6} {len(digits)}")

    # ── JOB ANALYSIS ──
    print("\n" + "=" * 70)
    print("JOB REFERENCE ANALYSIS")
    print("=" * 70)

    job_counts = Counter(job_refs)
    matched_jobs = {r for r in set(job_refs) if r in valid_jobs}
    above_range_j = set()
    in_range_unmatched_j = set()
    below_min_j = set()

    for ref in set(job_refs) - matched_jobs:
        digits = int(re.sub(r'[^0-9]', '', ref))
        if digits > QB_JOB_MAX:
            above_range_j.add(ref)
        elif digits < 32:
            below_min_j.add(ref)
        else:
            in_range_unmatched_j.add(ref)

    print(f"\nMatched:           {len(matched_jobs):>6} unique refs ({sum(job_counts[r] for r in matched_jobs):>6} occurrences)")
    print(f"Above max range:   {len(above_range_j):>6} unique refs ({sum(job_counts[r] for r in above_range_j):>6} occurrences) [hallucinated, >J{QB_JOB_MAX}]")
    print(f"Below minimum:     {len(below_min_j):>6} unique refs ({sum(job_counts[r] for r in below_min_j):>6} occurrences) [J0-J31]")
    print(f"In range, no match:{len(in_range_unmatched_j):>6} unique refs ({sum(job_counts[r] for r in in_range_unmatched_j):>6} occurrences) [J32-J{QB_JOB_MAX}]")

    by_digit_count_j: dict[int, list[tuple[str, int]]] = {}
    for ref in in_range_unmatched_j:
        digits = re.sub(r'[^0-9]', '', ref)
        dc = len(digits)
        by_digit_count_j.setdefault(dc, []).append((ref, job_counts[ref]))

    print(f"\n--- In-range unmatched jobs by digit count ---")
    print(f"{'Digits':<8} {'Unique':<8} {'Occurrences':<14} {'Verdict'}")
    print("-" * 55)
    for dc in sorted(by_digit_count_j.keys()):
        items = by_digit_count_j[dc]
        total_occ = sum(c for _, c in items)
        if dc <= 3:
            verdict = "LIKELY FALSE POSITIVE"
        elif dc == 4:
            verdict = "MIXED"
        else:
            verdict = "LIKELY REAL GAPS"
        print(f"{dc:<8} {len(items):<8} {total_occ:<14} {verdict}")

    print(f"\n--- Top 20 unmatched job refs by occurrence ---")
    print(f"{'Ref':<12} {'Occ':<6} {'Digits':<8} {'Signal'}")
    print("-" * 45)
    sorted_unmatched_j = sorted(
        [(r, job_counts[r]) for r in in_range_unmatched_j],
        key=lambda x: -x[1]
    )
    for ref, occ in sorted_unmatched_j[:20]:
        digits = re.sub(r'[^0-9]', '', ref)
        dc = len(digits)
        signal = "FALSE POS" if dc <= 3 else ("MIXED" if dc == 4 else "REAL GAP")
        print(f"{ref:<12} {occ:<6} {dc:<8} {signal}")

    # ── SUMMARY ──
    total_extracted = len(quote_refs) + len(job_refs)
    total_matched_occ = sum(quote_counts[r] for r in matched_quotes) + sum(job_counts[r] for r in matched_jobs)
    total_false_pos_occ = (
        sum(quote_counts[r] for r in above_range) +
        sum(quote_counts[r] for r in below_min) +
        sum(job_counts[r] for r in above_range_j) +
        sum(job_counts[r] for r in below_min_j) +
        sum(quote_counts[r] for r in in_range_unmatched if len(re.sub(r'[^0-9]', '', r)) <= 3) +
        sum(job_counts[r] for r in in_range_unmatched_j if len(re.sub(r'[^0-9]', '', r)) <= 3)
    )
    total_real_gap_occ = total_extracted - total_matched_occ - total_false_pos_occ

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total extracted ref occurrences: {total_extracted}")
    print(f"  Matched:         {total_matched_occ:>6} ({100*total_matched_occ/total_extracted:.1f}%)")
    print(f"  False positives: {total_false_pos_occ:>6} ({100*total_false_pos_occ/total_extracted:.1f}%) [short numbers + above range]")
    print(f"  Real gaps:       {total_real_gap_occ:>6} ({100*total_real_gap_occ/total_extracted:.1f}%) [4+ digit, in range, no match]")
    print(f"\nActionable:")
    print(f"  - Tighten prompt: require min 4 digits for quotes, 5 for jobs -> eliminates {total_false_pos_occ} false positives")
    print(f"  - Real gaps ({total_real_gap_occ}) need QB sync expansion or acceptance")


if __name__ == "__main__":
    main()
