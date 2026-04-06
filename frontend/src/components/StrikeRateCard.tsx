import React, { useState, useEffect } from 'react';
import { companiesApi } from '../services/analyticsService';
import { RefreshCw, Target } from 'lucide-react';
import { ContentSkeleton } from '@/components/ui/empty-state';

interface Props { companyId: string; }

const StrikeRateCard: React.FC<Props> = ({ companyId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = (force = false) => {
    setLoading(true);
    companiesApi.getStrikeRate(companyId, force).then(setData).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [companyId]);

  if (loading) return <div className="rounded-lg border bg-white shadow-sm p-4"><div className="flex items-center gap-2 mb-3"><Target className="h-4 w-4 text-primary" /><span className="text-sm font-semibold">Strike Rate</span></div><ContentSkeleton rows={3} className="p-0" /></div>;

  const total = data?.company_total;

  return (
    <div className="rounded-lg border bg-white shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2"><Target className="h-4 w-4 text-primary" /><span className="text-sm font-semibold text-slate-900">Strike Rate</span></div>
        <button onClick={() => load(true)} className="p-1 rounded hover:bg-slate-100"><RefreshCw className="h-3.5 w-3.5 text-slate-400" /></button>
      </div>
      {total && total.total_quotes > 0 ? (
        <>
          <div className="flex items-baseline gap-2 mb-3">
            <span className="text-2xl font-semibold tabular-nums text-slate-900">{total.strike_rate_pct}%</span>
            <span className="text-xs text-slate-500">{total.converted} / {total.total_quotes} converted</span>
          </div>
          {data.by_contact?.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">By Contact</p>
              {data.by_contact.slice(0, 5).map((c: any) => (
                <div key={c.contact_email} className="flex items-center justify-between text-sm">
                  <span className="text-slate-700 truncate">{c.contact_name || c.contact_email}</span>
                  <span className="tabular-nums text-slate-500">{c.strike_rate_pct}% ({c.converted}/{c.total_quotes})</span>
                </div>
              ))}
            </div>
          )}
          {data.by_year?.length > 0 && (
            <div className="mt-3 space-y-1">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">By Year</p>
              {data.by_year.slice(0, 4).map((y: any) => (
                <div key={y.year} className="flex items-center justify-between text-sm">
                  <span className="text-slate-700">{y.year}</span>
                  <span className="tabular-nums text-slate-500">{y.strike_rate_pct}% ({y.converted}/{y.total_quotes})</span>
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-slate-400">No quote data available</p>
      )}
    </div>
  );
};

export default StrikeRateCard;
