-- 121: distinct_email_categories — server-side DISTINCT for the category filter dropdown.
-- Same class of bug as the data-health missing-days check (migration 120): the endpoint did
-- email_categories.select('category').limit(10000) and deduped client-side, but PostgREST caps
-- at db-max-rows (1000), so it only saw the first 1000 of 412K rows -> dropdown showed 2 of 24
-- real categories. DISTINCT in SQL returns the true set cheaply.

CREATE OR REPLACE FUNCTION distinct_email_categories()
RETURNS jsonb
LANGUAGE sql STABLE
SET search_path = public
AS $$
  SELECT coalesce(jsonb_agg(category ORDER BY category), '[]'::jsonb)
  FROM (
    SELECT DISTINCT category
    FROM email_categories
    WHERE category IS NOT NULL
      AND category NOT LIKE '_meta_%'
  ) s;
$$;

GRANT EXECUTE ON FUNCTION distinct_email_categories() TO anon, authenticated, service_role;
