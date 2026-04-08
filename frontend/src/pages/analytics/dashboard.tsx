import React, { useState, useEffect, useRef } from 'react';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { useNavigate } from 'react-router-dom';
import { useClient } from '../../contexts/ClientContext';
import { MetricCard } from '../../components/analytics/MetricCard';
import { ChartCard } from '../../components/analytics/ChartCard';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import {
  dashboardAnalyticsApi, formatRelativeTime, formatResponseTime,
} from '../../services/analyticsService';
import type { DashboardSummary } from '../../types/analytics';
import { formatCurrency } from '../../utils/numberFormat';
import { Users, Building2, Mail, MessageSquare, AlertTriangle, Clock } from 'lucide-react';

const THREAD_COLORS: Record<string, string> = { Active: '#06b6d4', Awaiting: '#667eea', Overdue: '#ef4444' };

const PERIOD_OPTIONS = [
  { value: 0, label: 'All Time' },
  { value: 7, label: 'Last 7 Days' },
  { value: 30, label: 'Last 30 Days' },
  { value: 90, label: 'Last 90 Days' },
  { value: 180, label: 'Last 6 Months' },
  { value: 365, label: 'Last 1 Year' },
];

export const AnalyticsDashboard: React.FC = () => {
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const { clientId } = useClient();
  const [periodDays, setPeriodDays] = useState<number>(0);
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    const load = async () => {
      setLoading(true);
      const result = await dashboardAnalyticsApi.getSummary(clientId, periodDays || undefined);
      if (isMountedRef.current) { setData(result); setLoading(false); }
    };
    load();
    const interval = setInterval(load, 60000);
    return () => clearInterval(interval);
  }, [clientId, periodDays]);

  const engagementPieData = data ? [
    { name: 'Active', value: data.active_contacts, color: '#10b981' },
    { name: 'Quiet', value: data.quiet_contacts, color: '#f59e0b' },
    { name: 'At Risk', value: data.at_risk_contacts, color: '#ef4444' },
  ].filter(d => d.value > 0) : [];

  const threadBarData = data ? [
    { status: 'Active', count: data.active_threads, fill: THREAD_COLORS.Active },
    { status: 'Awaiting', count: data.awaiting_response_threads, fill: THREAD_COLORS.Awaiting },
    { status: 'Overdue', count: data.overdue_threads, fill: THREAD_COLORS.Overdue },
  ] : [];

  const periodLabel = PERIOD_OPTIONS.find(p => p.value === periodDays)?.label || 'All Time';

  return (
    <PageShell>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <PageHeader title="Analytics" description="Engagement analytics overview" />
        <select value={periodDays} onChange={e => setPeriodDays(Number(e.target.value))}
          className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white">
          {PERIOD_OPTIONS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </div>

      {!clientId ? (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 text-sm">Select a client to view analytics</div>
      ) : (
        <>
          {/* Metric Cards */}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
            <MetricCard title="Contacts" value={data?.total_contacts} loading={loading}
              prefix={<Users className="h-4 w-4 text-primary inline mr-1" />}
              onClick={() => navigate('/customers/contacts')} />
            <MetricCard title="Companies" value={data?.total_companies} loading={loading}
              prefix={<Building2 className="h-4 w-4 text-primary inline mr-1" />}
              onClick={() => navigate('/customers')} />
            <MetricCard title={periodDays ? `Emails (${periodLabel})` : 'Total Emails'} value={data?.total_emails} loading={loading}
              prefix={<Mail className="h-4 w-4 text-primary inline mr-1" />} />
            <MetricCard title="Active Threads" value={data?.active_threads} loading={loading}
              prefix={<MessageSquare className="h-4 w-4 text-primary inline mr-1" />}
              onClick={() => navigate('/customers/threads?status=active')} />
            <MetricCard title="Overdue" value={data?.overdue_threads} loading={loading}
              prefix={<AlertTriangle className="h-4 w-4 text-destructive inline mr-1" />}
              onClick={() => navigate('/customers/threads?status=overdue')} />
            <MetricCard title="Avg Response" value={formatResponseTime(data?.avg_response_time_hours)} loading={loading}
              prefix={<Clock className="h-4 w-4 text-primary inline mr-1" />}
              onClick={() => navigate('/manage/response-times')} />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
            <ChartCard title={`Contact Engagement${periodDays ? ` (${periodLabel})` : ''}`} loading={loading} height={280}>
              {engagementPieData.length > 0 ? (
                <ResponsiveContainer>
                  <PieChart>
                    <Pie data={engagementPieData} cx="50%" cy="50%" innerRadius={60} outerRadius={100}
                      paddingAngle={3} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                      {engagementPieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                    </Pie>
                    <Tooltip /><Legend />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-slate-400 text-center py-8">No contact data yet</p>
              )}
            </ChartCard>
            <ChartCard title={`Thread Status${periodDays ? ` (${periodLabel})` : ''}`} loading={loading} height={280}>
              {threadBarData.some(d => d.count > 0) ? (
                <ResponsiveContainer>
                  <BarChart data={threadBarData}>
                    <XAxis dataKey="status" /><YAxis /><Tooltip />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {threadBarData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-sm text-slate-400 text-center py-8">No thread data yet</p>
              )}
            </ChartCard>
          </div>

          {/* Tables */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
            {/* Top Contacts */}
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b">
                <button onClick={() => navigate('/customers/contacts')} className="text-sm font-semibold text-primary hover:underline">
                  Top Engaged Contacts
                </button>
              </div>
              {loading ? <div className="p-4"><ContentSkeleton rows={5} /></div> : (
                <div className="divide-y">
                  {(data?.top_engaged_contacts || []).map((r: any) => (
                    <div key={r.id} onClick={() => navigate(`/customers/contacts/${r.id}`)}
                      className="px-4 py-2 hover:bg-slate-50 cursor-pointer flex items-center justify-between">
                      <div>
                        <span className="text-sm font-medium text-slate-900">{r.full_name || r.email_address}</span>
                        {r.company_name && <span className="text-xs text-slate-400 ml-2">{r.company_name}</span>}
                      </div>
                      <button onClick={e => { e.stopPropagation(); navigate(`/emails?contact_id=${r.id}`); }}
                        className="text-xs text-primary tabular-nums hover:underline">{r.total_emails || 0}</button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Top Companies */}
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b">
                <button onClick={() => navigate('/customers')} className="text-sm font-semibold text-primary hover:underline">
                  Top Engaged Companies
                </button>
              </div>
              {loading ? <div className="p-4"><ContentSkeleton rows={5} /></div> : (
                <div className="divide-y">
                  {(data?.top_engaged_companies || []).map((r: any) => (
                    <div key={r.id} onClick={() => navigate(`/customers/${r.id}`)}
                      className="px-4 py-2 hover:bg-slate-50 cursor-pointer flex items-center justify-between">
                      <div>
                        <span className="text-sm font-medium text-slate-900">{r.company_name}</span>
                        {r.qb_tier && <StatusBadge variant="purple" size="sm">{r.qb_tier}</StatusBadge>}
                      </div>
                      <span className="text-xs tabular-nums text-slate-500">{formatCurrency(r.qb_total_revenue)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* At-Risk Contacts */}
            <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-destructive" />
                <button onClick={() => navigate('/customers/contacts')} className="text-sm font-semibold text-primary hover:underline">
                  At-Risk Contacts
                </button>
              </div>
              {loading ? <div className="p-4"><ContentSkeleton rows={5} /></div> : (
                <div className="divide-y">
                  {(data?.at_risk_contacts_list || []).map((r: any) => (
                    <div key={r.id} onClick={() => navigate(`/customers/contacts/${r.id}`)}
                      className="px-4 py-2 hover:bg-slate-50 cursor-pointer flex items-center justify-between">
                      <div>
                        <span className="text-sm text-slate-800">{r.full_name || r.email_address}</span>
                        {r.company_name && <span className="text-xs text-slate-400 ml-2">{r.company_name}</span>}
                      </div>
                      <StatusBadge variant={r.days_since_contact > 90 ? 'danger' : 'warning'} size="sm">
                        {r.days_since_contact}d
                      </StatusBadge>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Footer */}
          <p className="text-xs text-slate-400 text-right">
            Last extraction: {formatRelativeTime(data?.last_extraction_date)} |
            Last contact: {formatRelativeTime(data?.last_contact_date)} |
            Avg engagement: {data?.avg_engagement_score != null ? Math.round(data.avg_engagement_score) : 'N/A'}/100
          </p>
        </>
      )}
    </PageShell>
  );
};
