"""
THROWAWAY — Raw-latency plausibility check for the Tier-A responsiveness metric (read-only).

Question: the responsiveness metric (am_structural_metrics.median_raw_hours, migration 126)
shows implausibly fast RAW median reply latencies — Linda ~0.1h (~6 min), Ehab ~0.04h (~2 min).
Are these genuine human replies, or artifacts (auto-replies/OOO, read/delivery receipts,
threading mis-pairs, bulk/identical sends, automated inbound)?

We mirror the metric's EXACT population so the numbers reconcile:
    email_response_metrics m
      JOIN emails o ON o.id = m.email_id          -- the responding (reply) email
      WHERE o.mailbox_id = <AM>
        AND o.is_outbound IS TRUE                 -- WE (the AM) replied
        AND coalesce(m.is_auto_reply,false)=false -- metric already drops flagged auto-replies
        AND o.sent_date in window
    median over m.response_time_seconds / 3600  ==  median_raw_hours

Outputs, per mailbox AM (headline = trailing 12 months, + all-time for context):
  1. Full latency distribution bucketed (<10s, <1min, 1-5min, 5-30min, 30m-2h, 2-8h, 8-24h, >24h)
     + median/percentiles + sub-5-min and sub-1-min share.   <-- the red-flag cluster
  2. Server-side artifact classification of the ENTIRE sub-5-min cluster (not just a sample):
       auto_or_receipt | not_a_reply_pair | automated_inbound | subject_mismatch |
       bulk_identical | recipient_mismatch | genuine_candidate
     (non-exclusive flag counts also reported).
  3. A representative text sample (~20, spread across the sub-5-min band via ntile) showing the
     inbound subj/snippet, outbound subj/snippet, gap, sender, and each artifact flag — for eyeballing.

All aggregation + classification is server-side (throwaway RPCs, raised statement_timeout); only
small jsonb is returned (egress discipline, DATA_ANALYSIS_GUIDELINES). READ-ONLY: creates/drops
temp functions only, no data writes. Writes scripts/db/_resp_latency_plausibility.json.
"""
import os, sys, io, json, time
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
from dotenv import load_dotenv
from supabase import create_client

HERE = os.path.dirname(__file__)
env_path = os.path.join(HERE, "..", "..", "backend", ".env.production")
if not os.path.exists(env_path):
    env_path = os.path.join(HERE, "..", "..", "backend", ".env")
load_dotenv(env_path)

CARBON8 = "241d7b99-f099-4557-96e5-212c4af10812"
TODAY = "2026-06-15"
HEADLINE_START = "2025-06-15T00:00:00+00:00"   # trailing 12 months (matches service HEADLINE_DAYS=365)
HEADLINE_END   = "2026-06-16T00:00:00+00:00"
ALL_START      = "2000-01-01T00:00:00+00:00"
ALL_END        = "2100-01-01T00:00:00+00:00"

AM_TARGETS = ["Nic Doyle", "Linda D'Arcy", "Ehab Kamel", "Kenneth Beck-Pedersen"]


def _client():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


sb = _client()


def with_retry(build, tries=5):
    global sb
    for i in range(tries):
        try:
            return build()
        except Exception as e:
            if i == tries - 1:
                raise
            print(f"    retry {i+1} after {type(e).__name__}: {str(e)[:80]}", flush=True)
            time.sleep(2 * (i + 1))
            sb = _client()


def exec_sql(q):
    return with_retry(lambda: sb.rpc("exec_sql", {"query": q}).execute())


def rpc(name, args):
    return with_retry(lambda: sb.rpc(name, args).execute()).data


# ── 0. resolve mailboxes -> AM names ───────────────────────────────────────
print("[0] resolving Carbon8 mailboxes ...", flush=True)
mboxes = with_retry(lambda: sb.table("mailboxes")
                    .select("id, name, user_id, is_active").eq("client_id", CARBON8).execute()).data or []
profiles = with_retry(lambda: sb.table("user_profiles").select("id, name").execute()).data or []
uid_to_name = {p["id"]: (p.get("name") or "") for p in profiles}


def classify(uname):
    low = (uname or "").lower()
    if low.startswith("hello"):
        return "Hello (shared)"
    for am in AM_TARGETS:
        if low.startswith(am.lower()):
            return am
    return uname or "<no-user>"


mb_disp = {}     # mailbox_id -> display name
for m in mboxes:
    mb_disp[m["id"]] = classify(uid_to_name.get(m.get("user_id"), ""))
for mid, d in mb_disp.items():
    print(f"    {d:<28} active={next((m.get('is_active') for m in mboxes if m['id']==mid), '?')}  {mid}")


# ── 1. throwaway RPCs ──────────────────────────────────────────────────────
RPC_DIST = """
CREATE OR REPLACE FUNCTION _tmp_resp_dist(p_mailbox uuid, p_start timestamptz, p_end timestamptz)
RETURNS jsonb LANGUAGE sql STABLE SET search_path = public SET statement_timeout='120s' AS $fn$
WITH resp AS (
  SELECT m.response_time_seconds rt
  FROM email_response_metrics m
  JOIN emails e ON e.id = m.email_id
  WHERE e.mailbox_id = p_mailbox
    AND e.is_outbound IS TRUE
    AND coalesce(m.is_auto_reply,false) = false
    AND e.sent_date >= p_start AND e.sent_date < p_end
)
SELECT jsonb_build_object(
  'reply_rows', count(*),
  'median_raw_seconds', round(percentile_cont(0.5) WITHIN GROUP (ORDER BY rt)::numeric,1),
  'median_raw_hours',   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY rt)/3600.0)::numeric,3),
  'p10_seconds', round(percentile_cont(0.10) WITHIN GROUP (ORDER BY rt)::numeric,1),
  'p25_seconds', round(percentile_cont(0.25) WITHIN GROUP (ORDER BY rt)::numeric,1),
  'p75_seconds', round(percentile_cont(0.75) WITHIN GROUP (ORDER BY rt)::numeric,1),
  'min_seconds', min(rt), 'max_seconds', max(rt),
  'buckets', jsonb_build_object(
     'lt_10s',   count(*) FILTER (WHERE rt < 10),
     'lt_1min',  count(*) FILTER (WHERE rt < 60),
     'b1_5min',  count(*) FILTER (WHERE rt >= 60 AND rt < 300),
     'b5_30min', count(*) FILTER (WHERE rt >= 300 AND rt < 1800),
     'b30m_2h',  count(*) FILTER (WHERE rt >= 1800 AND rt < 7200),
     'b2_8h',    count(*) FILTER (WHERE rt >= 7200 AND rt < 28800),
     'b8_24h',   count(*) FILTER (WHERE rt >= 28800 AND rt < 86400),
     'gt_24h',   count(*) FILTER (WHERE rt >= 86400)),
  'sub5min_count', count(*) FILTER (WHERE rt < 300),
  'sub1min_count', count(*) FILTER (WHERE rt < 60)
) FROM resp;
$fn$;
"""

# Classifies the ENTIRE sub-5-min cluster + returns a spread sample.
RPC_FAST = """
CREATE OR REPLACE FUNCTION _tmp_resp_fast(p_mailbox uuid, p_start timestamptz, p_end timestamptz, p_sample int)
RETURNS jsonb LANGUAGE sql STABLE SET search_path = public SET statement_timeout='120s' AS $fn$
WITH pairs AS (
  SELECT m.response_time_seconds rt,
         o.id o_id, o.subject o_subj, o.subject_normalized o_subjn,
         o.sender_email o_from, o.sender_name o_name, o.is_outbound o_out,
         o.canonical_thread_id o_ct, o.recipients o_rcpt, left(o.body_text,220) o_body,
         i.subject i_subj, i.subject_normalized i_subjn,
         i.sender_email i_from, i.sender_name i_name, i.is_outbound i_out,
         i.canonical_thread_id i_ct, left(i.body_text,220) i_body
  FROM email_response_metrics m
  JOIN emails o ON o.id = m.email_id
  JOIN emails i ON i.id = m.responding_to_email_id
  WHERE o.mailbox_id = p_mailbox
    AND o.is_outbound IS TRUE
    AND coalesce(m.is_auto_reply,false) = false
    AND o.sent_date >= p_start AND o.sent_date < p_end
    AND m.response_time_seconds < 300
),
flagged AS (
  SELECT p.*,
    (p.o_subj ~* '(out of office|out of the office|automatic reply|auto.?reply|autoreply|vacation|away from (the )?office|currently out|i am away|i''m away|absence notification|delivery status notification|mail delivery (failed|sub)|undeliverable|read:|^not read|delivered:|message recall|recall:|automatische antwort|abwesen|annual leave|^re: read|tracking:)') auto_or_receipt,
    (p.i_from ~* '(no.?reply|do.?not.?reply|noreply|donotreply|mailer.?daemon|postmaster|@.*notification|notifications?@|automated|^alerts?@|^system@|bounce|mailgun|sendgrid|^info@.*\\.)') automated_inbound,
    (coalesce(p.o_subjn,'') <> '' AND coalesce(p.i_subjn,'') <> '' AND lower(btrim(p.o_subjn)) <> lower(btrim(p.i_subjn))) subj_mismatch,
    (p.o_ct IS DISTINCT FROM p.i_ct) thread_mismatch,
    NOT EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(p.o_rcpt,'[]'::jsonb)) r
                WHERE lower(r->>'email') = lower(p.i_from)) recip_mismatch,
    (p.i_out IS TRUE) inbound_actually_outbound
  FROM pairs p
),
dup AS (
  SELECT md5(coalesce(o_body,'')) h, count(*) c FROM flagged
  WHERE length(coalesce(o_body,'')) > 40 GROUP BY 1
),
verdict AS (
  SELECT f.*,
    CASE
      WHEN f.auto_or_receipt THEN 'auto_or_receipt'
      WHEN f.inbound_actually_outbound THEN 'not_a_reply_pair'
      WHEN f.automated_inbound THEN 'automated_inbound'
      WHEN f.subj_mismatch THEN 'subject_mismatch'
      WHEN coalesce((SELECT c FROM dup d WHERE d.h = md5(coalesce(f.o_body,''))),0) >= 3
           AND length(coalesce(f.o_body,'')) > 40 THEN 'bulk_identical'
      WHEN f.recip_mismatch THEN 'recipient_mismatch'
      ELSE 'genuine_candidate'
    END verdict
  FROM flagged f
),
ranked AS (
  SELECT v.*, ntile(LEAST(p_sample, GREATEST((SELECT count(*) FROM verdict),1))::int)
                OVER (ORDER BY rt, o_id) tile
  FROM verdict v
)
SELECT jsonb_build_object(
  'total_sub5', (SELECT count(*) FROM verdict),
  'verdict_counts', (SELECT jsonb_object_agg(verdict, c)
                     FROM (SELECT verdict, count(*) c FROM verdict GROUP BY 1) z),
  'flag_counts', jsonb_build_object(
     'auto_or_receipt',          (SELECT count(*) FROM flagged WHERE auto_or_receipt),
     'automated_inbound',        (SELECT count(*) FROM flagged WHERE automated_inbound),
     'subject_mismatch',         (SELECT count(*) FROM flagged WHERE subj_mismatch),
     'thread_mismatch',          (SELECT count(*) FROM flagged WHERE thread_mismatch),
     'recipient_mismatch',       (SELECT count(*) FROM flagged WHERE recip_mismatch),
     'inbound_actually_outbound',(SELECT count(*) FROM flagged WHERE inbound_actually_outbound)),
  'sample', (SELECT jsonb_agg(s ORDER BY (s->>'rt_s')::int) FROM (
      SELECT DISTINCT ON (tile) jsonb_build_object(
        'rt_s', rt, 'verdict', verdict,
        'out_from', o_from, 'out_name', o_name, 'out_subj', o_subj, 'out_body', o_body,
        'in_from', i_from, 'in_name', i_name, 'in_subj', i_subj, 'in_body', i_body,
        'subj_mismatch', subj_mismatch, 'thread_mismatch', thread_mismatch,
        'recip_mismatch', recip_mismatch, 'auto_or_receipt', auto_or_receipt,
        'automated_inbound', automated_inbound) s, tile, rt
      FROM ranked ORDER BY tile, rt) q)
);
$fn$;
"""

print("\n[1] creating throwaway RPCs ...", flush=True)
exec_sql(RPC_DIST)
exec_sql(RPC_FAST)
exec_sql("NOTIFY pgrst, 'reload schema'")
time.sleep(3)


# ── 2. run per mailbox ─────────────────────────────────────────────────────
results = {}
# order: targets first (with mailbox), then any other boxes
ordered = [m for m in mboxes if mb_disp[m["id"]] in AM_TARGETS] + \
          [m for m in mboxes if mb_disp[m["id"]] not in AM_TARGETS]

for m in ordered:
    mid = m["id"]; disp = mb_disp[mid]
    print(f"[2] {disp} ({mid}) ...", flush=True)
    dist_h = rpc("_tmp_resp_dist", {"p_mailbox": mid, "p_start": HEADLINE_START, "p_end": HEADLINE_END})
    dist_a = rpc("_tmp_resp_dist", {"p_mailbox": mid, "p_start": ALL_START, "p_end": ALL_END})
    fast_h = rpc("_tmp_resp_fast", {"p_mailbox": mid, "p_start": HEADLINE_START,
                                    "p_end": HEADLINE_END, "p_sample": 20})
    results[mid] = {"display": disp, "is_active": m.get("is_active"),
                    "dist_headline": dist_h, "dist_alltime": dist_a, "fast_headline": fast_h}


# ── 3. cleanup ─────────────────────────────────────────────────────────────
print("[3] dropping RPCs ...", flush=True)
exec_sql("DROP FUNCTION IF EXISTS _tmp_resp_dist(uuid, timestamptz, timestamptz)")
exec_sql("DROP FUNCTION IF EXISTS _tmp_resp_fast(uuid, timestamptz, timestamptz, int)")
exec_sql("NOTIFY pgrst, 'reload schema'")

OUT = os.path.join(HERE, "_resp_latency_plausibility.json")
with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"today": TODAY, "headline_window": [HEADLINE_START, HEADLINE_END],
               "results": results}, f, indent=2, default=str)


# ── 4. REPORT ──────────────────────────────────────────────────────────────
W = 112
def bar(t):
    print("\n" + "=" * W); print(t); print("=" * W)


def pct(n, d):
    return (n / d * 100) if d else 0.0


bar("RAW-LATENCY PLAUSIBILITY — Tier-A responsiveness metric (median_raw_hours)  [read-only]")
print(f"today={TODAY}   headline window = trailing 12 months  ({HEADLINE_START[:10]} .. {HEADLINE_END[:10]})")
print("population mirrors the metric EXACTLY: outbound AM reply, is_auto_reply=false, sent in window\n")

# ---- distribution table (headline) ----
print("DISTRIBUTION OF RAW REPLY LATENCY — headline window (share of each AM's reply_rows)")
hdr = (f"  {'AM':<22}{'rows':>7}{'medRAW':>8}{'<10s':>7}{'<1m':>7}{'1-5m':>7}{'5-30m':>7}"
       f"{'30m-2h':>8}{'2-8h':>7}{'8-24h':>7}{'>24h':>7}{'sub5%':>7}")
print(hdr); print("  " + "-" * (W - 2))
for mid, r in results.items():
    d = r["dist_headline"] or {}
    rows = d.get("reply_rows", 0) or 0
    b = d.get("buckets", {}) or {}
    if rows == 0:
        print(f"  {r['display']:<22}{0:>7}   (no reply rows in window)")
        continue
    medh = d.get("median_raw_hours")
    print(f"  {r['display']:<22}{rows:>7,}{(medh if medh is not None else 0):>8.3f}"
          f"{pct(b.get('lt_10s',0),rows):>6.1f}%{pct(b.get('lt_1min',0),rows):>6.1f}%"
          f"{pct(b.get('b1_5min',0),rows):>6.1f}%{pct(b.get('b5_30min',0),rows):>6.1f}%"
          f"{pct(b.get('b30m_2h',0),rows):>7.1f}%{pct(b.get('b2_8h',0),rows):>6.1f}%"
          f"{pct(b.get('b8_24h',0),rows):>6.1f}%{pct(b.get('gt_24h',0),rows):>6.1f}%"
          f"{pct(d.get('sub5min_count',0),rows):>6.1f}%")
print("  medRAW = median_raw_hours (what the coaching metric reports).  <1m column INCLUDES <10s.")

# ---- all-time medians for context ----
print("\nFor context — all-time (no window):")
for mid, r in results.items():
    da = r["dist_alltime"] or {}
    if not da.get("reply_rows"):
        continue
    print(f"  {r['display']:<22} rows={da['reply_rows']:>7,}  median_raw_hours={da.get('median_raw_hours')}"
          f"  sub5min={pct(da.get('sub5min_count',0), da['reply_rows']):.1f}%"
          f"  sub1min={pct(da.get('sub1min_count',0), da['reply_rows']):.1f}%")

# ---- artifact classification of the sub-5-min cluster (headline) ----
bar("ARTIFACT CLASSIFICATION OF THE SUB-5-MIN CLUSTER (entire cluster, headline window)")
for mid, r in results.items():
    f = r["fast_headline"] or {}
    tot = f.get("total_sub5", 0) or 0
    if tot == 0:
        print(f"\n{r['display']}: no sub-5-min pairs.")
        continue
    vc = f.get("verdict_counts", {}) or {}
    fc = f.get("flag_counts", {}) or {}
    genuine = vc.get("genuine_candidate", 0)
    print(f"\n{r['display']}  — {tot:,} sub-5-min pairs")
    print(f"   exclusive verdict:")
    for k in ("auto_or_receipt", "not_a_reply_pair", "automated_inbound", "subject_mismatch",
              "bulk_identical", "recipient_mismatch", "genuine_candidate"):
        if k in vc:
            print(f"      {k:<22}{vc[k]:>6,} ({pct(vc[k],tot):>5.1f}%)")
    print(f"   non-exclusive flags: " + ", ".join(f"{k}={v}" for k, v in fc.items() if v))
    print(f"   => artifact share (non-genuine): {pct(tot-genuine, tot):.1f}%   "
          f"genuine_candidate: {pct(genuine, tot):.1f}%")

# ---- text samples ----
bar("SAMPLED SUB-5-MIN PAIRS (spread across the band) — inbound -> AM outbound reply")
for mid, r in results.items():
    f = r["fast_headline"] or {}
    sample = f.get("sample") or []
    if not sample:
        continue
    print(f"\n----- {r['display']}  (showing {len(sample)} of {f.get('total_sub5',0):,}) -----")
    for s in sample:
        rt = s.get("rt_s", 0)
        flags = [k for k in ("auto_or_receipt", "automated_inbound", "subj_mismatch",
                             "thread_mismatch", "recip_mismatch") if s.get(k)]
        print(f"\n  [{rt:>4}s] verdict={s.get('verdict')}  flags={','.join(flags) or 'none'}")
        print(f"    IN  <{s.get('in_from')}> ({s.get('in_name')}) :: {(s.get('in_subj') or '')[:80]}")
        ib = (s.get("in_body") or "").replace("\n", " ").replace("\r", " ")
        print(f"        | {ib[:140]}")
        print(f"    OUT <{s.get('out_from')}> ({s.get('out_name')}) :: {(s.get('out_subj') or '')[:80]}")
        ob = (s.get("out_body") or "").replace("\n", " ").replace("\r", " ")
        print(f"        | {ob[:140]}")

bar(f"wrote -> {OUT}")
