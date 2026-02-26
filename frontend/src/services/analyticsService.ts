/**
 * Analytics Service — 30 endpoint wrappers for Sprint 2 analytics API
 *
 * Follows dashboardService.ts patterns: TTL cache, in-flight dedup, error fallbacks.
 * All methods return typed Promises and never throw to UI.
 */

import api from './apiClient';
import type {
  // Extraction
  ExtractionJobCreate,
  ExtractionJobResponse,
  ExtractionJobDetail,
  ExtractionJobListResponse,
  ExtractionProgressResponse,
  ExtractionJobFilterParams,
  // Contacts
  ContactAnalytics,
  ContactAnalyticsListResponse,
  TopEngagedContact,
  AtRiskContact,
  ContactTypeGrouping,
  ContactFilterParams,
  // Companies
  CompanyAnalytics,
  CompanyAnalyticsListResponse,
  TopEngagedCompany,
  AtRiskCompany,
  EngagementStatusGrouping,
  CompanyFilterParams,
  // Threads
  ThreadStatusListResponse,
  OverdueThread,
  ThreadStatusCount,
  ThreadFilterParams,
  // Response Times
  ResponseTimeListResponse,
  ResponseTimeStats,
  SlowestResponder,
  // Communication Patterns
  InitiationPattern,
  FrequencyPattern,
  EngagementTrend,
  CommunicationPattern,
  // Dashboard
  DashboardSummary,
  ClientSummary,
  PaginationParams,
} from '../types/analytics';

const API_PREFIX = '/v1/analytics';

// ============================================================================
// CACHE INFRASTRUCTURE
// ============================================================================

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

const CACHE_TTL_SHORT = 30_000;   // 30s for lists/dashboard
const CACHE_TTL_LONG = 60_000;    // 60s for aggregations

const cache: Record<string, CacheEntry<any>> = {};

function getCached<T>(key: string, ttl: number): T | null {
  const entry = cache[key];
  if (entry && (Date.now() - entry.timestamp) < ttl) {
    return entry.data as T;
  }
  return null;
}

function setCache<T>(key: string, data: T): void {
  cache[key] = { data, timestamp: Date.now() };
}

// In-flight dedup map
const inFlight: Record<string, Promise<any>> = {};

async function dedupedFetch<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  if (inFlight[key]) {
    return inFlight[key] as Promise<T>;
  }
  inFlight[key] = fetcher().finally(() => { delete inFlight[key]; });
  return inFlight[key] as Promise<T>;
}

function buildQuery(params: Record<string, any>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') {
      parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
    }
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

// ============================================================================
// A) EXTRACTION CONTROL (5 endpoints)
// ============================================================================

export const extractionApi = {
  /** POST /extraction/run — Trigger a new extraction job */
  async run(params: ExtractionJobCreate): Promise<ExtractionJobResponse | null> {
    try {
      return await api.post<ExtractionJobResponse>(`${API_PREFIX}/extraction/run`, params, { timeout: 15000 });
    } catch (error: any) {
      console.error('[Analytics] Failed to start extraction:', error?.message);
      return null;
    }
  },

  /** GET /extraction/jobs/{job_id} — Get job details */
  async getJob(jobId: string): Promise<ExtractionJobDetail | null> {
    try {
      return await api.get<ExtractionJobDetail>(`${API_PREFIX}/extraction/jobs/${jobId}`, { timeout: 10000 });
    } catch (error: any) {
      console.error('[Analytics] Failed to get job:', error?.message);
      return null;
    }
  },

  /** GET /extraction/jobs — List extraction jobs */
  async listJobs(params: ExtractionJobFilterParams = {}): Promise<ExtractionJobListResponse> {
    const qs = buildQuery(params);
    const key = `extraction-jobs${qs}`;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<ExtractionJobListResponse>(`${API_PREFIX}/extraction/jobs${qs}`, { timeout: 10000 })
      );
      return result || { jobs: [], total: 0 };
    } catch {
      return { jobs: [], total: 0 };
    }
  },

  /** POST /extraction/jobs/{job_id}/cancel — Cancel a running job */
  async cancelJob(jobId: string): Promise<{ message: string } | null> {
    try {
      return await api.post<{ message: string }>(`${API_PREFIX}/extraction/jobs/${jobId}/cancel`, {}, { timeout: 10000 });
    } catch (error: any) {
      console.error('[Analytics] Failed to cancel job:', error?.message);
      return null;
    }
  },

  /** GET /extraction/progress/{job_id} — Real-time progress from Redis */
  async getProgress(jobId: string): Promise<ExtractionProgressResponse | null> {
    try {
      return await api.get<ExtractionProgressResponse>(`${API_PREFIX}/extraction/progress/${jobId}`, { timeout: 5000 });
    } catch {
      return null;
    }
  },
};

// ============================================================================
// B) CONTACT ANALYTICS (6 endpoints)
// ============================================================================

export const contactsApi = {
  /** GET /contacts — Paginated contacts with engagement analytics */
  async list(params: ContactFilterParams = {}): Promise<ContactAnalyticsListResponse> {
    const qs = buildQuery(params);
    const key = `contacts${qs}`;
    const cached = getCached<ContactAnalyticsListResponse>(key, CACHE_TTL_SHORT);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<ContactAnalyticsListResponse>(`${API_PREFIX}/contacts${qs}`, { timeout: 10000 })
      );
      const data = result || { contacts: [], total: 0 };
      setCache(key, data);
      return data;
    } catch {
      return { contacts: [], total: 0 };
    }
  },

  /** GET /contacts/{contactId} — Single contact with full analytics */
  async getDetail(contactId: string): Promise<ContactAnalytics | null> {
    try {
      return await api.get<ContactAnalytics>(`${API_PREFIX}/contacts/${contactId}`, { timeout: 10000 });
    } catch {
      return null;
    }
  },

  /** GET /contacts/top-engaged — Top engaged contacts */
  async topEngaged(clientId?: string, limit: number = 10): Promise<TopEngagedContact[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    const key = `contacts-top${qs}`;
    const cached = getCached<TopEngagedContact[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<TopEngagedContact[]>(`${API_PREFIX}/contacts/top-engaged${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /contacts/at-risk — At-risk contacts */
  async atRisk(clientId?: string, daysThreshold: number = 60, limit: number = 50): Promise<AtRiskContact[]> {
    const qs = buildQuery({ client_id: clientId, days_threshold: daysThreshold, limit });
    const key = `contacts-atrisk${qs}`;
    const cached = getCached<AtRiskContact[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<AtRiskContact[]>(`${API_PREFIX}/contacts/at-risk${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /contacts/decision-makers — Decision maker contacts */
  async decisionMakers(clientId?: string, limit: number = 100, offset: number = 0): Promise<ContactAnalyticsListResponse> {
    const qs = buildQuery({ client_id: clientId, limit, offset });
    const key = `contacts-dm${qs}`;
    const cached = getCached<ContactAnalyticsListResponse>(key, CACHE_TTL_SHORT);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<ContactAnalyticsListResponse>(`${API_PREFIX}/contacts/decision-makers${qs}`, { timeout: 10000 })
      );
      const data = result || { contacts: [], total: 0 };
      setCache(key, data);
      return data;
    } catch {
      return { contacts: [], total: 0 };
    }
  },

  /** GET /contacts/by-type — Contacts grouped by type */
  async byType(clientId?: string): Promise<ContactTypeGrouping[]> {
    const qs = buildQuery({ client_id: clientId });
    const key = `contacts-bytype${qs}`;
    const cached = getCached<ContactTypeGrouping[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<ContactTypeGrouping[]>(`${API_PREFIX}/contacts/by-type${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },
};

// ============================================================================
// C) COMPANY ANALYTICS (5 endpoints)
// ============================================================================

export const companiesApi = {
  /** GET /companies — Paginated companies with analytics */
  async list(params: CompanyFilterParams = {}): Promise<CompanyAnalyticsListResponse> {
    const qs = buildQuery(params);
    const key = `companies${qs}`;
    const cached = getCached<CompanyAnalyticsListResponse>(key, CACHE_TTL_SHORT);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<CompanyAnalyticsListResponse>(`${API_PREFIX}/companies${qs}`, { timeout: 10000 })
      );
      const data = result || { companies: [], total: 0 };
      setCache(key, data);
      return data;
    } catch {
      return { companies: [], total: 0 };
    }
  },

  /** GET /companies/{companyId} — Single company with full analytics */
  async getDetail(companyId: string): Promise<CompanyAnalytics | null> {
    try {
      return await api.get<CompanyAnalytics>(`${API_PREFIX}/companies/${companyId}`, { timeout: 10000 });
    } catch {
      return null;
    }
  },

  /** GET /companies/top-engaged — Top engaged companies */
  async topEngaged(clientId?: string, limit: number = 10): Promise<TopEngagedCompany[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    const key = `companies-top${qs}`;
    const cached = getCached<TopEngagedCompany[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<TopEngagedCompany[]>(`${API_PREFIX}/companies/top-engaged${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /companies/at-risk — At-risk companies */
  async atRisk(clientId?: string, daysThreshold: number = 90, limit: number = 50): Promise<AtRiskCompany[]> {
    const qs = buildQuery({ client_id: clientId, days_threshold: daysThreshold, limit });
    const key = `companies-atrisk${qs}`;
    const cached = getCached<AtRiskCompany[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<AtRiskCompany[]>(`${API_PREFIX}/companies/at-risk${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /companies/by-engagement — Companies by engagement status */
  async byEngagement(clientId?: string): Promise<EngagementStatusGrouping[]> {
    const qs = buildQuery({ client_id: clientId });
    const key = `companies-byeng${qs}`;
    const cached = getCached<EngagementStatusGrouping[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<EngagementStatusGrouping[]>(`${API_PREFIX}/companies/by-engagement${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },
};

// ============================================================================
// D) THREAD ANALYTICS (4 endpoints)
// ============================================================================

export const threadsApi = {
  /** GET /threads/status — Paginated thread statuses */
  async list(params: ThreadFilterParams = {}): Promise<ThreadStatusListResponse> {
    const qs = buildQuery(params);
    const key = `threads${qs}`;
    const cached = getCached<ThreadStatusListResponse>(key, CACHE_TTL_SHORT);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<ThreadStatusListResponse>(`${API_PREFIX}/threads/status${qs}`, { timeout: 10000 })
      );
      const data = result || { threads: [], total: 0 };
      setCache(key, data);
      return data;
    } catch {
      return { threads: [], total: 0 };
    }
  },

  /** GET /threads/overdue — Overdue threads */
  async overdue(clientId?: string, limit: number = 50): Promise<OverdueThread[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    const key = `threads-overdue${qs}`;
    const cached = getCached<OverdueThread[]>(key, CACHE_TTL_SHORT);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<OverdueThread[]>(`${API_PREFIX}/threads/overdue${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /threads/by-status — Count threads by status */
  async byStatus(clientId?: string): Promise<ThreadStatusCount[]> {
    const qs = buildQuery({ client_id: clientId });
    const key = `threads-bystatus${qs}`;
    const cached = getCached<ThreadStatusCount[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<ThreadStatusCount[]>(`${API_PREFIX}/threads/by-status${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /threads/by-contact/{contactId} — Threads for a contact */
  async byContact(contactId: string, limit: number = 100, offset: number = 0): Promise<ThreadStatusListResponse> {
    const qs = buildQuery({ limit, offset });
    try {
      const result = await api.get<ThreadStatusListResponse>(
        `${API_PREFIX}/threads/by-contact/${contactId}${qs}`, { timeout: 10000 }
      );
      return result || { threads: [], total: 0 };
    } catch {
      return { threads: [], total: 0 };
    }
  },
};

// ============================================================================
// E) RESPONSE TIME ANALYTICS (4 endpoints)
// ============================================================================

export const responseTimesApi = {
  /** GET /response-times — Paginated response time metrics */
  async list(params: PaginationParams & { client_id?: string; contact_id?: string } = {}): Promise<ResponseTimeListResponse> {
    const qs = buildQuery(params);
    const key = `rt${qs}`;
    const cached = getCached<ResponseTimeListResponse>(key, CACHE_TTL_SHORT);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<ResponseTimeListResponse>(`${API_PREFIX}/response-times${qs}`, { timeout: 10000 })
      );
      const data = result || { metrics: [], total: 0 };
      setCache(key, data);
      return data;
    } catch {
      return { metrics: [], total: 0 };
    }
  },

  /** GET /response-times/stats — Aggregate statistics */
  async stats(clientId?: string, contactId?: string): Promise<ResponseTimeStats | null> {
    const qs = buildQuery({ client_id: clientId, contact_id: contactId });
    const key = `rt-stats${qs}`;
    const cached = getCached<ResponseTimeStats>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<ResponseTimeStats>(`${API_PREFIX}/response-times/stats${qs}`, { timeout: 10000 })
      );
      if (result) setCache(key, result);
      return result;
    } catch {
      return null;
    }
  },

  /** GET /response-times/slowest — Slowest responders */
  async slowest(clientId?: string, limit: number = 20): Promise<SlowestResponder[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    const key = `rt-slowest${qs}`;
    const cached = getCached<SlowestResponder[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<SlowestResponder[]>(`${API_PREFIX}/response-times/slowest${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /response-times/by-contact/{contactId} — Response times for a contact */
  async byContact(contactId: string, limit: number = 100, offset: number = 0): Promise<ResponseTimeListResponse> {
    const qs = buildQuery({ limit, offset });
    try {
      const result = await api.get<ResponseTimeListResponse>(
        `${API_PREFIX}/response-times/by-contact/${contactId}${qs}`, { timeout: 10000 }
      );
      return result || { metrics: [], total: 0 };
    } catch {
      return { metrics: [], total: 0 };
    }
  },
};

// ============================================================================
// F) COMMUNICATION PATTERNS (4 endpoints)
// ============================================================================

export const patternsApi = {
  /** GET /patterns/initiation — Thread initiation patterns (requires client_id) */
  async initiation(clientId: string, limit: number = 100): Promise<InitiationPattern[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    const key = `patterns-init${qs}`;
    const cached = getCached<InitiationPattern[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<InitiationPattern[]>(`${API_PREFIX}/patterns/initiation${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /patterns/frequency — Communication frequency */
  async frequency(clientId?: string, limit: number = 100): Promise<FrequencyPattern[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    const key = `patterns-freq${qs}`;
    const cached = getCached<FrequencyPattern[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<FrequencyPattern[]>(`${API_PREFIX}/patterns/frequency${qs}`, { timeout: 10000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /patterns/engagement-trends — Engagement trends over time */
  async engagementTrends(clientId?: string, limit: number = 100): Promise<EngagementTrend[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    const key = `trends:${qs}`;
    const cached = getCached<EngagementTrend[]>(key, CACHE_TTL_LONG);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<EngagementTrend[]>(`${API_PREFIX}/patterns/engagement-trends${qs}`, { timeout: 15000 })
      );
      const data = result || [];
      setCache(key, data);
      return data;
    } catch {
      return [];
    }
  },

  /** GET /patterns/by-contact/{contactId} — Communication pattern for a contact */
  async byContact(contactId: string): Promise<CommunicationPattern | null> {
    try {
      return await api.get<CommunicationPattern>(`${API_PREFIX}/patterns/by-contact/${contactId}`, { timeout: 10000 });
    } catch {
      return null;
    }
  },
};

// ============================================================================
// G) DASHBOARD (2 endpoints)
// ============================================================================

export const dashboardAnalyticsApi = {
  /** GET /dashboard — Complete dashboard summary (requires client_id) */
  async getSummary(clientId: string): Promise<DashboardSummary | null> {
    const qs = buildQuery({ client_id: clientId });
    const key = `dashboard${qs}`;
    const cached = getCached<DashboardSummary>(key, CACHE_TTL_SHORT);
    if (cached) return cached;
    try {
      const result = await dedupedFetch(key, () =>
        api.get<DashboardSummary>(`${API_PREFIX}/dashboard${qs}`, { timeout: 15000 })
      );
      if (result) setCache(key, result);
      return result;
    } catch {
      return null;
    }
  },

  /** GET /summary/{clientId} — Client-specific summary */
  async getClientSummary(clientId: string): Promise<ClientSummary | null> {
    const key = `client-summary-${clientId}`;
    const cached = getCached<ClientSummary>(key, CACHE_TTL_SHORT);
    if (cached) return cached;
    try {
      const result = await api.get<ClientSummary>(`${API_PREFIX}/summary/${clientId}`, { timeout: 10000 });
      if (result) setCache(key, result);
      return result;
    } catch {
      return null;
    }
  },
};

// ============================================================================
// CACHE MANAGEMENT
// ============================================================================

/** Clear all analytics caches (call after mutations like extraction run) */
export function clearAnalyticsCache(): void {
  Object.keys(cache).forEach(key => delete cache[key]);
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/** Format engagement score as colored label */
export function getEngagementColor(score: number | null | undefined): string {
  if (score == null) return '#999';
  if (score >= 70) return '#52c41a'; // green
  if (score >= 40) return '#faad14'; // yellow
  if (score >= 20) return '#fa8c16'; // orange
  return '#f5222d'; // red
}

/** Format engagement score label */
export function getEngagementLabel(score: number | null | undefined): string {
  if (score == null) return 'N/A';
  if (score >= 70) return 'High';
  if (score >= 40) return 'Medium';
  if (score >= 20) return 'Low';
  return 'Very Low';
}

/** Format response time in human-readable form */
export function formatResponseTime(hours: number | null | undefined): string {
  if (hours == null) return 'N/A';
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 24) return `${hours.toFixed(1)}h`;
  return `${(hours / 24).toFixed(1)}d`;
}

/** Format a ratio (0-1) as percentage string */
export function formatRatio(ratio: number | null | undefined): string {
  if (ratio == null) return 'N/A';
  return `${Math.round(ratio * 100)}%`;
}

/** Format relative time from ISO date string */
export function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;
  return `${Math.floor(diffDays / 365)}y ago`;
}

/** Thread status display config */
export const threadStatusConfig: Record<string, { label: string; color: string }> = {
  complete: { label: 'Complete', color: 'green' },
  awaiting_response: { label: 'Awaiting Response', color: 'blue' },
  awaiting_our_response: { label: 'Awaiting Our Response', color: 'orange' },
  overdue: { label: 'Overdue', color: 'red' },
  dropped: { label: 'Dropped', color: 'default' },
  ongoing: { label: 'Ongoing', color: 'cyan' },
};

/** Contact type display config */
export const contactTypeConfig: Record<string, { label: string; color: string }> = {
  person: { label: 'Person', color: 'blue' },
  automated: { label: 'Automated', color: 'default' },
  shared: { label: 'Shared', color: 'purple' },
  mailing_list: { label: 'Mailing List', color: 'cyan' },
  internal: { label: 'Internal', color: 'gold' },
  unknown: { label: 'Unknown', color: 'default' },
};

/** Engagement status display config */
export const engagementStatusConfig: Record<string, { label: string; color: string }> = {
  active: { label: 'Active', color: 'green' },
  quiet: { label: 'Quiet', color: 'gold' },
  at_risk: { label: 'At Risk', color: 'red' },
  unknown: { label: 'Unknown', color: 'default' },
};
