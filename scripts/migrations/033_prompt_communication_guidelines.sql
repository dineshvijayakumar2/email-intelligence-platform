-- ============================================================================
-- Migration 033: Add communication guidelines to AI prompt templates
-- ============================================================================
-- Purpose: Prepend a "Communication Guidelines" block to all global AI prompt
--          templates. Updates existing seeded DB rows so the change takes effect
--          immediately without requiring a re-seed or playground edit.
--
-- Safety:
--   - Only updates rows where client_id IS NULL (global defaults, not customisations)
--   - Idempotent: skips rows that already contain the guidelines block
--   - Bumps version on each updated row
-- ============================================================================

DO $$
DECLARE
    v_guidelines TEXT := E'COMMUNICATION GUIDELINES:\n'
        'Write as a trusted senior adviser — commercially grounded, outcome-focused, direct.\n'
        '- Lead with what matters: revenue at risk, relationships cooling, timing windows, unresolved issues.\n'
        '- Frame every signal as a consequence: what happens if acted on, what happens if ignored.\n'
        '- Be precise — short sentences, clear thinking, no filler phrases, no superlatives or marketing language.\n'
        '- Treat account silences, reorder gaps, and campaign timing windows as deliberate business signals.\n\n';
BEGIN

    -- email_analysis_system (v1.3 → v1.4)
    UPDATE ai_prompt_config
    SET
        prompt_text = v_guidelines || prompt_text,
        version = 'v1.4',
        description = COALESCE(description, '') || ' [v1.4: communication guidelines]'
    WHERE prompt_key = 'email_analysis_system'
      AND client_id IS NULL
      AND prompt_text NOT LIKE '%COMMUNICATION GUIDELINES%';

    -- daily_digest (v2.0 → v2.1)
    UPDATE ai_prompt_config
    SET
        prompt_text = v_guidelines || prompt_text,
        version = 'v2.1',
        description = COALESCE(description, '') || ' [v2.1: communication guidelines]'
    WHERE prompt_key = 'daily_digest'
      AND client_id IS NULL
      AND prompt_text NOT LIKE '%COMMUNICATION GUIDELINES%';

    -- weekly_digest (v2.0 → v2.1)
    UPDATE ai_prompt_config
    SET
        prompt_text = v_guidelines || prompt_text,
        version = 'v2.1',
        description = COALESCE(description, '') || ' [v2.1: communication guidelines]'
    WHERE prompt_key = 'weekly_digest'
      AND client_id IS NULL
      AND prompt_text NOT LIKE '%COMMUNICATION GUIDELINES%';

    -- strategic_digest (v2.0 → v2.1)
    UPDATE ai_prompt_config
    SET
        prompt_text = v_guidelines || prompt_text,
        version = 'v2.1',
        description = COALESCE(description, '') || ' [v2.1: communication guidelines]'
    WHERE prompt_key = 'strategic_digest'
      AND client_id IS NULL
      AND prompt_text NOT LIKE '%COMMUNICATION GUIDELINES%';

    -- insight_company
    UPDATE ai_prompt_config
    SET
        prompt_text = v_guidelines || prompt_text,
        version = 'v1.1',
        description = COALESCE(description, '') || ' [v1.1: communication guidelines]'
    WHERE prompt_key = 'insight_company'
      AND client_id IS NULL
      AND prompt_text NOT LIKE '%COMMUNICATION GUIDELINES%';

    -- insight_contact
    UPDATE ai_prompt_config
    SET
        prompt_text = v_guidelines || prompt_text,
        version = 'v1.1',
        description = COALESCE(description, '') || ' [v1.1: communication guidelines]'
    WHERE prompt_key = 'insight_contact'
      AND client_id IS NULL
      AND prompt_text NOT LIKE '%COMMUNICATION GUIDELINES%';

    -- insight_thread
    UPDATE ai_prompt_config
    SET
        prompt_text = v_guidelines || prompt_text,
        version = 'v1.1',
        description = COALESCE(description, '') || ' [v1.1: communication guidelines]'
    WHERE prompt_key = 'insight_thread'
      AND client_id IS NULL
      AND prompt_text NOT LIKE '%COMMUNICATION GUIDELINES%';

END $$;

-- Verify updates
SELECT prompt_key, version, left(prompt_text, 60) AS prompt_preview
FROM ai_prompt_config
WHERE client_id IS NULL
  AND prompt_key IN (
    'email_analysis_system', 'daily_digest', 'weekly_digest',
    'strategic_digest', 'insight_company', 'insight_contact', 'insight_thread'
  )
ORDER BY prompt_key;
