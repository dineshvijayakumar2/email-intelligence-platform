import React from 'react';
import { formatCurrency } from '../utils/numberFormat';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';

interface Category { category: string; revenue: number; }
interface Operation { operation: string; department?: string; }
interface CapabilityBreakdown { capability: string; operation_count: number; }

interface Props {
  categories: Category[];
  operations: Operation[];
  capability_breakdown?: CapabilityBreakdown[];
  process_tags?: string[];
  embellishment_tags?: string[];
  loading?: boolean;
}

/**
 * Renders multiple separate cards for the company detail grid.
 * Must be used inside a parent grid (grid-cols-2).
 */
export const ProductProfileCards: React.FC<Props> = ({
  categories, operations, capability_breakdown, process_tags, embellishment_tags, loading,
}) => {
  if (loading) return <div className="rounded-lg border bg-white shadow-sm p-4"><Skeleton className="h-4 w-32 mb-2" /><ContentSkeleton rows={3} className="p-0" /></div>;

  const hasCategories = categories.length > 0;
  const hasCapabilities = (capability_breakdown || []).length > 0;
  const hasProcesses = (process_tags || []).length > 0;
  const hasEmbellishments = (embellishment_tags || []).length > 0;
  const hasOperations = operations.length > 0;

  if (!hasCategories && !hasCapabilities && !hasProcesses && !hasEmbellishments && !hasOperations) return null;

  // Group operations by department
  const deptCounts: { department: string; count: number }[] = [];
  const deptMap: Record<string, number> = {};
  operations.forEach(op => { const d = op.department || 'Other'; deptMap[d] = (deptMap[d] || 0) + 1; });
  Object.entries(deptMap).sort((a, b) => b[1] - a[1]).forEach(([dept, count]) => deptCounts.push({ department: dept, count }));

  return (
    <>
      {/* Revenue by Category */}
      {hasCategories && (
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b"><span className="text-sm font-bold text-slate-900">Revenue by Category</span></div>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-50">
              {categories.map(c => (
                <tr key={c.category} className="hover:bg-slate-50/50">
                  <td className="px-4 py-2 text-slate-700">{c.category}</td>
                  <td className="px-4 py-2 text-right tabular-nums font-medium text-slate-900">{formatCurrency(c.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Capabilities */}
      {hasCapabilities && (
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b">
            <span className="text-sm font-bold text-slate-900">Capabilities</span>
            <span className="text-xs text-slate-400 ml-2">{capability_breakdown!.reduce((s, c) => s + c.operation_count, 0)} ops</span>
          </div>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-50">
              {capability_breakdown!.map(c => (
                <tr key={c.capability} className="hover:bg-slate-50/50">
                  <td className="px-4 py-2 text-slate-700">{c.capability}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-500">{c.operation_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Operations by Dept + Processes/Embellishments */}
      {(deptCounts.length > 0 || hasProcesses || hasEmbellishments) && (
        <div className="rounded-lg border bg-white shadow-sm p-4">
          {deptCounts.length > 0 && (
            <div className={hasProcesses || hasEmbellishments ? 'mb-3' : ''}>
              <p className="text-sm font-bold text-slate-900 mb-2">Operations by Department <span className="text-xs text-slate-400 font-normal">({operations.length})</span></p>
              <div className="space-y-1">
                {deptCounts.map(d => (
                  <div key={d.department} className="flex items-center justify-between text-sm">
                    <span className="text-slate-700">{d.department}</span>
                    <span className="tabular-nums text-slate-500">{d.count}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {hasProcesses && (
            <div className={hasEmbellishments ? 'mb-3' : ''}>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1">Processes ({process_tags!.length})</p>
              <div className="flex flex-wrap gap-1">
                {process_tags!.map(t => <span key={t} className="inline-flex px-1.5 py-0 text-[11px] rounded bg-slate-100 text-slate-600">{t}</span>)}
              </div>
            </div>
          )}
          {hasEmbellishments && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1">Embellishments ({embellishment_tags!.length})</p>
              <div className="flex flex-wrap gap-1">
                {embellishment_tags!.map(t => <span key={t} className="inline-flex px-1.5 py-0 text-[11px] rounded bg-slate-100 text-slate-600">{t}</span>)}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
};

export const ProductProfileCard = ProductProfileCards;
