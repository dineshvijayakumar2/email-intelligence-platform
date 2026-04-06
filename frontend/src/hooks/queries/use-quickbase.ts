/**
 * TanStack Query hooks for QuickBase synced data tables.
 * Generic useQBTable hook works for all 7 QB tables.
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query';
import api from '../../services/apiClient';

export interface QBTableParams {
  clientId: string;
  endpoint: string;       // 'customers' | 'contacts' | 'quotes' | etc.
  responseKey: string;    // Key in response object containing the array
  page: number;
  pageSize: number;
  search?: string;
  sort_by?: string;
  sort_dir?: string;
}

export function useQBTable<T = any>(params: QBTableParams) {
  const { clientId, endpoint, responseKey, page, pageSize, search, sort_by, sort_dir } = params;
  const offset = (page - 1) * pageSize;

  return useQuery({
    queryKey: ['qb-table', endpoint, clientId, page, pageSize, search, sort_by, sort_dir] as const,
    queryFn: async (): Promise<{ items: T[]; total: number }> => {
      const qs = new URLSearchParams({
        client_id: clientId,
        limit: String(pageSize),
        offset: String(offset),
      });
      if (search) qs.set('search', search);
      if (sort_by) qs.set('sort_by', sort_by);
      if (sort_dir) qs.set('sort_dir', sort_dir);
      const resp = await api.get<any>(`/v1/quickbase/${endpoint}?${qs}`);
      return { items: resp?.[responseKey] || [], total: resp?.total || 0 };
    },
    enabled: !!clientId,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
}

export function useQBSyncStatus(clientId?: string | null) {
  return useQuery({
    queryKey: ['qb-sync-status', clientId] as const,
    queryFn: async () => {
      const resp = await api.get<any>(`/v1/quickbase/sync-status?client_id=${clientId}`);
      return resp;
    },
    enabled: !!clientId,
    staleTime: 10_000,
  });
}
