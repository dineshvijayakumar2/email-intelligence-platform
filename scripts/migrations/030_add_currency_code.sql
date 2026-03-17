-- Migration 030: Per-client currency code (like timezone)
-- Allows each client to display financial figures in their local currency.
-- Default: AUD (Australian Dollar) — matches the target market.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS currency_code TEXT NOT NULL DEFAULT 'AUD';

-- Seed existing rows with AUD
UPDATE clients SET currency_code = 'AUD' WHERE currency_code IS NULL OR currency_code = '';

COMMENT ON COLUMN clients.currency_code IS
    'ISO 4217 currency code for formatting financial figures (e.g. AUD, USD, GBP). '
    'Controls both the currency symbol and locale formatting throughout the platform.';
