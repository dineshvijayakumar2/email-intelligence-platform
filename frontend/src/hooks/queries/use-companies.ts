/**
 * TanStack Query hooks for company data.
 * Replaces manual useState/useEffect + cache in companies.tsx.
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { companiesApi } from '../../services/analyticsService';
import api from '../../services/apiClient';
import type {
  CompanyAnalytics,
  CompanyAnalyticsListResponse,
  CompanyFilterParams,
  TopEngagedCompany,
  AtRiskCompany,
  EngagementStatusGrouping,
} from '../../types/analytics';

export function useCompanies(params: CompanyFilterParams) {
  return useQuery<CompanyAnalyticsListResponse>({
    queryKey: ['companies', params],
    queryFn: () => companiesApi.list(params),
    placeholderData: keepPreviousData,  // Smooth pagination — no flash to skeleton
    enabled: !!params.client_id,
  });
}

export function useCompanyDetail(companyId: string | undefined) {
  return useQuery<CompanyAnalytics | null>({
    queryKey: ['company', companyId],
    queryFn: () => companiesApi.getDetail(companyId!),
    enabled: !!companyId,
  });
}

export function useTopEngagedCompanies(clientId: string, limit = 50) {
  return useQuery<TopEngagedCompany[]>({
    queryKey: ['companies-top', clientId, limit],
    queryFn: () => companiesApi.topEngaged(clientId, limit),
    enabled: !!clientId,
    staleTime: 60_000,  // Aggregation — longer stale time
  });
}

export function useAtRiskCompanies(clientId: string) {
  return useQuery<AtRiskCompany[]>({
    queryKey: ['companies-atrisk', clientId],
    queryFn: () => companiesApi.atRisk(clientId),
    enabled: !!clientId,
    staleTime: 60_000,
  });
}

export function useCompanyEngagementGroups(clientId: string) {
  return useQuery<EngagementStatusGrouping[]>({
    queryKey: ['companies-engagement', clientId],
    queryFn: () => companiesApi.byEngagement(clientId),
    enabled: !!clientId,
    staleTime: 60_000,
  });
}

export function useOrderHistory(companyId: string | undefined) {
  return useQuery<{
    items: any[]; total: number; quote_count?: number; job_count?: number; active_jobs?: number; accepted_quotes?: number;
    computed_revenue?: number; computed_invoiced_ty?: number; computed_invoiced_ly?: number; computed_growth_90d?: number; computed_days_since_last_order?: number;
  }>({
    queryKey: ['order-history', companyId],
    queryFn: () => companiesApi.getOrderHistory(companyId!),
    enabled: !!companyId,
    staleTime: 60_000,
  });
}

export function useProductProfile(companyId: string | undefined) {
  return useQuery<{ categories: any[]; operations: any[]; capability_breakdown?: any[]; process_tags?: string[]; embellishment_tags?: string[] }>({
    queryKey: ['product-profile', companyId],
    queryFn: () => companiesApi.getProductProfile(companyId!),
    enabled: !!companyId,
    staleTime: 60_000,
  });
}

export function useCompanyFilterOptions(clientId: string) {
  return useQuery<{ tiers: string[]; account_managers: string[] }>({
    queryKey: ['company-filter-options', clientId],
    queryFn: async () => {
      const data = await api.get<{ tiers: string[]; account_managers: string[] }>(
        `/v1/analytics/companies/filter-options?client_id=${clientId}`
      );
      return data || { tiers: [], account_managers: [] };
    },
    enabled: !!clientId,
    staleTime: 5 * 60_000,  // Filter options change rarely
  });
}
