/**
 * TanStack Query hooks for Data Health page data.
 */

import { useQuery } from '@tanstack/react-query';
import {
  dataHealthApi,
  type DataHealthResponse,
} from '../../services/analyticsService';
import api from '../../services/apiClient';

export function useDataHealth(clientId: string) {
  return useQuery<DataHealthResponse>({
    queryKey: ['data-health', clientId],
    queryFn: () => dataHealthApi.get(clientId),
    enabled: !!clientId,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useClassificationHealth(clientId: string) {
  return useQuery<any>({
    queryKey: ['data-health-classification', clientId],
    queryFn: () => api.get<any>(`/v1/analytics/data-health/classification?client_id=${clientId}`).catch(() => null),
    enabled: !!clientId,
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
}

export function useThreadHealth(clientId: string) {
  return useQuery<any>({
    queryKey: ['data-health-threads', clientId],
    queryFn: () => api.get<any>(`/v1/analytics/data-health/threads?client_id=${clientId}`).catch(() => null),
    enabled: !!clientId,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });
}
