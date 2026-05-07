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
  ThreadDetail,
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

// ==========================================================================
// QUERY HELPERS (cache + dedup handled by TanStack Query)
// ==========================================================================

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
    try {
      const result = await api.get<ExtractionJobListResponse>(`${API_PREFIX}/extraction/jobs${qs}`, { timeout: 10000 });
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
    try {
      const result = await api.get<ContactAnalyticsListResponse>(`${API_PREFIX}/contacts${qs}`, { timeout: 10000 });
      const data = result || { contacts: [], total: 0 };
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

  /** GET /contacts/{id}/emails — Emails linked to a contact */
  async getEmails(contactId: string, limit = 50, offset = 0): Promise<{ emails: any[]; total: number; total_sent?: number; total_received?: number }> {
    try {
      return await api.get<{ emails: any[]; total: number; total_sent?: number; total_received?: number }>(
        `${API_PREFIX}/contacts/${contactId}/emails?limit=${limit}&offset=${offset}`,
        { timeout: 10000 }
      );
    } catch {
      return { emails: [], total: 0 };
    }
  },

  /** GET /contacts/top-engaged — Top engaged contacts */
  async topEngaged(clientId?: string, limit: number = 10): Promise<TopEngagedContact[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    try {
      const result = await api.get<TopEngagedContact[]>(`${API_PREFIX}/contacts/top-engaged${qs}`, { timeout: 10000 });
      return result || [];
    } catch {
      return [];
    }
  },

  /** GET /contacts/at-risk — At-risk contacts */
  async atRisk(clientId?: string, daysThreshold: number = 60, limit: number = 50): Promise<AtRiskContact[]> {
    const qs = buildQuery({ client_id: clientId, days_threshold: daysThreshold, limit });
    try {
      const result = await api.get<AtRiskContact[]>(`${API_PREFIX}/contacts/at-risk${qs}`, { timeout: 10000 });
      return result || [];
    } catch {
      return [];
    }
  },

  /** GET /contacts/decision-makers — Decision maker contacts */
  async decisionMakers(clientId?: string, limit: number = 100, offset: number = 0): Promise<ContactAnalyticsListResponse> {
    const qs = buildQuery({ client_id: clientId, limit, offset });
    try {
      const result = await api.get<ContactAnalyticsListResponse>(`${API_PREFIX}/contacts/decision-makers${qs}`, { timeout: 10000 });
      const data = result || { contacts: [], total: 0 };
      return data;
    } catch {
      return { contacts: [], total: 0 };
    }
  },

  /** GET /contacts/by-type — Contacts grouped by type */
  async byType(clientId?: string): Promise<ContactTypeGrouping[]> {
    const qs = buildQuery({ client_id: clientId });
    try {
      const result = await api.get<ContactTypeGrouping[]>(`${API_PREFIX}/contacts/by-type${qs}`, { timeout: 10000 });
      return result || [];
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
    try {
      const result = await api.get<CompanyAnalyticsListResponse>(`${API_PREFIX}/companies${qs}`, { timeout: 10000 });
      const data = result || { companies: [], total: 0 };
      return data;
    } catch {
      return { companies: [], total: 0 };
    }
  },

  /** GET /companies/{companyId} — Single company with full analytics */
  async getDetail(companyId: string): Promise<CompanyAnalytics | null> {
    try {
      return await api.get<CompanyAnalytics>(`${API_PREFIX}/companies/${companyId}`, { timeout: 30000 });
    } catch {
      return null;
    }
  },

  /** GET /companies/{companyId}/emails — Emails linked to a company */
  async getEmails(companyId: string, limit = 50, offset = 0): Promise<{ emails: any[]; total: number; total_sent?: number; total_received?: number }> {
    try {
      return await api.get<{ emails: any[]; total: number; total_sent?: number; total_received?: number }>(
        `${API_PREFIX}/companies/${companyId}/emails?limit=${limit}&offset=${offset}`,
        { timeout: 10000 }
      );
    } catch {
      return { emails: [], total: 0 };
    }
  },

  /** GET /companies/top-engaged — Top engaged companies */
  async topEngaged(clientId?: string, limit: number = 10): Promise<TopEngagedCompany[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    try {
      const result = await api.get<TopEngagedCompany[]>(`${API_PREFIX}/companies/top-engaged${qs}`, { timeout: 10000 });
      return result || [];
    } catch {
      return [];
    }
  },

  /** GET /companies/at-risk — At-risk companies */
  async atRisk(clientId?: string, daysThreshold: number = 90, limit: number = 50): Promise<AtRiskCompany[]> {
    const qs = buildQuery({ client_id: clientId, days_threshold: daysThreshold, limit });
    try {
      const result = await api.get<AtRiskCompany[]>(`${API_PREFIX}/companies/at-risk${qs}`, { timeout: 10000 });
      return result || [];
    } catch {
      return [];
    }
  },

  /** GET /companies/by-engagement — Companies by engagement status */
  async byEngagement(clientId?: string): Promise<EngagementStatusGrouping[]> {
    const qs = buildQuery({ client_id: clientId });
    try {
      const result = await api.get<EngagementStatusGrouping[]>(`${API_PREFIX}/companies/by-engagement${qs}`, { timeout: 10000 });
      return result || [];
    } catch {
      return [];
    }
  },

  // Sprint 4: Sales Intelligence endpoints (on /customers router, no /v1 prefix)

  /** GET /customers/{companyId}/order-history */
  async getOrderHistory(companyId: string, limit = 200): Promise<{ items: any[]; total: number }> {
    try {
      return await api.get<{ items: any[]; total: number }>(
        `/customers/${companyId}/order-history?limit=${limit}`,
        { timeout: 10000 }
      );
    } catch {
      return { items: [], total: 0 };
    }
  },

  /** GET /customers/{companyId}/product-profile */
  async getProductProfile(companyId: string): Promise<{ categories: any[]; operations: any[] }> {
    try {
      return await api.get<{ categories: any[]; operations: any[] }>(
        `/customers/${companyId}/product-profile`,
        { timeout: 10000 }
      );
    } catch {
      return { categories: [], operations: [] };
    }
  },

  /** GET /customers/{companyId}/recommendations */
  async getRecommendations(companyId: string, force = false): Promise<{ cross_contact_recs: any[]; related_product_recs: any[]; product_profile: any; revenue_insight?: any; computed_at?: string }> {
    try {
      return await api.get<any>(
        `/customers/${companyId}/recommendations${force ? '?force=true' : ''}`,
        { timeout: 15000 }
      );
    } catch {
      return { cross_contact_recs: [], related_product_recs: [], product_profile: {} };
    }
  },

  /** GET /customers/portfolio-insights?client_id=... */
  async getPortfolioInsights(clientId: string): Promise<{ client_id: string; insights: any[]; total: number; by_type: Record<string, number> }> {
    try {
      return await api.get<any>(
        `/customers/portfolio-insights?client_id=${clientId}`,
        { timeout: 30000 }
      );
    } catch {
      return { client_id: clientId, insights: [], total: 0, by_type: {} };
    }
  },

  /** GET /customers/{companyId}/strike-rate */
  async getStrikeRate(companyId: string, force = false): Promise<any> {
    try {
      return await api.get<any>(
        `/customers/${companyId}/strike-rate${force ? '?force=true' : ''}`,
        { timeout: 30000 }
      );
    } catch (e) {
      console.error('Strike rate fetch failed:', e);
      return { company_total: { total_quotes: 0, converted: 0, strike_rate_pct: 0 }, by_contact: [], by_year: [] };
    }
  },

  /** GET /customers/{companyId}/contact-capabilities */
  async getContactCapabilities(companyId: string, force = false): Promise<any> {
    try {
      return await api.get<any>(
        `/customers/${companyId}/contact-capabilities${force ? '?force=true' : ''}`,
        { timeout: 15000 }
      );
    } catch {
      return { contacts: [] };
    }
  },

  /** GET /customers/{companyId}/seasonality */
  async getSeasonality(companyId: string, force = false): Promise<any> {
    try {
      return await api.get<any>(
        `/customers/${companyId}/seasonality${force ? '?force=true' : ''}`,
        { timeout: 15000 }
      );
    } catch {
      return { monthly: [], quarterly: [], peak_months: [], trough_months: [], total_orders: 0 };
    }
  },

  /** GET /customers/{companyId}/capability-rhythm */
  async getCapabilityRhythm(companyId: string, force = false): Promise<any> {
    try {
      return await api.get<any>(
        `/customers/${companyId}/capability-rhythm${force ? '?force=true' : ''}`,
        { timeout: 15000 }
      );
    } catch {
      return { rhythms: [], alerts: [] };
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
    try {
      const result = await api.get<ThreadStatusListResponse>(`${API_PREFIX}/threads/status${qs}`, { timeout: 10000 });
      const data = result || { threads: [], total: 0 };
      return data;
    } catch {
      return { threads: [], total: 0 };
    }
  },

  /** GET /threads/overdue — Overdue threads */
  async overdue(clientId?: string, limit: number = 50): Promise<OverdueThread[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    try {
      const result = await api.get<OverdueThread[]>(`${API_PREFIX}/threads/overdue${qs}`, { timeout: 10000 });
      return result || [];
    } catch {
      return [];
    }
  },

  /** GET /threads/by-status — Count threads by status */
  async byStatus(clientId?: string): Promise<ThreadStatusCount[]> {
    const qs = buildQuery({ client_id: clientId });
    try {
      const result = await api.get<ThreadStatusCount[]>(`${API_PREFIX}/threads/by-status${qs}`, { timeout: 10000 });
      return result || [];
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

  /** GET /threads/by-company/{companyId} — Threads for a company */
  async byCompany(companyId: string, limit: number = 100, offset: number = 0): Promise<ThreadStatusListResponse> {
    const qs = buildQuery({ limit, offset });
    try {
      const result = await api.get<ThreadStatusListResponse>(
        `${API_PREFIX}/threads/by-company/${companyId}${qs}`, { timeout: 10000 }
      );
      return result || { threads: [], total: 0 };
    } catch {
      return { threads: [], total: 0 };
    }
  },

  /** GET /threads/{threadId}/emails — Thread detail with emails */
  async getDetail(threadId: string): Promise<ThreadDetail | null> {
    try {
      return await api.get<ThreadDetail>(
        `${API_PREFIX}/threads/${encodeURIComponent(threadId)}/emails`, { timeout: 10000 }
      );
    } catch {
      return null;
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
    try {
      const result = await api.get<ResponseTimeListResponse>(`${API_PREFIX}/response-times${qs}`, { timeout: 10000 });
      const data = result || { metrics: [], total: 0 };
      return data;
    } catch {
      return { metrics: [], total: 0 };
    }
  },

  /** GET /response-times/stats — Aggregate statistics */
  async stats(clientId?: string, contactId?: string): Promise<ResponseTimeStats | null> {
    const qs = buildQuery({ client_id: clientId, contact_id: contactId });
    try {
      const result = await api.get<ResponseTimeStats>(`${API_PREFIX}/response-times/stats${qs}`, { timeout: 10000 });
      return result;
    } catch {
      return null;
    }
  },

  /** GET /response-times/slowest — Slowest responders */
  async slowest(clientId?: string, limit: number = 20): Promise<SlowestResponder[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    try {
      const result = await api.get<SlowestResponder[]>(`${API_PREFIX}/response-times/slowest${qs}`, { timeout: 10000 });
      return result || [];
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
    try {
      const result = await api.get<InitiationPattern[]>(`${API_PREFIX}/patterns/initiation${qs}`, { timeout: 10000 });
      return result || [];
    } catch {
      return [];
    }
  },

  /** GET /patterns/frequency — Communication frequency */
  async frequency(clientId?: string, limit: number = 100): Promise<FrequencyPattern[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    try {
      const result = await api.get<FrequencyPattern[]>(`${API_PREFIX}/patterns/frequency${qs}`, { timeout: 10000 });
      return result || [];
    } catch {
      return [];
    }
  },

  /** GET /patterns/engagement-trends — Engagement trends over time */
  async engagementTrends(clientId?: string, limit: number = 100): Promise<EngagementTrend[]> {
    const qs = buildQuery({ client_id: clientId, limit });
    try {
      const result = await api.get<EngagementTrend[]>(`${API_PREFIX}/patterns/engagement-trends${qs}`, { timeout: 15000 });
      return result || [];
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
  async getSummary(clientId: string, periodDays?: number): Promise<DashboardSummary | null> {
    const qs = buildQuery({ client_id: clientId, period_days: periodDays });
    try {
      const result = await api.get<DashboardSummary>(`${API_PREFIX}/dashboard${qs}`, { timeout: 15000 });
      return result;
    } catch {
      return null;
    }
  },

  /** GET /summary/{clientId} — Client-specific summary */
  async getClientSummary(clientId: string): Promise<ClientSummary | null> {
    try {
      const result = await api.get<ClientSummary>(`${API_PREFIX}/summary/${clientId}`, { timeout: 10000 });
      return result;
    } catch {
      return null;
    }
  },
};

// ============================================================================
// H) CONTACT INTELLIGENCE (persona views + deal activity)
// ============================================================================

export const contactIntelligenceApi = {
  async getPersona(contactId: string): Promise<any> {
    try {
      return await api.get<any>(`/contacts-intelligence/${contactId}/persona`, { timeout: 15000 });
    } catch {
      return null;
    }
  },

  async getDealActivity(contactId: string): Promise<any> {
    try {
      return await api.get<any>(`/contacts-intelligence/${contactId}/deal-activity`, { timeout: 15000 });
    } catch {
      return null;
    }
  },

  async getCompanyContacts(companyId: string): Promise<{ contacts: any[]; total: number }> {
    try {
      return await api.get<{ contacts: any[]; total: number }>(
        `/contacts-intelligence/company/${companyId}/contacts?limit=50&sort_by=engagement_score&sort_order=desc`,
        { timeout: 15000 }
      );
    } catch {
      return { contacts: [], total: 0 };
    }
  },
};

// ============================================================================
// CACHE MANAGEMENT (handled by TanStack Query — see queryClient.invalidateQueries)
// ============================================================================

/** @deprecated Use queryClient.invalidateQueries() instead */
export function clearAnalyticsCache(): void {
  // No-op: cache is now managed by TanStack Query
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

// Re-export from centralized dateUtils for backward compatibility
export { formatRelativeTime } from '../utils/dateUtils';

/** Thread status display config — covers both timing-derived AND override values
 * (the `status` column now holds the EFFECTIVE post-override value).
 */
export const threadStatusConfig: Record<string, { label: string; color: string }> = {
  // Timing-derived
  complete: { label: 'Complete', color: 'green' },
  awaiting_response: { label: 'Awaiting Response', color: 'blue' },
  awaiting_our_response: { label: 'Awaiting Our Response', color: 'orange' },
  overdue: { label: 'Overdue', color: 'red' },
  dropped: { label: 'Dropped', color: 'default' },
  ongoing: { label: 'Ongoing', color: 'cyan' },
  outbound_pending: { label: 'Outbound Pending', color: 'orange' },
  stale: { label: 'Stale', color: 'cyan' },
  awaiting_reply: { label: 'Awaiting Response', color: 'blue' },
  // Override-derived (intent rules; migration 077)
  urgent: { label: 'Urgent', color: 'red' },
  revenue_opportunity: { label: 'Revenue Opportunity', color: 'green' },
  closing: { label: 'Closing', color: 'green' },
  escalation: { label: 'Escalation', color: 'orange' },
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
  unknown: { label: 'No Activity', color: 'default' },
};

// ============================================================================
// METRIC HISTORY
// ============================================================================

export interface MetricHistoryEntry {
  engagement_score: number;
  scoring_version: number;
  response_time_score: number | null;
  thread_completeness_score: number | null;
  initiation_balance_score: number | null;
  reply_rate_score: number | null;
  frequency_score: number | null;
  recency_score: number | null;
  decision_maker_bonus: number | null;
  seniority_bonus: number | null;
  emails_per_month_avg: number | null;
  avg_response_time_seconds: number | null;
  reply_rate: number | null;
  calculated_at: string;
}

// ---------- Data Health ----------

export interface MailboxHealth {
  mailbox_id: string;
  email_address: string;
  provider: string;
  status: string;
  last_sync_at: string | null;
  last_extraction_at: string | null;
  sync_lag_hours: number | null;
  extraction_lag_hours: number | null;
}

export interface IdentityResolution {
  total_emails: number;
  resolved_emails: number;
  unresolved_emails: number;
  coverage_percent: number;
}

export interface ThreadDistributionEntry {
  status: string;
  count: number;
  percent: number;
}

export interface ExtractionJobHealth {
  id: string;
  status: string;
  extraction_mode: string;
  started_at: string | null;
  completed_at: string | null;
  total_emails: number | null;
  processed_emails: number | null;
  errors: any[] | null;
}

export interface DataHealthResponse {
  mailbox_health: MailboxHealth[];
  identity_resolution: IdentityResolution;
  thread_distribution: ThreadDistributionEntry[];
  missing_weekdays: string[];
  missing_weekday_count: number;
  recent_extraction_jobs: ExtractionJobHealth[];
}

export const dataHealthApi = {
  async get(clientId?: string): Promise<DataHealthResponse> {
    const params = clientId ? `?client_id=${clientId}` : '';
    return api.get<DataHealthResponse>(`${API_PREFIX}/data-health${params}`);
  },
};

export const metricHistoryApi = {
  async get(entityType: 'contact' | 'company', entityId: string, limit = 30): Promise<MetricHistoryEntry[]> {
    const data = await api.get<{ history: MetricHistoryEntry[]; total: number }>(
      `${API_PREFIX}/metric-history/${entityType}/${entityId}?limit=${limit}`
    );
    return data.history;
  },
};
