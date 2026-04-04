/**
 * TanStack Query hooks for thread data.
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { threadsApi } from '../../services/analyticsService';
import type {
  ThreadStatusListResponse,
  ThreadFilterParams,
  OverdueThread,
  ThreadStatusCount,
  ThreadDetail,
} from '../../types/analytics';

export function useThreads(params: ThreadFilterParams) {
  return useQuery<ThreadStatusListResponse>({
    queryKey: ['threads', params],
    queryFn: () => threadsApi.list(params),
    placeholderData: keepPreviousData,
    enabled: !!(params.client_id || params.mailbox_id),
  });
}

export function useThreadsByCompany(companyId: string | undefined, limit = 500) {
  return useQuery<ThreadStatusListResponse>({
    queryKey: ['threads-by-company', companyId, limit],
    queryFn: () => threadsApi.byCompany(companyId!, limit),
    enabled: !!companyId,
  });
}

export function useThreadsByContact(contactId: string | undefined, limit = 500) {
  return useQuery<ThreadStatusListResponse>({
    queryKey: ['threads-by-contact', contactId, limit],
    queryFn: () => threadsApi.byContact(contactId!, limit),
    enabled: !!contactId,
  });
}

export function useOverdueThreads(clientId: string) {
  return useQuery<OverdueThread[]>({
    queryKey: ['threads-overdue', clientId],
    queryFn: () => threadsApi.overdue(clientId),
    enabled: !!clientId,
    staleTime: 60_000,
  });
}

export function useThreadStatusCounts(clientId: string) {
  return useQuery<ThreadStatusCount[]>({
    queryKey: ['threads-counts', clientId],
    queryFn: () => threadsApi.byStatus(clientId),
    enabled: !!clientId,
    staleTime: 60_000,
  });
}

export function useThreadDetail(threadId: string | undefined) {
  return useQuery<ThreadDetail | null>({
    queryKey: ['thread-detail', threadId],
    queryFn: () => threadsApi.getDetail(threadId!),
    enabled: !!threadId,
  });
}
