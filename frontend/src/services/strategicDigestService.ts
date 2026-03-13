/**
 * Strategic Digest API Service — Sprint 3
 */

import api from './apiClient';
import type { StrategicDigest, StrategicDigestHistory, PeriodType, AIInsight, AIModel } from '../types/strategic-digest';

const API_PREFIX = '/v1/ai';

// --- Strategic Digest ---

export const strategicDigestApi = {
  get: async (clientId: string, periodType: PeriodType = 'monthly', date?: string) => {
    const params = new URLSearchParams({ period_type: periodType });
    if (date) params.append('date', date);
    return api.get<{ digest: StrategicDigest | null }>(`${API_PREFIX}/strategic-digest/${clientId}?${params}`);
  },

  generate: async (clientId: string, periodType: PeriodType = 'monthly', periodStart?: string, periodEnd?: string) => {
    const params = new URLSearchParams({ period_type: periodType });
    if (periodStart) params.append('period_start', periodStart);
    if (periodEnd) params.append('period_end', periodEnd);
    return api.post<{ status: string; message: string }>(`${API_PREFIX}/strategic-digest/${clientId}/generate?${params}`);
  },

  getHistory: async (clientId: string, limit = 10) => {
    return api.get<{ digests: StrategicDigestHistory[] }>(`${API_PREFIX}/strategic-digest/${clientId}/history?limit=${limit}`);
  },

  getProgress: async (clientId: string) => {
    return api.get<{
      phase: string;
      current: number;
      total: number;
      pct: number;
      message: string;
      elapsed_s?: number;
    }>(`${API_PREFIX}/strategic-digest/${clientId}/progress`);
  },
};

// --- AM Performance ---

export const amPerformanceApi = {
  get: async (clientId: string, periodStart?: string, periodEnd?: string) => {
    const params = new URLSearchParams();
    if (periodStart) params.append('period_start', periodStart);
    if (periodEnd) params.append('period_end', periodEnd);
    const qs = params.toString();
    return api.get<{ snapshots: any[] }>(`${API_PREFIX}/am-performance/${clientId}${qs ? `?${qs}` : ''}`);
  },
};

// --- AI Insights (per-page) ---

export const insightsApi = {
  company: async (companyId: string, force = false) => {
    return api.get<{ insight: AIInsight }>(`${API_PREFIX}/insights/company/${companyId}?force=${force}`);
  },

  contact: async (contactId: string, force = false) => {
    return api.get<{ insight: AIInsight }>(`${API_PREFIX}/insights/contact/${contactId}?force=${force}`);
  },

  thread: async (threadId: string, force = false) => {
    return api.get<{ insight: AIInsight }>(`${API_PREFIX}/insights/thread/${threadId}?force=${force}`);
  },
};

// --- Model Management ---

export const modelsApi = {
  getAvailable: async () => {
    return api.get<{ models: AIModel[] }>(`${API_PREFIX}/models`);
  },

  updateDefaults: async (cheapModel: string, strategicModel: string) => {
    return api.put<{ status: string }>(`${API_PREFIX}/models/defaults?cheap_model=${cheapModel}&strategic_model=${strategicModel}`);
  },
};
