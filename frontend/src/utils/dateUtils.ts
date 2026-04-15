/**
 * Centralized date formatting utilities.
 *
 * All backend dates arrive as ISO 8601 UTC strings (e.g. "2026-03-09T15:42:30+00:00").
 * These helpers convert them to the user's local timezone for display, using
 * Australian English locale (en-AU) so month/day order stays consistent
 * regardless of the viewer's browser locale.
 */

import { LOCALE } from '../config';

// ---------------------------------------------------------------------------
// Core formatters — all output in the browser's local timezone, en-AU format
// ---------------------------------------------------------------------------

/** Full datetime: "9 Mar 2026, 9:12 pm" */
export function formatDateTime(
  dateStr: string | null | undefined
): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleString(LOCALE, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/** Date only: "9 Mar 2026" */
export function formatDate(
  dateStr: string | null | undefined
): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(LOCALE, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/** Short date (no year): "9 Mar" */
export function formatShortDate(
  dateStr: string | null | undefined
): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(LOCALE, {
    month: 'short',
    day: 'numeric',
  });
}

/** Time only: "9:12 pm" */
export function formatTime(
  dateStr: string | null | undefined
): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return '—';
  return date.toLocaleTimeString(LOCALE, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

// ---------------------------------------------------------------------------
// Relative formatters
// ---------------------------------------------------------------------------

/**
 * Relative time for analytics: "Today", "Yesterday", "5d ago", "2w ago", "3mo ago"
 * Replaces the 4 duplicate definitions across services.
 */
export function formatRelativeTime(
  dateStr: string | null | undefined
): string {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return 'Never';

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffDays < 0) return 'Just now'; // future date edge-case
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;
  return `${Math.floor(diffDays / 365)}y ago`;
}

/**
 * Compact relative date for email lists: "Just now", "5m", "2h", "3d", "Mar 9"
 * Replaces the inline function in emails.tsx.
 */
export function formatRelativeDate(
  dateStr: string | null | undefined
): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return '—';

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 7) return `${diffDays}d`;

  return formatShortDate(dateStr);
}

// ---------------------------------------------------------------------------
// Duration formatters
// ---------------------------------------------------------------------------

/** Format seconds into human-readable duration: "2h 15m", "45m", "< 1m" */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return '—';
  if (seconds < 60) return '< 1m';
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

/**
 * Format elapsed time between two ISO dates: "2m 15s", "1h 30m", etc.
 * Useful for processing job durations.
 */
export function formatElapsed(
  startStr: string | null | undefined,
  endStr?: string | null | undefined
): string {
  if (!startStr) return '—';
  const start = new Date(startStr);
  const end = endStr ? new Date(endStr) : new Date();
  if (isNaN(start.getTime())) return '—';

  const diffS = Math.floor((end.getTime() - start.getTime()) / 1000);
  if (diffS < 0) return '—';
  if (diffS < 60) return `${diffS}s`;
  if (diffS < 3600) {
    const m = Math.floor(diffS / 60);
    const s = diffS % 60;
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  }
  const h = Math.floor(diffS / 3600);
  const m = Math.floor((diffS % 3600) / 60);
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

/** Format a Date or ISO string to YYYY-MM-DD for API calls */
export function formatDateForApi(
  date: Date | string | null | undefined
): string {
  if (!date) return '';
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return '';
  // Use local date components so "today" means the user's today
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/**
 * Convert a local YYYY-MM-DD date string to an ISO start-of-day timestamp
 * in the user's local timezone. Useful for digest and analysis date boundaries.
 *
 * Example: "2026-03-09" in IST → "2026-03-08T18:30:00.000Z" (UTC equivalent)
 */
export function localDateToISOStart(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const local = new Date(y, m - 1, d, 0, 0, 0, 0);
  return local.toISOString();
}

/** Convert a local YYYY-MM-DD to end-of-day ISO (23:59:59.999 local → UTC) */
export function localDateToISOEnd(dateStr: string): string {
  const [y, m, d] = dateStr.split('-').map(Number);
  const local = new Date(y, m - 1, d, 23, 59, 59, 999);
  return local.toISOString();
}

/** Get the user's IANA timezone string, e.g. "Asia/Kolkata" */
export function getUserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return 'UTC';
  }
}

/** Get the user's UTC offset in minutes (e.g. -330 for IST = UTC+5:30) */
export function getUtcOffsetMinutes(): number {
  return new Date().getTimezoneOffset();
}
