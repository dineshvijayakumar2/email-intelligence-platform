/**
 * Intelligence Config Service — Capability taxonomy, classifier rules, cache management.
 */

import api from './apiClient';

const BASE = '/v1/intelligence-config';

function qs(clientId?: string, extra?: Record<string, string>): string {
  const params = new URLSearchParams();
  if (clientId) params.set('client_id', clientId);
  if (extra) Object.entries(extra).forEach(([k, v]) => { if (v) params.set(k, v); });
  const str = params.toString();
  return str ? `?${str}` : '';
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface CapabilityTag {
  tag_id: string;
  name: string;
  color: string;
  description: string;
}

export interface ClassifierRule {
  dept: string;
  op: string;
  machine: string;
  count: number;
  tag: string | null;
  granular_tags: string[];
  flags: string[];
  row_type: string | null;
}

export interface RushSettings {
  am_rush_pattern: string;
  rush_pct_threshold: number;
  gap_count_threshold: number;
}

export interface ReclassifyStatus {
  status: 'idle' | 'running' | 'complete' | 'error';
  updated?: number;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

// ── Capability Tags ────────────────────────────────────────────────────────

export async function getCapabilityTags(clientId?: string): Promise<{ tags: CapabilityTag[]; version: number }> {
  return api.get(`${BASE}/capability-tags${qs(clientId)}`);
}

export async function updateCapabilityTags(tags: CapabilityTag[], clientId?: string): Promise<void> {
  return api.put(`${BASE}/capability-tags${qs(clientId)}`, { tags });
}

// ── Classifier Rules ───────────────────────────────────────────────────────

export async function getClassifierRules(params: {
  page?: number;
  page_size?: number;
  tag?: string;
  dept?: string;
  clientId?: string;
}): Promise<{ rules: ClassifierRule[]; total: number; page: number; page_size: number; version: number }> {
  return api.get(`${BASE}/classifier-rules${qs(params.clientId, {
    page: params.page ? String(params.page) : '',
    page_size: params.page_size ? String(params.page_size) : '',
    tag: params.tag || '',
    dept: params.dept || '',
  })}`);
}

export async function importClassifierRules(payload: {
  rules?: ClassifierRule[];
  csv_text?: string;
  replace?: boolean;
}, clientId?: string): Promise<{ ok: boolean; imported: number; total_rules: number }> {
  return api.post(`${BASE}/classifier-rules/import${qs(clientId)}`, payload);
}

// ── Rush Settings ──────────────────────────────────────────────────────────

export async function getRushSettings(clientId?: string): Promise<{ settings: RushSettings; version: number }> {
  return api.get(`${BASE}/rush-settings${qs(clientId)}`);
}

export async function updateRushSettings(settings: RushSettings, clientId?: string): Promise<void> {
  return api.put(`${BASE}/rush-settings${qs(clientId)}`, settings);
}

// ── Reclassify ─────────────────────────────────────────────────────────────

export async function triggerReclassify(clientId?: string): Promise<{ ok: boolean; message: string }> {
  return api.post(`${BASE}/reclassify${qs(clientId)}`, {});
}

export async function getReclassifyStatus(clientId?: string): Promise<ReclassifyStatus> {
  return api.get(`${BASE}/reclassify/status${qs(clientId)}`);
}

// ── Cache ──────────────────────────────────────────────────────────────────

export async function getCacheStatus(params?: {
  cache_type?: string;
  page?: number;
  clientId?: string;
}): Promise<{ entries: any[]; page: number; page_size: number }> {
  return api.get(`${BASE}/cache${qs(params?.clientId, {
    cache_type: params?.cache_type || '',
    page: params?.page ? String(params.page) : '',
  })}`);
}

export async function clearCache(cacheType?: string, clientId?: string): Promise<{ ok: boolean; deleted: number }> {
  return api.delete(`${BASE}/cache${qs(clientId, { cache_type: cacheType || '' })}`);
}
