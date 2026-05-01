"""
Throwaway script: Update ai_prompt_config DB rows with the latest
prompt templates that include QB reference extraction instructions.

Updates both email_analysis_user and email_analysis_system prompt keys.
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

# Import the latest prompt templates from code
from src.services.ai_email_analyzer import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

print("[1/4] Checking current DB prompts...")
resp = sb.table("ai_prompt_config").select("id, prompt_key, version, description").is_("client_id", "null").in_(
    "prompt_key", ["email_analysis_system", "email_analysis_user"]
).execute()

existing_keys = {r["prompt_key"]: r for r in (resp.data or [])}
print(f"  Found {len(existing_keys)} existing global prompts: {list(existing_keys.keys())}")

# Update user prompt (the one with QB reference extraction added)
print("\n[2/4] Updating email_analysis_user prompt...")
if "email_analysis_user" in existing_keys:
    row = existing_keys["email_analysis_user"]
    # Bump version
    old_ver = row.get("version", "v1.0")
    new_ver = "v1.3"
    sb.table("ai_prompt_config").update({
        "prompt_text": USER_PROMPT_TEMPLATE,
        "version": new_ver,
        "description": "Email analysis user prompt with QB reference extraction (v1.3)",
    }).eq("id", row["id"]).execute()
    print(f"  [ok] Updated (version {old_ver} -> {new_ver})")
else:
    sb.table("ai_prompt_config").insert({
        "prompt_key": "email_analysis_user",
        "prompt_text": USER_PROMPT_TEMPLATE,
        "client_id": None,
        "is_active": True,
        "description": "Email analysis user prompt with QB reference extraction (v1.3)",
        "version": "v1.3",
    }).execute()
    print("  [ok] Inserted new global row")

# Update system prompt (for completeness — keeps DB in sync with code)
print("\n[3/4] Updating email_analysis_system prompt...")
if "email_analysis_system" in existing_keys:
    row = existing_keys["email_analysis_system"]
    old_ver = row.get("version", "v1.0")
    new_ver = "v1.3"
    sb.table("ai_prompt_config").update({
        "prompt_text": SYSTEM_PROMPT,
        "version": new_ver,
        "description": "Email analysis system prompt (v1.3)",
    }).eq("id", row["id"]).execute()
    print(f"  [ok] Updated (version {old_ver} -> {new_ver})")
else:
    sb.table("ai_prompt_config").insert({
        "prompt_key": "email_analysis_system",
        "prompt_text": SYSTEM_PROMPT,
        "client_id": None,
        "is_active": True,
        "description": "Email analysis system prompt (v1.3)",
        "version": "v1.3",
    }).execute()
    print("  [ok] Inserted new global row")

# Verify
print("\n[4/4] Verifying...")
resp = sb.table("ai_prompt_config").select("prompt_key, version, is_active").is_("client_id", "null").in_(
    "prompt_key", ["email_analysis_system", "email_analysis_user"]
).execute()
for r in (resp.data or []):
    print(f"  {r['prompt_key']}: version={r['version']}, active={r['is_active']}")

# Check that user prompt now contains qb_references
user_resp = sb.table("ai_prompt_config").select("prompt_text").is_("client_id", "null").eq(
    "prompt_key", "email_analysis_user"
).limit(1).execute()
if user_resp.data and "qb_references" in user_resp.data[0].get("prompt_text", ""):
    print("  [ok] User prompt contains qb_references field")
else:
    print("  [WARN] User prompt does NOT contain qb_references — check manually")

print("\n[ok] Prompt DB update complete. Delete this script after verification.")
