/**
 * Email Rules Intelligence — analyze email rules across account managers.
 * Moved to Insights section. Zero antd.
 */
import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  useReactTable, getCoreRowModel, getSortedRowModel, getFilteredRowModel,
  createColumnHelper, type SortingState,
} from '@tanstack/react-table';
import { useClient } from '../../contexts/ClientContext';
import { formatDateTime } from '../../utils/dateUtils';
import { rulesApi, clearRulesCache, getSignalLabel } from '../../services/rulesService';
import type { RulesAnalyticsResponse, MailboxRulesMetrics, RulesInsight, UnifiedRule } from '../../services/rulesService';
import { DataTable } from '../../components/DataTable';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { KPICard, KPIStrip } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton, EmptyState } from '@/components/ui/empty-state';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import {
  Filter, RefreshCw, Download, AlertTriangle, Info, Search, X,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';

const signalVariant = (s: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple' => {
  if (s === 'high_value') return 'success';
  if (s === 'escalation') return 'info';
  if (s === 'low_priority') return 'warning';
  if (s === 'segmentation') return 'purple';
  return 'neutral';
};

export const EmailRulesPage: React.FC = () => {
  const isMountedRef = useRef(true);
  const { clientId } = useClient();
  const [analytics, setAnalytics] = useState<RulesAnalyticsResponse | null>(null);
  const [insights, setInsights] = useState<RulesInsight[]>([]);
  const [allRules, setAllRules] = useState<UnifiedRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'comparison' | 'rules' | 'insights'>('comparison');
  const [rulesPage, setRulesPage] = useState(1);
  const RULES_PAGE_SIZE = 25;
  const [rulesSorting, setRulesSorting] = useState<SortingState>([]);
  const [rulesSearch, setRulesSearch] = useState('');
  const [signalFilter, setSignalFilter] = useState('');

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
    if (!live.length) { toast.info('No LIVE mailbox connections to sync.'); return; }
    setSyncing(true);
    try {
      const results = await Promise.allSettled(live.map(mb => rulesApi.importRules(mb.mailbox_id)));
      const total = results.filter((r): r is PromiseFulfilledResult<any> => r.status === 'fulfilled')
        .reduce((sum, r) => sum + (r.value?.imported_count || 0), 0);
      toast.success(`Synced ${total} rules from ${live.length} mailbox(es)`);
      clearRulesCache();
      await loadData(clientId);
    } catch { toast.error('Failed to sync rules'); }
    finally { if (isMountedRef.current) setSyncing(false); }
  };

  const handleImport = async (mailboxId: string) => {
    setSyncing(true);
    try {
      const result = await rulesApi.importRules(mailboxId);
      toast.success(`Imported ${result.imported_count} rules`);
      clearRulesCache();
      await loadData(clientId);
    } catch { toast.error('Failed to import rules'); }
    finally { if (isMountedRef.current) setSyncing(false); }
  };

  const [mailboxFilter, setMailboxFilter] = useState('');

  // Unique mailboxes for filter
  const mailboxOptions = useMemo(() => {
    const mbs = new Set(allRules.map(r => r.mailbox_email));
    return Array.from(mbs).sort();
  }, [allRules]);

  // Filtered rules
  const filteredRules = useMemo(() => {
    let rules = allRules;
    if (signalFilter) rules = rules.filter(r => r.engagement_signal === signalFilter);
    if (mailboxFilter) rules = rules.filter(r => r.mailbox_email === mailboxFilter);
    if (rulesSearch) {
      const q = rulesSearch.toLowerCase();
      rules = rules.filter(r =>
        r.name.toLowerCase().includes(q) ||
        r.mailbox_email.toLowerCase().includes(q) ||
        r.conditions.from_addresses.some(a => a.toLowerCase().includes(q)) ||
        r.conditions.from_domains.some(d => d.toLowerCase().includes(q)) ||
        r.conditions.subject_contains.some(s => s.toLowerCase().includes(q))
      );
    }
    return rules;
  }, [allRules, signalFilter, mailboxFilter, rulesSearch]);

  // TanStack Table columns for rules
  const rulesColumns = useMemo(() => [
    col.accessor('source_type', { header: 'Source', size: 70,
      cell: info => <span className="text-xs text-slate-500">{info.getValue() === 'gmail' ? 'Gmail' : 'Outlook'}</span>,
    }),
    col.accessor('mailbox_email', { header: 'Mailbox', size: 180,
      cell: info => <span className="text-xs text-slate-600 truncate block max-w-[160px]">{info.getValue()}</span>,
    }),
    col.accessor('name', { header: 'Rule Name',
      cell: info => <span className="text-sm text-slate-800 font-medium">{info.getValue()}</span>,
    }),
    col.accessor('engagement_signal', { header: 'Signal', size: 110,
      cell: info => <StatusBadge variant={signalVariant(info.getValue())} size="sm">{getSignalLabel(info.getValue())}</StatusBadge>,
    }),
    col.accessor('conditions', { header: 'Conditions', enableSorting: false,
      cell: info => {
        const c = info.getValue();
        const parts = [
          c.from_addresses.length ? `From: ${c.from_addresses.slice(0, 2).join(', ')}${c.from_addresses.length > 2 ? '...' : ''}` : '',
          c.from_domains.length ? `Domain: ${c.from_domains.slice(0, 2).join(', ')}` : '',
          c.subject_contains.length ? `Subject: ${c.subject_contains.slice(0, 2).join(', ')}` : '',
          c.has_attachment ? 'Has attachment' : '',
        ].filter(Boolean);
        return <span className="text-xs text-slate-500">{parts.join(' · ') || 'Any'}</span>;
      },
    }),
    col.accessor('actions', { header: 'Actions', enableSorting: false,
      cell: info => {
        const a = info.getValue();
        const tags: string[] = [];
        if (a.mark_important) tags.push('Important');
        if (a.forward_to?.length) tags.push(`Fwd → ${a.forward_to.slice(0, 1).join(', ')}`);
        if (a.label) tags.push(`Label: ${a.label}`);
        if (a.move_to_folder) tags.push(`Move: ${a.move_to_folder}`);
        if (a.mark_read) tags.push('Mark Read');
        if (a.skip_inbox) tags.push('Skip Inbox');
        if (a.delete) tags.push('Delete');
        return tags.length
          ? <div className="flex flex-wrap gap-1">{tags.map(t => <span key={t} className="inline-flex px-1.5 py-0 text-[10px] rounded bg-slate-100 text-slate-600">{t}</span>)}</div>
          : <span className="text-xs text-slate-300">None</span>;
      },
    }),
    col.accessor('is_active', { header: 'Active', size: 60,
      cell: info => info.getValue() ? <span className="text-xs text-success font-medium">Yes</span> : <span className="text-xs text-slate-400">No</span>,
    }),
  ], []);

  const rulesTable = useReactTable({
    data: filteredRules,
    columns: rulesColumns,
    state: { sorting: rulesSorting },
    onSortingChange: setRulesSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const hasRulesFilters = !!signalFilter || !!rulesSearch || !!mailboxFilter;

  // Unique signals for filter dropdown
  const signalOptions = useMemo(() => {
    const signals = new Set(allRules.map(r => r.engagement_signal));
    return Array.from(signals).sort();
  }, [allRules]);

  return (
    <PageShell>
      <PageHeader title="Email Rules Intelligence" description="Analyze email rules across account managers"
        actions={
          <div className="flex items-center gap-3">
            {lastSyncedAt && <span className="text-xs text-slate-400">Synced: {formatDateTime(lastSyncedAt)}</span>}
            <button onClick={handleSync} disabled={syncing || !analytics}
              className="h-8 px-3 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark disabled:opacity-50 inline-flex items-center gap-1.5">
              {syncing ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Sync Rules
            </button>
          </div>
        }
      />

      {!clientId ? (
        <EmptyState icon={<Filter className="h-10 w-10" />} title="Select a client" description="Choose a client from the top-right menu to view email rules" />
      ) : loading ? (
        <ContentSkeleton rows={8} />
      ) : (
        <>
          {/* KPIs */}
          <KPIStrip className="mb-4">
            <KPICard title="Total Rules" value={analytics?.total_rules || 0} />
            <KPICard title="Mailboxes Covered" value={(analytics?.total_mailboxes || 0) - (analytics?.mailboxes_with_no_rules || 0)}
              subtitle={`of ${analytics?.total_mailboxes || 0}`} />
            <KPICard title="Avg / Mailbox" value={analytics?.avg_rules_per_mailbox || 0} />
            <KPICard title="No Rules" value={analytics?.mailboxes_with_no_rules || 0}
              danger={(analytics?.mailboxes_with_no_rules || 0) > 0} />
          </KPIStrip>

          {/* Tab bar */}
          <div className="flex gap-1 mb-4 border-b border-slate-200 pb-px">
            {(['comparison', 'rules', 'insights'] as const).map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={cn('px-4 py-2 text-sm font-medium rounded-t-md transition-colors -mb-px',
                  activeTab === tab ? 'text-primary border-b-2 border-primary bg-white' : 'text-slate-500 hover:text-slate-700')}>
                {tab === 'comparison' ? 'Cross-AM Comparison' : tab === 'rules' ? `All Rules (${allRules.length})` : `Insights (${insights.length})`}
              </button>
            ))}
          </div>

          {/* Comparison tab */}
          {activeTab === 'comparison' && (
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-slate-50/50">
                    <th className="px-4 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Mailbox</th>
                    <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Total</th>
                    <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Active</th>
                    <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">High Val</th>
                    <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Escalate</th>
                    <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Low Pri</th>
                    <th className="px-3 py-2.5 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Fwd</th>
                    <th className="px-3 py-2.5 w-20"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {(analytics?.mailboxes || []).map(mb => (
                    <tr key={mb.mailbox_id} className={cn('hover:bg-slate-50/50', mb.total_rules === 0 && 'bg-warning-subtle')}>
                      <td className="px-4 py-2.5">
                        <span className="font-medium text-slate-900">{mb.mailbox_email || 'Unknown'}</span>
                        <div className="text-xs text-slate-400">{mb.live_connection === 'gmail' ? 'Gmail' : mb.live_connection === 'outlook' ? 'Outlook' : 'Archive'}</div>
                      </td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.total_rules}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.active_rules}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.high_value_count || '—'}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.escalation_count || '—'}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.low_priority_count || '—'}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{mb.forward_count || '—'}</td>
                      <td className="px-3 py-2.5">
                        {mb.live_connection && (
                          <button onClick={() => handleImport(mb.mailbox_id)} disabled={syncing}
                            className="text-xs text-primary hover:underline disabled:opacity-50">Import</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Rules tab — TanStack Table with filters */}
          {activeTab === 'rules' && (
            <>
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
                  <input type="text" placeholder="Search rules, mailbox, conditions..."
                    value={rulesSearch} onChange={e => { setRulesSearch(e.target.value); setRulesPage(1); }}
                    className="h-8 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-64" />
                </div>
                <select value={signalFilter} onChange={e => { setSignalFilter(e.target.value); setRulesPage(1); }}
                  className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
                  <option value="">All Signals</option>
                  {signalOptions.map(s => <option key={s} value={s}>{getSignalLabel(s)}</option>)}
                </select>
                <select value={mailboxFilter} onChange={e => { setMailboxFilter(e.target.value); setRulesPage(1); }}
                  className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 max-w-[200px]">
                  <option value="">All Mailboxes</option>
                  {mailboxOptions.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
                {hasRulesFilters && (
                  <button onClick={() => { setRulesSearch(''); setSignalFilter(''); setMailboxFilter(''); setRulesPage(1); }}
                    className="inline-flex items-center gap-1 text-xs text-primary hover:underline"><X className="h-3 w-3" />Clear</button>
                )}
                <span className="text-xs text-slate-400 ml-auto tabular-nums">{filteredRules.length} rules</span>
              </div>
              <DataTable<UnifiedRule>
                table={rulesTable}
                total={filteredRules.length}
                loading={false}
                pageSize={RULES_PAGE_SIZE}
                currentPage={rulesPage}
                onPageChange={setRulesPage}
              />
            </>
          )}

          {/* Insights tab — grouped by severity */}
          {activeTab === 'insights' && (
            <div>
              {insights.length === 0 ? (
                <EmptyState icon={<Info className="h-8 w-8" />} title="No insights" description="Import rules first to generate insights" />
              ) : (() => {
                // Group by severity
                const critical = insights.filter(i => i.severity === 'critical');
                const warnings = insights.filter(i => i.severity === 'warning');
                const info = insights.filter(i => i.severity !== 'critical' && i.severity !== 'warning');

                const renderGroup = (title: string, items: RulesInsight[], variant: 'danger' | 'warning' | 'info') => {
                  if (!items.length) return null;
                  return (
                    <div className="mb-5">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-2 flex items-center gap-2">
                        {variant === 'danger' && <AlertTriangle className="h-3.5 w-3.5 text-destructive" />}
                        {variant === 'warning' && <AlertTriangle className="h-3.5 w-3.5 text-warning" />}
                        {variant === 'info' && <Info className="h-3.5 w-3.5 text-primary" />}
                        {title} ({items.length})
                      </h3>
                      <div className="space-y-2">
                        {items.map((insight, idx) => (
                          <div key={idx} className={cn(
                            'rounded-lg border bg-white shadow-sm p-4',
                            variant === 'danger' && 'border-l-4 border-l-destructive',
                            variant === 'warning' && 'border-l-4 border-l-warning',
                            variant === 'info' && 'border-l-4 border-l-primary',
                          )}>
                            <p className="text-sm font-bold text-slate-900 mb-1">
                              {insight.insight_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                            </p>
                            <p className="text-sm text-slate-700 mb-2">{insight.description}</p>
                            <p className="text-xs text-slate-500"><span className="font-medium">Recommendation:</span> {insight.recommendation}</p>
                            {insight.affected_mailboxes.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-2">
                                {insight.affected_mailboxes.map((mb, i) => (
                                  <span key={i} className="inline-flex px-1.5 py-0 text-[11px] rounded bg-slate-100 text-slate-500">{mb}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                };

                return (
                  <>
                    {renderGroup('Critical Issues', critical, 'danger')}
                    {renderGroup('Warnings', warnings, 'warning')}
                    {renderGroup('Recommendations', info, 'info')}
                  </>
                );
              })()}
            </div>
          )}
        </>
      )}
    </PageShell>
  );
};

export default EmailRulesPage;
