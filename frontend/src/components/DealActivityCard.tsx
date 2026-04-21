import React from 'react';
import { useContactDealActivity } from '@/hooks/queries';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { formatCurrency } from '@/utils/numberFormat';
import { GitBranch, FileText, Briefcase, ArrowRight } from 'lucide-react';

interface Props { contactId: string; }

function FunnelRow({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-slate-400">{icon}</span>
      <span className="text-slate-600 flex-1">{label}</span>
      <span className="font-semibold tabular-nums text-slate-900">{value}</span>
    </div>
  );
}

const DealActivityCard: React.FC<Props> = ({ contactId }) => {
  const { data, isLoading } = useContactDealActivity(contactId);

  if (isLoading) {
    return (
      <div className="rounded-lg border bg-white shadow-sm p-4">
        <div className="flex items-center gap-2 mb-3">
          <GitBranch className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">Deal Activity</span>
        </div>
        <ContentSkeleton rows={4} className="p-0" />
      </div>
    );
  }

  if (!data || data.total_threads === 0) return null;

  const hasDeals = data.linked_threads > 0;

  return (
    <div className="rounded-lg border bg-white shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-primary" />
          <span className="text-sm font-bold text-slate-900">Deal Activity</span>
        </div>
        {hasDeals && (
          <span className="text-xs text-slate-400">
            {data.linked_threads}/{data.total_threads} threads linked
          </span>
        )}
      </div>

      {!hasDeals ? (
        <p className="text-sm text-slate-400">No thread-to-deal links yet</p>
      ) : (
        <div className="space-y-3">
          {/* Thread → Quote → Job funnel */}
          <div className="space-y-1.5">
            <FunnelRow label="Threads with deals" value={data.linked_threads} icon={<GitBranch className="h-3 w-3" />} />
            <div className="flex items-center gap-1 ml-5">
              <ArrowRight className="h-2.5 w-2.5 text-slate-300" />
            </div>
            <FunnelRow label="Linked quotes" value={data.linked_quotes} icon={<FileText className="h-3 w-3" />} />
            <div className="flex items-center gap-1 ml-5">
              <ArrowRight className="h-2.5 w-2.5 text-slate-300" />
            </div>
            <FunnelRow label="Converted to jobs" value={data.converted_quotes} icon={<Briefcase className="h-3 w-3" />} />
          </div>

          {/* Pipeline values */}
          {(data.open_quotes > 0 || data.converted_value > 0) && (
            <div className="pt-2 border-t space-y-1.5">
              {data.open_quotes > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-1.5">
                    <StatusBadge variant="warning" size="sm">{data.open_quotes} open</StatusBadge>
                  </div>
                  <span className="font-semibold tabular-nums text-slate-700">{formatCurrency(data.open_pipeline_value)}</span>
                </div>
              )}
              {data.converted_value > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-1.5">
                    <StatusBadge variant="success" size="sm">{data.converted_quotes} won</StatusBadge>
                  </div>
                  <span className="font-semibold tabular-nums text-slate-700">{formatCurrency(data.converted_value)}</span>
                </div>
              )}
              {data.linked_jobs > 0 && data.linked_job_revenue > 0 && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">Job revenue</span>
                  <span className="font-semibold tabular-nums text-slate-700">{formatCurrency(data.linked_job_revenue)}</span>
                </div>
              )}
            </div>
          )}

          {/* Recent links */}
          {data.recent_links?.length > 0 && (
            <div className="pt-2 border-t">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Recent Links</p>
              {data.recent_links.map((link: any) => (
                <div key={link.id} className="flex items-center justify-between text-xs py-0.5">
                  <div className="flex items-center gap-1.5">
                    {link.link_type === 'quote' ? <FileText className="h-3 w-3 text-slate-400" /> : <Briefcase className="h-3 w-3 text-slate-400" />}
                    <span className="text-slate-700 font-medium">{link.qb_reference || link.qb_record_id}</span>
                  </div>
                  <StatusBadge variant={link.source === 'regex' ? 'info' : link.source === 'ai' ? 'purple' : 'success'} size="sm">
                    {link.source}
                  </StatusBadge>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default DealActivityCard;
