/**
 * Vector Service — API client for semantic search + embedding management (Sprint 4 S4.4)
 */

import api from './apiClient';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SearchResult {
  query: string;
  results: any[];
  count: number;
}

export interface UnifiedSearchResult {
  query: string;
  emails: any[];
  companies: any[];
  operations: any[];
  total: number;
}

export interface VectorStats {
  emails: { total: number; embedded: number };
  companies: { total: number; embedded: number };
  operations: { total: number; embedded: number };
}

export interface ReembedStatus {
  status: 'idle' | 'running' | 'complete' | 'stopped' | 'error';
  started_at?: number;
  completed_at?: number;
  result?: {
    emails: { embedded: number; skipped?: number; elapsed_s: number };
    companies: { embedded: number; elapsed_s: number };
    operations: { embedded: number; elapsed_s: number };
    total_embedded: number;
  };
  error?: string;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export async function searchEmails(
  q: string, clientId?: string, threshold = 0.65, limit = 10
): Promise<SearchResult> {
  const params = new URLSearchParams({ q, threshold: String(threshold), limit: String(limit) });
  if (clientId) params.set('client_id', clientId);
  return api.get<SearchResult>(`/v1/ai/vector/search/emails?${params}`);
}

export async function searchCompanies(
  q: string, clientId?: string, threshold = 0.65, limit = 10
): Promise<SearchResult> {
  const params = new URLSearchParams({ q, threshold: String(threshold), limit: String(limit) });
  if (clientId) params.set('client_id', clientId);
  return api.get<SearchResult>(`/v1/ai/vector/search/companies?${params}`);
}

export async function searchOperations(
  q: string, clientId?: string, threshold = 0.65, limit = 10
): Promise<SearchResult> {
  const params = new URLSearchParams({ q, threshold: String(threshold), limit: String(limit) });
  if (clientId) params.set('client_id', clientId);
  return api.get<SearchResult>(`/v1/ai/vector/search/operations?${params}`);
}

export async function searchAll(
  q: string, clientId?: string, threshold = 0.65, limit = 5
): Promise<UnifiedSearchResult> {
  const params = new URLSearchParams({ q, threshold: String(threshold), limit: String(limit) });
  if (clientId) params.set('client_id', clientId);
  return api.get<UnifiedSearchResult>(`/v1/ai/vector/search?${params}`);
}

// ---------------------------------------------------------------------------
// Hybrid search (vector + keyword + temporal + RRF)
// ---------------------------------------------------------------------------

export interface HybridResult {
  id: string;
  source_type: 'email' | 'company' | 'operation';
  score: number;
  title: string;
  snippet: string;
  metadata: Record<string, any>;
  vector_score: number;
  keyword_score: number;
  recency_score: number;
}

export interface HybridSearchResponse {
  query: string;
  cleaned_query: string;
  date_from: string | null;
  date_to: string | null;
  results: HybridResult[];
  total: number;
  total_vector_hits: number;
  total_keyword_hits: number;
}

export async function hybridSearch(
  q: string, clientId?: string, sources?: string[], limit = 20, threshold = 0.55,
): Promise<HybridSearchResponse> {
  const params = new URLSearchParams({ q, threshold: String(threshold), limit: String(limit) });
  if (clientId) params.set('client_id', clientId);
  if (sources?.length) params.set('sources', sources.join(','));
  return api.get<HybridSearchResponse>(`/v1/ai/vector/hybrid-search?${params}`, { timeout: 30000 });
}

// ---------------------------------------------------------------------------
// Embedding management
// ---------------------------------------------------------------------------

export async function getVectorStats(clientId?: string): Promise<VectorStats> {
  const params = clientId ? `?client_id=${clientId}` : '';
  return api.get<VectorStats>(`/v1/ai/vector/stats${params}`);
}

export async function triggerReembed(
  clientId?: string, tables?: string[],
): Promise<{ status: string; client_id?: string }> {
  const params = new URLSearchParams();
  if (clientId) params.set('client_id', clientId);
  if (tables && tables.length > 0) params.set('tables', tables.join(','));
  return api.post<any>(`/v1/ai/vector/reembed?${params}`);
}

export async function getReembedStatus(clientId?: string): Promise<ReembedStatus> {
  const params = clientId ? `?client_id=${clientId}` : '';
  return api.get<ReembedStatus>(`/v1/ai/vector/reembed/status${params}`);
}

export async function stopReembed(clientId?: string): Promise<{ status: string }> {
  const params = clientId ? `?client_id=${clientId}` : '';
  return api.post<any>(`/v1/ai/vector/reembed/stop${params}`);
}

export async function backfillSearchText(batchSize = 10000): Promise<{ updated: number; done: boolean }> {
  return api.post<{ updated: number; batch_size: number; done: boolean }>(
    `/v1/ai/vector/backfill-search-text?batch_size=${batchSize}`,
    undefined,
    { timeout: 120000 },
  );
}
