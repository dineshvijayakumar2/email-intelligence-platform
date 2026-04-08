import React, { useState, useEffect } from 'react';
import { companiesApi } from '../services/analyticsService';
import { RefreshCw, Calendar, TrendingUp, TrendingDown } from 'lucide-react';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { formatCurrency } from '../utils/numberFormat';

const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

interface Props { companyId: string; }

const SeasonalityChart: React.FC<Props> = ({ companyId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

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

  return (
    <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-3">
          <Calendar className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold text-slate-900">Seasonality</h3>
          <span className="text-2xl font-bold tabular-nums text-slate-900">{data.total_orders}</span>
          <span className="text-xs text-slate-400">total orders</span>
        </div>
        <button onClick={() => load(true)} className="p-1 rounded hover:bg-slate-100">
          <RefreshCw className="h-3.5 w-3.5 text-slate-400" />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-slate-100">
        {/* Monthly breakdown — 2/3 width */}
        <div className="md:col-span-2">
          <div className="px-4 py-2 bg-slate-50/50 border-b">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">Monthly</h4>
          </div>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-50">
              {data.monthly.map((m: any) => (
                <tr key={m.month} className="hover:bg-slate-50/30">
                  <td className="px-4 py-1.5 w-16">
                    <span className="font-medium text-slate-800">{MONTHS[m.month]}</span>
                    {peakSet.has(m.month) && <TrendingUp className="inline h-3 w-3 text-success ml-1.5" />}
                    {troughSet.has(m.month) && <TrendingDown className="inline h-3 w-3 text-slate-300 ml-1.5" />}
                  </td>
                  <td className="px-4 py-1.5 text-right tabular-nums text-slate-600 w-20">{m.order_count}</td>
                  <td className="px-4 py-1.5 text-right tabular-nums font-medium text-slate-800">{formatCurrency(Number(m.revenue))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Quarterly breakdown — 1/3 width */}
        {data.quarterly?.length > 0 && (
          <div>
            <div className="px-4 py-2 bg-slate-50/50 border-b">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">Quarterly</h4>
            </div>
            <table className="w-full text-sm">
              <tbody className="divide-y divide-slate-50">
                {data.quarterly.map((q: any) => (
                  <tr key={q.quarter} className="hover:bg-slate-50/30">
                    <td className="px-4 py-2.5 font-bold text-slate-800">Q{q.quarter}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">{q.order_count}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums font-bold text-slate-900">{formatCurrency(Number(q.revenue))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.date_range && (
              <p className="px-4 py-2 text-[10px] text-slate-400 border-t">
                Data: {data.date_range.earliest} to {data.date_range.latest}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default SeasonalityChart;
