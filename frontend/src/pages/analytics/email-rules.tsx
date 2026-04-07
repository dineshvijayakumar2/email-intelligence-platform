/**
 * Email Rules Intelligence — Two-panel layout with grouped insights.
 * Left: insight list grouped by type. Right: detail panel with rules.
 */
import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  createColumnHelper, type SortingState,
} from '@tanstack/react-table';
import { useClient } from '../../contexts/ClientContext';
import { formatDateTime } from '../../utils/dateUtils';
import { rulesApi, clearRulesCache, getSignalLabel } from '../../services/rulesService';
import type { RulesAnalyticsResponse, RulesInsight, UnifiedRule } from '../../services/rulesService';
import type { RuleActions } from '../../services/rulesService';
import { DataTable } from '../../components/DataTable';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { KPICard, KPIStrip } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton, EmptyState } from '@/components/ui/empty-state';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Filter, RefreshCw, AlertTriangle, Info, Search, X,
  ChevronDown, ChevronRight, CheckCircle2,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';

// ── Helpers ──────────────────────────────────────────────────────────
const isOutlookFolderId = (val: string): boolean => !!(val && val.startsWith('AAMk') && val.length > 30);

const describeActions = (actions: RuleActions): string[] => {
  const parts: string[] = [];
  if (actions.mark_important) parts.push('Mark Important');
  if (actions.mark_read) parts.push('Mark Read');
  if (actions.skip_inbox) parts.push('Skip Inbox');
  if (actions.delete) parts.push('Delete');
  if (actions.move_to_folder) parts.push(isOutlookFolderId(actions.move_to_folder) ? 'Move to Folder' : `Move to "${actions.move_to_folder}"`);
  if (actions.label) parts.push(isOutlookFolderId(actions.label) ? 'Apply Label' : `Label: ${actions.label}`);
  if (actions.forward_to?.length) parts.push(`Forward to ${actions.forward_to[0]}${actions.forward_to.length > 1 ? ` +${actions.forward_to.length - 1}` : ''}`);
  return parts;
};

const signalVariant = (s: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple' => {
  if (s === 'high_value') return 'success';
  if (s === 'escalation') return 'info';
  if (s === 'low_priority') return 'warning';
  if (s === 'segmentation') return 'purple';
  return 'neutral';
};

// ── Rule Detail Modal ──────────────────────────────────────────────
const RuleDetailModal: React.FC<{ rule: UnifiedRule | null; open: boolean; onClose: () => void }> = ({ rule, open, onClose }) => {
  if (!rule) return null;
  const conditionRows = [
    { label: 'From Addresses', value: rule.conditions.from_addresses },
    { label: 'From Domains', value: rule.conditions.from_domains },
    { label: 'To Addresses', value: rule.conditions.to_addresses },
    { label: 'Subject Contains', value: rule.conditions.subject_contains },
    { label: 'Body Contains', value: rule.conditions.body_contains },
    { label: 'Has Attachment', value: rule.conditions.has_attachment != null ? [String(rule.conditions.has_attachment)] : [] },
  ].filter(r => r.value.length > 0);
  const actionRows = describeActions(rule.actions);

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader><DialogTitle className="text-base">{rule.name}</DialogTitle></DialogHeader>
        <div className="space-y-4 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div><span className="text-xs font-bold uppercase tracking-wider text-slate-500 block mb-0.5">Source</span><span className="text-slate-700">{rule.source_type === 'gmail' ? 'Gmail' : 'Outlook'}</span></div>
            <div><span className="text-xs font-bold uppercase tracking-wider text-slate-500 block mb-0.5">Mailbox</span><span className="text-slate-700">{rule.mailbox_email}</span></div>
            <div><span className="text-xs font-bold uppercase tracking-wider text-slate-500 block mb-0.5">Signal</span><StatusBadge variant={signalVariant(rule.engagement_signal)} size="sm">{getSignalLabel(rule.engagement_signal)}</StatusBadge></div>
            <div><span className="text-xs font-bold uppercase tracking-wider text-slate-500 block mb-0.5">Status</span><span className={rule.is_active ? 'text-success font-medium' : 'text-slate-400'}>{rule.is_active ? 'Active' : 'Inactive'}</span></div>
          </div>
          {conditionRows.length > 0 && (
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">Conditions</h4>
              <div className="rounded-md border border-slate-100 divide-y divide-slate-50">
                {conditionRows.map(r => (
                  <div key={r.label} className="flex gap-3 px-3 py-2">
                    <span className="text-xs text-slate-500 w-28 shrink-0">{r.label}</span>
                    <div className="flex flex-wrap gap-1">{r.value.map((v, i) => <span key={i} className="inline-flex px-1.5 py-0 text-[11px] rounded bg-slate-100 text-slate-700">{v}</span>)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {actionRows.length > 0 && (
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">Actions</h4>
              <div className="flex flex-wrap gap-1.5">{actionRows.map(a => <span key={a} className="inline-flex px-2 py-0.5 text-xs rounded-md bg-primary-subtle text-primary">{a}</span>)}</div>
            </div>
          )}
          {rule.actions.move_to_folder && isOutlookFolderId(rule.actions.move_to_folder) && (
            <div><h4 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">Raw Folder ID</h4><p className="text-[11px] font-mono text-slate-400 break-all">{rule.actions.move_to_folder}</p></div>
          )}
          {rule.imported_at && <p className="text-xs text-slate-400">Imported: {formatDateTime(rule.imported_at)}</p>}
        </div>
      </DialogContent>
    </Dialog>
  );
};

// ── Grouped Insight type ─────────────────────────────────────────
interface GroupedInsight {
  type: string;
  severity: string;
  insights: RulesInsight[];
  allMailboxes: string[];
}

// ── Main Page ────────────────────────────────────────────────────
export const EmailRulesPage: React.FC = () => {
  const isMountedRef = useRef(true);
  const { clientId } = useClient();
  const [analytics, setAnalytics] = useState<RulesAnalyticsResponse | null>(null);
  const [insights, setInsights] = useState<RulesInsight[]>([]);
  const [allRules, setAllRules] = useState<UnifiedRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'comparison' | 'rules' | 'insights'>('insights');
  const [selectedRule, setSelectedRule] = useState<UnifiedRule | null>(null);
  const [selectedInsight, setSelectedInsight] = useState<GroupedInsight | null>(null);
  const [expandedMailboxes, setExpandedMailboxes] = useState<Set<string>>(new Set());

  // Rules tab state
  const [rulesPage, setRulesPage] = useState(1);
  const RULES_PAGE_SIZE = 25;
  const [rulesSorting, setRulesSorting] = useState<SortingState>([]);
  const [rulesSearch, setRulesSearch] = useState('');
  const [signalFilter, setSignalFilter] = useState('');
  const [mailboxFilter, setMailboxFilter] = useState('');
  const col = createColumnHelper<UnifiedRule>();

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  const loadData = async (cId: string) => {
    const result = await rulesApi.fullAnalytics(cId);
    if (!isMountedRef.current) return;
    setAnalytics(result.analytics);
    setInsights(result.insights?.insights || []);
    setAllRules(result.rules || []);
    setLastSyncedAt(result.last_rules_import_at);
  };

  useEffect(() => {
    if (!clientId) return;
    setLoading(true);
    loadData(clientId).finally(() => { if (isMountedRef.current) setLoading(false); });
  }, [clientId]);

  const handleSync = async () => {
    if (!analytics) return;
    const live = (analytics.mailboxes || []).filter(mb => mb.live_connection);
    if (!live.length) { toast.info('No LIVE connections to sync.'); return; }
    setSyncing(true);
    try {
      const results = await Promise.allSettled(live.map(mb => rulesApi.importRules(mb.mailbox_id)));
      const total = results.filter((r): r is PromiseFulfilledResult<any> => r.status === 'fulfilled')
        .reduce((sum, r) => sum + (r.value?.imported_count || 0), 0);
      toast.success(`Synced ${total} rules from ${live.length} mailbox(es)`);
      clearRulesCache();
      await loadData(clientId);
    } catch { toast.error('Failed to sync'); }
    finally { if (isMountedRef.current) setSyncing(false); }
  };

  const handleImport = async (mailboxId: string) => {
    setSyncing(true);
    try { const r = await rulesApi.importRules(mailboxId); toast.success(`Imported ${r.imported_count} rules`); clearRulesCache(); await loadData(clientId); }
    catch { toast.error('Failed to import'); }
    finally { if (isMountedRef.current) setSyncing(false); }
  };

  // ── Grouped insights ──────────────────────────────────────────
  const groupedInsights = useMemo((): GroupedInsight[] => {
    const map = new Map<string, GroupedInsight>();
    for (const ins of insights) {
      const key = ins.insight_type;
      if (!map.has(key)) {
        map.set(key, { type: key, severity: ins.severity, insights: [], allMailboxes: [] });
      }
      const g = map.get(key)!;
      g.insights.push(ins);
      for (const mb of ins.affected_mailboxes) {
        if (!g.allMailboxes.includes(mb)) g.allMailboxes.push(mb);
      }
      // Keep highest severity
      if (ins.severity === 'critical') g.severity = 'critical';
      else if (ins.severity === 'warning' && g.severity !== 'critical') g.severity = 'warning';
    }
    // Sort: critical first, then warnings, then info
    const order: Record<string, number> = { critical: 0, warning: 1, info: 2 };
    return Array.from(map.values()).sort((a, b) => (order[a.severity] ?? 2) - (order[b.severity] ?? 2));
  }, [insights]);

  const warnings = groupedInsights.filter(g => g.severity === 'critical' || g.severity === 'warning');
  const recommendations = groupedInsights.filter(g => g.severity !== 'critical' && g.severity !== 'warning');

  // Auto-select first insight
  useEffect(() => {
    if (activeTab === 'insights' && groupedInsights.length > 0 && !selectedInsight) {
      setSelectedInsight(groupedInsights[0]);
    }
  }, [activeTab, groupedInsights]);

  // Rules for selected insight
  const insightRules = useMemo(() => {
    if (!selectedInsight) return [];
    const mbSet = new Set(selectedInsight.allMailboxes.map(m => m.toLowerCase()));
    return allRules.filter(r => mbSet.has(r.mailbox_email.toLowerCase()));
  }, [selectedInsight, allRules]);

  // Rules per mailbox for accordion
  const rulesByMailbox = useMemo(() => {
    const map: Record<string, UnifiedRule[]> = {};
    for (const r of insightRules) {
      const mb = r.mailbox_email;
      if (!map[mb]) map[mb] = [];
      map[mb].push(r);
    }
    return map;
  }, [insightRules]);

  const toggleMailbox = (mb: string) => {
    setExpandedMailboxes(prev => {
      const next = new Set(prev);
      if (next.has(mb)) next.delete(mb); else next.add(mb);
      return next;
    });
  };

  // ── All Rules tab ─────────────────────────────────────────────
  const mailboxOptions = useMemo(() => Array.from(new Set(allRules.map(r => r.mailbox_email))).sort(), [allRules]);
  const signalOptions = useMemo(() => Array.from(new Set(allRules.map(r => r.engagement_signal))).sort(), [allRules]);

  const filteredRules = useMemo(() => {
    let rules = allRules;
    if (signalFilter) rules = rules.filter(r => r.engagement_signal === signalFilter);
    if (mailboxFilter) rules = rules.filter(r => r.mailbox_email === mailboxFilter);
    if (rulesSearch) {
      const q = rulesSearch.toLowerCase();
      rules = rules.filter(r => r.name.toLowerCase().includes(q) || r.mailbox_email.toLowerCase().includes(q)
        || r.conditions.from_addresses.some(a => a.toLowerCase().includes(q))
        || r.conditions.subject_contains.some(s => s.toLowerCase().includes(q)));
    }
    return rules;
  }, [allRules, signalFilter, mailboxFilter, rulesSearch]);

  const rulesColumns = useMemo(() => [
    col.accessor('name', { header: 'Rule Name', cell: info => (<div><span className="text-sm font-medium text-slate-800">{info.getValue()}</span>{!info.row.original.is_active && <span className="text-[10px] text-slate-400 italic ml-2">inactive</span>}</div>) }),
    col.accessor('mailbox_email', { header: 'Mailbox', size: 160, cell: info => <span className="text-xs text-slate-600">{info.getValue().split('@')[0]}</span> }),
    col.accessor('engagement_signal', { header: 'Signal', size: 100, cell: info => <StatusBadge variant={signalVariant(info.getValue())} size="sm">{getSignalLabel(info.getValue())}</StatusBadge> }),
    col.accessor('conditions', { header: 'Conditions', enableSorting: false, cell: info => { const c = info.getValue(); const parts = [c.from_addresses.length && `${c.from_addresses.length} addr`, c.from_domains.length && `${c.from_domains.length} dom`, c.subject_contains.length && `${c.subject_contains.length} subj`].filter(Boolean); return parts.length ? <span className="text-xs text-slate-500">{parts.join(', ')}</span> : <span className="text-xs text-slate-300">Any</span>; } }),
    col.accessor('actions', { id: 'rule_actions', header: 'Actions', enableSorting: false, cell: info => { const p = describeActions(info.getValue()); return p.length ? <span className="text-xs text-slate-600">{p.slice(0, 2).join(', ')}{p.length > 2 ? ` +${p.length - 2}` : ''}</span> : <span className="text-xs text-slate-300">None</span>; } }),
  ], []);

  const rulesTable = useReactTable({ data: filteredRules, columns: rulesColumns, state: { sorting: rulesSorting }, onSortingChange: setRulesSorting, getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel() });
  const hasRulesFilters = !!signalFilter || !!rulesSearch || !!mailboxFilter;

  // ── Insight detail DataTable ───────────────────────────────────
  const insightRulesTable = useReactTable({
    data: insightRules,
    columns: rulesColumns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <PageShell>
      <PageHeader title="Email Rules Intelligence" description="Analyze email rules across account managers"
        actions={
          <div className="flex items-center gap-3">
            {lastSyncedAt && <span className="text-xs text-slate-400">Synced: {formatDateTime(lastSyncedAt)}</span>}
            <button onClick={handleSync} disabled={syncing || !analytics}
              className="h-8 px-3 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark disabled:opacity-50 inline-flex items-center gap-1.5">
              {syncing ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}Sync Rules
            </button>
          </div>
        }
      />

      {!clientId ? <EmptyState icon={<Filter className="h-10 w-10" />} title="Select a client" /> : loading ? <ContentSkeleton rows={8} /> : (
        <>
          {/* KPIs with context */}
          <KPIStrip className="mb-4">
            <KPICard title="Total Rules" value={analytics?.total_rules || 0}
              subtitle={`across ${analytics?.total_mailboxes || 0} mailboxes`} />
            <KPICard title="Mailboxes with Rules" value={(analytics?.total_mailboxes || 0) - (analytics?.mailboxes_with_no_rules || 0)}
              subtitle={`of ${analytics?.total_mailboxes || 0} total`} />
            <KPICard title="Avg / Mailbox" value={analytics?.avg_rules_per_mailbox || 0}
              subtitle="rules per mailbox" />
            <KPICard title="No Rules" value={analytics?.mailboxes_with_no_rules || 0}
              danger={(analytics?.mailboxes_with_no_rules || 0) > 0}
              subtitle={(analytics?.mailboxes_with_no_rules || 0) > 0 ? 'needs attention' : 'all good'} />
          </KPIStrip>

          {/* Tab bar */}
          <div className="flex gap-1 mb-4 border-b border-slate-200 pb-px">
            {(['insights', 'rules', 'comparison'] as const).map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={cn('px-4 py-2 text-sm font-medium rounded-t-md transition-colors -mb-px',
                  activeTab === tab ? 'text-primary border-b-2 border-primary bg-white' : 'text-slate-500 hover:text-slate-700')}>
                {tab === 'insights' ? `Insights (${groupedInsights.length})` : tab === 'rules' ? `All Rules (${allRules.length})` : 'Cross-AM Comparison'}
              </button>
            ))}
          </div>

          {/* ── Insights tab — two-panel layout ── */}
          {activeTab === 'insights' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Left panel — insight list */}
              <div className="lg:col-span-1 space-y-2">
                {/* Warnings */}
                {warnings.length > 0 && (
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5 flex items-center gap-1.5">
                      <AlertTriangle className="h-3.5 w-3.5 text-warning" /> Warnings ({warnings.length})
                    </p>
                    {warnings.map(g => (
                      <button key={g.type} onClick={() => { setSelectedInsight(g); setExpandedMailboxes(new Set()); }}
                        className={cn('w-full text-left rounded-lg border p-3 mb-1.5 transition-all border-l-4 border-l-warning',
                          selectedInsight?.type === g.type ? 'bg-warning-subtle border-warning shadow-sm' : 'bg-white hover:bg-slate-50')}>
                        <p className="text-sm font-medium text-slate-800">{g.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{g.allMailboxes.length} mailbox{g.allMailboxes.length !== 1 ? 'es' : ''} affected</p>
                      </button>
                    ))}
                  </div>
                )}
                {/* Recommendations */}
                {recommendations.length > 0 && (
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-1.5 flex items-center gap-1.5">
                      <CheckCircle2 className="h-3.5 w-3.5 text-success" /> Recommendations ({recommendations.length})
                    </p>
                    {recommendations.map(g => (
                      <button key={g.type} onClick={() => { setSelectedInsight(g); setExpandedMailboxes(new Set()); }}
                        className={cn('w-full text-left rounded-lg border p-3 mb-1.5 transition-all border-l-4 border-l-success',
                          selectedInsight?.type === g.type ? 'bg-success-subtle border-success shadow-sm' : 'bg-white hover:bg-slate-50')}>
                        <p className="text-sm font-medium text-slate-800">{g.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</p>
                        <p className="text-xs text-slate-500 mt-0.5">{g.allMailboxes.length} mailbox{g.allMailboxes.length !== 1 ? 'es' : ''}</p>
                      </button>
                    ))}
                  </div>
                )}
                {groupedInsights.length === 0 && (
                  <EmptyState icon={<Info className="h-8 w-8" />} title="No insights" description="Import rules to generate insights" />
                )}
              </div>

              {/* Right panel — selected insight detail */}
              <div className="lg:col-span-2">
                {selectedInsight ? (
                  <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
                    {/* Header */}
                    <div className={cn('p-4 border-b',
                      selectedInsight.severity === 'critical' || selectedInsight.severity === 'warning' ? 'bg-warning-subtle' : 'bg-success-subtle')}>
                      <h3 className="text-base font-bold text-slate-900">
                        {selectedInsight.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                      </h3>
                      <p className="text-sm text-slate-600 mt-1">{selectedInsight.insights[0]?.description}</p>
                      <p className="text-xs text-slate-500 mt-2">
                        <span className="font-medium">Recommendation:</span> {selectedInsight.insights[0]?.recommendation}
                      </p>
                    </div>

                    {/* Mailbox accordion with percentage bars */}
                    <div className="p-4">
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
                        Affected Mailboxes ({selectedInsight.allMailboxes.length})
                      </p>
                      <div className="space-y-1.5">
                        {selectedInsight.allMailboxes.map(mb => {
                          const mbRules = rulesByMailbox[mb] || [];
                          const isExpanded = expandedMailboxes.has(mb);

                          return (
                            <div key={mb} className="rounded-md border border-slate-100 overflow-hidden">
                              <button onClick={() => toggleMailbox(mb)}
                                className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-slate-50 transition-colors">
                                {isExpanded ? <ChevronDown className="h-3.5 w-3.5 text-slate-400 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 text-slate-400 shrink-0" />}
                                <span className="text-sm font-medium text-slate-800 flex-1 text-left truncate">{mb}</span>
                                <span className="text-xs text-slate-500 tabular-nums shrink-0">{mbRules.length} rule{mbRules.length !== 1 ? 's' : ''}</span>
                              </button>
                              {/* Expanded — inline rules */}
                              {isExpanded && mbRules.length > 0 && (
                                <div className="border-t bg-slate-50/50 divide-y divide-slate-100">
                                  {mbRules.map((rule, ri) => (
                                    <div key={ri} className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-white"
                                      onClick={() => setSelectedRule(rule)}>
                                      <span className="text-xs text-slate-700 font-medium flex-1 truncate">{rule.name}</span>
                                      <StatusBadge variant={signalVariant(rule.engagement_signal)} size="sm">{getSignalLabel(rule.engagement_signal)}</StatusBadge>
                                      <span className="text-[10px] text-slate-400">{describeActions(rule.actions).slice(0, 1).join('')}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Related rules DataTable */}
                    {insightRules.length > 0 && (
                      <div className="border-t p-4">
                        <p className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2">
                          All Related Rules ({insightRules.length})
                        </p>
                        <DataTable<UnifiedRule>
                          table={insightRulesTable}
                          total={insightRules.length}
                          loading={false}
                          pageSize={10}
                          currentPage={1}
                          onRowClick={setSelectedRule}
                        />
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="rounded-lg border bg-white shadow-sm p-8">
                    <EmptyState icon={<Info className="h-8 w-8" />} title="Select an insight" description="Click an insight from the left panel to view details" />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── All Rules tab ── */}
          {activeTab === 'rules' && (
            <>
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
                  <input type="text" placeholder="Search rules..." value={rulesSearch} onChange={e => { setRulesSearch(e.target.value); setRulesPage(1); }}
                    className="h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-56" />
                </div>
                <select value={signalFilter} onChange={e => { setSignalFilter(e.target.value); setRulesPage(1); }}
                  className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white"><option value="">All Signals</option>{signalOptions.map(s => <option key={s} value={s}>{getSignalLabel(s)}</option>)}</select>
                <select value={mailboxFilter} onChange={e => { setMailboxFilter(e.target.value); setRulesPage(1); }}
                  className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white max-w-[200px]"><option value="">All Mailboxes</option>{mailboxOptions.map(m => <option key={m} value={m}>{m}</option>)}</select>
                {hasRulesFilters && <button onClick={() => { setRulesSearch(''); setSignalFilter(''); setMailboxFilter(''); setRulesPage(1); }} className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><X className="h-3 w-3" />Clear</button>}
                <span className="text-xs text-slate-400 ml-auto tabular-nums">{filteredRules.length} rules</span>
              </div>
              <DataTable<UnifiedRule> table={rulesTable} total={filteredRules.length} loading={false} pageSize={RULES_PAGE_SIZE} currentPage={rulesPage} onPageChange={setRulesPage} onRowClick={setSelectedRule} />
            </>
          )}

          {/* ── Comparison tab ── */}
          {activeTab === 'comparison' && (
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead><tr className="border-b bg-slate-50/50">
                  <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Mailbox</th>
                  <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Total</th>
                  <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Active</th>
                  <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">High Val</th>
                  <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Escalate</th>
                  <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Low Pri</th>
                  <th className="px-3 py-2.5 w-16"></th>
                </tr></thead>
                <tbody className="divide-y divide-slate-50">
                  {(analytics?.mailboxes || []).map(mb => (
                    <tr key={mb.mailbox_id} className={cn('hover:bg-slate-50/50', mb.total_rules === 0 && 'bg-warning-subtle')}>
                      <td className="px-4 py-2.5"><span className="font-medium text-slate-900">{mb.mailbox_email || 'Unknown'}</span><div className="text-xs text-slate-400">{mb.live_connection || 'Archive'}</div></td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.total_rules}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.active_rules}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.high_value_count || '—'}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.escalation_count || '—'}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.low_priority_count || '—'}</td>
                      <td className="px-3 py-2.5">{mb.live_connection && <button onClick={() => handleImport(mb.mailbox_id)} disabled={syncing} className="text-xs text-primary hover:underline disabled:opacity-50">Import</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      <RuleDetailModal rule={selectedRule} open={!!selectedRule} onClose={() => setSelectedRule(null)} />
    </PageShell>
  );
};

export default EmailRulesPage;
