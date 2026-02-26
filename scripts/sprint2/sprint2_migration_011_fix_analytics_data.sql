-- ============================================================================
-- Sprint 2 Migration 011: Fix Analytics Data (Email Counts, Subjects, Company Stats)
-- ============================================================================
-- Purpose: Fix batch update RPCs to include missing columns, backfill existing data
-- Run After: sprint2_migration_010_incremental_mode.sql
-- Duration: 1-3 minutes (depends on data volume)
--
-- Fixes:
--   1. batch_update_contact_analytics() missing total_emails_sent/received
--   2. batch_update_company_analytics() missing total_emails/inbound/outbound/dates
--   3. thread_status.subject never populated
--   4. thread_status.message_count always 0
--   5. thread_status.customer_contact_id/customer_company_id missing
-- ============================================================================

-- ============================================================================
-- PART 1: Fix batch_update_contact_analytics() — add email count columns
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_update_contact_analytics(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    UPDATE customer_contacts c
    SET
        -- Response time metrics
        avg_response_time_seconds = COALESCE(u.avg_response_time_seconds::INTEGER, c.avg_response_time_seconds),
        their_avg_response_time = COALESCE(u.their_avg_response_time::INTEGER, c.their_avg_response_time),

        -- Thread tracking
        open_thread_count = COALESCE(u.open_thread_count::INTEGER, c.open_thread_count),
        dropped_thread_count = COALESCE(u.dropped_thread_count::INTEGER, c.dropped_thread_count),

        -- Communication patterns
        initiation_ratio = COALESCE(u.initiation_ratio::NUMERIC, c.initiation_ratio),
        reply_rate = COALESCE(u.reply_rate::NUMERIC, c.reply_rate),
        emails_per_month_avg = COALESCE(u.emails_per_month_avg::NUMERIC, c.emails_per_month_avg),
        frequency_trend = COALESCE(u.frequency_trend, c.frequency_trend),
        avg_thread_depth = COALESCE(u.avg_thread_depth::NUMERIC, c.avg_thread_depth),
        last_inbound_at = COALESCE(u.last_inbound_at::TIMESTAMPTZ, c.last_inbound_at),
        last_outbound_at = COALESCE(u.last_outbound_at::TIMESTAMPTZ, c.last_outbound_at),

        -- Email counts (NEW — previously missing)
        total_emails_sent = COALESCE(u.total_emails_sent::INTEGER, c.total_emails_sent),
        total_emails_received = COALESCE(u.total_emails_received::INTEGER, c.total_emails_received),

        -- Contact dates (NEW — previously missing)
        first_contacted_at = COALESCE(u.first_contacted_at::TIMESTAMPTZ, c.first_contacted_at),
        last_contacted_at = COALESCE(u.last_contacted_at::TIMESTAMPTZ, c.last_contacted_at),

        -- Engagement score
        engagement_score = COALESCE(u.engagement_score::INTEGER, c.engagement_score),

        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        contact_id UUID,
        avg_response_time_seconds TEXT,
        their_avg_response_time TEXT,
        open_thread_count TEXT,
        dropped_thread_count TEXT,
        initiation_ratio TEXT,
        reply_rate TEXT,
        emails_per_month_avg TEXT,
        frequency_trend TEXT,
        avg_thread_depth TEXT,
        last_inbound_at TEXT,
        last_outbound_at TEXT,
        total_emails_sent TEXT,
        total_emails_received TEXT,
        first_contacted_at TEXT,
        last_contacted_at TEXT,
        engagement_score TEXT
    )
    WHERE c.id = u.contact_id;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN QUERY SELECT v_updated_count, v_error_count;

EXCEPTION WHEN OTHERS THEN
    v_error_count := 1;
    RETURN QUERY SELECT v_updated_count, v_error_count;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN RAISE NOTICE '1/7 batch_update_contact_analytics updated (added email counts)'; END $$;


-- ============================================================================
-- PART 2: Fix batch_update_company_analytics() — add email stats + dates
-- ============================================================================

CREATE OR REPLACE FUNCTION batch_update_company_analytics(
    updates JSONB
) RETURNS TABLE (
    updated_count INTEGER,
    error_count INTEGER
) AS $$
DECLARE
    v_updated_count INTEGER := 0;
    v_error_count INTEGER := 0;
BEGIN
    UPDATE customer_companies c
    SET
        -- Contact aggregates
        contact_count = COALESCE(u.contact_count::INTEGER, c.contact_count),
        decision_maker_count = COALESCE(u.decision_maker_count::INTEGER, c.decision_maker_count),
        highest_seniority = COALESCE(u.highest_seniority, c.highest_seniority),

        -- Thread tracking
        open_thread_count = COALESCE(u.open_thread_count::INTEGER, c.open_thread_count),
        dropped_thread_count = COALESCE(u.dropped_thread_count::INTEGER, c.dropped_thread_count),

        -- Communication health
        avg_response_time_seconds = COALESCE(u.avg_response_time_seconds::INTEGER, c.avg_response_time_seconds),
        avg_emails_per_month = COALESCE(u.avg_emails_per_month::NUMERIC, c.avg_emails_per_month),
        frequency_trend = COALESCE(u.frequency_trend, c.frequency_trend),
        relationship_status = COALESCE(u.relationship_status, c.relationship_status),
        communication_health = COALESCE(u.communication_health, c.communication_health),

        -- Email stats (NEW — previously missing)
        total_emails = COALESCE(u.total_emails::INTEGER, c.total_emails),
        total_inbound = COALESCE(u.total_inbound::INTEGER, c.total_inbound),
        total_outbound = COALESCE(u.total_outbound::INTEGER, c.total_outbound),
        first_contact_date = COALESCE(u.first_contact_date::TIMESTAMPTZ, c.first_contact_date),
        last_contact_date = COALESCE(u.last_contact_date::TIMESTAMPTZ, c.last_contact_date),

        -- Engagement score
        engagement_score = COALESCE(u.engagement_score::INTEGER, c.engagement_score),

        updated_at = NOW()
    FROM jsonb_to_recordset(updates) AS u(
        company_id UUID,
        contact_count TEXT,
        decision_maker_count TEXT,
        highest_seniority TEXT,
        open_thread_count TEXT,
        dropped_thread_count TEXT,
        avg_response_time_seconds TEXT,
        avg_emails_per_month TEXT,
        frequency_trend TEXT,
        relationship_status TEXT,
        communication_health TEXT,
        total_emails TEXT,
        total_inbound TEXT,
        total_outbound TEXT,
        first_contact_date TEXT,
        last_contact_date TEXT,
        engagement_score TEXT
    )
    WHERE c.id = u.company_id;

    GET DIAGNOSTICS v_updated_count = ROW_COUNT;
    RETURN QUERY SELECT v_updated_count, v_error_count;

EXCEPTION WHEN OTHERS THEN
    v_error_count := 1;
    RETURN QUERY SELECT v_updated_count, v_error_count;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN RAISE NOTICE '2/7 batch_update_company_analytics updated (added email stats + dates)'; END $$;


-- ============================================================================
-- PART 3: Backfill contact email counts from emails table
-- ============================================================================

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE customer_contacts cc
    SET
        total_emails_received = counts.inbound,
        total_emails_sent = counts.outbound,
        updated_at = NOW()
    FROM (
        SELECT
            customer_contact_id,
            COUNT(*) FILTER (WHERE NOT is_outbound) AS inbound,
            COUNT(*) FILTER (WHERE is_outbound) AS outbound
        FROM emails
        WHERE customer_contact_id IS NOT NULL
        GROUP BY customer_contact_id
    ) counts
    WHERE cc.id = counts.customer_contact_id;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '3/8 Backfilled email counts for % contacts', v_updated;
END $$;


-- ============================================================================
-- PART 3b: Backfill contact first_contacted_at / last_contacted_at
-- ============================================================================

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE customer_contacts cc
    SET
        first_contacted_at = COALESCE(dates.first_date, cc.first_contacted_at),
        last_contacted_at = COALESCE(dates.last_date, cc.last_contacted_at),
        updated_at = NOW()
    FROM (
        SELECT
            customer_contact_id,
            MIN(sent_date) AS first_date,
            MAX(sent_date) AS last_date
        FROM emails
        WHERE customer_contact_id IS NOT NULL
          AND sent_date IS NOT NULL
        GROUP BY customer_contact_id
    ) dates
    WHERE cc.id = dates.customer_contact_id;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '3b/8 Backfilled contact dates for % contacts', v_updated;
END $$;


-- ============================================================================
-- PART 4: Backfill company email stats from emails table
-- ============================================================================

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE customer_companies cc
    SET
        total_emails = stats.total,
        total_inbound = stats.inbound,
        total_outbound = stats.outbound,
        first_contact_date = COALESCE(stats.first_date, cc.first_contact_date),
        last_contact_date = COALESCE(stats.last_date, cc.last_contact_date),
        updated_at = NOW()
    FROM (
        SELECT
            customer_company_id,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE NOT is_outbound) AS inbound,
            COUNT(*) FILTER (WHERE is_outbound) AS outbound,
            MIN(sent_date) AS first_date,
            MAX(sent_date) AS last_date
        FROM emails
        WHERE customer_company_id IS NOT NULL
        GROUP BY customer_company_id
    ) stats
    WHERE cc.id = stats.customer_company_id;

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '4/7 Backfilled email stats for % companies', v_updated;
END $$;


-- ============================================================================
-- PART 5: Backfill thread subjects from emails table
-- ============================================================================

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE thread_status ts
    SET subject = e.subject
    FROM (
        SELECT DISTINCT ON (thread_id)
            thread_id,
            subject
        FROM emails
        WHERE thread_id IS NOT NULL
          AND subject IS NOT NULL
          AND subject != ''
        ORDER BY thread_id, sent_date ASC
    ) e
    WHERE ts.thread_id = e.thread_id
      AND (ts.subject IS NULL OR ts.subject = '');

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '5/7 Backfilled subjects for % threads', v_updated;
END $$;


-- ============================================================================
-- PART 6: Backfill thread message_count from emails table
-- ============================================================================

DO $$
DECLARE
    v_updated INTEGER;
BEGIN
    UPDATE thread_status ts
    SET message_count = counts.msg_count
    FROM (
        SELECT thread_id, COUNT(*) AS msg_count
        FROM emails
        WHERE thread_id IS NOT NULL
        GROUP BY thread_id
    ) counts
    WHERE ts.thread_id = counts.thread_id
      AND (ts.message_count IS NULL OR ts.message_count = 0);

    GET DIAGNOSTICS v_updated = ROW_COUNT;
    RAISE NOTICE '6/7 Backfilled message_count for % threads', v_updated;
END $$;


-- ============================================================================
-- PART 7: Backfill thread customer_contact_id and customer_company_id
-- ============================================================================

DO $$
DECLARE
    v_contacts_updated INTEGER;
    v_companies_updated INTEGER;
BEGIN
    -- Fill customer_contact_id from primary_contact_id where missing
    UPDATE thread_status
    SET customer_contact_id = primary_contact_id
    WHERE customer_contact_id IS NULL
      AND primary_contact_id IS NOT NULL;
    GET DIAGNOSTICS v_contacts_updated = ROW_COUNT;

    -- Fill customer_company_id from primary_company_id where missing
    UPDATE thread_status
    SET customer_company_id = primary_company_id
    WHERE customer_company_id IS NULL
      AND primary_company_id IS NOT NULL;
    GET DIAGNOSTICS v_companies_updated = ROW_COUNT;

    RAISE NOTICE '7/7 Backfilled thread contacts (%) and companies (%)',
        v_contacts_updated, v_companies_updated;
END $$;


-- ============================================================================
-- VERIFICATION
-- ============================================================================

DO $$
DECLARE
    v_contacts_with_emails INTEGER;
    v_companies_with_emails INTEGER;
    v_threads_with_subjects INTEGER;
    v_threads_with_messages INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_contacts_with_emails
    FROM customer_contacts
    WHERE total_emails_sent > 0 OR total_emails_received > 0;

    SELECT COUNT(*) INTO v_companies_with_emails
    FROM customer_companies
    WHERE total_emails > 0;

    SELECT COUNT(*) INTO v_threads_with_subjects
    FROM thread_status
    WHERE subject IS NOT NULL AND subject != '';

    SELECT COUNT(*) INTO v_threads_with_messages
    FROM thread_status
    WHERE message_count > 0;

    RAISE NOTICE '====================================';
    RAISE NOTICE 'Migration 011 — Verification';
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Contacts with email counts: %', v_contacts_with_emails;
    RAISE NOTICE 'Companies with email stats:  %', v_companies_with_emails;
    RAISE NOTICE 'Threads with subjects:       %', v_threads_with_subjects;
    RAISE NOTICE 'Threads with message count:  %', v_threads_with_messages;
    RAISE NOTICE '====================================';
END $$;
