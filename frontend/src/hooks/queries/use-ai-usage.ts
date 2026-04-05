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

export function useAIControls() {
  return useQuery<AIControlSettings | null>({
    queryKey: ['ai-controls'],
    queryFn: () => controlsApi.get(),
    staleTime: 30_000,
  });
}

export function useAIRecentLogs(limit = 30) {
  return useQuery<{ items: UsageLogEntry[] }>({
    queryKey: ['ai-recent-logs', limit],
    queryFn: () => usageApi.getRecent(limit),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useAIModels() {
  return useQuery<{ models: AIModel[] }>({
    queryKey: ['ai-models'],
    queryFn: () => modelsApi.getAvailable().catch(() => ({ models: [] })),
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
