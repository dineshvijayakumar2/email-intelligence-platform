/**
 * Intelligence Config Service — Capability taxonomy, classifier rules, cache management.
 */

import api from './apiClient';

const BASE = '/v1/intelligence-config';

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

export async function getCapabilityTags(): Promise<{ tags: CapabilityTag[]; version: number }> {
  return api.get(`${BASE}/capability-tags`);
}

export async function updateCapabilityTags(tags: CapabilityTag[]): Promise<void> {
  return api.put(`${BASE}/capability-tags`, { tags });
}

// ── Classifier Rules ───────────────────────────────────────────────────────

export async function getClassifierRules(params: {
  page?: number;
  page_size?: number;
  tag?: string;
  dept?: string;
}): Promise<{ rules: ClassifierRule[]; total: number; page: number; page_size: number; version: number }> {
  const qs = new URLSearchParams();
  if (params.page)      qs.set('page', String(params.page));
  if (params.page_size) qs.set('page_size', String(params.page_size));
  if (params.tag)       qs.set('tag', params.tag);
  if (params.dept)      qs.set('dept', params.dept);
  return api.get(`${BASE}/classifier-rules?${qs}`);
}

export async function importClassifierRules(payload: {
  rules?: ClassifierRule[];
  csv_text?: string;
  replace?: boolean;
}): Promise<{ ok: boolean; imported: number; total_rules: number }> {
  return api.post(`${BASE}/classifier-rules/import`, payload);
}

// ── Rush Settings ──────────────────────────────────────────────────────────

export async function getRushSettings(): Promise<{ settings: RushSettings; version: number }> {
  return api.get(`${BASE}/rush-settings`);
}

export async function updateRushSettings(settings: RushSettings): Promise<void> {
  return api.put(`${BASE}/rush-settings`, settings);
}

// ── Reclassify ─────────────────────────────────────────────────────────────

export async function triggerReclassify(): Promise<{ ok: boolean; message: string }> {
  return api.post(`${BASE}/reclassify`, {});
}

export async function getReclassifyStatus(): Promise<ReclassifyStatus> {
  return api.get(`${BASE}/reclassify/status`);
}

// ── Cache ──────────────────────────────────────────────────────────────────

export async function getCacheStatus(params?: {
  cache_type?: string;
  page?: number;
}): Promise<{ entries: any[]; page: number; page_size: number }> {
  const qs = new URLSearchParams();
  if (params?.cache_type) qs.set('cache_type', params.cache_type);
  if (params?.page)       qs.set('page', String(params.page));
  return api.get(`${BASE}/cache?${qs}`);
}

export async function clearCache(cacheType?: string): Promise<{ ok: boolean; deleted: number }> {
  const qs = cacheType ? `?cache_type=${cacheType}` : '';
  return api.delete(`${BASE}/cache${qs}`);
}
