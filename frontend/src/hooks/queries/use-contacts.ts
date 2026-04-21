/**
 * TanStack Query hooks for contact data.
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { contactsApi, contactIntelligenceApi } from '../../services/analyticsService';
import type {
  ContactAnalytics,
  ContactAnalyticsListResponse,
  ContactFilterParams,
  TopEngagedContact,
  AtRiskContact,
} from '../../types/analytics';

export function useContacts(params: ContactFilterParams) {
  return useQuery<ContactAnalyticsListResponse>({
    queryKey: ['contacts', params],
    queryFn: () => contactsApi.list(params),
    placeholderData: keepPreviousData,
    enabled: !!params.client_id,
  });
}

export function useContactDetail(contactId: string | undefined) {
  return useQuery<ContactAnalytics | null>({
    queryKey: ['contact', contactId],
    queryFn: () => contactsApi.getDetail(contactId!),
    enabled: !!contactId,
  });
}

export function useTopEngagedContacts(clientId: string, limit = 50) {
  return useQuery<TopEngagedContact[]>({
    queryKey: ['contacts-top', clientId, limit],
    queryFn: () => contactsApi.topEngaged(clientId, limit),
    enabled: !!clientId,
    staleTime: 60_000,
  });
}

export function useAtRiskContacts(clientId: string) {
  return useQuery<AtRiskContact[]>({
    queryKey: ['contacts-atrisk', clientId],
    queryFn: () => contactsApi.atRisk(clientId),
    enabled: !!clientId,
    staleTime: 60_000,
  });
}

export function useContactPersona(contactId: string | undefined) {
  return useQuery<any>({
    queryKey: ['contact-persona', contactId],
    queryFn: () => contactIntelligenceApi.getPersona(contactId!),
    enabled: !!contactId,
    staleTime: 60_000,
  });
}

export function useContactDealActivity(contactId: string | undefined) {
  return useQuery<any>({
    queryKey: ['contact-deal-activity', contactId],
    queryFn: () => contactIntelligenceApi.getDealActivity(contactId!),
    enabled: !!contactId,
    staleTime: 60_000,
  });
}
