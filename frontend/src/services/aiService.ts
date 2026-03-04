/**
 * AI Intelligence Service — Sprint 3
 *
 * Follows analyticsService.ts patterns: TTL cache, in-flight dedup, error fallbacks.
 * All methods return typed Promises and never throw to UI.
 */

import api from './apiClient';
import type {
  IntelligenceListResponse,
  IntelligenceStats,
  IntelligenceFilterParams,
  ActionItemsResponse,
  BucketSummary,
  BucketConfig,
  EntityListResponse,
  CompetitorLandscape,
  OpportunitySignalsResponse,
  FeedbackRequest,
  FeedbackResponse,
  AnalyzeRequest,
  AnalyzeResponse,
  DailyDigest,
  DigestHistoryResponse,
  UsageSummary,
  MonitoringStats,
  AIControlSettings,
  UsageLogEntry,
} from '../types/ai';

const API_PREFIX = '/v1/ai';

// ============================================================================
// CACHE INFRASTRUCTURE
// ============================================================================

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

const CACHE_TTL_SHORT = 30_000;   // 30s for lists
const CACHE_TTL_LONG = 60_000;    // 60s for aggregations/stats

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

export function invalidateCache(prefix?: string): void {
  if (prefix) {
    for (const key of Object.keys(cache)) {
      if (key.startsWith(prefix)) delete cache[key];
    }
  } else {
    for (const key of Object.keys(cache)) delete cache[key];
  }
}

// In-flight dedup
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
// A) INTELLIGENCE (3 endpoints)
// ============================================================================

export const intelligenceApi = {
  /** POST /ai/analyze/{mailbox_id} — Trigger analysis */
  async analyze(mailboxId: string, params: AnalyzeRequest = {}): Promise<AnalyzeResponse | null> {
    try {
      invalidateCache('intel');
      return await api.post<AnalyzeResponse>(
        `${API_PREFIX}/analyze/${mailboxId}`, params, { timeout: 15000 }
      );
    } catch (error: any) {
      console.error('[AI] Failed to trigger analysis:', error?.message);
      return null;
    }
  },

  /** GET /ai/intelligence/{mailbox_id} — List results (paginated, filterable) */
  async list(mailboxId: string, filters: IntelligenceFilterParams = {}): Promise<IntelligenceListResponse> {
    const qs = buildQuery(filters);
    const key = `intel-list-${mailboxId}${qs}`;
    const cached = getCached<IntelligenceListResponse>(key, CACHE_TTL_SHORT);
    if (cached) return cached;

    try {
      const result = await dedupedFetch(key, () =>
        api.get<IntelligenceListResponse>(
          `${API_PREFIX}/intelligence/${mailboxId}${qs}`, { timeout: 15000 }
        )
      );
      if (result) setCache(key, result);
      return result || { items: [], page: 1, page_size: 25 };
    } catch {
      return { items: [], page: 1, page_size: 25 };
    }
  },

  /** GET /ai/intelligence/stats/{mailbox_id} — Stats breakdown */
  async stats(mailboxId: string): Promise<IntelligenceStats> {
    const key = `intel-stats-${mailboxId}`;
    const cached = getCached<IntelligenceStats>(key, CACHE_TTL_LONG);
    if (cached) return cached;

    try {
      const result = await dedupedFetch(key, () =>
        api.get<IntelligenceStats>(
          `${API_PREFIX}/intelligence/stats/${mailboxId}`, { timeout: 10000 }
        )
      );
      if (result) setCache(key, result);
      return result || { total: 0, by_status: {}, by_intent: {}, by_urgency: {}, by_sentiment: {}, by_bucket: {}, by_business_signal: {}, avg_confidence: 0 };
    } catch {
      return { total: 0, by_status: {}, by_intent: {}, by_urgency: {}, by_sentiment: {}, by_bucket: {}, by_business_signal: {}, avg_confidence: 0 };
    }
  },
};


// ============================================================================
// B) ACTION BUCKETS (2 endpoints)
// ============================================================================

export const bucketApi = {
  /** GET /ai/action-items/{mailbox_id} — Prioritized action items */
  async getActionItems(mailboxId: string, clientId?: string, minConfidence = 0.5, limit = 50): Promise<ActionItemsResponse> {
    const qs = buildQuery({ client_id: clientId, min_confidence: minConfidence, limit });
    const key = `bucket-items-${mailboxId}${qs}`;
    const cached = getCached<ActionItemsResponse>(key, CACHE_TTL_SHORT);
    if (cached) return cached;

    try {
      const result = await dedupedFetch(key, () =>
        api.get<ActionItemsResponse>(
          `${API_PREFIX}/action-items/${mailboxId}${qs}`, { timeout: 10000 }
        )
      );
      if (result) setCache(key, result);
      return result || { items: [], total: 0 };
    } catch {
      return { items: [], total: 0 };
    }
  },

  /** GET /ai/action-items/{mailbox_id}/summary — Bucket counts */
  async getSummary(mailboxId: string, clientId?: string): Promise<BucketSummary> {
    const qs = buildQuery({ client_id: clientId });
    const key = `bucket-summary-${mailboxId}${qs}`;
    const cached = getCached<BucketSummary>(key, CACHE_TTL_LONG);
    if (cached) return cached;

    try {
      const result = await dedupedFetch(key, () =>
        api.get<BucketSummary>(
          `${API_PREFIX}/action-items/${mailboxId}/summary${qs}`, { timeout: 10000 }
        )
      );
      if (result) setCache(key, result);
      return result || { buying_signal: 0, expansion_signal: 0, churn_risk: 0, competitor_threat: 0, missed_opportunity: 0, stakeholder_entry: 0, silent_champion: 0, unresolved_block: 0, total: 0 };
    } catch {
      return { buying_signal: 0, expansion_signal: 0, churn_risk: 0, competitor_threat: 0, missed_opportunity: 0, stakeholder_entry: 0, silent_champion: 0, unresolved_block: 0, total: 0 };
    }
  },

  /** GET /ai/buckets/config — Bucket config for display */
  async getConfig(): Promise<Record<string, BucketConfig>> {
    const key = 'bucket-config';
    const cached = getCached<Record<string, BucketConfig>>(key, CACHE_TTL_LONG);
    if (cached) return cached;

    try {
      const result = await api.get<Record<string, BucketConfig>>(
        `${API_PREFIX}/buckets/config`, { timeout: 5000 }
      );
      if (result) setCache(key, result);
      return result || {};
    } catch {
      return {};
    }
  },
};


// ============================================================================
// C) FEEDBACK (1 endpoint)
// ============================================================================

export const feedbackApi = {
  /** POST /ai/intelligence/{email_id}/feedback — Submit structured feedback */
  async submit(emailId: string, data: FeedbackRequest): Promise<FeedbackResponse | null> {
    try {
      invalidateCache('intel');
      return await api.post<FeedbackResponse>(
        `${API_PREFIX}/intelligence/${emailId}/feedback`, data, { timeout: 10000 }
      );
    } catch (error: any) {
      console.error('[AI] Failed to submit feedback:', error?.message);
      return null;
    }
  },
};


// ============================================================================
// D) ENTITIES (3 endpoints)
// ============================================================================

export const entityApi = {
  /** GET /ai/entities/{client_id} */
  async list(clientId: string, entityType?: string, limit = 100): Promise<EntityListResponse> {
    const qs = buildQuery({ entity_type: entityType, limit });
    const key = `entities-${clientId}${qs}`;
    const cached = getCached<EntityListResponse>(key, CACHE_TTL_LONG);
    if (cached) return cached;

    try {
      const result = await dedupedFetch(key, () =>
        api.get<EntityListResponse>(
          `${API_PREFIX}/entities/${clientId}${qs}`, { timeout: 10000 }
        )
      );
      if (result) setCache(key, result);
      return result || { items: [], total: 0 };
    } catch {
      return { items: [], total: 0 };
    }
  },

  /** GET /ai/entities/{client_id}/competitors */
  async getCompetitors(clientId: string): Promise<CompetitorLandscape> {
    const key = `competitors-${clientId}`;
    const cached = getCached<CompetitorLandscape>(key, CACHE_TTL_LONG);
    if (cached) return cached;

    try {
      const result = await dedupedFetch(key, () =>
        api.get<CompetitorLandscape>(
          `${API_PREFIX}/entities/${clientId}/competitors`, { timeout: 10000 }
        )
      );
      if (result) setCache(key, result);
      return result || { competitors: [], total_mentions: 0, accounts_affected: 0 };
    } catch {
      return { competitors: [], total_mentions: 0, accounts_affected: 0 };
    }
  },

  /** GET /ai/entities/{client_id}/opportunities */
  async getOpportunities(clientId: string, mailboxId: string, limit = 50): Promise<OpportunitySignalsResponse> {
    const qs = buildQuery({ mailbox_id: mailboxId, limit });
    const key = `opportunities-${clientId}${qs}`;
    const cached = getCached<OpportunitySignalsResponse>(key, CACHE_TTL_SHORT);
    if (cached) return cached;

    try {
      const result = await dedupedFetch(key, () =>
        api.get<OpportunitySignalsResponse>(
          `${API_PREFIX}/entities/${clientId}/opportunities${qs}`, { timeout: 10000 }
        )
      );
      if (result) setCache(key, result);
      return result || { items: [], total: 0 };
    } catch {
      return { items: [], total: 0 };
    }
  },
};


// ============================================================================
// E) DIGEST (2 endpoints)
// ============================================================================

export const digestApi = {
  /** GET /ai/digest/{mailbox_id}?date=YYYY-MM-DD — Get/generate digest */
  async get(mailboxId: string, date?: string, clientId?: string, force?: boolean): Promise<DailyDigest | null> {
    const qs = buildQuery({ date, client_id: clientId, force: force ? 'true' : undefined });
    const key = `digest-${mailboxId}-${date || 'today'}`;

    // Skip frontend cache when forcing regeneration
    if (!force) {
      const cached = getCached<DailyDigest>(key, CACHE_TTL_LONG);
      if (cached) return cached;
    }

    try {
      const result = await api.get<DailyDigest>(
        `${API_PREFIX}/digest/${mailboxId}${qs}`, { timeout: 30000 }
      );
      if (result) setCache(key, result);
      return result;
    } catch (error: any) {
      console.error('[AI] Failed to get digest:', error?.message);
      return null;
    }
  },

  /** GET /ai/digest/{mailbox_id}/history */
  async getHistory(mailboxId: string, limit = 30): Promise<DigestHistoryResponse> {
    const qs = buildQuery({ limit });
    try {
      const result = await api.get<DigestHistoryResponse>(
        `${API_PREFIX}/digest/${mailboxId}/history${qs}`, { timeout: 10000 }
      );
      return result || { items: [], total: 0 };
    } catch {
      return { items: [], total: 0 };
    }
  },
};


// ============================================================================
// F) USAGE & MONITORING (3 endpoints)
// ============================================================================

export const usageApi = {
  /** GET /ai/usage/costs — Cost summary */
  async getCosts(clientId?: string, days = 30): Promise<UsageSummary> {
    const qs = buildQuery({ client_id: clientId, days });
    const key = `usage-costs${qs}`;
    const cached = getCached<UsageSummary>(key, CACHE_TTL_SHORT);
    if (cached) return cached;

    try {
      const result = await dedupedFetch(key, () =>
        api.get<UsageSummary>(`${API_PREFIX}/usage/costs${qs}`, { timeout: 10000 })
      );
      if (result) setCache(key, result);
      return result || { total_cost_usd: 0, total_input_tokens: 0, total_output_tokens: 0, total_requests: 0, by_operation: {}, by_model: {}, failure_rate: 0, avg_latency_ms: 0 };
    } catch {
      return { total_cost_usd: 0, total_input_tokens: 0, total_output_tokens: 0, total_requests: 0, by_operation: {}, by_model: {}, failure_rate: 0, avg_latency_ms: 0 };
    }
  },

  /** GET /ai/usage/monitoring — Real-time monitoring (24h) */
  async getMonitoring(clientId?: string): Promise<MonitoringStats> {
    const qs = buildQuery({ client_id: clientId });
    const key = `usage-monitoring${qs}`;
    const cached = getCached<MonitoringStats>(key, CACHE_TTL_SHORT);
    if (cached) return cached;

    try {
      const result = await dedupedFetch(key, () =>
        api.get<MonitoringStats>(`${API_PREFIX}/usage/monitoring${qs}`, { timeout: 10000 })
      );
      if (result) setCache(key, result);
      return result || { parse_failure_rate: 0, api_failure_rate: 0, avg_retry_count: 0, cost_per_1000_emails: 0, total_failures_24h: 0, total_requests_24h: 0 };
    } catch {
      return { parse_failure_rate: 0, api_failure_rate: 0, avg_retry_count: 0, cost_per_1000_emails: 0, total_failures_24h: 0, total_requests_24h: 0 };
    }
  },

  /** GET /ai/usage/recent — Recent log entries */
  async getRecent(limit = 50): Promise<{ items: UsageLogEntry[]; total: number }> {
    const qs = buildQuery({ limit });
    try {
      const result = await api.get<{ items: UsageLogEntry[]; total: number }>(
        `${API_PREFIX}/usage/recent${qs}`, { timeout: 10000 }
      );
      return result || { items: [], total: 0 };
    } catch {
      return { items: [], total: 0 };
    }
  },
};


// ============================================================================
// G) AI CONTROLS (3 endpoints)
// ============================================================================

export const controlsApi = {
  /** GET /ai/controls — Get current settings */
  async get(): Promise<AIControlSettings> {
    try {
      const result = await api.get<AIControlSettings>(
        `${API_PREFIX}/controls`, { timeout: 5000 }
      );
      return result || {
        ai_enabled: false, email_analysis_enabled: false, digest_enabled: false,
        relationship_summary_enabled: false, daily_budget_usd: 2, monthly_budget_usd: 16,
        batch_size: 10, max_emails_per_run: 500, max_requests_per_second: 10,
        session_spend_usd: 0, session_requests: 0,
      };
    } catch {
      return {
        ai_enabled: false, email_analysis_enabled: false, digest_enabled: false,
        relationship_summary_enabled: false, daily_budget_usd: 2, monthly_budget_usd: 16,
        batch_size: 10, max_emails_per_run: 500, max_requests_per_second: 10,
        session_spend_usd: 0, session_requests: 0,
      };
    }
  },

  /** PUT /ai/controls — Update settings */
  async update(settings: Partial<AIControlSettings>): Promise<any> {
    try {
      invalidateCache('usage');
      return await api.put(`${API_PREFIX}/controls`, settings, { timeout: 5000 });
    } catch (error: any) {
      console.error('[AI] Failed to update controls:', error?.message);
      return null;
    }
  },

  /** POST /ai/controls/reset-session-spend — Reset session counters */
  async resetSessionSpend(): Promise<any> {
    try {
      return await api.post(`${API_PREFIX}/controls/reset-session-spend`, {}, { timeout: 5000 });
    } catch (error: any) {
      console.error('[AI] Failed to reset session spend:', error?.message);
      return null;
    }
  },
};
