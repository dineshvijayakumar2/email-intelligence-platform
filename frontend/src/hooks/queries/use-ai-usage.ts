/**
 * TanStack Query hooks for AI Usage page data.
 */

import { useQuery } from '@tanstack/react-query';
import { usageApi, controlsApi } from '../../services/aiService';
import { modelsApi } from '../../services/strategicDigestService';
import api from '../../services/apiClient';
import type { UsageSummary, MonitoringStats, AIControlSettings, UsageLogEntry } from '../../types/ai';
import type { AIModel } from '../../types/strategic-digest';

export function useAICosts(clientId: string, days = 30) {
  return useQuery<UsageSummary | null>({
    queryKey: ['ai-costs', clientId, days],
    queryFn: () => usageApi.getCosts(clientId || undefined, days),
    enabled: !!clientId,
    refetchInterval: 60_000,  // Auto-refresh every 60s
  });
}

export function useAIMonitoring(clientId: string) {
  return useQuery<MonitoringStats | null>({
    queryKey: ['ai-monitoring', clientId],
    queryFn: () => usageApi.getMonitoring(clientId || undefined),
    enabled: !!clientId,
    refetchInterval: 60_000,
  });
}

export function useAIControls(clientId?: string) {
  return useQuery<AIControlSettings | null>({
    queryKey: ['ai-controls', clientId],
    queryFn: () => clientId ? controlsApi.getWithClient(clientId) : controlsApi.get(),
    staleTime: 30_000,
    enabled: !!clientId,
  });
}

export function useAITaskModels(clientId: string) {
  return useQuery<any>({
    queryKey: ['ai-task-models', clientId],
    queryFn: () => api.get<any>(`/v1/ai/task-models?client_id=${clientId}`).catch(() => null),
    enabled: !!clientId,
    staleTime: 30_000,
  });
}

export function useAIRecentLogs(clientId: string, limit = 30) {
  return useQuery<{ items: UsageLogEntry[] }>({
    queryKey: ['ai-recent-logs', clientId, limit],
    queryFn: () => usageApi.getRecent(limit, clientId),
    enabled: !!clientId,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

// Static fallback models — ensures the model assignment section always renders
const FALLBACK_MODELS: AIModel[] = [
  { name: 'haiku', label: 'Claude Haiku (fast, cheap)', provider: 'anthropic', cost_input_per_mtok: 0.80, cost_output_per_mtok: 4.00, available: true },
  { name: 'sonnet', label: 'Claude Sonnet (strategic)', provider: 'anthropic', cost_input_per_mtok: 3.00, cost_output_per_mtok: 15.00, available: true },
  { name: 'gemini', label: 'Gemini 2.5 Flash', provider: 'google', cost_input_per_mtok: 0.15, cost_output_per_mtok: 0.60, available: true },
  { name: 'gpt4o-mini', label: 'GPT-4o Mini (cheap)', provider: 'openai', cost_input_per_mtok: 0.15, cost_output_per_mtok: 0.60, available: true },
  { name: 'gpt4o', label: 'GPT-4o (strategic)', provider: 'openai', cost_input_per_mtok: 2.50, cost_output_per_mtok: 10.00, available: true },
];

export function useAIModels() {
  return useQuery<{ models: AIModel[] }>({
    queryKey: ['ai-models'],
    queryFn: async () => {
      try {
        const result = await modelsApi.getAvailable();
        if (result?.models?.length) return result;
      } catch { /* fallback below */ }
      return { models: FALLBACK_MODELS };
    },
    staleTime: 5 * 60_000,
  });
}

export function useAIApiKeys(clientId: string) {
  return useQuery<any>({
    queryKey: ['ai-api-keys', clientId],
    queryFn: () => api.get<any>(`/v1/ai/api-keys${clientId ? `?client_id=${clientId}` : ''}`).catch(() => null),
    enabled: !!clientId,
    staleTime: 60_000,
  });
}

export function useVectorStats(clientId: string) {
  return useQuery<any>({
    queryKey: ['vector-stats', clientId],
    queryFn: async () => {
      const { getVectorStats } = await import('../../services/vectorService');
      return getVectorStats(clientId);
    },
    enabled: !!clientId,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useEmbeddingConfig(clientId: string) {
  return useQuery<any>({
    queryKey: ['ai-embedding-config', clientId],
    queryFn: () => api.get<any>(`/v1/ai/embedding-config?client_id=${clientId}`).catch(() => null),
    enabled: !!clientId,
    staleTime: 30_000,
  });
}

export function useClientAISettings(clientId: string) {
  return useQuery<Record<string, string>>({
    queryKey: ['ai-client-settings', clientId],
    queryFn: async () => {
      const resp = await api.get<any[]>(`/v1/ai/client-settings?client_id=${clientId}`);
      if (!resp) return {};
      const map: Record<string, string> = {};
      for (const row of resp) map[row.key] = row.value;
      return map;
    },
    enabled: !!clientId,
    staleTime: 30_000,
  });
}
