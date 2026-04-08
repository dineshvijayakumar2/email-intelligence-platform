/**
 * Opportunities Page — Zero antd.
 * 4-tab view: Action Items, Opportunities, Competitors, Entities
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Zap, DollarSign, Trophy, Users, RefreshCw, X } from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { StatusBadge } from '@/components/ui/status-badge';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { ContentSkeleton } from '@/components/ui/empty-state';
import dayjs from 'dayjs';
import { bucketApi, entityApi, intelligenceApi } from '../../services/aiService';
import { emailService } from '../../services/emailService';
import { MailboxSelector } from '../../components/MailboxSelector';
import { formatDate } from '../../utils/dateUtils';
import type {
  ActionItem, BusinessEntity, OpportunitySignal, IntelligenceResult,
} from '../../types/ai';
import type { Email } from '../../services/emailService';

const BUCKET_VARIANTS: Record<string, 'danger' | 'warning' | 'success' | 'info' | 'neutral'> = {
  response_urgency: 'danger', deal_at_risk: 'warning', retention_risk: 'danger',
  revenue_opportunity: 'success', new_relationship: 'info', account_neglect: 'warning',
};
const URGENCY_VARIANTS: Record<string, 'danger' | 'warning' | 'info' | 'neutral'> = {
  critical: 'danger', high: 'warning', medium: 'info', low: 'neutral',
};

const OpportunitiesPage: React.FC = () => {
  const isMountedRef = useRef(true);
  const [loading, setLoading] = useState(false);
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';
  const [clientId, setClientId] = useState('');
  const [activeTab, setActiveTab] = useState('actions');
  const [dateRange, setDateRange] = useState(30);

  const [actionItems, setActionItems] = useState<ActionItem[]>([]);
  const [opportunities, setOpportunities] = useState<IntelligenceResult[]>([]);
  const [competitors, setCompetitors] = useState<BusinessEntity[]>([]);
  const [entities, setEntities] = useState<BusinessEntity[]>([]);

  const [previewEmail, setPreviewEmail] = useState<Email | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  const loadData = useCallback(async () => {
    if (!mailboxId) return;
    setLoading(true);
    try {
      const dateFrom = new Date();
      dateFrom.setDate(dateFrom.getDate() - dateRange);
      const dateFromStr = dateFrom.toISOString().split('T')[0];

      const [actionsData, intelData] = await Promise.all([
        bucketApi.getActionItems(mailboxId, clientId, 0.3, 100),
        intelligenceApi.list(mailboxId, { page_size: 100, date_from: dateFromStr } as any),
      ]);
      if (!isMountedRef.current) return;
      setActionItems(actionsData.items || []);
      setOpportunities(intelData.items || []);

      const resolvedClientId = clientId ||
        (actionsData.items?.[0] as any)?.client_id ||
        (intelData.items?.[0] as any)?.client_id || '';
      if (resolvedClientId && resolvedClientId !== clientId) setClientId(resolvedClientId);

      if (resolvedClientId) {
        const [compData, entityData] = await Promise.all([
          entityApi.getCompetitors(resolvedClientId),
          entityApi.list(resolvedClientId, undefined, 100),
        ]);
        if (!isMountedRef.current) return;
        setCompetitors(compData.competitors || []);
        setEntities(entityData.items || []);
      }
    } catch (err) {
      console.error('Failed to load opportunities:', err);
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [mailboxId, clientId, dateRange]);

  useEffect(() => { if (mailboxId) loadData(); }, [mailboxId, loadData]);

  const handleMailboxChange = (ids: string[]) => { setMailboxIds(ids); setClientId(''); };

  const openEmailPreview = async (emailId?: string) => {
    if (!emailId) return;
    setPreviewLoading(true);
    setPreviewEmail(null);
    const email = await emailService.getEmail(emailId);
    if (isMountedRef.current) { setPreviewEmail(email); setPreviewLoading(false); }
  };

  const TABS = [
    { key: 'actions', label: 'Action Items', count: actionItems.length, icon: <Zap className="h-3.5 w-3.5" /> },
    { key: 'opportunities', label: 'Opportunities', count: opportunities.length, icon: <DollarSign className="h-3.5 w-3.5" /> },
    { key: 'competitors', label: 'Competitors', count: competitors.length, icon: <Trophy className="h-3.5 w-3.5" /> },
    { key: 'entities', label: 'Entities', count: entities.length, icon: <Users className="h-3.5 w-3.5" /> },
  ];

  return (
    <PageShell>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <PageHeader title="Opportunities & Signals" />
        <div className="flex items-center gap-2 flex-wrap">
          <MailboxSelector value={mailboxIds} onChange={handleMailboxChange} mode="single" size="small" />
          <select value={dateRange} onChange={e => setDateRange(Number(e.target.value))}
            className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white">
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={180}>Last 6 months</option>
          </select>
          <button onClick={loadData} disabled={!mailboxId}
            className="h-8 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5 disabled:opacity-50">
            <RefreshCw className="h-3.5 w-3.5" /> Refresh
          </button>
        </div>
      </div>

      {!mailboxId ? (
        <div className="rounded-lg border bg-white shadow-sm p-12 text-center">
          <p className="text-sm text-slate-400">Select a mailbox to view opportunities</p>
        </div>
      ) : (
        <>
          {/* Tab bar */}
          <div className="flex items-center gap-1 mb-4 border-b">
            {TABS.map(t => (
              <button key={t.key} onClick={() => setActiveTab(t.key)}
                className={`inline-flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 transition-colors ${
                  activeTab === t.key
                    ? 'border-primary text-primary font-medium'
                    : 'border-transparent text-slate-500 hover:text-slate-700'
                }`}>
                {t.icon} {t.label} ({t.count})
              </button>
            ))}
          </div>

          {loading && <ContentSkeleton rows={8} />}

          {/* Action Items */}
          {!loading && activeTab === 'actions' && (
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-slate-50/50">
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-32">Bucket</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Severity</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Date</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Email</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Action</th>
                    <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {actionItems.map((r, i) => (
                    <tr key={r.email_id || i} className="hover:bg-slate-50/50 cursor-pointer" onClick={() => openEmailPreview(r.email_id)}>
                      <td className="px-3 py-2">
                        <StatusBadge variant={BUCKET_VARIANTS[r.bucket] || 'neutral'} size="sm">
                          {r.bucket?.replace(/_/g, ' ')}
                        </StatusBadge>
                      </td>
                      <td className="px-3 py-2">
                        <StatusBadge variant={r.severity === 'critical' ? 'danger' : r.severity === 'high' ? 'warning' : 'info'} size="sm">
                          {r.severity}
                        </StatusBadge>
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-500">{r.email_date ? formatDate(r.email_date) : '—'}</td>
                      <td className="px-3 py-2">
                        <span className="text-sm text-slate-800 truncate block max-w-[200px]">{r.email_subject || r.email_summary || '—'}</span>
                        <span className="text-xs text-slate-400">{r.email_sender_name || r.email_sender || ''}</span>
                      </td>
                      <td className="px-3 py-2 text-sm text-slate-600 truncate max-w-[200px]">{r.recommended_action}</td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">{r.business_signal_score}</td>
                    </tr>
                  ))}
                  {actionItems.length === 0 && (
                    <tr><td colSpan={6} className="text-center py-8 text-sm text-slate-400">No action items</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Opportunities */}
          {!loading && activeTab === 'opportunities' && (
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-slate-50/50">
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Date</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Subject</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Intent</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Urgency</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-32">Signal</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Summary</th>
                    <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-16">Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {opportunities.map((r, i) => (
                    <tr key={r.email_id || i} className="hover:bg-slate-50/50 cursor-pointer" onClick={() => openEmailPreview(r.email_id)}>
                      <td className="px-3 py-2 text-xs text-slate-500">{r.email_date ? formatDate(r.email_date) : '—'}</td>
                      <td className="px-3 py-2">
                        <span className="text-sm truncate block max-w-[200px]">{r.email_subject || '—'}</span>
                        <span className="text-xs text-slate-400">{r.email_sender_name || r.email_sender || ''}</span>
                      </td>
                      <td className="px-3 py-2">{r.intent ? <StatusBadge variant="neutral" size="sm">{r.intent.replace(/_/g, ' ')}</StatusBadge> : '—'}</td>
                      <td className="px-3 py-2">{r.urgency ? <StatusBadge variant={URGENCY_VARIANTS[r.urgency] || 'neutral'} size="sm">{r.urgency}</StatusBadge> : '—'}</td>
                      <td className="px-3 py-2">{r.business_signal ? <StatusBadge variant="success" size="sm">{(r.business_signal as string).replace(/_/g, ' ')}</StatusBadge> : '—'}</td>
                      <td className="px-3 py-2 text-xs text-slate-500 truncate max-w-[200px]">{r.summary}</td>
                      <td className="px-3 py-2 text-right tabular-nums font-medium">{(r as any).business_signal_score}</td>
                    </tr>
                  ))}
                  {opportunities.length === 0 && (
                    <tr><td colSpan={7} className="text-center py-8 text-sm text-slate-400">No opportunities</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Competitors */}
          {!loading && activeTab === 'competitors' && (
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-slate-50/50">
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Competitor</th>
                    <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Mentions</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">First Seen</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Last Seen</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Context</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {competitors.map(r => (
                    <tr key={r.id || r.entity_name}>
                      <td className="px-3 py-2 font-medium">{r.entity_name}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.mention_count || 0}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{r.first_seen_at ? formatDate(r.first_seen_at) : '—'}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{r.last_seen_at ? formatDate(r.last_seen_at) : '—'}</td>
                      <td className="px-3 py-2 text-xs text-slate-400 truncate max-w-[300px]">{r.context_snippets?.[0] || '—'}</td>
                    </tr>
                  ))}
                  {competitors.length === 0 && (
                    <tr><td colSpan={5} className="text-center py-8 text-sm text-slate-400">No competitors detected</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Entities */}
          {!loading && activeTab === 'entities' && (
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-slate-50/50">
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Type</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Name</th>
                    <th className="px-3 py-2 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-24">Mentions</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">First Seen</th>
                    <th className="px-3 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Last Seen</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {entities.map(r => (
                    <tr key={r.id || `${r.entity_type}-${r.entity_name}`}>
                      <td className="px-3 py-2">
                        <StatusBadge variant={r.entity_type === 'competitor' ? 'danger' : r.entity_type === 'product' ? 'info' : 'success'} size="sm">
                          {r.entity_type}
                        </StatusBadge>
                      </td>
                      <td className="px-3 py-2 font-medium">{r.entity_name}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{r.mention_count || 0}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{r.first_seen_at ? formatDate(r.first_seen_at) : '—'}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{r.last_seen_at ? formatDate(r.last_seen_at) : '—'}</td>
                    </tr>
                  ))}
                  {entities.length === 0 && (
                    <tr><td colSpan={5} className="text-center py-8 text-sm text-slate-400">No entities detected</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Email preview modal */}
      {(previewLoading || previewEmail) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => { setPreviewEmail(null); setPreviewLoading(false); }}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl mx-4 max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            {previewLoading ? (
              <div className="flex items-center justify-center py-16">
                <Spinner className="h-6 w-6 animate-spin text-primary" />
              </div>
            ) : previewEmail ? (
              <div className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-slate-900 truncate">{previewEmail.subject || '(No Subject)'}</h3>
                  <button onClick={() => setPreviewEmail(null)} className="p-1 rounded hover:bg-slate-100">
                    <X className="h-4 w-4 text-slate-400" />
                  </button>
                </div>
                <div className="text-xs text-slate-500 mb-3">
                  <p><span className="font-medium">From:</span> {previewEmail.sender_name || previewEmail.sender_email}</p>
                  {previewEmail.recipients?.length ? <p><span className="font-medium">To:</span> {previewEmail.recipients.map(r => r.email).join(', ')}</p> : null}
                  <p><span className="font-medium">Date:</span> {previewEmail.sent_date ? formatDate(previewEmail.sent_date) : '—'}</p>
                </div>
                {previewEmail.body_html ? (
                  <iframe
                    srcDoc={`<!DOCTYPE html><html><head><meta charset="UTF-8"><base target="_blank"><style>body{font-family:system-ui;font-size:14px;line-height:1.6;color:#333;padding:16px;margin:0}img{max-width:100%}a{color:#667eea}blockquote{border-left:3px solid #d9d9d9;padding-left:16px;margin-left:0;color:#666}</style></head><body>${previewEmail.body_html}</body></html>`}
                    className="w-full min-h-[300px] border rounded"
                    sandbox="allow-same-origin"
                  />
                ) : (
                  <div className="p-3 bg-slate-50 rounded text-sm whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                    {previewEmail.body_text || 'No content available'}
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </PageShell>
  );
};

export default OpportunitiesPage;
