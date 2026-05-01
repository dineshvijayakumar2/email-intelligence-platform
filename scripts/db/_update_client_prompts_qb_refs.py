"""
Throwaway script: Add qb_references field to client-specific
ai_prompt_config rows for email_analysis_user.

These rows have a custom schema (different from the global default).
We add the qb_references array to the JSON schema and the
QB REFERENCE EXTRACTION instruction block.
"""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
from dotenv import load_dotenv
from supabase import create_client

env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env.production')
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(__file__), '..', '..', 'backend', '.env')
load_dotenv(env_path)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Fetch all client-specific email_analysis_user prompts
resp = sb.table("ai_prompt_config").select("id, prompt_text, client_id, version").eq(
    "prompt_key", "email_analysis_user"
).not_.is_("client_id", "null").execute()

if not resp.data:
    print("No client-specific email_analysis_user prompts found")
    sys.exit(0)

QB_REFS_SCHEMA_FIELD = '    "qb_references": [{"type": "quote|job", "number": "Q##### or J######"}]'

QB_REFS_INSTRUCTION = """QB REFERENCE EXTRACTION:
- Look for QuickBase reference numbers in the email subject or body.
- Quote numbers: Q followed by 4-6 digits (e.g., Q20334), or "Quote #12345", "QT-12345", "quote 12345".
- Job numbers: J followed by 5-7 digits (e.g., J460037), or "Job #123456", "JB-123456", "job number 123456".
- Return just the numeric part prefixed with Q or J. E.g., "Quote #20334" -> {"type": "quote", "number": "Q20334"}.
- If no references found, return empty array.
- Only extract references explicitly present -- do not guess or infer."""

for row in resp.data:
    row_id = row["id"]
    client_id = row["client_id"]
    text = row["prompt_text"]
    old_version = row.get("version", "v1.0")

    if "qb_references" in text:
        print(f"[skip] client_id={client_id} already has qb_references")
        continue

    # 1. Add qb_references field to JSON schema (after "classification_note" line)
    if '"classification_note"' in text:
        text = text.replace(
            '    "classification_note":',
            QB_REFS_SCHEMA_FIELD + ',\n    "classification_note":'
        )
    elif '"key_entities"' in text:
        # Fallback: add after key_entities line
        # Find the key_entities line and the next line
        lines = text.split('\n')
        new_lines = []
        for line in lines:
            new_lines.append(line)
            if '"key_entities"' in line:
                new_lines.append(QB_REFS_SCHEMA_FIELD + ',')
        text = '\n'.join(new_lines)

    # 2. Add QB REFERENCE EXTRACTION block before "NEW INTENT NOTES"
    if "NEW INTENT NOTES" in text:
        text = text.replace(
            "NEW INTENT NOTES",
            QB_REFS_INSTRUCTION + "\n\nNEW INTENT NOTES"
        )
    else:
        # Fallback: append at end
        text = text + "\n\n" + QB_REFS_INSTRUCTION

    # 3. Bump version
    new_version = old_version.replace("+intents3", "+intents3+qbrefs")
    if new_version == old_version:
        new_version = old_version + "+qbrefs"

    print(f"[update] client_id={client_id} version {old_version} -> {new_version}")

    sb.table("ai_prompt_config").update({
        "prompt_text": text,
        "version": new_version,
    }).eq("id", row_id).execute()

    print(f"  [ok] Updated ({len(text)} chars)")

# Verify
print("\n[verify]")
resp = sb.table("ai_prompt_config").select("client_id, version").eq(
    "prompt_key", "email_analysis_user"
).not_.is_("client_id", "null").execute()
for r in (resp.data or []):
    print(f"  client_id={r['client_id']}  version={r['version']}")

# Check qb_references is present
resp = sb.table("ai_prompt_config").select("prompt_text, client_id").eq(
    "prompt_key", "email_analysis_user"
).not_.is_("client_id", "null").execute()
for r in (resp.data or []):
    has = "qb_references" in r["prompt_text"]
    print(f"  client_id={r['client_id']}  has qb_references: {has}")

print("\n[ok] Done. Delete this script after verification.")
