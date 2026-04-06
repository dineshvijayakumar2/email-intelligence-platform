import React, { useState, useEffect } from 'react';
import { companiesApi } from '../services/analyticsService';
import { RefreshCw, Calendar, ArrowUp, ArrowDown } from 'lucide-react';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { cn } from '@/lib/utils';

const MONTHS = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

interface Props { companyId: string; }

const SeasonalityChart: React.FC<Props> = ({ companyId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = (force = false) => {
    setLoading(true);
    companiesApi.getSeasonality(companyId, force).then(setData).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [companyId]);

  if (loading) return <div className="rounded-lg border bg-white shadow-sm p-4"><div className="flex items-center gap-2 mb-3"><Calendar className="h-4 w-4 text-primary" /><span className="text-sm font-semibold">Seasonality</span></div><ContentSkeleton rows={3} className="p-0" /></div>;
  if (!data?.monthly?.length) return <div className="rounded-lg border bg-white shadow-sm p-4"><div className="flex items-center gap-2"><Calendar className="h-4 w-4 text-primary" /><span className="text-sm font-semibold">Seasonality</span></div><p className="text-sm text-slate-400 mt-2">No ordering history</p></div>;

  const peakSet = new Set(data.peak_months || []);
  const troughSet = new Set(data.trough_months || []);

  return (
    <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold text-slate-900">Seasonality</span>
          <span className="text-xs text-slate-400">{data.total_orders} orders</span>
        </div>
        <button onClick={() => load(true)} className="p-1 rounded hover:bg-slate-100"><RefreshCw className="h-3.5 w-3.5 text-slate-400" /></button>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-slate-50/50">
            <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-slate-500">Month</th>
            <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-slate-500">Orders</th>
            <th className="px-3 py-2 text-right text-xs font-medium uppercase tracking-wider text-slate-500">Revenue</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {data.monthly.map((m: any) => (
            <tr key={m.month} className="hover:bg-slate-50/50">
              <td className="px-3 py-1.5">
                <span className="text-slate-700">{MONTHS[m.month]}</span>
                {peakSet.has(m.month) && <ArrowUp className="inline h-3 w-3 text-success ml-1" />}
                {troughSet.has(m.month) && <ArrowDown className="inline h-3 w-3 text-slate-300 ml-1" />}
              </td>
              <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">{m.order_count}</td>
              <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">${Number(m.revenue).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
        {data.quarterly?.length > 0 && (
          <tfoot className="border-t">
            {data.quarterly.map((q: any) => (
              <tr key={q.quarter} className="bg-slate-50/30">
                <td className="px-3 py-1.5 font-medium text-slate-700">Q{q.quarter}</td>
                <td className="px-3 py-1.5 text-right tabular-nums font-medium text-slate-700">{q.order_count}</td>
                <td className="px-3 py-1.5 text-right tabular-nums font-medium text-slate-700">${Number(q.revenue).toLocaleString()}</td>
              </tr>
            ))}
          </tfoot>
        )}
      </table>
    </div>
  );
};

export default SeasonalityChart;
