/**
 * Email Rules Intelligence — analyze email rules across account managers.
 * Moved to Insights section. Zero antd.
 */
import React, { useState, useEffect, useRef } from 'react';
import { useClient } from '../../contexts/ClientContext';
import { formatDateTime } from '../../utils/dateUtils';
import { rulesApi, clearRulesCache, getSignalLabel } from '../../services/rulesService';
import type { RulesAnalyticsResponse, MailboxRulesMetrics, RulesInsight, UnifiedRule } from '../../services/rulesService';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { KPICard, KPIStrip } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton, EmptyState } from '@/components/ui/empty-state';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import {
  Filter, RefreshCw, Download, AlertTriangle, Info, ChevronLeft, ChevronRight,
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
  const RULES_PAGE_SIZE = 20;

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

  const pagedRules = allRules.slice((rulesPage - 1) * RULES_PAGE_SIZE, rulesPage * RULES_PAGE_SIZE);
  const totalRulesPages = Math.ceil(allRules.length / RULES_PAGE_SIZE);

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

          {/* Rules tab */}
          {activeTab === 'rules' && (
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-slate-50/50">
                      <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Source</th>
                      <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-44">Mailbox</th>
                      <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Rule Name</th>
                      <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Signal</th>
                      <th className="px-3 py-2.5 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Conditions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {pagedRules.map((r, i) => (
                      <tr key={`${r.source_type}-${r.source_rule_id}-${i}`} className="hover:bg-slate-50/50">
                        <td className="px-3 py-2 text-xs text-slate-500">{r.source_type === 'gmail' ? 'Gmail' : 'Outlook'}</td>
                        <td className="px-3 py-2 text-xs text-slate-600 truncate max-w-[170px]">{r.mailbox_email}</td>
                        <td className="px-3 py-2 text-slate-800">{r.name}</td>
                        <td className="px-3 py-2"><StatusBadge variant={signalVariant(r.engagement_signal)} size="sm">{getSignalLabel(r.engagement_signal)}</StatusBadge></td>
                        <td className="px-3 py-2 text-xs text-slate-500 truncate max-w-[250px]">
                          {[
                            r.conditions.from_addresses.length ? `From: ${r.conditions.from_addresses.join(', ')}` : '',
                            r.conditions.from_domains.length ? `Domain: ${r.conditions.from_domains.join(', ')}` : '',
                            r.conditions.subject_contains.length ? `Subject: ${r.conditions.subject_contains.join(', ')}` : '',
                          ].filter(Boolean).join(' | ') || 'Any'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {allRules.length > RULES_PAGE_SIZE && (
                <div className="flex items-center justify-between px-4 py-3 border-t bg-slate-50/30">
                  <span className="text-xs text-slate-500">{allRules.length} rules</span>
                  <div className="flex items-center gap-1">
                    <button onClick={() => setRulesPage(p => Math.max(1, p - 1))} disabled={rulesPage <= 1} className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
                    <span className="text-xs text-slate-600 px-2 tabular-nums">{rulesPage} / {totalRulesPages}</span>
                    <button onClick={() => setRulesPage(p => Math.min(totalRulesPages, p + 1))} disabled={rulesPage >= totalRulesPages} className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Insights tab */}
          {activeTab === 'insights' && (
            <div className="space-y-3">
              {insights.length === 0 ? (
                <EmptyState icon={<Info className="h-8 w-8" />} title="No insights" description="Import rules first to generate insights" />
              ) : insights.map((insight, idx) => {
                const variant = insight.severity === 'critical' ? 'danger' : insight.severity === 'warning' ? 'warning' : 'info';
                return (
                  <div key={idx} className={cn('rounded-lg border bg-white shadow-sm p-4', variant === 'danger' && 'border-l-4 border-l-destructive', variant === 'warning' && 'border-l-4 border-l-warning')}>
                    <div className="flex items-start gap-3">
                      {insight.severity === 'critical' || insight.severity === 'warning'
                        ? <AlertTriangle className={cn('h-4 w-4 mt-0.5 shrink-0', variant === 'danger' ? 'text-destructive' : 'text-warning')} />
                        : <Info className="h-4 w-4 mt-0.5 text-primary shrink-0" />}
                      <div>
                        <p className="text-sm font-bold text-slate-900 mb-1">{insight.insight_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</p>
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
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </PageShell>
  );
};

export default EmailRulesPage;
