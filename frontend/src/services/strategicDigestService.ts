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

  cancel: async (clientId: string) => {
    return api.post<{ status: string; message: string }>(`${API_PREFIX}/strategic-digest/${clientId}/cancel`);
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

/**
 * Stream digest generation via SSE.
 * Replaces the generate-then-poll pattern with a single streaming connection.
 */
export async function streamDigestGeneration(
  clientId: string,
  periodType: PeriodType = 'monthly',
  callbacks: {
    onProgress: (phase: string, pct: number, message: string) => void;
    onComplete: (digest: StrategicDigest | null) => void;
    onError: (detail: string) => void;
    onCancelled?: () => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const { getAccessToken } = await import('../lib/supabase');
  const token = await getAccessToken();
  const { default: config } = await import('../config');

  const params = new URLSearchParams({ period_type: periodType });
  const response = await fetch(
    `${config.apiBaseUrl}${API_PREFIX}/strategic-digest/${clientId}/stream?${params}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(`Stream failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() || '';

    for (const chunk of chunks) {
      if (!chunk.trim() || chunk.trim().startsWith(':')) continue;

      let eventType = '';
      let dataStr = '';
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        else if (line.startsWith('data: ')) dataStr = line.slice(6);
      }

      if (!eventType || !dataStr) continue;

      try {
        const data = JSON.parse(dataStr);
        switch (eventType) {
          case 'progress':
            callbacks.onProgress(data.phase, data.pct, data.message);
            break;
          case 'complete':
            callbacks.onComplete(data.digest ?? null);
            break;
          case 'error':
            callbacks.onError(data.detail || 'Generation failed');
            break;
          case 'cancelled':
            callbacks.onCancelled?.();
            break;
        }
      } catch { /* skip malformed */ }
    }
  }
}

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
  company: async (companyId: string, force = false, clientId?: string) => {
    const qs = `force=${force}${clientId ? `&client_id=${clientId}` : ''}`;
    return api.get<{ insight: AIInsight }>(`${API_PREFIX}/insights/company/${companyId}?${qs}`, { timeout: 60000 });
  },

  contact: async (contactId: string, force = false, clientId?: string) => {
    const qs = `force=${force}${clientId ? `&client_id=${clientId}` : ''}`;
    return api.get<{ insight: AIInsight }>(`${API_PREFIX}/insights/contact/${contactId}?${qs}`, { timeout: 60000 });
  },

  thread: async (threadId: string, force = false, clientId?: string) => {
    const qs = `force=${force}${clientId ? `&client_id=${clientId}` : ''}`;
    return api.get<{ insight: AIInsight }>(`${API_PREFIX}/insights/thread/${threadId}?${qs}`, { timeout: 60000 });
  },
};

// --- Model Management ---

export const modelsApi = {
  getAvailable: async () => {
    return api.get<{ models: AIModel[] }>(`${API_PREFIX}/models`);
  },

  updateDefaults: async (cheapModel: string, strategicModel: string, clientId?: string) => {
    const qs = `cheap_model=${cheapModel}&strategic_model=${strategicModel}${clientId ? `&client_id=${clientId}` : ''}`;
    return api.put<{ status: string }>(`${API_PREFIX}/models/defaults?${qs}`);
  },
};
