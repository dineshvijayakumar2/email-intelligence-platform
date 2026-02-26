-- ============================================================================
-- Sprint 2 Migration 012: Backfill Scoring Input Fields
-- ============================================================================
-- Purpose: Populate contact/company fields used by engagement scorer so scores
--          are varied instead of uniform (all contacts=33, all companies=51)
--
-- Root cause: comm_pattern_analyzer.save_patterns() was not sending
--   emails_per_month_avg, last_inbound_at, last_outbound_at, and had wrong
--   field name (engagement_trend vs frequency_trend). These fields stayed NULL,
--   causing the scorer to use neutral fallback values → uniform scores.
--
-- Run After: sprint2_migration_011_fix_analytics_data.sql
-- Duration: 1-2 minutes (depends on data volume)
--
-- Parts:
--   1. Backfill contact last_inbound_at / last_outbound_at
--   2. Backfill contact emails_per_month_avg
--   3. Backfill contact initiation_ratio (from thread data)
--   4. Backfill contact reply_rate (from email data)
--   5. Backfill company avg_emails_per_month
--   6. Fix frequency_trend (was never saved due to field name mismatch)
-- ============================================================================


-- ============================================================================
-- PART 1: Backfill contact last_inbound_at / last_outbound_at
-- ============================================================================
-- These feed into recency scoring (25% weight). Without them, recency_score = 0.

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE customer_contacts cc
    SET
        last_inbound_at = COALESCE(dates.last_in, cc.last_inbound_at),
        last_outbound_at = COALESCE(dates.last_out, cc.last_outbound_at),
        updated_at = NOW()
    FROM (
        SELECT
            customer_contact_id,
            MAX(sent_date) FILTER (WHERE NOT is_outbound) AS last_in,
            MAX(sent_date) FILTER (WHERE is_outbound) AS last_out
        FROM emails
        WHERE customer_contact_id IS NOT NULL
          AND sent_date IS NOT NULL
        GROUP BY customer_contact_id
    ) dates
    WHERE cc.id = dates.customer_contact_id
      AND (cc.last_inbound_at IS NULL OR cc.last_outbound_at IS NULL);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '1/6 Backfilled last_inbound_at/last_outbound_at for % contacts', v_updated;
END $$;


-- ============================================================================
-- PART 2: Backfill contact emails_per_month_avg
-- ============================================================================
-- Feeds into frequency scoring (15% weight). Without it, frequency_score = 0.

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE customer_contacts cc
    SET
        emails_per_month_avg = stats.epm,
        updated_at = NOW()
    FROM (
        SELECT
            customer_contact_id,
            CASE
                WHEN EXTRACT(DAYS FROM (MAX(sent_date) - MIN(sent_date))) < 30
                    THEN COUNT(*)::NUMERIC  -- Less than a month of data: use raw count
                ELSE ROUND(
                    COUNT(*)::NUMERIC /
                    GREATEST(EXTRACT(DAYS FROM (MAX(sent_date) - MIN(sent_date))) / 30.0, 1),
                    2
                )
            END AS epm
        FROM emails
        WHERE customer_contact_id IS NOT NULL
          AND sent_date IS NOT NULL
        GROUP BY customer_contact_id
        HAVING COUNT(*) >= 1
    ) stats
    WHERE cc.id = stats.customer_contact_id
      AND cc.emails_per_month_avg IS NULL;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '2/6 Backfilled emails_per_month_avg for % contacts', v_updated;
END $$;


-- ============================================================================
-- PART 3: Backfill contact initiation_ratio from thread data
-- ============================================================================
-- Feeds into initiation_balance scoring (10% weight). Without it = 50 (neutral).
-- initiation_ratio: 0.0 = they always start, 1.0 = we always start, 0.5 = balanced

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE customer_contacts cc
    SET
        initiation_ratio = ratios.ratio,
        updated_at = NOW()
    FROM (
        SELECT
            ts.customer_contact_id,
            CASE
                WHEN COUNT(*) = 0 THEN 0.5
                ELSE ROUND(
                    COUNT(*) FILTER (WHERE first_sender.is_outbound = TRUE)::NUMERIC /
                    GREATEST(COUNT(*), 1),
                    2
                )
            END AS ratio
        FROM thread_status ts
        JOIN LATERAL (
            SELECT e.is_outbound
            FROM emails e
            WHERE e.thread_id = ts.thread_id
            ORDER BY e.sent_date ASC
            LIMIT 1
        ) first_sender ON TRUE
        WHERE ts.customer_contact_id IS NOT NULL
        GROUP BY ts.customer_contact_id
    ) ratios
    WHERE cc.id = ratios.customer_contact_id
      AND cc.initiation_ratio IS NULL;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '3/6 Backfilled initiation_ratio for % contacts', v_updated;
END $$;


-- ============================================================================
-- PART 4: Backfill contact reply_rate from email data
-- ============================================================================
-- Feeds into reply_rate scoring (15% weight). Without it = 50 (neutral).
-- reply_rate: fraction of their inbound emails that got a reply from us

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE customer_contacts cc
    SET
        reply_rate = rates.rr,
        updated_at = NOW()
    FROM (
        SELECT
            inbound.customer_contact_id,
            CASE
                WHEN inbound.cnt = 0 THEN 0
                ELSE ROUND(
                    LEAST(replies.cnt, inbound.cnt)::NUMERIC / inbound.cnt,
                    2
                )
            END AS rr
        FROM (
            -- Count inbound emails per contact
            SELECT customer_contact_id, COUNT(*) AS cnt
            FROM emails
            WHERE customer_contact_id IS NOT NULL
              AND NOT is_outbound
            GROUP BY customer_contact_id
        ) inbound
        LEFT JOIN (
            -- Count outbound replies per contact (is_reply=true means it's a reply)
            SELECT customer_contact_id, COUNT(*) AS cnt
            FROM emails
            WHERE customer_contact_id IS NOT NULL
              AND is_outbound
              AND is_reply = TRUE
            GROUP BY customer_contact_id
        ) replies ON replies.customer_contact_id = inbound.customer_contact_id
    ) rates
    WHERE cc.id = rates.customer_contact_id
      AND cc.reply_rate IS NULL;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '4/6 Backfilled reply_rate for % contacts', v_updated;
END $$;


-- ============================================================================
-- PART 5: Backfill company avg_emails_per_month
-- ============================================================================
-- Used in company frequency scoring (15% weight). Without it = 0.

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE customer_companies cc
    SET
        avg_emails_per_month = stats.epm,
        updated_at = NOW()
    FROM (
        SELECT
            customer_company_id,
            CASE
                WHEN EXTRACT(DAYS FROM (MAX(sent_date) - MIN(sent_date))) < 30
                    THEN COUNT(*)::NUMERIC
                ELSE ROUND(
                    COUNT(*)::NUMERIC /
                    GREATEST(EXTRACT(DAYS FROM (MAX(sent_date) - MIN(sent_date))) / 30.0, 1),
                    2
                )
            END AS epm
        FROM emails
        WHERE customer_company_id IS NOT NULL
          AND sent_date IS NOT NULL
        GROUP BY customer_company_id
        HAVING COUNT(*) >= 1
    ) stats
    WHERE cc.id = stats.customer_company_id
      AND cc.avg_emails_per_month IS NULL;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '5/6 Backfilled avg_emails_per_month for % companies', v_updated;
END $$;


-- ============================================================================
-- PART 6: Backfill contact frequency_trend
-- ============================================================================
-- Was never saved because code sent 'engagement_trend' (wrong field name).
-- Calculate trend based on email volume in recent vs older periods.

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE customer_contacts cc
    SET
        frequency_trend = trends.trend,
        updated_at = NOW()
    FROM (
        SELECT
            customer_contact_id,
            CASE
                WHEN recent_count = 0 AND older_count = 0 THEN 'inactive'
                WHEN older_count = 0 THEN 'increasing'
                WHEN recent_count = 0 THEN 'declining'
                WHEN recent_count::NUMERIC / GREATEST(older_count, 1) > 1.2 THEN 'increasing'
                WHEN recent_count::NUMERIC / GREATEST(older_count, 1) < 0.8 THEN 'declining'
                ELSE 'stable'
            END AS trend
        FROM (
            SELECT
                customer_contact_id,
                COUNT(*) FILTER (WHERE sent_date >= NOW() - INTERVAL '90 days') AS recent_count,
                COUNT(*) FILTER (WHERE sent_date < NOW() - INTERVAL '90 days') AS older_count
            FROM emails
            WHERE customer_contact_id IS NOT NULL
              AND sent_date IS NOT NULL
            GROUP BY customer_contact_id
        ) counts
    ) trends
    WHERE cc.id = trends.customer_contact_id
      AND cc.frequency_trend IS NULL;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '6/6 Backfilled frequency_trend for % contacts', v_updated;
END $$;


-- ============================================================================
-- DONE
-- ============================================================================
-- After running this migration, re-run extraction (or just the scoring step)
-- to recalculate engagement scores using the newly populated fields.
--
-- Expected impact:
--   - Contacts: scores will vary based on actual email patterns (not all 33)
--   - Companies: scores will vary based on actual recency + frequency (not all 51)
-- ============================================================================
DO $$ BEGIN RAISE NOTICE 'Migration 012 complete: scoring input fields backfilled'; END $$;
