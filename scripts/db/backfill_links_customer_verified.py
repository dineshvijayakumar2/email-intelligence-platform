"""
Customer-verified backfill + cleanup for thread_qb_links.

CONTEXT
-------
The existing linker (_link_ai_refs_full.py) matched threads to quotes by
Q-number ALONE, with no check that the quote's customer == the thread's
customer. Diagnosis found:
  - New staged links: 858/5816 cross-customer mismatches (800 true, 58 name-norm false)
  - Existing links:   957/1270 RESOLVED links are true cross-customer mismatches (75.4%)

This script applies a CUSTOMER FILTER (with name normalization) in two modes:
  --mode clean-existing : quarantine/remove existing true-mismatch links
  --mode add-new        : write customer-verified NEW links from _staged_links.json

Both modes are DRY-RUN by default. Pass --execute to actually write.

SAFETY
------
  * Dry-run default: prints what WOULD happen, writes nothing.
  * New links tagged source="regex_cust_verified" + batch_tag for reversibility.
  * Cleanup QUARANTINES (sets verified=False + a flag) by default, only hard-
    deletes with --hard-delete. Quarantine is reversible; deletion is not.
  * qb_link_count on thread_status is re-synced after any write (mirrors the
    original linker, so thread-level counts stay correct).
  * NEVER touches links it cannot verify (unresolved thread company) — those
    are left as-is in clean mode, written as unverified in add mode.

Customer-match decision (shared by both modes):
    resolve quote_company_id and thread_company_id
    if both resolved:
        if norm(quote_name) == norm(thread_name)  -> VERIFIED   (keep / write verified)
        else                                       -> MISMATCH   (drop / quarantine)
    else (thread company unresolved or Carbon8):
        -> UNVERIFIED  (keep as-is / write with low confidence; never dropped)
"""

import os, sys, re, io, json, time, argparse
from collections import defaultdict, Counter
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env.production")
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env")
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

CARBON8 = "241d7b99-f099-4557-96e5-212c4af10812"
PAGE = 500
STAGED_PATH = os.path.join(os.path.dirname(__file__), "_staged_links.json")
BATCH_TAG = "cust_verified_" + datetime.now(timezone.utc).strftime("%Y%m%d")

# Carbon8's own company id(s) — threads resolving here are internal, treated UNVERIFIED not MISMATCH.
# (Resolved at runtime by name match to "carbon8".)

# ──────────────────────────────────────────────────────────────────────
# Name normalization (validated against mismatch_refinement.json samples)
# ──────────────────────────────────────────────────────────────────────
_SUFFIXES = re.compile(
    r"\b(pty\s*ltd|pty|ltd|limited|inc|llc|co|group|australia|aust)\b",
    re.IGNORECASE,
)

def norm_name(name: str) -> str:
    if not name:
        return ""
    s = name.lower()
    s = _SUFFIXES.sub("", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return s

def names_match(a: str, b: str) -> bool:
    """Equal OR substring, mirroring the diagnosis rule. Guard against tiny strings."""
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # substring only when the shorter is reasonably long (avoid 'co' matching everything)
    short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
    return len(short) >= 5 and short in long


# ──────────────────────────────────────────────────────────────────────
# Pagination helpers
# ──────────────────────────────────────────────────────────────────────
def fetch_in_chunks(table, select, id_col, id_list, extra_filters=None, chunk_size=50):
    rows = []
    id_list = list(id_list)
    for i in range(0, len(id_list), chunk_size):
        chunk = id_list[i:i + chunk_size]
        q = sb.table(table).select(select).in_(id_col, chunk)
        if extra_filters:
            for fn in extra_filters:
                q = fn(q)
        offset = 0
        while True:
            resp = q.range(offset, offset + PAGE - 1).execute()
            batch = resp.data or []
            rows.extend(batch)
            if len(batch) < PAGE:
                break
            offset += PAGE
    return rows


def strip_version(qno: str) -> str:
    m = re.match(r"^(Q\d+)", qno or "")
    return m.group(1) if m else (qno or "")


# ──────────────────────────────────────────────────────────────────────
# Company resolution (mirrors _validate_staged_links.py method)
# ──────────────────────────────────────────────────────────────────────
def build_quote_company_map(quote_nos):
    """base quote_no -> (company_id, company_name). Direct matched_company_id, then qb_customer_id fallback."""
    quote_rows = fetch_in_chunks(
        "qb_quotes", "quote_no, matched_company_id, qb_customer_id",
        "quote_no", quote_nos,
        extra_filters=[lambda q: q.eq("client_id", CARBON8)],
    )
    q_company_id, q_qb_cust = {}, {}
    for r in quote_rows:
        base = strip_version(r.get("quote_no"))
        if not base:
            continue
        if base not in q_company_id and r.get("matched_company_id"):
            q_company_id[base] = r["matched_company_id"]
        if base not in q_qb_cust and r.get("qb_customer_id"):
            q_qb_cust[base] = r["qb_customer_id"]

    # fallback via qb_customer_id -> customer_companies.id
    if q_qb_cust:
        cc_rows = fetch_in_chunks(
            "customer_companies", "id, qb_customer_id",
            "qb_customer_id", set(q_qb_cust.values()),
            extra_filters=[lambda q: q.eq("client_id", CARBON8)], chunk_size=100,
        )
        qbcid_to_id = {r["qb_customer_id"]: r["id"] for r in cc_rows if r.get("qb_customer_id")}
        for base, cid in q_qb_cust.items():
            if base not in q_company_id and cid in qbcid_to_id:
                q_company_id[base] = qbcid_to_id[cid]
    return q_company_id


def build_thread_company_map(thread_ids):
    """thread -> company_id, by majority vote of emails.customer_company_id."""
    email_meta = fetch_in_chunks(
        "emails", "canonical_thread_id, customer_company_id",
        "canonical_thread_id", thread_ids,
    )
    votes = defaultdict(Counter)
    for em in email_meta:
        tid, cid = em.get("canonical_thread_id"), em.get("customer_company_id")
        if tid and cid:
            votes[tid][cid] += 1
    return {tid: c.most_common(1)[0][0] for tid, c in votes.items() if c}


def load_company_names(company_ids):
    rows = fetch_in_chunks(
        "customer_companies", "id, company_name", "id", set(company_ids), chunk_size=100,
    )
    return {r["id"]: (r.get("company_name") or "") for r in rows}


# ──────────────────────────────────────────────────────────────────────
# Core classifier
# ──────────────────────────────────────────────────────────────────────
def classify(qno, tid, q_company, t_company, names):
    """Return ('verified'|'mismatch'|'unverified', quote_name, thread_name)."""
    base = strip_version(qno)
    qcid = q_company.get(base)
    tcid = t_company.get(tid)
    qname = names.get(qcid, "") if qcid else ""
    tname = names.get(tcid, "") if tcid else ""

    # Thread unresolved -> cannot verify, never drop
    if not tcid:
        return "unverified", qname, tname
    # Internal Carbon8 thread -> treat as unverified, not a real customer mismatch
    if norm_name(tname) == "carbon8":
        return "unverified", qname, tname
    if not qcid:
        return "unverified", qname, tname
    # Both resolved -> name-aware compare
    if names_match(qname, tname):
        return "verified", qname, tname
    return "mismatch", qname, tname


def sync_link_counts(thread_ids, execute):
    if not execute:
        return 0
    synced = 0
    for tid in thread_ids:
        try:
            cnt = sb.table("thread_qb_links").select("id", count="exact").eq(
                "client_id", CARBON8).eq("canonical_thread_id", tid).execute()
            n = cnt.count if cnt.count is not None else len(cnt.data or [])
            sb.table("thread_status").update({"qb_link_count": n}).eq(
                "canonical_thread_id", tid).execute()
            synced += 1
        except Exception:
            pass
    return synced


# ──────────────────────────────────────────────────────────────────────
# MODE: add-new  (write customer-verified new links from staging)
# ──────────────────────────────────────────────────────────────────────
def mode_add_new(execute):
    staged = json.load(open(STAGED_PATH, encoding="utf-8"))
    new_links = [l for l in staged["links"] if l.get("is_new") is True]
    print(f"[add-new] {len(new_links)} new staged links")

    qnos = {strip_version(l["quote_no"]) for l in new_links}
    tids = {l["canonical_thread_id"] for l in new_links}
    q_company = build_quote_company_map(qnos)
    t_company = build_thread_company_map(tids)
    names = load_company_names(set(q_company.values()) | set(t_company.values()))

    buckets = Counter()
    to_write = []
    for l in new_links:
        verdict, qname, tname = classify(l["quote_no"], l["canonical_thread_id"], q_company, t_company, names)
        buckets[verdict] += 1
        if verdict == "mismatch":
            continue  # DROP
        conf = 0.7 if verdict == "verified" else 0.5
        for rid in (l.get("all_record_ids") or [None]):
            to_write.append({
                "client_id": CARBON8,
                "canonical_thread_id": l["canonical_thread_id"],
                "link_type": "quote",
                "qb_record_id": rid,
                "qb_reference": l["quote_no"],
                "confidence": conf,
                "source": "regex_cust_verified",
                "verified": verdict == "verified",
                "batch_tag": BATCH_TAG,
            })

    print(f"  verified={buckets['verified']}  unverified={buckets['unverified']}  mismatch(DROP)={buckets['mismatch']}")
    print(f"  rows to write: {len(to_write)}  (tag={BATCH_TAG})")

    if not execute:
        print("  DRY-RUN — nothing written. Re-run with --execute to write.")
        return
    written = 0
    for i in range(0, len(to_write), 200):
        sb.table("thread_qb_links").upsert(
            to_write[i:i+200],
            on_conflict="client_id,canonical_thread_id,link_type,qb_record_id",
        ).execute()
        written += len(to_write[i:i+200])
    synced = sync_link_counts({r["canonical_thread_id"] for r in to_write}, execute)
    print(f"  WROTE {written} links; synced {synced} thread counts.")


# ──────────────────────────────────────────────────────────────────────
# MODE: clean-existing  (quarantine true-mismatch existing links)
# ──────────────────────────────────────────────────────────────────────
def mode_clean_existing(execute, hard_delete):
    existing = fetch_in_chunks  # noqa - keep name; fetch below
    rows, offset = [], 0
    while True:
        resp = sb.table("thread_qb_links").select(
            "id, canonical_thread_id, qb_reference, link_type, source"
        ).eq("client_id", CARBON8).eq("link_type", "quote").range(offset, offset+PAGE-1).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE:
            break
        offset += PAGE
    print(f"[clean-existing] {len(rows)} existing quote links")

    qnos = {strip_version(r["qb_reference"]) for r in rows if r.get("qb_reference")}
    tids = {r["canonical_thread_id"] for r in rows}
    q_company = build_quote_company_map(qnos)
    t_company = build_thread_company_map(tids)
    names = load_company_names(set(q_company.values()) | set(t_company.values()))

    buckets = Counter()
    targets = []
    for r in rows:
        if not r.get("qb_reference"):
            continue
        verdict, qn, tn = classify(r["qb_reference"], r["canonical_thread_id"], q_company, t_company, names)
        buckets[verdict] += 1
        if verdict == "mismatch":
            targets.append(r["id"])

    print(f"  verified(keep)={buckets['verified']}  unverified(keep)={buckets['unverified']}  mismatch(TARGET)={buckets['mismatch']}")
    action = "HARD-DELETE" if hard_delete else "QUARANTINE (verified=False, contaminated flag)"
    print(f"  action on {len(targets)} mismatch links: {action}")

    if not execute:
        print("  DRY-RUN — nothing changed. Re-run with --execute (+ --hard-delete to delete).")
        return
    affected_threads = {r["canonical_thread_id"] for r in rows if r["id"] in set(targets)}
    for i in range(0, len(targets), 200):
        chunk = targets[i:i+200]
        if hard_delete:
            sb.table("thread_qb_links").delete().in_("id", chunk).execute()
        else:
            sb.table("thread_qb_links").update(
                {"verified": False, "source": "contaminated_quarantine"}
            ).in_("id", chunk).execute()
    synced = sync_link_counts(affected_threads, execute)
    print(f"  {action} applied to {len(targets)} links; synced {synced} thread counts.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["add-new", "clean-existing"], required=True)
    ap.add_argument("--execute", action="store_true", help="actually write (default: dry-run)")
    ap.add_argument("--hard-delete", action="store_true", help="clean-existing: delete instead of quarantine")
    args = ap.parse_args()

    print(f"{'='*70}\nMODE={args.mode}  EXECUTE={args.execute}  HARD_DELETE={args.hard_delete}\n{'='*70}")
    if args.mode == "add-new":
        mode_add_new(args.execute)
    else:
        mode_clean_existing(args.execute, args.hard_delete)


if __name__ == "__main__":
    main()
