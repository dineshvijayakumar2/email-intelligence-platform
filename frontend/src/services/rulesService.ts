/**
 * Email Rules Service — Unified rules view + cross-AM analysis
 *
 * Fetches normalized Gmail filters and Outlook inbox rules,
 * cross-AM comparison metrics, and derived insights.
 */

import api from './apiClient';

const API_PREFIX = '/v1/rules';

// ============================================================================
// TYPES
// ============================================================================

export interface RuleConditions {
  from_addresses: string[];
  from_domains: string[];
  to_addresses: string[];
  subject_contains: string[];
  body_contains: string[];
  has_attachment: boolean | null;
}

export interface RuleActions {
  label: string | null;
  move_to_folder: string | null;
  forward_to: string[];
  mark_important: boolean;
  mark_read: boolean;
  skip_inbox: boolean;
  delete: boolean;
}

export interface UnifiedRule {
  id: string | null;
  mailbox_id: string;
  mailbox_email: string;
  source_type: 'gmail' | 'outlook';
  source_rule_id: string;
  name: string;
  is_active: boolean;
  conditions: RuleConditions;
  actions: RuleActions;
  engagement_signal: 'high_value' | 'escalation' | 'low_priority' | 'segmentation' | 'neutral';
  imported_at: string | null;
}

export interface RulesListResponse {
  items: UnifiedRule[];
  total: number;
  mailbox_email: string;
  source_type: string;
}

export interface MailboxRulesMetrics {
  mailbox_id: string;
  mailbox_email: string;
  mailbox_type: string;
  live_connection: string;  // 'gmail', 'outlook', or '' (no LIVE connection)
  total_rules: number;
  active_rules: number;
  high_value_count: number;
  escalation_count: number;
  low_priority_count: number;
  segmentation_count: number;
  neutral_count: number;
  forward_count: number;
  covered_domains: string[];
  covered_addresses: string[];
}

export interface RulesAnalyticsResponse {
  mailboxes: MailboxRulesMetrics[];
  total_mailboxes: number;
  total_rules: number;
  avg_rules_per_mailbox: number;
  mailboxes_with_no_rules: number;
}

export interface RulesInsight {
  insight_type: string;
  severity: 'info' | 'warning' | 'critical';
  description: string;
  affected_mailboxes: string[];
  recommendation: string;
}

export interface RulesInsightsResponse {
  insights: RulesInsight[];
  total: number;
}

// ============================================================================
// CACHE
// ============================================================================

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

const CACHE_TTL = 60_000; // 60s
const cache: Record<string, CacheEntry<any>> = {};

function getCached<T>(key: string): T | null {
  const entry = cache[key];
  if (entry && (Date.now() - entry.timestamp) < CACHE_TTL) {
    return entry.data as T;
  }
  return null;
}

function setCache<T>(key: string, data: T): void {
  cache[key] = { data, timestamp: Date.now() };
}

export function clearRulesCache(): void {
  for (const key of Object.keys(cache)) delete cache[key];
}

// ============================================================================
// API CALLS
// ============================================================================

export const rulesApi = {
  /** Get unified rules for one mailbox */
  async list(mailboxId: string): Promise<RulesListResponse> {
    const cacheKey = `rules:${mailboxId}`;
    const cached = getCached<RulesListResponse>(cacheKey);
    if (cached) return cached;

    try {
      const resp = await api.get(`${API_PREFIX}/${mailboxId}`);
      if (!resp) {
        return { items: [], total: 0, mailbox_email: '', source_type: '' };
      }
      const data = resp as RulesListResponse;
      setCache(cacheKey, data);
      return data;
    } catch (error) {
      console.error('[RulesService] Failed to list rules:', error);
      return { items: [], total: 0, mailbox_email: '', source_type: '' };
    }
  },

  /** Import rules from mail server for a mailbox */
  async importRules(mailboxId: string): Promise<{ status: string; source: string; imported_count: number }> {
    try {
      clearRulesCache();
      const resp = await api.post(`${API_PREFIX}/${mailboxId}/import`);
      return resp as { status: string; source: string; imported_count: number };
    } catch (error) {
      console.error('[RulesService] Failed to import rules:', error);
      throw error;
    }
  },

  /** Get cross-AM rules analytics */
  async analytics(clientId: string): Promise<RulesAnalyticsResponse> {
    const cacheKey = `rules:analytics:${clientId}`;
    const cached = getCached<RulesAnalyticsResponse>(cacheKey);
    if (cached) return cached;

    try {
      const resp = await api.get(`${API_PREFIX}/analytics/${clientId}`);
      if (!resp) {
        return { mailboxes: [], total_mailboxes: 0, total_rules: 0, avg_rules_per_mailbox: 0, mailboxes_with_no_rules: 0 };
      }
      const data = resp as RulesAnalyticsResponse;
      setCache(cacheKey, data);
      return data;
    } catch (error) {
      console.error('[RulesService] Failed to get analytics:', error);
      return { mailboxes: [], total_mailboxes: 0, total_rules: 0, avg_rules_per_mailbox: 0, mailboxes_with_no_rules: 0 };
    }
  },

  /** Get derived insights from cross-AM comparison */
  async insights(clientId: string): Promise<RulesInsightsResponse> {
    const cacheKey = `rules:insights:${clientId}`;
    const cached = getCached<RulesInsightsResponse>(cacheKey);
    if (cached) return cached;

    try {
      const resp = await api.get(`${API_PREFIX}/analytics/${clientId}/insights`);
      if (!resp) {
        return { insights: [], total: 0 };
      }
      const data = resp as RulesInsightsResponse;
      setCache(cacheKey, data);
      return data;
    } catch (error) {
      console.error('[RulesService] Failed to get insights:', error);
      return { insights: [], total: 0 };
    }
  },
};

// ============================================================================
// HELPERS
// ============================================================================

const SIGNAL_COLORS: Record<string, string> = {
  high_value: '#52c41a',
  escalation: '#1890ff',
  low_priority: '#faad14',
  segmentation: '#722ed1',
  neutral: '#d9d9d9',
};

const SIGNAL_LABELS: Record<string, string> = {
  high_value: 'High Value',
  escalation: 'Escalation',
  low_priority: 'Low Priority',
  segmentation: 'Segmentation',
  neutral: 'Neutral',
};

export function getSignalColor(signal: string): string {
  return SIGNAL_COLORS[signal] || '#d9d9d9';
}

export function getSignalLabel(signal: string): string {
  return SIGNAL_LABELS[signal] || signal;
}
