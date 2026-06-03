"""Merge duplicate customer_companies (same normalized name) into one canonical row.

Root cause: an earlier dedup created clean spaced-name records, matched them to QB,
and moved customer_contacts to them, but left the old squished-name artifact records
behind still holding stale stored counts + email_contact_links. Result: list/detail
show a stale contact_count while the drilldown (live) finds none.

This consolidates each duplicate group:
  - pick a CANONICAL (most live contacts; tie-break on domain / qb match / emails)
  - REPOINT every SET-NULL reference (emails, email_contact_links, qb_*, thread_status,
    customer_contacts, ...) from artifact -> canonical
  - resolve qb_customers unique-match collisions by NULLing the artifact's match
  - let CASCADE-derived cache/staging rows drop with the artifact
  - DELETE the artifact, then recompute the canonical's stored aggregates
  - write a rollback manifest

Dry-run by default. Pass --execute to apply. Per-group transaction; --limit N to cap.

Usage:
  backend/venv/Scripts/python.exe scripts/db/merge_duplicate_companies.py            # dry-run
  backend/venv/Scripts/python.exe scripts/db/merge_duplicate_companies.py --execute
"""
import os
import re
import sys
import json
import datetime
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

EXECUTE = "--execute" in sys.argv
LIMIT = None
for a in sys.argv:
    if a.startswith("--limit="):
        LIMIT = int(a.split("=", 1)[1])

env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env.production")
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env")
load_dotenv(env_path)

CLIENT_ID = "241d7b99-f099-4557-96e5-212c4af10812"
ROLLBACK_PATH = os.path.join(os.path.dirname(__file__), "_merge_rollback.json")
PLAN_PATH = os.path.join(os.path.dirname(__file__), "_merge_plan.json")

# SET NULL refs -> repoint artifact -> canonical to preserve association.
# customer_contacts handled specially (unique on company_id+email_address).
REPOINT = [
    ("emails", "customer_company_id"),
    ("email_contact_links", "company_id"),
    ("email_response_metrics", "responder_company_id"),
    ("qb_jobs", "matched_company_id"),
    ("qb_operations", "matched_company_id"),
    ("qb_quotes", "matched_company_id"),
    ("qb_sales_line_items", "matched_company_id"),
    ("thread_status", "customer_company_id"),
    ("thread_status", "primary_company_id"),
    ("unified_email_rules", "matched_company_id"),
]
# CASCADE-backed derived/cache/staging -> let drop with the artifact (regenerable).
CASCADE_DROP = [
    ("ai_relationship_summaries", "company_id"),
    ("customer_intelligence_cache", "company_id"),
    ("customer_recommendations", "company_id"),
    ("customer_recognition_rules", "customer_company_id"),
    ("relationship_context_cache", "company_id"),
    ("qb_match_candidates", "sb_company_id"),
]
METHOD_RANK = {  # higher = more trustworthy canonical signal
    "email_verified_link": 5, "email_lookup": 4, "exact_name": 3,
    "domain_root": 2, "fuzzy": 1, "manual": 1, None: 0,
}


def norm(n):
    return re.sub(r"[^a-z0-9]", "", (n or "").lower())


def name_quality(name):
    """Prefer human-readable spaced/punctuated names ('Q Report') over squished
    artifacts ('Qreport'). Counts word separators."""
    return sum(1 for ch in (name or "") if ch in " .&-/'")


def best_display_name(records):
    """Nicest display name in the group: most separators, then longest, with
    runs of whitespace collapsed. Used to rename the survivor so it keeps a
    readable name even when the data-holding row was the squished artifact."""
    best = max(records, key=lambda r: (name_quality(r.get("company_name")),
                                       len(r.get("company_name") or "")))
    return re.sub(r"\s+", " ", (best.get("company_name") or "").strip())


def pick_canonical(records, live):
    """Pick the row that SURVIVES. Ranked by data-integrity signals that live on
    the company row itself (live contacts, domain, qb match + its revenue), since
    those columns are not recomputed on merge. Name readability is only a low
    tiebreak — the survivor is separately renamed to the group's nicest name."""
    def key(r):
        return (
            live.get(r["id"], 0),
            1 if (r.get("email_domains") or []) else 0,
            1 if r.get("qb_customer_id") else 0,
            METHOD_RANK.get(r.get("qb_match_method"), 0),
            float(r.get("qb_total_revenue") or 0),
            name_quality(r.get("company_name")),
            r.get("total_emails") or 0,
        )
    return max(records, key=key)


def main():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Load companies + live contact counts
    cur.execute(
        "SELECT id, company_name, email_domains, total_emails, contact_count, "
        "qb_customer_id, qb_match_method, qb_total_revenue "
        "FROM customer_companies WHERE client_id = %s", (CLIENT_ID,))
    comps = cur.fetchall()
    cur.execute(
        "SELECT customer_company_id, COUNT(*) c, "
        "COUNT(*) FILTER (WHERE is_decision_maker) dm "
        "FROM customer_contacts WHERE client_id = %s "
        "GROUP BY customer_company_id", (CLIENT_ID,))
    live, live_dm = {}, {}
    for r in cur.fetchall():
        live[r["customer_company_id"]] = r["c"]
        live_dm[r["customer_company_id"]] = r["dm"]

    groups = {}
    for c in comps:
        k = norm(c["company_name"])
        if k:
            groups.setdefault(k, []).append(c)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

    # Which qb_customers rows reverse-reference a given company (unique match)
    cur.execute(
        "SELECT matched_company_id, COUNT(*) c FROM qb_customers "
        "WHERE client_id = %s AND matched_company_id IS NOT NULL "
        "GROUP BY matched_company_id", (CLIENT_ID,))
    qbcust_ref = {r["matched_company_id"]: r["c"] for r in cur.fetchall()}

    plan = []
    skipped = []
    clean = []
    for k, recs in dup_groups.items():
        canon = pick_canonical(recs, live)
        artifacts = [r for r in recs if r["id"] != canon["id"]]

        # Conflict: artifact & canonical reference DIFFERENT qb customers, both with
        # materially different revenue -> needs human resolution, skip.
        conflict_reason = None
        for a in artifacts:
            aq, cq = a.get("qb_customer_id"), canon.get("qb_customer_id")
            ar = float(a.get("qb_total_revenue") or 0)
            crv = float(canon.get("qb_total_revenue") or 0)
            if aq and cq and aq != cq and ar > 1000 and abs(ar - crv) > 1000:
                conflict_reason = (
                    f"qb conflict: artifact {a['company_name']!r} qb={aq} ${ar:,.0f} "
                    f"vs canonical qb={cq} ${crv:,.0f}")
                break
        if conflict_reason:
            skipped.append({"norm": k, "canonical": canon["company_name"],
                            "reason": conflict_reason})
            continue

        clean.append((k, canon, artifacts, best_display_name(recs)))

    if LIMIT:
        clean = clean[:LIMIT]

    print(f"duplicate groups: {len(dup_groups)}")
    print(f"  clean-mergeable: {len(clean)}")
    print(f"  skipped (qb conflict, manual review): {len(skipped)}")
    print(f"  mode: {'EXECUTE' if EXECUTE else 'DRY-RUN'}"
          + (f"  limit={LIMIT}" if LIMIT else ""))

    rollback = {"generated_at": datetime.datetime.utcnow().isoformat() + "Z",
                "merges": []}
    total_repointed = 0

    for idx, (k, canon, artifacts, best_name) in enumerate(clean):
        cid = canon["id"]
        rename = best_name if best_name and best_name != canon["company_name"] else None
        group_log = {"norm": k, "canonical": {"id": cid, "name": canon["company_name"]},
                     "rename_to": rename,
                     "artifacts": [], "repoints": [], "qb_unmatched": [], "deleted": []}
        try:
            for a in artifacts:
                aid = a["id"]
                group_log["artifacts"].append({"id": aid, "name": a["company_name"]})

                # 1) qb_customers reverse-match: repoint, or NULL if canonical already matched
                cur.execute(
                    "SELECT id, customer_key_id, matched_company_id FROM qb_customers "
                    "WHERE client_id=%s AND matched_company_id=%s", (CLIENT_ID, aid))
                for q in cur.fetchall():
                    if qbcust_ref.get(cid, 0) > 0:
                        # collision: drop the artifact's (lower-confidence) match
                        group_log["qb_unmatched"].append({"qb_customers_id": q["id"],
                                                           "old": aid})
                        if EXECUTE:
                            cur.execute("UPDATE qb_customers SET matched_company_id=NULL "
                                        "WHERE id=%s", (q["id"],))
                    else:
                        group_log["repoints"].append(
                            {"table": "qb_customers", "pk": q["id"], "old": aid})
                        if EXECUTE:
                            cur.execute("UPDATE qb_customers SET matched_company_id=%s "
                                        "WHERE id=%s", (cid, q["id"]))
                        qbcust_ref[cid] = qbcust_ref.get(cid, 0) + 1

                # 2) generic SET-NULL repoints
                for tbl, col in REPOINT:
                    cur.execute(f"SELECT COUNT(*) n FROM {tbl} WHERE {col}=%s", (aid,))
                    n = cur.fetchone()["n"]
                    if not n:
                        continue
                    group_log["repoints"].append(
                        {"table": tbl, "col": col, "old": aid, "count": n})
                    total_repointed += n
                    if EXECUTE:
                        cur.execute(
                            f"UPDATE {tbl} SET {col}=%s WHERE {col}=%s", (cid, aid))

                # 3) customer_contacts: repoint, dropping email collisions with canonical
                cur.execute(
                    "SELECT id, email_address FROM customer_contacts "
                    "WHERE customer_company_id=%s", (aid,))
                a_contacts = cur.fetchall()
                if a_contacts:
                    cur.execute(
                        "SELECT lower(email_address) e FROM customer_contacts "
                        "WHERE customer_company_id=%s", (cid,))
                    canon_emails = {r["e"] for r in cur.fetchall()}
                    move, drop = [], []
                    for ct in a_contacts:
                        ea = (ct["email_address"] or "").lower()
                        (drop if ea in canon_emails else move).append(ct["id"])
                    if move:
                        group_log["repoints"].append(
                            {"table": "customer_contacts", "old": aid, "count": len(move)})
                        total_repointed += len(move)
                        if EXECUTE:
                            cur.execute(
                                "UPDATE customer_contacts SET customer_company_id=%s "
                                "WHERE id = ANY(%s::uuid[])", (cid, move))
                    if drop and EXECUTE:
                        cur.execute("DELETE FROM customer_contacts WHERE id = ANY(%s::uuid[])", (drop,))

                # 4) delete the artifact (CASCADE drops derived/cache/staging rows)
                cur.execute("SELECT row_to_json(c) j FROM customer_companies c WHERE id=%s",
                            (aid,))
                snap = cur.fetchone()
                group_log["deleted"].append(snap["j"] if snap else {"id": aid})
                if EXECUTE:
                    cur.execute("DELETE FROM customer_companies WHERE id=%s", (aid,))

            # 5) adopt the group's nicest display name, then recompute aggregates
            if EXECUTE:
                if rename:
                    cur.execute("UPDATE customer_companies SET company_name=%s "
                                "WHERE id=%s", (rename, cid))
                cur.execute("""
                    UPDATE customer_companies cc SET
                      contact_count = COALESCE((SELECT COUNT(*) FROM customer_contacts
                          WHERE customer_company_id=cc.id), 0),
                      decision_maker_count = COALESCE((SELECT COUNT(*) FROM customer_contacts
                          WHERE customer_company_id=cc.id AND is_decision_maker), 0),
                      total_emails = COALESCE((SELECT COUNT(DISTINCT email_id)
                          FROM email_contact_links WHERE company_id=cc.id), 0),
                      last_contact_date = (SELECT MAX(e.sent_date) FROM email_contact_links l
                          JOIN emails e ON e.id=l.email_id WHERE l.company_id=cc.id),
                      first_contact_date = (SELECT MIN(e.sent_date) FROM email_contact_links l
                          JOIN emails e ON e.id=l.email_id WHERE l.company_id=cc.id),
                      updated_at = now()
                    WHERE cc.id=%s
                """, (cid,))
                conn.commit()
            else:
                conn.rollback()  # ensure dry-run leaves nothing
            rollback["merges"].append(group_log)
        except Exception as e:
            conn.rollback()
            skipped.append({"norm": k, "canonical": canon["company_name"],
                            "reason": f"ERROR (rolled back): {e}"})
            print(f"  [{idx}] {k!r} ERROR rolled back: {e}")

    # Concise full listing of every planned merge (for review)
    full = []
    for m in rollback["merges"]:
        full.append({
            "norm": m["norm"],
            "keep": m["rename_to"] or m["canonical"]["name"],
            "renamed_from": m["canonical"]["name"] if m["rename_to"] else None,
            "drop": [a["name"] for a in m["artifacts"]],
            "repoint": sum(r.get("count", 1) for r in m["repoints"]),
            "qb_unmatched": len(m["qb_unmatched"]),
        })

    # Output plan + rollback
    with open(PLAN_PATH, "w") as f:
        json.dump({"clean": len(clean), "skipped": skipped,
                   "full": full, "sample": rollback["merges"][:30]}, f, indent=1, default=str)
    if EXECUTE:
        with open(ROLLBACK_PATH, "w") as f:
            json.dump(rollback, f, indent=1, default=str)

    print(f"\nrows repointed (planned/applied): {total_repointed}")
    print(f"groups processed: {len(rollback['merges'])}")
    print(f"plan written: {PLAN_PATH}")
    if EXECUTE:
        print(f"rollback written: {ROLLBACK_PATH}")
        print("NOTE: run NOTIFY pgrst + refresh stored counts already done per group.")

    # Show a few sample plans
    print("\nSample merges:")
    for m in rollback["merges"][:12]:
        arts = ", ".join(a["name"] for a in m["artifacts"])
        rp = sum(r.get("count", 1) for r in m["repoints"])
        print(f"  [{m['norm']}] keep {m['canonical']['name']!r}  <- drop [{arts}]  "
              f"repoint={rp} qb_unmatched={len(m['qb_unmatched'])}")
    if skipped:
        print("\nSkipped (qb conflict / error) — first 15:")
        for s in skipped[:15]:
            print(f"  [{s['norm']}] keep {s['canonical']!r}: {s['reason']}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
