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

// Note: server now returns a superset of these fields. Status values now also
// include 'pending' and 'failed' (mapped from processing_jobs.status). Legacy
// values 'complete' / 'error' are no longer emitted by the new endpoint, but
// the type keeps them for transitional compatibility with old clients.
export interface ReembedStatus {
  status: 'idle' | 'pending' | 'running' | 'complete' | 'completed' | 'stopped' | 'failed' | 'error';
  // Legacy fields (still returned for backward compatibility)
  started_at?: number | string;
  completed_at?: number | string;
  result?: {
    emails: { embedded: number; skipped?: number; elapsed_s: number };
    companies: { embedded: number; elapsed_s: number };
    operations: { embedded: number; elapsed_s: number };
    total_embedded: number;
  };
  error?: string | unknown;
  // New fields from processing_jobs migration
  job_id?: string;
  client_id?: string;
  current_stage?: string | null;
  tables?: string[];
  limit?: number | null;
  processed_records?: number | null;
  failed_records?: number | null;
  total_records?: number | null;
  error_summary?: { total_errors: number; error_types: Record<string, number>; sample_errors: unknown[] } | null;
}

export interface TriggerReembedResponse {
  status: 'started' | 'already_running';
  job_id?: string;
  client_id?: string;
  tables?: string[];
  limit?: number | null;
  // 409 already_running shape (when thrown via api error wrapper, may surface in detail)
  current_status?: string;
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

export interface ThreadEmail {
  id: string;
  subject: string;
  sender_name: string | null;
  sender_email: string | null;
  sent_date: string | null;
  is_outbound: boolean;
  is_match: boolean;
}

export interface ThreadGroup {
  thread_id: string;
  subject: string;
  score: number;
  matched_count: number;
  total_emails: number;
  matched_email_ids: string[];
  emails: ThreadEmail[];
  vector_score: number;
  keyword_score: number;
  recency_score: number;
}

export interface HybridSearchResponse {
  query: string;
  cleaned_query: string;
  date_from: string | null;
  date_to: string | null;
  threads: ThreadGroup[];
  other_results: HybridResult[];
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
): Promise<TriggerReembedResponse> {
  const params = new URLSearchParams();
  if (clientId) params.set('client_id', clientId);
  if (tables && tables.length > 0) params.set('tables', tables.join(','));
  return api.post<TriggerReembedResponse>(`/v1/ai/vector/reembed?${params}`);
}

export async function getReembedStatus(clientId?: string, jobId?: string): Promise<ReembedStatus> {
  const params = new URLSearchParams();
  if (clientId) params.set('client_id', clientId);
  if (jobId) params.set('job_id', jobId);
  const qs = params.toString() ? `?${params}` : '';
  return api.get<ReembedStatus>(`/v1/ai/vector/reembed/status${qs}`);
}

export async function stopReembed(clientId?: string, jobId?: string): Promise<{ status: string; job_id?: string }> {
  const params = new URLSearchParams();
  if (clientId) params.set('client_id', clientId);
  if (jobId) params.set('job_id', jobId);
  const qs = params.toString() ? `?${params}` : '';
  return api.post<{ status: string; job_id?: string }>(`/v1/ai/vector/reembed/stop${qs}`);
}

/**
 * Stream reembed progress via SSE. Mirrors the streamDigestGeneration pattern
 * in strategicDigestService.ts (fetch + getReader + manual SSE parsing) — same
 * reasons it doesn't use EventSource: needs Authorization header.
 *
 * Calls onEvent for each event received. Resolves when the stream closes
 * (terminal event or disconnect). Pass an AbortSignal to cancel.
 */
export async function streamReembed(
  jobId: string,
  callbacks: {
    onSnapshot?: (status: ReembedStatus) => void;
    onProgress?: (status: ReembedStatus) => void;
    onTerminal?: (eventName: 'completed' | 'failed' | 'stopped', status: ReembedStatus) => void;
    onError?: (detail: string) => void;
  },
  signal?: AbortSignal,
): Promise<void> {
  const { getAccessToken } = await import('../lib/supabase');
  const token = await getAccessToken();
  const { default: config } = await import('../config');

  const response = await fetch(
    `${config.apiBaseUrl}/v1/ai/vector/reembed/stream/${jobId}`,
    {
      method: 'GET',
      headers: {
        'Accept': 'text/event-stream',
        'Authorization': `Bearer ${token}`,
      },
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(`Stream failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() || '';

    for (const chunk of chunks) {
      if (!chunk.trim() || chunk.trim().startsWith(':')) continue;

      let eventType = '';
      let dataStr = '';
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        else if (line.startsWith('data: ')) dataStr = line.slice(6);
      }

      if (!eventType || !dataStr) continue;

      try {
        const data = JSON.parse(dataStr) as ReembedStatus;
        switch (eventType) {
          case 'snapshot': callbacks.onSnapshot?.(data); break;
          case 'progress': callbacks.onProgress?.(data); break;
          case 'completed':
          case 'failed':
          case 'stopped':
            callbacks.onTerminal?.(eventType, data);
            return; // close cleanly on terminal event
          case 'error': callbacks.onError?.((data as unknown as { detail?: string }).detail || 'Stream error'); break;
        }
      } catch { /* skip malformed */ }
    }
  }
}

export async function backfillSearchText(batchSize = 10000): Promise<{ updated: number; done: boolean }> {
  return api.post<{ updated: number; batch_size: number; done: boolean }>(
    `/v1/ai/vector/backfill-search-text?batch_size=${batchSize}`,
    undefined,
    { timeout: 120000 },
  );
}
