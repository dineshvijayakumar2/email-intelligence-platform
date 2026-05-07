import React, { useState, useEffect } from 'react';
import { companiesApi } from '../services/analyticsService';
import { RefreshCw, Users, Lightbulb, ChevronDown, ChevronRight, AlertTriangle } from 'lucide-react';

interface CrossContactRec {
  type: 'cross_contact';
  contact_id: string;
  contact_name: string;
  already_buys: string[];
  untapped_capabilities: string[];
  reason: string;
}

interface RelatedProductRec {
  type: 'related_product';
  current_operation: string;
  recommended_operation: string;
  confidence: number;
  supporting_count: number;
  message: string;
}

interface RevenueInsight {
  insight_type: 'concentration_risk' | 'buyer_decay_risk';
  company_total_revenue: number;
  total_contacts: number;
  revenue_producing_contacts: number;
  top_buyer_name: string;
  top_buyer_persona: string;
  top_revenue_contacts: { name: string; pct_of_revenue: number; persona: string; total_job_value: number }[];
  unengaged_contacts: { name: string; persona: string; engagement_score: number }[];
}

interface Props { companyId: string; }

export const RecommendationsPanel: React.FC<Props> = ({ companyId }) => {
  const [crossContact, setCrossContact] = useState<CrossContactRec[]>([]);
  const [relatedProduct, setRelatedProduct] = useState<RelatedProductRec[]>([]);
  const [revenueInsight, setRevenueInsight] = useState<RevenueInsight | null>(null);
  const [loading, setLoading] = useState(true);
  const [computedAt, setComputedAt] = useState<string | undefined>();
  const [expanded, setExpanded] = useState(false);
  const [expandedContact, setExpandedContact] = useState<string | null>(null);

  const load = async (force = false) => {
    setLoading(true);
    try {
      const data = await companiesApi.getRecommendations(companyId, force);
      setCrossContact(data?.cross_contact_recs || []);
      setRelatedProduct(data?.related_product_recs || []);
      setRevenueInsight(data?.revenue_insight || null);
      setComputedAt(data?.computed_at);
    } catch { /* handled */ }
    setLoading(false);
  };

  useEffect(() => { load(true); }, [companyId]);

  if (loading) return <div className="space-y-2 py-2"><div className="h-3 w-3/4 bg-slate-100 rounded animate-pulse" /><div className="h-3 w-1/2 bg-slate-100 rounded animate-pulse" /></div>;

  const hasAny = crossContact.length > 0 || relatedProduct.length > 0 || revenueInsight != null;
  if (!hasAny) return <p className="text-sm text-slate-400 py-2">No recommendations yet</p>;

  const totalGaps = crossContact.reduce((sum, r) => sum + r.untapped_capabilities.length, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        {computedAt && <span className="text-[11px] text-slate-400">Computed {new Date(computedAt).toLocaleString('en-AU')}</span>}
        <button onClick={() => load(true)} className="ml-auto p-1 rounded hover:bg-slate-100"><RefreshCw className="h-3.5 w-3.5 text-slate-400" /></button>
      </div>

      {/* Collapsed summary */}
      {!expanded && (
        <div className="space-y-1">
          {revenueInsight && (
            <div className={`flex items-center gap-2 text-sm ${revenueInsight.insight_type === 'buyer_decay_risk' ? 'text-red-700' : 'text-amber-700'}`}>
              <AlertTriangle className="h-3.5 w-3.5" />
              <span className="font-medium">
                {revenueInsight.insight_type === 'buyer_decay_risk'
                  ? `Buyer decay risk — top buyer (${revenueInsight.top_buyer_name}) is inactive`
                  : `Revenue concentrated in ${revenueInsight.revenue_producing_contacts} of ${revenueInsight.total_contacts} contacts`}
              </span>
            </div>
          )}
          {crossContact.length > 0 && (
            <div className="flex items-center gap-2 text-sm">
              <Users className="h-3.5 w-3.5 text-primary" />
              <span><span className="font-medium">{crossContact.length}</span> contact{crossContact.length !== 1 ? 's' : ''} with untapped capabilities ({totalGaps})</span>
            </div>
          )}
          {relatedProduct.length > 0 && (
            <div className="flex items-center gap-2 text-sm">
              <Lightbulb className="h-3.5 w-3.5 text-warning" />
              <span><span className="font-medium">{relatedProduct.length}</span> product opportunit{relatedProduct.length !== 1 ? 'ies' : 'y'}</span>
            </div>
          )}
        </div>
      )}

      {/* Expanded detail */}
      {expanded && (
        <div>
          {revenueInsight && (
            <div className={`rounded border px-3 py-2.5 mb-3 ${
              revenueInsight.insight_type === 'buyer_decay_risk'
                ? 'border-red-200 bg-red-50/50'
                : 'border-amber-200 bg-amber-50/50'
            }`}>
              <p className="text-xs font-medium uppercase tracking-wide mb-2 flex items-center gap-1.5"
                style={{ color: revenueInsight.insight_type === 'buyer_decay_risk' ? '#b91c1c' : '#b45309' }}>
                <AlertTriangle className="h-3 w-3" />
                {revenueInsight.insight_type === 'buyer_decay_risk' ? 'Buyer Decay Risk' : 'Revenue Concentration Risk'}
              </p>
              <div className="grid grid-cols-3 gap-2 text-sm mb-2">
                <div>
                  <span className="text-xs text-slate-500">Revenue</span>
                  <div className="font-semibold tabular-nums">${revenueInsight.company_total_revenue.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
                </div>
                <div>
                  <span className="text-xs text-slate-500">Contacts</span>
                  <div className="font-medium">{revenueInsight.total_contacts} total</div>
                </div>
                <div>
                  <span className="text-xs text-slate-500">Revenue Contacts</span>
                  <div className="font-medium">{revenueInsight.revenue_producing_contacts} of {revenueInsight.total_contacts}</div>
                </div>
              </div>
              {revenueInsight.top_revenue_contacts.length > 0 && (
                <div className="mb-2">
                  <span className="text-xs text-slate-500">Top Revenue Contacts</span>
                  <div className="space-y-0.5 mt-0.5">
                    {revenueInsight.top_revenue_contacts.map((c, i) => (
                      <div key={i} className="text-sm flex items-center gap-2">
                        <span className="font-medium">{c.name}</span>
                        <span className="text-xs text-slate-500">{c.pct_of_revenue}% · ${c.total_job_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                        <span className="text-[11px] px-1 rounded bg-slate-100 text-slate-500">{c.persona?.replace(/_/g, ' ')}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {revenueInsight.unengaged_contacts.length > 0 && (
                <div>
                  <span className="text-xs text-slate-500">Unengaged Contacts ({revenueInsight.unengaged_contacts.length})</span>
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {revenueInsight.unengaged_contacts.slice(0, 8).map((c, i) => (
                      <span key={i} className="inline-flex px-1.5 py-0 text-[11px] rounded bg-slate-100 text-slate-600">
                        {c.name} <span className="text-slate-400 ml-1">({c.persona?.replace(/_/g, ' ')})</span>
                      </span>
                    ))}
                    {revenueInsight.unengaged_contacts.length > 8 && (
                      <span className="text-[11px] text-slate-400">+{revenueInsight.unengaged_contacts.length - 8} more</span>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {crossContact.length > 0 && (
            <div className="mb-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-2">
                <Users className="h-3 w-3 inline mr-1" />Capability Gaps ({crossContact.length} contacts)
              </p>
              {crossContact.map(rec => {
                const id = rec.contact_id || rec.contact_name;
                const isOpen = expandedContact === id;
                return (
                  <div key={id} className="rounded border border-slate-100 mb-1.5 overflow-hidden">
                    <div className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-slate-50" onClick={() => setExpandedContact(isOpen ? null : id)}>
                      {isOpen ? <ChevronDown className="h-3 w-3 text-slate-400" /> : <ChevronRight className="h-3 w-3 text-slate-400" />}
                      <span className="text-sm font-medium text-slate-800">{rec.contact_name}</span>
                      <span className="text-xs text-slate-400 ml-auto">{rec.untapped_capabilities.length} untapped</span>
                    </div>
                    {isOpen && (
                      <div className="px-3 pb-2 pt-0 space-y-1.5">
                        <div>
                          <span className="text-[11px] text-slate-400 uppercase tracking-wide">Already buys</span>
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {rec.already_buys.map(cap => (
                              <span key={cap} className="inline-flex px-1.5 py-0 text-[11px] rounded bg-emerald-50 text-emerald-700 border border-emerald-100">{cap}</span>
                            ))}
                          </div>
                        </div>
                        <div>
                          <span className="text-[11px] text-slate-400 uppercase tracking-wide">Untapped capabilities</span>
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {rec.untapped_capabilities.map(cap => (
                              <span key={cap} className="inline-flex px-1.5 py-0 text-[11px] rounded bg-amber-50 text-amber-700 border border-amber-100">{cap}</span>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {relatedProduct.length > 0 && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-2">
                <Lightbulb className="h-3 w-3 inline mr-1" />Product Opportunities ({relatedProduct.length})
              </p>
              {relatedProduct.map((rec, i) => (
                <div key={i} className="rounded border border-slate-100 px-3 py-2 mb-1.5">
                  <p className="text-sm text-slate-700">{rec.message}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs text-slate-500">Try: <span className="font-medium">{rec.recommended_operation}</span></span>
                    <span className="text-xs text-slate-400">{Math.round(rec.confidence * 100)}% · {rec.supporting_count} customers</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <button onClick={() => setExpanded(!expanded)} className="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-2">
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {expanded ? 'Show less' : 'Show details'}
      </button>
    </div>
  );
};
