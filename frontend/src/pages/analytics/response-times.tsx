import React, { useState, useEffect, useRef } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { useClient } from '../../contexts/ClientContext';
import { responseTimesApi, formatResponseTime } from '../../services/analyticsService';
import type { ResponseTimeStats, SlowestResponder } from '../../types/analytics';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { KPICard, KPIStrip } from '@/components/ui/kpi-card';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { Clock } from 'lucide-react';

export const ResponseTimesAnalytics: React.FC = () => {
  const isMountedRef = useRef(true);
  const { clientId } = useClient();
  const [stats, setStats] = useState<ResponseTimeStats | null>(null);
  const [slowest, setSlowest] = useState<SlowestResponder[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => { isMountedRef.current = true; return () => { isMountedRef.current = false; }; }, []);

  useEffect(() => {
    if (!clientId) return;
    setLoading(true);
    Promise.all([responseTimesApi.stats(clientId), responseTimesApi.slowest(clientId)])
      .then(([s, sl]) => { if (isMountedRef.current) { setStats(s); setSlowest(sl); } })
      .finally(() => { if (isMountedRef.current) setLoading(false); });
  }, [clientId]);

  const comparisonData = stats ? [
    { label: 'Our Avg', hours: stats.our_avg_response_time || 0 },
    { label: 'Their Avg', hours: stats.their_avg_response_time || 0 },
    { label: 'Overall', hours: stats.avg_response_time_hours || 0 },
  ] : [];

  return (
    <PageShell>
      <PageHeader title="Response Times" description="Average response times, medians, and slowest responders" />

      {/* KPIs */}
      <KPIStrip className="mb-5">
        <KPICard title="Avg Response" value={formatResponseTime(stats?.avg_response_time_hours)} loading={loading} />
        <KPICard title="Median" value={formatResponseTime(stats?.median_response_time_hours)} loading={loading} />
        <KPICard title="Fastest" value={formatResponseTime(stats?.min_response_time_hours)} loading={loading} />
        <KPICard title="Slowest" value={formatResponseTime(stats?.max_response_time_hours)} loading={loading}
          danger={stats?.max_response_time_hours != null && stats.max_response_time_hours > 48} />
      </KPIStrip>

      {/* Business hours KPIs */}
      {stats?.avg_business_hours_response_time_hours != null && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
          <KPICard title="Avg (BH)" value={formatResponseTime(stats.avg_business_hours_response_time_hours)} loading={loading}
            subtitle="Business hours only" />
          <KPICard title="Median (BH)" value={formatResponseTime(stats.median_business_hours_response_time_hours)} loading={loading} />
          <KPICard title="Auto-Replies" value={stats.auto_reply_count ?? 0} loading={loading} />
          <KPICard title="Auto-Reply %" value={stats.auto_reply_percentage != null ? `${stats.auto_reply_percentage.toFixed(1)}%` : 'N/A'} loading={loading} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Chart */}
        <div className="rounded-lg border bg-white shadow-sm p-5">
          <h3 className="text-sm font-bold text-slate-900 mb-4">Response Time Comparison</h3>
          {loading ? <ContentSkeleton rows={4} className="p-0" /> : (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={comparisonData}>
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={(v: number) => formatResponseTime(v)} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="hours" fill="#667eea" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Slowest responders */}
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
          <div className="px-5 py-3 border-b">
            <h3 className="text-sm font-bold text-slate-900">Slowest Responders</h3>
          </div>
          {loading ? <ContentSkeleton rows={5} /> : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-slate-50/50">
                  <th className="px-4 py-2 text-left text-xs font-bold uppercase tracking-wider text-slate-600">Contact</th>
                  <th className="px-4 py-2 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-28">Avg Response</th>
                  <th className="px-4 py-2 text-right text-xs font-bold uppercase tracking-wider text-slate-600 w-20">Count</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {slowest.map(r => (
                  <tr key={r.contact_id || r.contact_email} className="hover:bg-slate-50/50">
                    <td className="px-4 py-2">
                      <span className="font-medium text-slate-800">{r.contact_name || r.contact_email}</span>
                      {r.company_name && <div className="text-xs text-slate-400">{r.company_name}</div>}
                    </td>
                    <td className="px-4 py-2 text-right text-xs text-warning font-medium tabular-nums">{formatResponseTime(r.avg_response_time_hours)}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-slate-600">{r.response_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </PageShell>
  );
};
