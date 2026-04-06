/**
 * TanStack Query hooks for Email list page.
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { emailService } from '../../services/emailService';
import type { EmailFilters, Email } from '../../services/emailService';

export interface EmailQueryParams {
  filters: EmailFilters;
  page: number;
  pageSize: number;
  sort_by?: string;
  sort_dir?: string;
}

export function useEmails(params: EmailQueryParams) {
  return useQuery({
    queryKey: ['emails', params] as const,
    queryFn: (): Promise<{ emails: Email[]; totalCount: number }> => emailService.getEmails(
      params.filters, params.page, params.pageSize,
      params.sort_by, params.sort_dir,
    ),
    enabled: !!(params.filters.mailbox || params.filters.company_id),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
}

export function useEmailDetail(emailId?: string | null) {
  return useQuery<Email | null>({
    queryKey: ['email-detail', emailId],
    queryFn: () => emailService.getEmail(emailId!),
    enabled: !!emailId,
    staleTime: 60_000,
  });
}
