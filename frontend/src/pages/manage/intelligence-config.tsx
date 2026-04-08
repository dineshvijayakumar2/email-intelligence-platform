/**
 * Intelligence Config — Capability taxonomy, classifier rules, rush settings, cache.
 * Route: /manage/intelligence-config (admin only)
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  RefreshCw, CheckCircle2, AlertTriangle, Upload, Trash2, Info,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { notify } from '@/lib/toast';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { useClient } from '../../contexts/ClientContext';
import { formatNumber } from '../../utils/numberFormat';
import {
  getCapabilityTags, getClassifierRules, importClassifierRules,
  getRushSettings, updateRushSettings,
  triggerReclassify, getReclassifyStatus,
  getCacheStatus, clearCache,
  type CapabilityTag, type ClassifierRule, type RushSettings, type ReclassifyStatus,
} from '../../services/intelligenceConfigService';

const FLAG_COLORS: Record<string, { bg: string; text: string }> = {
  has_coating:             { bg: 'bg-blue-100',   text: 'text-blue-700' },
  has_sewing:              { bg: 'bg-purple-100', text: 'text-purple-700' },
  has_outsource_component: { bg: 'bg-orange-100', text: 'text-orange-700' },
};

const ROW_TYPE_COLORS: Record<string, { bg: string; text: string }> = {
  production:  { bg: 'bg-green-100',  text: 'text-green-700' },
  process:     { bg: 'bg-cyan-100',   text: 'text-cyan-700' },
  outsource:   { bg: 'bg-orange-100', text: 'text-orange-700' },
  logistics:   { bg: 'bg-blue-100',   text: 'text-blue-700' },
  leadtime:    { bg: 'bg-red-100',    text: 'text-red-700' },
  costing:     { bg: 'bg-yellow-100', text: 'text-yellow-700' },
  rush_charge: { bg: 'bg-red-100',    text: 'text-red-700' },
  admin:       { bg: 'bg-slate-100',  text: 'text-slate-600' },
  constraint:  { bg: 'bg-indigo-100', text: 'text-indigo-700' },
};

const TAG_OPTIONS = [
  'Flat Sheets', 'Soft Cover Books', 'Hard Cover Books', 'Wide Format',
  'Embellishment', 'Specialty Finishing', 'Design Services', 'Display / Installation',
];

// ─────────────────────────────────────────────────────────────────────────────
// Tab 1: Capability Tags
// ─────────────────────────────────────────────────────────────────────────────

function CapabilityTagsTab({ clientId }: { clientId?: string }) {
  const [tags, setTags] = useState<CapabilityTag[]>([]);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getCapabilityTags(clientId)
      .then(r => { setTags(r.tags); setVersion(r.version); })
      .catch(() => notify.error('Failed to load capability tags'))
      .finally(() => setLoading(false));
  }, [clientId]);

  if (loading) return <ContentSkeleton rows={4} />;

  return (
    <div>
      {/* Info alert */}
      <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-3 mb-4">
        <Info className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-medium text-blue-800">8 MVP Capability Tags</p>
          <p className="text-xs text-blue-600 mt-0.5">
            These are the top-level product categories used for recommendations and customer profiles.
            Phase 2A will expand these into ~30 granular sub-tags.
          </p>
        </div>
      </div>

      {/* Tag grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        {tags.map(tag => (
          <div
            key={tag.tag_id}
            className="rounded-lg border bg-white shadow-sm p-3"
            style={{ borderLeft: `4px solid ${tag.color}` }}
          >
            <p className="text-sm font-semibold" style={{ color: tag.color }}>{tag.name}</p>
            <p className="text-xs text-slate-500 mt-0.5">{tag.description}</p>
          </div>
        ))}
      </div>

      <p className="text-xs text-slate-400 mt-4">
        Config version: {version} — Tag editing will be available in Phase 2A.
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 2: Classifier Rules
// ─────────────────────────────────────────────────────────────────────────────

function ClassifierRulesTab({ clientId }: { clientId?: string }) {
  const [rules, setRules] = useState<ClassifierRule[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [tagFilter, setTagFilter] = useState<string>('');
  const [deptFilter, setDeptFilter] = useState<string>('');
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [csvText, setCsvText] = useState('');
  const [replaceMode, setReplaceMode] = useState(false);
  const [importing, setImporting] = useState(false);

  const PAGE_SIZE = 50;

  const load = useCallback(() => {
    setLoading(true);
    getClassifierRules({ page, page_size: PAGE_SIZE, tag: tagFilter || undefined, dept: deptFilter || undefined, clientId })
      .then(r => { setRules(r.rules); setTotal(r.total); setVersion(r.version); })
      .catch(() => notify.error('Failed to load classifier rules'))
      .finally(() => setLoading(false));
  }, [page, tagFilter, deptFilter, clientId]);

  useEffect(() => { load(); }, [load]);

  const handleImport = async () => {
    if (!csvText.trim()) { notify.warning('Paste CSV data first'); return; }
    setImporting(true);
    try {
      const result = await importClassifierRules({ csv_text: csvText, replace: replaceMode }, clientId);
      notify.success(`Imported ${result.imported} rules — ${result.total_rules} total`);
      setImportModalOpen(false);
      setCsvText('');
      load();
    } catch {
      notify.error('Import failed — check CSV format');
    } finally {
      setImporting(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div>
      {/* Filters toolbar */}
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            type="text"
            placeholder="Filter by department..."
            value={deptFilter}
            onChange={e => { setDeptFilter(e.target.value); setPage(1); }}
            className="h-8 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-52"
          />
          <select
            value={tagFilter}
            onChange={e => { setTagFilter(e.target.value); setPage(1); }}
            className="h-8 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-48"
          >
            <option value="">All tags</option>
            {TAG_OPTIONS.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <span className="text-xs text-slate-400">
            {formatNumber(total)} rules &middot; v{version}
          </span>
        </div>
        <button
          onClick={() => setImportModalOpen(true)}
          className="inline-flex items-center gap-1.5 h-8 px-3 text-sm font-medium rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition-colors"
        >
          <Upload className="h-3.5 w-3.5" />
          Import CSV
        </button>
      </div>

      {/* Rules table */}
      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        {loading ? (
          <ContentSkeleton rows={8} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[900px]">
              <thead>
                <tr className="border-b bg-slate-50/50">
                  <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-40">Department</th>
                  <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Operation</th>
                  <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-44">Machine</th>
                  <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Count</th>
                  <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-40">MVP Tag</th>
                  <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-48">Flags</th>
                  <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Row Type</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rules.map((r, i) => (
                  <tr key={`${r.dept}-${r.op}-${r.machine}-${i}`} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-3 py-2 text-xs truncate max-w-[160px]">{r.dept || <span className="text-slate-400">&mdash;</span>}</td>
                    <td className="px-3 py-2 text-xs truncate">{r.op}</td>
                    <td className="px-3 py-2 text-xs truncate max-w-[180px]">{r.machine || <span className="text-slate-400">&mdash;</span>}</td>
                    <td className="px-3 py-2 text-xs text-right text-slate-500">{formatNumber(r.count)}</td>
                    <td className="px-3 py-2">
                      {r.tag
                        ? <StatusBadge variant="info" size="sm">{r.tag}</StatusBadge>
                        : <span className="text-xs text-slate-400">&mdash;</span>}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {(r.flags || []).map(f => {
                          const colors = FLAG_COLORS[f] || { bg: 'bg-slate-100', text: 'text-slate-600' };
                          return (
                            <span key={f} className={cn('inline-flex items-center rounded-full px-1.5 py-0 text-[10px] font-medium', colors.bg, colors.text)}>
                              {f.replace('has_', '').replace(/_/g, ' ')}
                            </span>
                          );
                        })}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      {r.row_type ? (() => {
                        const colors = ROW_TYPE_COLORS[r.row_type] || { bg: 'bg-slate-100', text: 'text-slate-600' };
                        return (
                          <span className={cn('inline-flex items-center rounded-full px-2 py-0 text-[11px] font-medium', colors.bg, colors.text)}>
                            {r.row_type}
                          </span>
                        );
                      })() : null}
                    </td>
                  </tr>
                ))}
                {rules.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-sm text-slate-400">No rules found</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t bg-slate-50/50 text-xs text-slate-500">
            <span>{formatNumber(total)} rules</span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Prev
              </button>
              <span className="px-2">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Import Modal */}
      {importModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/40" onClick={() => setImportModalOpen(false)} />
          {/* Dialog */}
          <div className="relative bg-white rounded-xl shadow-xl w-full max-w-[700px] mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <h3 className="text-base font-semibold text-slate-900">Import Classifier Rules</h3>
              <button onClick={() => setImportModalOpen(false)} className="text-slate-400 hover:text-slate-600 transition-colors">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="px-6 py-4 space-y-4">
              {/* CSV format info */}
              <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-3">
                <Info className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-blue-800">CSV Format</p>
                  <p className="text-xs text-blue-600 mt-0.5 font-mono leading-relaxed">
                    Department,Operation,Machine,Count,MVP Tag,Flags,Row Type<br />
                    Coating,Cello,Celloglazer - Autobond,588,,has_coating,process<br />
                    <br />
                    Flags: comma-separated (has_coating, has_sewing, has_outsource_component)<br />
                    Paste directly from Excel or CSV export.
                  </p>
                </div>
              </div>

              <textarea
                rows={10}
                placeholder="Paste CSV here (including header row)..."
                value={csvText}
                onChange={e => setCsvText(e.target.value)}
                className="w-full px-3 py-2 text-xs font-mono rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 resize-y"
              />

              <div className="flex items-center gap-3">
                <select
                  value={replaceMode ? 'true' : 'false'}
                  onChange={e => setReplaceMode(e.target.value === 'true')}
                  className="h-8 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-56"
                >
                  <option value="false">Merge — update matching rows</option>
                  <option value="true">Replace all — overwrite everything</option>
                </select>
                <span className="text-xs text-slate-400">
                  Match key: (Department, Operation, Machine)
                </span>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 px-6 py-4 border-t bg-slate-50">
              <button
                onClick={() => setImportModalOpen(false)}
                className="h-8 px-4 text-sm font-medium rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleImport}
                disabled={importing}
                className="inline-flex items-center gap-1.5 h-8 px-4 text-sm font-medium rounded-md bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {importing && <Spinner className="h-3.5 w-3.5 animate-spin" />}
                Import
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 3: Rush Settings
// ─────────────────────────────────────────────────────────────────────────────

function RushSettingsTab({ clientId }: { clientId?: string }) {
  const [amRushPattern, setAmRushPattern] = useState('');
  const [rushPctThreshold, setRushPctThreshold] = useState<number>(0);
  const [gapCountThreshold, setGapCountThreshold] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoading(true);
    getRushSettings(clientId)
      .then(r => {
        setAmRushPattern(r.settings.am_rush_pattern);
        setRushPctThreshold(r.settings.rush_pct_threshold);
        setGapCountThreshold(r.settings.gap_count_threshold);
      })
      .catch(() => notify.error('Failed to load rush settings'))
      .finally(() => setLoading(false));
  }, [clientId]);

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!amRushPattern.trim()) { notify.warning('AM Rush Pattern is required'); return; }
    setSaving(true);
    try {
      await updateRushSettings(
        { am_rush_pattern: amRushPattern, rush_pct_threshold: rushPctThreshold, gap_count_threshold: gapCountThreshold },
        clientId,
      );
      notify.success('Rush settings saved');
    } catch {
      notify.error('Failed to save rush settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <ContentSkeleton rows={4} />;

  return (
    <div className="max-w-[600px]">
      {/* Info alert */}
      <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 p-3 mb-6">
        <Info className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
        <div>
          <p className="text-sm font-medium text-blue-800">Rush Detection Settings</p>
          <p className="text-xs text-blue-600 mt-0.5">
            These thresholds control how rush patterns are surfaced in recommendations and customer profiles.
          </p>
        </div>
      </div>

      <form onSubmit={onSave} className="space-y-5">
        {/* AM Rush Pattern */}
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 mb-1.5">
            AM Rush Pattern
            <span className="group relative">
              <Info className="h-3.5 w-3.5 text-slate-400 cursor-help" />
              <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block bg-slate-800 text-white text-xs rounded px-2 py-1 whitespace-nowrap z-10">
                Operation names starting with this text are flagged as am_rush=TRUE
              </span>
            </span>
          </label>
          <input
            type="text"
            value={amRushPattern}
            onChange={e => setAmRushPattern(e.target.value)}
            required
            className="h-9 w-full px-3 text-sm font-mono rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
        </div>

        {/* Rush % Threshold */}
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 mb-1.5">
            Rush % Threshold
            <span className="group relative">
              <Info className="h-3.5 w-3.5 text-slate-400 cursor-help" />
              <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block bg-slate-800 text-white text-xs rounded px-2 py-1 whitespace-nowrap z-10">
                Companies where rush jobs exceed this % are flagged in recommendations
              </span>
            </span>
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={0}
              max={100}
              value={rushPctThreshold}
              onChange={e => setRushPctThreshold(Number(e.target.value))}
              required
              className="h-9 w-40 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
            <span className="text-sm text-slate-500">%</span>
          </div>
        </div>

        {/* Gap Count Threshold */}
        <div>
          <label className="flex items-center gap-1.5 text-sm font-medium text-slate-700 mb-1.5">
            Factory Rush Gap Threshold
            <span className="group relative">
              <Info className="h-3.5 w-3.5 text-slate-400 cursor-help" />
              <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block bg-slate-800 text-white text-xs rounded px-2 py-1 whitespace-nowrap z-10">
                Companies with this many factory_rush=TRUE but am_rush=FALSE jobs are flagged (got rush free)
              </span>
            </span>
          </label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={0}
              value={gapCountThreshold}
              onChange={e => setGapCountThreshold(Number(e.target.value))}
              required
              className="h-9 w-40 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
            <span className="text-sm text-slate-500">jobs</span>
          </div>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-1.5 h-9 px-4 text-sm font-medium rounded-md bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {saving && <Spinner className="h-3.5 w-3.5 animate-spin" />}
          Save Settings
        </button>
      </form>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 4: Cache
// ─────────────────────────────────────────────────────────────────────────────

function CacheTab({ clientId }: { clientId?: string }) {
  const [entries, setEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [reclassifyStatus, setReclassifyStatus] = useState<ReclassifyStatus>({ status: 'idle' });
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadEntries = () => {
    getCacheStatus({ cache_type: 'capability_profile', clientId })
      .then(r => setEntries(r.entries))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const loadStatus = () => {
    getReclassifyStatus(clientId).then(setReclassifyStatus).catch(() => {});
  };

  useEffect(() => {
    loadEntries();
    loadStatus();
  }, [clientId]);

  // Poll reclassify status while running
  useEffect(() => {
    if (reclassifyStatus.status === 'running') {
      pollRef.current = setInterval(loadStatus, 3000);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
      if (reclassifyStatus.status === 'complete') loadEntries();
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [reclassifyStatus.status]);

  const handleReclassify = async () => {
    setTriggering(true);
    try {
      await triggerReclassify(clientId);
      notify.success('Reclassification started');
      setReclassifyStatus({ status: 'running' });
    } catch {
      notify.error('Failed to start reclassification');
    } finally {
      setTriggering(false);
    }
  };

  const handleClearCache = async () => {
    if (!window.confirm('Clear all intelligence cache?\n\nProfiles will recompute on next view. This is safe to do anytime.')) return;
    try {
      const r = await clearCache(undefined, clientId);
      notify.success(`Cleared ${r.deleted} cache entries`);
      loadEntries();
    } catch {
      notify.error('Failed to clear cache');
    }
  };

  const renderStatusBadge = () => {
    if (reclassifyStatus.status === 'running') {
      return (
        <span className="inline-flex items-center gap-1.5 text-sm text-blue-600">
          <Spinner className="h-3.5 w-3.5 animate-spin" />
          Running...
        </span>
      );
    }
    if (reclassifyStatus.status === 'complete') {
      return (
        <span className="inline-flex items-center gap-1.5 text-sm text-green-600">
          <CheckCircle2 className="h-3.5 w-3.5" />
          Complete — {formatNumber(reclassifyStatus.updated)} operations updated
        </span>
      );
    }
    if (reclassifyStatus.status === 'error') {
      return (
        <span className="inline-flex items-center gap-1.5 text-sm text-red-600">
          <AlertTriangle className="h-3.5 w-3.5" />
          Error: {reclassifyStatus.error}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 text-sm text-slate-500">
        <span className="h-2 w-2 rounded-full bg-slate-300" />
        Idle
      </span>
    );
  };

  // Pagination
  const PAGE_SIZE = 20;
  const [cachePage, setCachePage] = useState(1);
  const cachePageCount = Math.ceil(entries.length / PAGE_SIZE);
  const pagedEntries = entries.slice((cachePage - 1) * PAGE_SIZE, cachePage * PAGE_SIZE);

  return (
    <div>
      {/* Action cards */}
      <div className="flex flex-wrap gap-4 mb-6">
        {/* Reclassify card */}
        <div className="rounded-lg border bg-white shadow-sm p-4 min-w-[280px] flex-1">
          <p className="text-sm font-semibold text-slate-900 mb-1">Reclassify Operations</p>
          <p className="text-xs text-slate-500 mb-3">
            Re-tags all qb_operations rows using current classifier rules.
            Run after importing updated rules. Does not re-fetch from QB.
          </p>
          <div className="mb-3">{renderStatusBadge()}</div>
          <button
            onClick={handleReclassify}
            disabled={triggering || reclassifyStatus.status === 'running'}
            className="inline-flex items-center gap-1.5 h-8 px-3 text-sm font-medium rounded-md bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', reclassifyStatus.status === 'running' && 'animate-spin')} />
            {triggering ? 'Starting...' : 'Reclassify All Operations'}
          </button>
        </div>

        {/* Cache card */}
        <div className="rounded-lg border bg-white shadow-sm p-4 min-w-[240px] flex-1">
          <p className="text-sm font-semibold text-slate-900 mb-1">Intelligence Cache</p>
          <p className="text-xs text-slate-500 mb-3">
            Clears computed capability profiles. Profiles rebuild automatically on next request.
          </p>
          <button
            onClick={handleClearCache}
            className="inline-flex items-center gap-1.5 h-8 px-3 text-sm font-medium rounded-md border border-red-200 text-red-600 hover:bg-red-50 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear Cache
          </button>
        </div>
      </div>

      {/* Cache entries table */}
      <p className="text-sm font-semibold text-slate-900 mb-2">
        Cached Capability Profiles ({entries.length} companies)
      </p>
      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        {loading ? (
          <ContentSkeleton rows={6} />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-slate-50/50">
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Company</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-40">Cache Type</th>
                <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-48">Computed At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {pagedEntries.map((entry: any) => (
                <tr key={entry.id} className="hover:bg-slate-50/50 transition-colors">
                  <td className="px-4 py-2 text-sm truncate">{entry.customer_companies?.company_name || '—'}</td>
                  <td className="px-4 py-2">
                    <StatusBadge variant="neutral" size="sm">{entry.cache_type}</StatusBadge>
                  </td>
                  <td className="px-4 py-2 text-sm text-slate-500">
                    {entry.computed_at ? new Date(entry.computed_at).toLocaleString('en-AU') : '—'}
                  </td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-8 text-center text-sm text-slate-400">No cached profiles</td>
                </tr>
              )}
            </tbody>
          </table>
        )}

        {/* Pagination */}
        {cachePageCount > 1 && (
          <div className="flex items-center justify-between px-4 py-2.5 border-t bg-slate-50/50 text-xs text-slate-500">
            <span>{entries.length} entries</span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCachePage(p => Math.max(1, p - 1))}
                disabled={cachePage === 1}
                className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Prev
              </button>
              <span className="px-2">Page {cachePage} of {cachePageCount}</span>
              <button
                onClick={() => setCachePage(p => Math.min(cachePageCount, p + 1))}
                disabled={cachePage === cachePageCount}
                className="px-2 py-1 rounded border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────

const TABS = [
  { key: 'tags',  label: 'Capability Tags' },
  { key: 'rules', label: 'Classifier Rules' },
  { key: 'rush',  label: 'Rush Settings' },
  { key: 'cache', label: 'Cache & Rebuild' },
] as const;

type TabKey = typeof TABS[number]['key'];

export default function IntelligenceConfigPage() {
  const { clientId } = useClient();
  const [activeTab, setActiveTab] = useState<TabKey>('tags');

  const cid = clientId || undefined;

  return (
    <PageShell>
      <PageHeader
        title="Intelligence Configuration"
        description="Manage capability taxonomy, classifier rules, and computed profile cache. Changes to classifier rules take effect after clicking Reclassify All Operations in the Cache tab."
      />

      <div className="rounded-lg border bg-white shadow-sm">
        {/* Tab bar */}
        <div className="flex gap-1 border-b border-slate-200 px-4 pt-1">
          {TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                'px-4 py-2 text-sm font-medium rounded-t-md transition-colors -mb-px',
                activeTab === tab.key
                  ? 'text-primary border-b-2 border-primary bg-white'
                  : 'text-slate-500 hover:text-slate-700',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="p-5">
          {activeTab === 'tags'  && <CapabilityTagsTab clientId={cid} />}
          {activeTab === 'rules' && <ClassifierRulesTab clientId={cid} />}
          {activeTab === 'rush'  && <RushSettingsTab clientId={cid} />}
          {activeTab === 'cache' && <CacheTab clientId={cid} />}
        </div>
      </div>
    </PageShell>
  );
}
