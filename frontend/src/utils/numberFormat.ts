/**
 * Number Format Utility — per-client currency formatting.
 *
 * Mirrors the backend number_format.py pattern: reads currency_code from the
 * client record and formats financial figures consistently throughout the UI.
 *
 * Usage:
 *   import { formatCurrency, formatCurrencyCompact } from '../utils/numberFormat';
 *
 *   formatCurrency(123456, 'AUD')           // "$123,456"
 *   formatCurrency(123456.78, 'AUD', 2)     // "$123,456.78"
 *   formatCurrencyCompact(1234567, 'AUD')   // "$1.2M"
 */

/** Supported ISO 4217 currency codes and their display metadata. */
const CURRENCY_META: Record<string, { symbol: string; locale: string }> = {
  AUD: { symbol: '$', locale: 'en-AU' },
  USD: { symbol: '$', locale: 'en-US' },
  NZD: { symbol: '$', locale: 'en-NZ' },
  CAD: { symbol: '$', locale: 'en-CA' },
  SGD: { symbol: '$', locale: 'en-SG' },
  HKD: { symbol: '$', locale: 'en-HK' },
  GBP: { symbol: '£', locale: 'en-GB' },
  EUR: { symbol: '€', locale: 'de-DE' },
  JPY: { symbol: '¥', locale: 'ja-JP' },
  INR: { symbol: '₹', locale: 'en-IN' },
};

const DEFAULT_CURRENCY = 'AUD';

function getMeta(currencyCode: string) {
  return CURRENCY_META[currencyCode?.toUpperCase()] ?? CURRENCY_META[DEFAULT_CURRENCY];
}

/**
 * Format a number as a currency string.
 *
 * @param amount       Numeric value (null/undefined → 'N/A')
 * @param currencyCode ISO 4217 code, e.g. 'AUD'
 * @param decimals     Decimal places (default: 0)
 * @param includeCode  Prefix with code label, e.g. 'AUD $123,456' (useful for
 *                     tables where multiple currencies might appear)
 */
export function formatCurrency(
  amount: number | null | undefined,
  currencyCode: string = DEFAULT_CURRENCY,
  decimals = 0,
  includeCode = false,
): string {
  if (amount == null) return 'N/A';
  const meta = getMeta(currencyCode);
  const formatted = new Intl.NumberFormat(meta.locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(amount);
  const result = `${meta.symbol}${formatted}`;
  return includeCode ? `${currencyCode.toUpperCase()} ${result}` : result;
}

/**
 * Compact format for large numbers in summary cards: $1.2M, $345K, $12
 */
export function formatCurrencyCompact(
  amount: number | null | undefined,
  currencyCode: string = DEFAULT_CURRENCY,
): string {
  if (amount == null) return 'N/A';
  const meta = getMeta(currencyCode);
  const abs = Math.abs(amount);
  let value: number;
  let suffix: string;
  if (abs >= 1_000_000) {
    value = amount / 1_000_000;
    suffix = 'M';
  } else if (abs >= 1_000) {
    value = amount / 1_000;
    suffix = 'K';
  } else {
    return formatCurrency(amount, currencyCode, 0);
  }
  const formatted = new Intl.NumberFormat(meta.locale, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(value);
  return `${meta.symbol}${formatted}${suffix}`;
}

/**
 * Format a plain number with locale-correct thousand separators.
 * Always uses en-AU format (123,456) regardless of browser locale.
 * Use this instead of .toLocaleString() to avoid Indian format (1,23,456).
 */
export function formatNumber(value: number | null | undefined): string {
  if (value == null) return '0';
  return new Intl.NumberFormat('en-AU').format(value);
}

/** Options list for the currency selector in the settings page. */
export const CURRENCY_OPTIONS = [
  { label: 'AUD — Australian Dollar ($)', value: 'AUD' },
  { label: 'USD — US Dollar ($)', value: 'USD' },
  { label: 'NZD — New Zealand Dollar ($)', value: 'NZD' },
  { label: 'GBP — British Pound (£)', value: 'GBP' },
  { label: 'EUR — Euro (€)', value: 'EUR' },
  { label: 'SGD — Singapore Dollar ($)', value: 'SGD' },
  { label: 'HKD — Hong Kong Dollar ($)', value: 'HKD' },
  { label: 'CAD — Canadian Dollar ($)', value: 'CAD' },
  { label: 'JPY — Japanese Yen (¥)', value: 'JPY' },
  { label: 'INR — Indian Rupee (₹)', value: 'INR' },
];