"""
Update ai_prompt_config rows to add 3 new unambiguous intents:
  cancellation_intent, escalation_to_management, legal_or_compliance

Paired with migration 079. Rules in migration 079 reference these intent
values; this script ensures the AI classifier actually PRODUCES them.

Run ONCE after migration 079 is applied. Idempotent — re-running is safe
(only updates prompts that don't already contain the intent markers).
"""
import os
import sys
from pathlib import Path

# Load env
try:
    from dotenv import load_dotenv
    for p in [Path(__file__).parent.parent.parent / "backend" / ".env.production",
              Path(__file__).parent.parent.parent / "backend" / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)
            break
except ImportError:
    pass

import psycopg2


NEW_INTENTS = ("cancellation_intent", "escalation_to_management", "legal_or_compliance")


# Guidance block to append to each prompt. Short, unambiguous, example-driven.
# Placed as a dedicated section so it's easy to find/edit in the admin UI later.
NEW_INTENT_GUIDANCE = """

NEW INTENT NOTES (all three always map to urgent — do NOT assign if the signal is weak):
- cancellation_intent: explicit wording like "cancel our account", "terminate service", "close our account", "we are switching to [competitor]", or formal written notice to end the business relationship. Do NOT use this for cancelling a single quote/order (use general_enquiry instead) or for routine contract expiry without explicit intent to leave.
- escalation_to_management: explicit request to speak with a manager, supervisor, senior person, director, or CEO. Includes phrases like "take this to your boss", "can we speak to management", "someone senior". Do NOT use this for general follow-ups or routine escalations already being handled.
- legal_or_compliance: mentions of lawsuits, legal action, contract terms under dispute, GDPR, HIPAA, liability, insurance claims, indemnity, compliance audits, or similar regulated topics. Do NOT use this for routine contract renewal discussion or quote terms negotiation.
"""


def _prompt_needs_update(prompt_text: str) -> bool:
    """Check if the prompt is missing any of the new intents."""
    if not prompt_text:
        return False
    return not all(intent in prompt_text for intent in NEW_INTENTS)


def _expand_intent_list(prompt_text: str) -> str:
    """Append the 3 new intents to any existing intent enumeration.

    The Carbon8 client prompt has a pipe-separated intent string inside a
    JSON schema example. The global default has a JSON array. We handle both
    by searching for the marker intent 'complaint' which is in both, and
    appending the 3 new intents nearby. This is a targeted string munge —
    prompts that don't match either shape get the guidance block appended
    but no intent-list modification (reviewer must update manually).
    """
    # Pattern 1 (Carbon8 style): pipe-separated list inside JSON schema string
    # Example: "intent": "quote_request|...|out_of_office",
    pipe_marker = 'complaint|'
    if pipe_marker in prompt_text:
        # Find the end of the intent list (next '"' after "complaint|...")
        idx = prompt_text.find('"intent":')
        if idx != -1:
            quote1 = prompt_text.find('"', idx + len('"intent":'))
            quote2 = prompt_text.find('"', quote1 + 1)
            if quote1 != -1 and quote2 != -1:
                current_list = prompt_text[quote1 + 1:quote2]
                for intent in NEW_INTENTS:
                    if intent not in current_list:
                        current_list = current_list + '|' + intent
                return prompt_text[:quote1 + 1] + current_list + prompt_text[quote2:] + NEW_INTENT_GUIDANCE

    # Pattern 2 (global default): Python/JSON array with comma-separated values
    # Example: ["action_required", "fyi_update", ..., "other"]
    array_marker = '"complaint",'
    if array_marker in prompt_text:
        # Find the closing bracket of the intent array
        # Look for '"other"]' pattern (common closing) or '"other", ' then ']'
        end_markers = ['"other"]', '"other"\n  ]', '"other" ]']
        for m in end_markers:
            if m in prompt_text:
                # Insert new intents just before the closing bracket
                new_items = ', ' + ', '.join(f'"{i}"' for i in NEW_INTENTS)
                replacement = m.replace('"other"', '"other"' + new_items)
                return prompt_text.replace(m, replacement, 1) + NEW_INTENT_GUIDANCE

    # If neither pattern matches, just append the guidance — human can fix
    # the intent list manually via admin UI.
    return prompt_text + NEW_INTENT_GUIDANCE + (
        "\n\n# TODO: add the 3 new intents to this prompt's intent list manually — "
        "auto-update couldn't find a known pattern.\n"
    )


def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(2)

    conn = psycopg2.connect(url, application_name="prompt_intent_additions")
    cur = conn.cursor()

    # Target all email_analysis_user prompts (where the intent list lives)
    cur.execute("""
        SELECT id, client_id, prompt_text
        FROM ai_prompt_config
        WHERE prompt_key = 'email_analysis_user' AND is_active = TRUE
    """)
    rows = cur.fetchall()

    updated = 0
    skipped_up_to_date = 0
    for row_id, client_id, prompt_text in rows:
        if not _prompt_needs_update(prompt_text):
            skipped_up_to_date += 1
            print(f"  [skip] {client_id}: already contains all 3 new intents")
            continue

        new_text = _expand_intent_list(prompt_text)
        # version is a TEXT column (e.g. 'v1.4'). Append a marker rather than
        # incrementing — preserves the existing semver-ish convention without
        # parsing strings unsafely.
        cur.execute("""
            UPDATE ai_prompt_config
            SET prompt_text = %s,
                version = version || '+intents3',
                updated_at = NOW()
            WHERE id = %s
        """, (new_text, row_id))
        updated += 1
        print(f"  [update] {client_id}: +{len(new_text) - len(prompt_text)} chars, intents added")

    conn.commit()
    print(f"\n{updated} prompt(s) updated, {skipped_up_to_date} already current")

    # Invalidate AI prompt cache so the next analysis pass picks up changes
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"), decode_responses=True)
        # Match the key pattern the loader uses
        for key in r.scan_iter("ai_prompt:*"):
            r.delete(key)
        print("AI prompt cache invalidated.")
    except Exception as e:
        print(f"Cache invalidation skipped: {e}")

    conn.close()


if __name__ == "__main__":
    main()
