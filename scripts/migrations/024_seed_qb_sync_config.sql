-- Migration: 024_seed_qb_sync_config.sql
-- Purpose: Seed the qb_sync_config row for production with verified Carbon8 field mappings.
--          user_token_encrypted is left blank — go to QB Config page and enter the token to activate sync.
-- Date: March 2026

INSERT INTO qb_sync_config (
    client_id,
    realm_hostname,
    app_id,
    user_token_encrypted,
    customers_table_id,
    contacts_table_id,
    quotes_table_id,
    jobs_table_id,
    sales_line_items_table_id,
    field_mappings,
    sync_interval_hours,
    is_active,
    created_at,
    updated_at
)
SELECT
    id,                          -- Carbon8 client ID
    'dc.quickbase.com',
    'buzfemk4f',
    '',                          -- blank token — enter via QB Config page to activate
    'buzhzbv39',
    'bu4ctqehy',
    'buz9p6tzu',
    'buziry2ri',
    'bu4cwdinf',
    '{
        "customers": {
            "3": "qb_record_id", "6": "customer_code", "7": "customer_name",
            "9": "active", "16": "account_manager", "17": "customer_tier",
            "36": "recency_days", "59": "industry", "67": "customer_status",
            "68": "days_since_last_invoice", "101": "total_invoiced",
            "103": "invoiced_ty", "104": "invoiced_ly"
        },
        "contacts": {
            "3": "qb_record_id", "7": "qb_customer_id", "11": "first_name",
            "12": "surname", "13": "phone", "15": "email", "16": "active",
            "25": "quotes_accepted_count", "27": "most_recent_quote_date",
            "53": "contact_recency_days"
        },
        "quotes": {
            "3": "qb_record_id", "7": "quote_no", "8": "qb_customer_id",
            "9": "quote_am_name", "12": "sell_ex_tax", "13": "date_created",
            "14": "date_accepted", "36": "category", "40": "contact_name",
            "41": "contact_email", "51": "job_no", "57": "has_job",
            "65": "quantity", "67": "kinds", "68": "total_quantity"
        },
        "jobs": {
            "3": "qb_record_id", "7": "job_no", "9": "qb_customer_id",
            "10": "quote_no", "11": "retail_sale", "17": "invoiced_margin",
            "18": "margin_pct", "21": "factory_rush_level", "22": "due_date",
            "23": "accepted_date", "24": "job_status", "62": "pieces_ordered",
            "63": "kinds_ordered", "64": "total_qty_ordered"
        },
        "sales_line_items": {
            "3": "qb_record_id", "7": "invoice_id", "9": "job_am_name",
            "11": "invoice_no", "12": "job_no", "16": "customer_name",
            "17": "qb_customer_id", "19": "inv_date", "21": "subtotal",
            "22": "total", "24": "job_title", "56": "product_group", "60": "industry"
        }
    }'::jsonb,
    NULL,       -- manual sync mode
    false,      -- inactive until token is set
    NOW(),
    NOW()
FROM clients
WHERE client_name = 'Carbon8'
ON CONFLICT (client_id) DO NOTHING;
