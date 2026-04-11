import React, { useState, useEffect } from 'react';
import { companiesApi } from '../services/analyticsService';
import { RefreshCw, Calendar, TrendingUp, TrendingDown, Target, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { StatusBadge } from '@/components/ui/status-badge';
import { formatCurrency } from '../utils/numberFormat';

const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Year-over-year color palette
const YEAR_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'];

interface Props { companyId: string; }

const SeasonalityChart: React.FC<Props> = ({ companyId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'aggregate' | 'yoy'>('aggregate');

  const load = (force = false) => {
    setLoading(true);
    companiesApi.getSeasonality(companyId, force).then(setData).finally(() => setLoading(false));
  };

  useEffect(() => { load(true); }, [companyId]);

  if (loading) return (
    <div className="rounded-lg border bg-white shadow-sm p-4">
      <h3 className="text-sm font-bold text-slate-900 mb-3">Seasonality</h3>
      <ContentSkeleton rows={4} className="p-0" />
    </div>
  );

  if (!data?.monthly?.length) return (
    <div className="rounded-lg border bg-white shadow-sm p-4">
      <h3 className="text-sm font-bold text-slate-900">Seasonality</h3>
      <p className="text-sm text-slate-400 mt-2">No ordering history</p>
    </div>
  );

  const peakSet = new Set(data.peak_months || []);
  const troughSet = new Set(data.trough_months || []);
  const yearly = data.yearly || {};
  const years = Object.keys(yearly).sort().reverse();
  const ytd = data.ytd_comparison;
  const outreachWindows = data.outreach_windows || [];
  const maxRevenue = Math.max(...data.monthly.map((m: any) => m.revenue), 1);

  return (
    <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-3">
          <Calendar className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold text-slate-900">Seasonality</h3>
          <span className="text-2xl font-bold tabular-nums text-slate-900">{data.total_orders}</span>
          <span className="text-xs text-slate-400">orders</span>
          {data.date_range && (
            <span className="text-[10px] text-slate-400">
              {data.date_range.earliest_year}–{data.date_range.latest_year}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {years.length > 1 && (
            <div className="flex rounded-md border border-slate-200 text-[11px]">
              <button
                onClick={() => setView('aggregate')}
                className={`px-2 py-0.5 rounded-l-md transition ${view === 'aggregate' ? 'bg-indigo-50 text-indigo-700 font-semibold' : 'text-slate-500'}`}
              >All Years</button>
              <button
                onClick={() => setView('yoy')}
                className={`px-2 py-0.5 rounded-r-md transition ${view === 'yoy' ? 'bg-indigo-50 text-indigo-700 font-semibold' : 'text-slate-500'}`}
              >Year/Year</button>
            </div>
          )}
          <button onClick={() => load(true)} className="p-1 rounded hover:bg-slate-100">
            <RefreshCw className="h-3.5 w-3.5 text-slate-400" />
          </button>
        </div>
      </div>

      {/* YTD Comparison Banner */}
      {ytd && (
        <div className={`px-4 py-2 border-b text-xs flex items-center gap-3 ${
          ytd.growth_pct >= 0 ? 'bg-emerald-50' : 'bg-red-50'
        }`}>
          {ytd.growth_pct >= 0
            ? <ArrowUpRight className="h-3.5 w-3.5 text-emerald-600" />
            : <ArrowDownRight className="h-3.5 w-3.5 text-red-600" />
          }
          <span className={`font-semibold ${ytd.growth_pct >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
            {ytd.growth_pct > 0 ? '+' : ''}{ytd.growth_pct}% YTD
          </span>
          <span className="text-slate-600">
            {ytd.current_year}: {formatCurrency(ytd.current_ytd_revenue)} vs {ytd.prior_year}: {formatCurrency(ytd.prior_ytd_revenue)}
            <span className="text-slate-400 ml-1">(Jan–{MONTHS[ytd.months_compared]})</span>
          </span>
        </div>
      )}

      {/* Outreach Windows Alert */}
      {outreachWindows.some((w: any) => w.is_approaching) && (
        <div className="px-4 py-2 border-b bg-amber-50 text-xs flex items-center gap-2">
          <Target className="h-3.5 w-3.5 text-amber-600" />
          <span className="font-semibold text-amber-700">Outreach window open:</span>
          {outreachWindows.filter((w: any) => w.is_approaching).map((w: any, i: number) => (
            <span key={i} className="text-amber-800">
              {w.peak_month_name} peak (avg {formatCurrency(w.avg_peak_revenue)}/yr)
            </span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-slate-100">
        {/* Monthly breakdown — 2/3 width */}
        <div className="md:col-span-2">
          <div className="px-4 py-2 bg-slate-50/50 border-b flex items-center justify-between">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              {view === 'aggregate' ? 'Monthly (All Years)' : 'Year over Year'}
            </h4>
            {view === 'yoy' && (
              <div className="flex items-center gap-3">
                {years.slice(0, 4).map((yr, i) => (
                  <span key={yr} className="flex items-center gap-1 text-[10px]">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: YEAR_COLORS[i] }} />
                    {yr}
                  </span>
                ))}
              </div>
            )}
          </div>

          {view === 'aggregate' ? (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-50">
                {data.monthly.map((m: any) => (
                  <tr key={m.month} className="hover:bg-slate-50/30">
                    <td className="px-4 py-1.5 w-16">
                      <span className="font-medium text-slate-800">{MONTHS[m.month]}</span>
                      {peakSet.has(m.month) && <TrendingUp className="inline h-3 w-3 text-emerald-500 ml-1.5" />}
                      {troughSet.has(m.month) && <TrendingDown className="inline h-3 w-3 text-slate-300 ml-1.5" />}
                    </td>
                    <td className="px-2 py-1.5 w-1/3">
                      <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${peakSet.has(m.month) ? 'bg-emerald-500' : 'bg-indigo-400'}`}
                          style={{ width: `${(m.revenue / maxRevenue) * 100}%` }}
                        />
                      </div>
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums text-slate-500 w-12 text-xs">{m.order_count}</td>
                    <td className="px-4 py-1.5 text-right tabular-nums font-medium text-slate-800">{formatCurrency(Number(m.revenue))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            /* Year-over-year view */
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b bg-slate-50/30">
                  <th className="px-4 py-1.5 text-left font-bold text-slate-600 w-12">Month</th>
                  {years.slice(0, 4).map((yr, i) => (
                    <th key={yr} className="px-2 py-1.5 text-right font-bold" style={{ color: YEAR_COLORS[i] }}>{yr}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {Array.from({ length: 12 }, (_, i) => i + 1).map(mo => {
                  const hasData = years.some(yr => (yearly[yr] || []).find((m: any) => m.month === mo));
                  if (!hasData) return null;
                  return (
                    <tr key={mo} className="hover:bg-slate-50/30">
                      <td className="px-4 py-1 font-medium text-slate-800">
                        {MONTHS[mo]}
                        {peakSet.has(mo) && <TrendingUp className="inline h-2.5 w-2.5 text-emerald-500 ml-1" />}
                      </td>
                      {years.slice(0, 4).map((yr, i) => {
                        const entry = (yearly[yr] || []).find((m: any) => m.month === mo);
                        return (
                          <td key={yr} className="px-2 py-1 text-right tabular-nums" style={{ color: YEAR_COLORS[i] }}>
                            {entry ? formatCurrency(entry.revenue) : <span className="text-slate-200">—</span>}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Right panel — Quarterly + Outreach Windows */}
        <div>
          {data.quarterly?.length > 0 && (
            <>
              <div className="px-4 py-2 bg-slate-50/50 border-b">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">Quarterly</h4>
              </div>
              <table className="w-full text-sm">
                <tbody className="divide-y divide-slate-50">
                  {data.quarterly.map((q: any) => (
                    <tr key={q.quarter} className="hover:bg-slate-50/30">
                      <td className="px-4 py-2 font-bold text-slate-800">Q{q.quarter}</td>
                      <td className="px-4 py-2 text-right tabular-nums text-slate-600">{q.order_count}</td>
                      <td className="px-4 py-2 text-right tabular-nums font-bold text-slate-900">{formatCurrency(Number(q.revenue))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {/* Outreach Windows */}
          {outreachWindows.length > 0 && (
            <>
              <div className="px-4 py-2 bg-slate-50/50 border-b border-t">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">Outreach Windows</h4>
              </div>
              <div className="px-4 py-2 space-y-2">
                {outreachWindows.map((w: any, i: number) => (
                  <div key={i} className={`rounded-md p-2 text-xs ${w.is_approaching ? 'bg-amber-50 border border-amber-200' : 'bg-slate-50'}`}>
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="font-semibold text-slate-800">{w.peak_month_name} peak</span>
                      {w.is_approaching && <StatusBadge variant="warning" size="sm">Now</StatusBadge>}
                    </div>
                    <p className="text-slate-500">
                      Approach in {w.approach_month_name} &middot; {formatCurrency(w.avg_peak_revenue)}/yr avg
                    </p>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default SeasonalityChart;
