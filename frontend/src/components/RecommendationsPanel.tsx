import React, { useState, useEffect } from 'react';
import { companiesApi } from '../services/analyticsService';
import { RefreshCw, Users, Lightbulb, ChevronDown, ChevronRight } from 'lucide-react';

interface CrossContactRec {
  type: 'cross_contact';
  contact_id: string;
  contact_name: string;
  missing_operations: string[];
  departments: string[];
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

interface Props { companyId: string; }

export const RecommendationsPanel: React.FC<Props> = ({ companyId }) => {
  const [crossContact, setCrossContact] = useState<CrossContactRec[]>([]);
  const [relatedProduct, setRelatedProduct] = useState<RelatedProductRec[]>([]);
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
      setComputedAt(data?.computed_at);
    } catch { /* handled */ }
    setLoading(false);
  };

  useEffect(() => { load(true); }, [companyId]);

  if (loading) return <div className="space-y-2 py-2"><div className="h-3 w-3/4 bg-slate-100 rounded animate-pulse" /><div className="h-3 w-1/2 bg-slate-100 rounded animate-pulse" /></div>;

  const hasAny = crossContact.length > 0 || relatedProduct.length > 0;
  if (!hasAny) return <p className="text-sm text-slate-400 py-2">No recommendations yet</p>;

  const totalOps = crossContact.reduce((sum, r) => sum + r.missing_operations.length, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        {computedAt && <span className="text-[11px] text-slate-400">Computed {new Date(computedAt).toLocaleString('en-AU')}</span>}
        <button onClick={() => load(true)} className="ml-auto p-1 rounded hover:bg-slate-100"><RefreshCw className="h-3.5 w-3.5 text-slate-400" /></button>
      </div>

      {/* Collapsed summary */}
      {!expanded && (
        <div className="space-y-1">
          {crossContact.length > 0 && (
            <div className="flex items-center gap-2 text-sm">
              <Users className="h-3.5 w-3.5 text-primary" />
              <span><span className="font-medium">{crossContact.length}</span> contact{crossContact.length !== 1 ? 's' : ''} with gaps ({totalOps} ops)</span>
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
          {crossContact.length > 0 && (
            <div className="mb-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-2">
                <Users className="h-3 w-3 inline mr-1" />Cross-Contact Gaps ({crossContact.length})
              </p>
              {crossContact.map(rec => {
                const id = rec.contact_id || rec.contact_name;
                const isOpen = expandedContact === id;
                return (
                  <div key={id} className="rounded border border-slate-100 mb-1.5 overflow-hidden">
                    <div className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-slate-50" onClick={() => setExpandedContact(isOpen ? null : id)}>
                      {isOpen ? <ChevronDown className="h-3 w-3 text-slate-400" /> : <ChevronRight className="h-3 w-3 text-slate-400" />}
                      <span className="text-sm font-medium text-slate-800">{rec.contact_name}</span>
                      <span className="text-xs text-slate-400 ml-auto">{rec.missing_operations.length} ops</span>
                    </div>
                    {isOpen && (
                      <div className="px-3 pb-2 pt-0 flex flex-wrap gap-1">
                        {rec.missing_operations.map(op => (
                          <span key={op} className="inline-flex px-1.5 py-0 text-[11px] rounded bg-slate-100 text-slate-600">{op}</span>
                        ))}
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
