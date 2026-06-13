"""
Step 1b (branch-only file edit, NO DB write): correct the polluting exact-match seed tuples
in capability_classifier_data.json. These exact (dept,op,machine) tuples short-circuit the
keyword fallback, so the keyword corrections alone cannot fix them — the tuple tag must change.

Confirmed pollution (Step 0):
  - Fuse back to back / Fuse or mounting (Case Making)  Hard Cover Books -> Specialty Finishing
  - SwissQ Spot Gloss [Hi-Build] Varnish (Wide Format)  Embellishment    -> Wide Format
  - Cello/Gloss/Soft-touch/Matte/Anti-scuff matte (Coating) (none) -> Specialty Finishing
Idempotent: re-running makes no further change.
"""
import json, os, re

PATH = "backend/src/services/capability_classifier_data.json"
NONE = {"(none)", None, ""}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().strip())


def corrected_tag(dept_raw, op_raw, tag):
    """Pure correction: given a tuple's dept, op, and current capability tag, return the
    corrected tag, or None if no correction applies. Shape-agnostic — callers pass already-
    extracted dept/op/tag, so this works for both the JSON seed (department/operation/mvp_tag)
    and the live config (dept/op/tag)."""
    dept = norm(dept_raw)
    op = norm(op_raw)
    # ── Group A: pollution found in Step 0 ──
    # 1. fuse -> Specialty (not Hard Cover)
    if dept == "case making" and op in ("fuse back to back", "fuse or mounting") and tag == "Hard Cover Books":
        return "Specialty Finishing"
    # 2. SwissQ spot gloss varnish -> Wide Format (not Embellishment)
    if "wide format" in dept and op.startswith("swissq spot gloss") and tag == "Embellishment":
        return "Wide Format"
    # 3. Coating cello-family (none) -> Specialty
    if dept == "coating" and tag in NONE and re.search(
            r"(cello|celloglaze|soft.?touch|velvet|anti.?scuff|^matte?$|^gloss$|varnish)", op):
        return "Specialty Finishing"
    # ── Group B: mis-curated capability tuples found via the Step-2 gate diagnosis ──
    # 4. "Printing"/"Hand Lay onto SwissQ" tagged Embellishment are wide-format print, NOT embellishment
    #    (machine is a SwissQ/LED-UV flatbed). The single biggest inflator: Printing = 307 companies.
    if tag == "Embellishment" and op in ("printing", "hand lay onto swissq"):
        return "Wide Format"
    # 5. die-cutting tagged Embellishment (machine 'foil emboss die cut') is finishing, not embellishment
    if tag == "Embellishment" and op == "external die-cutting":
        return "Specialty Finishing"
    if tag == "Embellishment" and op == "zund large format cutting":
        return "Wide Format"
    # 6. oversewing / manual section sewing tagged Hard Cover are soft-cover binding (audit: section/oversew -> SC)
    if tag == "Hard Cover Books" and re.search(r"(oversewn|manual section sewing|^section sewing binding)", op):
        return "Soft Cover Books"
    # 7. D-ring / book ribbon tagged Hard Cover are specialty finishing add-ons, not casebinding
    if tag == "Hard Cover Books" and re.search(r"(d-ring|book ribbon)", op):
        return "Specialty Finishing"
    # 8. hand glue "text block to cover" is casing -> Hard Cover, mis-tagged Soft Cover
    if tag == "Soft Cover Books" and "text block to cover" in op:
        return "Hard Cover Books"
    return None


def fix(rows):
    """Apply corrections to JSON-seed-shape rows (department/operation/mvp_tag) in place."""
    changes = []
    for r in rows:
        new = corrected_tag(r.get("department"), r.get("operation"), r.get("mvp_tag"))
        if new and new != r.get("mvp_tag"):
            changes.append((r.get("department"), r.get("operation"), r.get("mvp_tag"), new))
            r["mvp_tag"] = new
    return changes


def main():
    rows = json.load(open(PATH, encoding="utf-8"))
    changes = fix(rows)
    if changes:
        json.dump(rows, open(PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"{len(changes)} tuple(s) corrected in {PATH}:")
    for dept, op, old, new in changes:
        print(f"  [{dept}] {op!r}: {old} -> {new}")
    # post-condition: no remaining fuse->HC or swissq-varnish->Emb or coating-cello-(none)
    residual = fix(json.load(open(PATH, encoding="utf-8")))
    print(f"residual after re-run (should be 0): {len(residual)}")


if __name__ == "__main__":
    main()
