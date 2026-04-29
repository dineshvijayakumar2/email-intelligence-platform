/**
 * TanStack Query hooks for Email list page.
 */

import { useMemo } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { emailService } from '../../services/emailService';
import { contactsApi, companiesApi } from '../../services/analyticsService';
import { useThreadDetail } from './use-threads';
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

export function useContactEmails(contactId: string | null, limit = 100) {
  return useQuery({
    queryKey: ['contact-emails', contactId, limit],
    queryFn: async () => {
      const r = await contactsApi.getEmails(contactId!, limit, 0);
      const sorted = ((r.emails || []) as Email[]).sort(
        (a, b) => new Date(b.sent_date).getTime() - new Date(a.sent_date).getTime(),
      );
      return { emails: sorted, total: r.total || 0 };
    },
    enabled: !!contactId,
    staleTime: 30_000,
  });
}

export function useCompanyEmails(companyId: string | null, limit = 100) {
  return useQuery({
    queryKey: ['company-emails', companyId, limit],
    queryFn: async () => {
      const r = await companiesApi.getEmails(companyId!, limit, 0);
      const sorted = ((r.emails || []) as Email[]).sort(
        (a, b) => new Date(b.sent_date).getTime() - new Date(a.sent_date).getTime(),
      );
      return { emails: sorted, total: r.total || 0 };
    },
    enabled: !!companyId,
    staleTime: 30_000,
  });
}

export function useThreadEmails(threadId: string | null) {
  const threadQuery = useThreadDetail(threadId ?? undefined);
  return useMemo(() => {
    const emails = ((threadQuery.data?.emails || []) as any[]).map(e => ({
      id: e.id, subject: e.subject || '', sender_email: e.sender_email || '',
      sender_name: e.sender_name || '', recipients: e.recipients || [],
      sent_date: e.sent_date || '', is_outbound: e.is_outbound ?? false,
      body_text: e.body_text || '', folder_path: e.folder_path || '',
    } as Email)).sort(
      (a, b) => new Date(b.sent_date).getTime() - new Date(a.sent_date).getTime(),
    );
    return {
      data: emails.length ? { emails, total: emails.length } : undefined,
      isLoading: threadQuery.isLoading,
      error: threadQuery.error,
    };
  }, [threadQuery.data, threadQuery.isLoading, threadQuery.error]);
}
