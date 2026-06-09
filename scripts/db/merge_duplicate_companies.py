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
ONLY = None            # restrict to these norms AND revive them past the conflict gate (vetted)
SURVIVOR = {}          # norm -> sb_id to FORCE as the surviving row (override pick_canonical)
for a in sys.argv:
    if a.startswith("--limit="):
        LIMIT = int(a.split("=", 1)[1])
    if a.startswith("--only="):
        ONLY = {x for x in a.split("=", 1)[1].split(",") if x}
    if a.startswith("--survivor="):
        for pair in a.split("=", 1)[1].split(","):
            if ":" in pair:
                nk, sid = pair.split(":", 1)
                SURVIVOR[nk] = sid

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


def build_qb_index(rows):
    """Index qb_customers by BOTH numeric spaces. A single number can be a valid
    customer_key_id for one customer AND a valid qb_record_id for a different one,
    so we keep both maps and disambiguate by name at lookup time."""
    by_key = {str(r["customer_key_id"]): r for r in rows
              if r.get("customer_key_id") is not None}
    by_rec = {str(r["qb_record_id"]): r for r in rows
              if r.get("qb_record_id") is not None}
    return by_key, by_rec


def resolve_qb(qid, sb_name, by_key, by_rec):
    """Resolve a mixed customer_companies.qb_customer_id (which may be a
    customer_key_id OR a qb_record_id, depending on which write path stamped it)
    to a single canonical qb_customers row.

    Disambiguation is name-aware: if the number resolves to two different QB
    customers (one via key space, one via record space), prefer the interpretation
    whose customer_name matches the SB company name. Returns the qb_customers row
    (with the true customer_key_id / total_invoiced) or None if unresolvable.

    This is the ONLY trustworthy way to compare these IDs — never compare the raw
    qb_customer_id values, since they may live in different numeric spaces."""
    if qid is None:
        return None
    s = str(qid)
    sn = norm(sb_name)
    ck = by_key.get(s)
    cr = by_rec.get(s)
    cands = []
    if ck:
        cands.append(ck)
    if cr and (not ck or cr["customer_key_id"] != ck["customer_key_id"]):
        cands.append(cr)
    if not cands:
        return None
    for row in cands:
        if norm(row["customer_name"]) == sn:
            return row
    return cands[0]  # default to key-space interpretation when name is ambiguous


def pick_canonical(records, live, by_key, by_rec):
    """Pick the row that SURVIVES. Ranked by data-integrity signals that live on
    the company row itself (live contacts, domain, qb match + its revenue), since
    those columns are not recomputed on merge. Name readability is only a low
    tiebreak — the survivor is separately renamed to the group's nicest name.

    Revenue is the RESOLVED QB customer's true total_invoiced (via resolve_qb), NOT
    the denormalized qb_total_revenue column — that column was corrupted by the same
    key/record mixing (e.g. Coco Republic shows $1,022,568 there while its resolved
    customer has $0), so ranking on it would pick the wrong survivor."""
    def key(r):
        qrow = resolve_qb(r.get("qb_customer_id"), r.get("company_name"), by_key, by_rec)
        true_rev = float(qrow.get("total_invoiced") or 0) if qrow else 0.0
        return (
            live.get(r["id"], 0),
            1 if (r.get("email_domains") or []) else 0,
            1 if r.get("qb_customer_id") else 0,
            METHOD_RANK.get(r.get("qb_match_method"), 0),
            true_rev,
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

    # Index qb_customers by both numeric spaces so qb_customer_id (a mixed
    # key_id/record_id field) can be resolved to the true underlying customer
    # before any comparison or canonical selection.
    cur.execute(
        "SELECT customer_key_id, qb_record_id, customer_name, total_invoiced "
        "FROM qb_customers WHERE client_id = %s", (CLIENT_ID,))
    by_key, by_rec = build_qb_index(cur.fetchall())

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
        canon = pick_canonical(recs, live, by_key, by_rec)
        artifacts = [r for r in recs if r["id"] != canon["id"]]

        # Conflict: artifact & canonical reference DIFFERENT qb customers, both with
        # materially different revenue -> needs human resolution, skip.
        #
        # CRITICAL: resolve each qb_customer_id to its true qb_customers row FIRST.
        # The raw values may live in different numeric spaces (key_id vs record_id),
        # so comparing them raw invented phantom conflicts (Themakehaus, Louisvuitton,
        # Matthewely, ...) where both SB rows actually point at ONE QB customer.
        c_qb = resolve_qb(canon.get("qb_customer_id"), canon.get("company_name"),
                          by_key, by_rec)
        conflict_reason = None
        for a in artifacts:
            a_qb = resolve_qb(a.get("qb_customer_id"), a.get("company_name"),
                              by_key, by_rec)
            if not (a_qb and c_qb):
                continue
            # Same underlying QB customer once resolved -> phantom conflict, safe to merge.
            if a_qb["customer_key_id"] == c_qb["customer_key_id"]:
                continue
            ar = float(a_qb.get("total_invoiced") or 0)
            crv = float(c_qb.get("total_invoiced") or 0)
            if ar > 1000 and abs(ar - crv) > 1000:
                conflict_reason = (
                    f"qb conflict: artifact {a['company_name']!r} -> QB "
                    f"{a_qb['customer_name']!r} key={a_qb['customer_key_id']} ${ar:,.0f} "
                    f"vs canonical -> QB {c_qb['customer_name']!r} "
                    f"key={c_qb['customer_key_id']} ${crv:,.0f}")
                break
        if conflict_reason:
            skipped.append({"norm": k, "canonical": canon["company_name"],
                            "reason": conflict_reason})
            continue

        clean.append((k, canon, artifacts, best_display_name(recs)))

    # --only: revive explicitly allow-listed groups that the conflict gate skipped
    # (these have been vetted by hand) and restrict processing to the allow-list.
    if ONLY is not None:
        revived = []
        for s in list(skipped):
            if s["norm"] in ONLY and s["norm"] in dup_groups:
                recs = dup_groups[s["norm"]]
                canon = pick_canonical(recs, live, by_key, by_rec)
                arts = [r for r in recs if r["id"] != canon["id"]]
                revived.append((s["norm"], canon, arts, best_display_name(recs)))
                skipped.remove(s)
        clean = [c for c in clean if c[0] in ONLY] + revived

    # --survivor: force a specific sb_id to survive (override pick_canonical), so a
    # high-revenue QB link is never NULLed just because the stray row has more contacts.
    if SURVIVOR:
        forced_clean = []
        for (k, canon, artifacts, best_name) in clean:
            if k in SURVIVOR:
                recs = [canon] + artifacts
                forced = next((r for r in recs if str(r["id"]) == SURVIVOR[k]), None)
                if forced is None:
                    skipped.append({"norm": k, "canonical": canon["company_name"],
                                    "reason": f"survivor override {SURVIVOR[k]} not in group"})
                    continue
                canon = forced
                artifacts = [r for r in recs if r["id"] != forced["id"]]
            forced_clean.append((k, canon, artifacts, best_name))
        clean = forced_clean

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

    def flush_rollback():
        """Persist the rollback manifest durably. Called per-group BEFORE that group's
        commit so a crash mid-run can never leave a committed merge unrecorded. Only
        ever invoked under EXECUTE, so dry-runs never touch ROLLBACK_PATH."""
        with open(ROLLBACK_PATH, "w") as f:
            json.dump(rollback, f, indent=1, default=str)
            f.flush()
            os.fsync(f.fileno())

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
                    "SELECT id, customer_key_id, total_invoiced, matched_company_id "
                    "FROM qb_customers "
                    "WHERE client_id=%s AND matched_company_id=%s", (CLIENT_ID, aid))
                for q in cur.fetchall():
                    if qbcust_ref.get(cid, 0) > 0:
                        # collision: canonical already has a QB match. Dropping the
                        # artifact's match is only safe if it carries no real revenue.
                        # GUARD: refuse to NULL a non-zero-revenue match — that would
                        # silently destroy a real QB linkage (the Coco Republic class
                        # of bug). Send the whole group to manual review instead.
                        if float(q.get("total_invoiced") or 0) > 0:
                            raise RuntimeError(
                                f"refuse to NULL non-zero-revenue qb match: "
                                f"qb_customers {q['id']} key={q['customer_key_id']} "
                                f"${float(q['total_invoiced']):,.0f} matched to artifact "
                                f"{aid} ({a['company_name']!r})")
                        # collision: drop the artifact's (zero-revenue) match
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
                # Counts from the CANONICAL assignment (emails.customer_company_id +
                # customer_contacts.customer_company_id), NOT email_contact_links.company_id
                # which diverges and inflates with broker/shared-domain spillover. Mirrors
                # migration 117 / the get_company_emails endpoint.
                cur.execute("""
                    UPDATE customer_companies cc SET
                      contact_count = COALESCE((SELECT COUNT(*) FROM customer_contacts
                          WHERE customer_company_id=cc.id), 0),
                      decision_maker_count = COALESCE((SELECT COUNT(*) FROM customer_contacts
                          WHERE customer_company_id=cc.id AND is_decision_maker), 0),
                      total_emails = COALESCE((SELECT COUNT(*)
                          FROM emails WHERE customer_company_id=cc.id), 0),
                      last_contact_date = (SELECT MAX(sent_date) FROM emails
                          WHERE customer_company_id=cc.id),
                      first_contact_date = (SELECT MIN(sent_date) FROM emails
                          WHERE customer_company_id=cc.id),
                      updated_at = now()
                    WHERE cc.id=%s
                """, (cid,))
                # Manifest BEFORE commit: record the undo plan durably first, then
                # commit. If the commit fails, un-record so the manifest never claims
                # a merge that did not happen.
                rollback["merges"].append(group_log)
                flush_rollback()
                try:
                    conn.commit()
                except Exception:
                    rollback["merges"].pop()
                    flush_rollback()
                    raise
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
