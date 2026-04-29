import { useEffect, useMemo, useState } from 'react';
import { Link2, FileText, Briefcase, Factory, Receipt, Clock, Plus, Calendar, Trash2, ChevronDown, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/status-badge';
import {
  getThreadJourney,
  deleteLink,
  type ThreadJourney,
  type ThreadQBLink,
} from '@/services/journeyService';
import { ManualLinkDialog } from './ManualLinkDialog';

interface Props {
  threadId: string;
  clientId: string;
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return '';
  const date = new Date(d);
  if (isNaN(date.getTime())) return '';
  return date.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
}

const SOURCE_RANK: Record<string, number> = { manual: 3, ai: 2, regex: 1 };

function deduplicateLinks(links: ThreadQBLink[]): ThreadQBLink[] {
  const seen = new Map<string, ThreadQBLink>();
  for (const lnk of links) {
    const key = `${lnk.qb_reference || lnk.qb_record_id}::${lnk.link_type}`;
    const existing = seen.get(key);
    if (!existing) {
      seen.set(key, lnk);
    } else {
      const newRank = (lnk.verified ? 10 : 0) + (SOURCE_RANK[lnk.source] || 0);
      const oldRank = (existing.verified ? 10 : 0) + (SOURCE_RANK[existing.source] || 0);
      if (newRank > oldRank) seen.set(key, lnk);
    }
  }
  return Array.from(seen.values());
}

const sourceVariant = (s: string): 'success' | 'info' | 'purple' | 'neutral' => {
  if (s === 'manual') return 'success';
  if (s === 'ai') return 'purple';
  if (s === 'regex') return 'info';
  return 'neutral';
};

const linkTypeConfig: Record<string, { icon: typeof FileText; label: string; variant: 'info' | 'success' | 'warning' }> = {
  quote: { icon: FileText, label: 'Quote', variant: 'info' },
  job: { icon: Briefcase, label: 'Job', variant: 'success' },
};

export function ThreadJourneyPanel({ threadId, clientId }: Props) {
  const [journey, setJourney] = useState<ThreadJourney | null>(null);
  const [loading, setLoading] = useState(true);
  const [showLink, setShowLink] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const refresh = () => getThreadJourney(threadId, clientId).then(setJourney);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch(() => setJourney(null))
      .finally(() => setLoading(false));
  }, [threadId, clientId]);

  const links = useMemo(() => journey ? deduplicateLinks(journey.links) : [], [journey]);

  const handleDelete = async (linkId: string) => {
    setDeleting(linkId);
    try {
      await deleteLink(linkId);
      await refresh();
    } catch { /* ignore */ }
    setDeleting(null);
  };

  if (loading) {
    return (
      <Card className="border-l-4 border-l-primary/30">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <Link2 className="h-4 w-4 text-primary" />
            Journey
          </CardTitle>
        </CardHeader>
        <CardContent><div className="text-xs text-slate-400 animate-pulse">Loading journey...</div></CardContent>
      </Card>
    );
  }

  if (!journey || links.length === 0) {
    return (
      <Card className="border-l-4 border-l-slate-200">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <Link2 className="h-4 w-4 text-slate-400" />
            Journey
          </CardTitle>
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setShowLink(true)}>
            <Plus className="h-3 w-3 mr-1" />Link
          </Button>
        </CardHeader>
        <CardContent>
          <div className="text-center py-6 space-y-2">
            <div className="text-sm text-slate-400">No QB references linked</div>
            <p className="text-xs text-slate-300">Link manually or run extraction to connect this thread to quotes &amp; jobs.</p>
          </div>
        </CardContent>
        {showLink && (
          <ManualLinkDialog threadId={threadId} clientId={clientId} open={showLink} onOpenChange={setShowLink}
            onLinked={() => { setShowLink(false); refresh(); }} />
        )}
      </Card>
    );
  }

  const hasDetail = journey.quotes.length > 0 || journey.jobs.length > 0 || journey.operations.length > 0 || journey.sales_line_items.length > 0;

  return (
    <Card className="border-l-4 border-l-primary">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm flex items-center gap-2">
          <Link2 className="h-4 w-4 text-primary" />
          <span>Journey</span>
          <span className="text-xs font-normal text-slate-400 bg-slate-100 rounded-full px-2 py-0.5 tabular-nums">
            {links.length} link{links.length !== 1 ? 's' : ''}
          </span>
        </CardTitle>
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setShowLink(true)}>
          <Plus className="h-3 w-3 mr-1" />Link
        </Button>
      </CardHeader>

      <CardContent className="space-y-1 pt-0">
        {/* Links */}
        {links.map((link) => {
          const cfg = linkTypeConfig[link.link_type] || linkTypeConfig.quote;
          const Icon = cfg.icon;
          return (
            <div key={link.id} className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-slate-50 transition-colors">
              <Icon className="h-3.5 w-3.5 text-slate-400 shrink-0" />
              <StatusBadge variant={cfg.variant} size="sm">{cfg.label}</StatusBadge>
              <span className="font-mono text-xs font-medium text-slate-800">{link.qb_reference || link.qb_record_id}</span>
              {!link.verified && (
                <span className="text-[10px] text-amber-500 italic">unverified</span>
              )}
              <div className="ml-auto flex items-center gap-1.5">
                <StatusBadge variant={sourceVariant(link.source)} size="sm">{link.source}</StatusBadge>
                {link.created_at && <span className="text-[10px] text-slate-300">{fmtDate(link.created_at)}</span>}
                <button
                  onClick={() => handleDelete(link.id)}
                  disabled={deleting === link.id}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 rounded hover:bg-red-50 text-slate-300 hover:text-red-500"
                  title="Remove link"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </div>
          );
        })}

        {/* Expandable QB detail */}
        {hasDetail && (
          <div className="pt-2">
            <button
              onClick={() => setDetailOpen(!detailOpen)}
              className="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-700 transition-colors w-full"
            >
              {detailOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              QB Details
            </button>

            {detailOpen && (
              <div className="mt-2 space-y-3">
                {journey.quotes.length > 0 && (
                  <Section title="Quotes" icon={FileText}>
                    {journey.quotes.map((q: any) => (
                      <div key={q.id} className="text-xs text-slate-600 space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{q.quote_no}</span>
                          <span className="text-slate-400">—</span>
                          <span>{q.contact_name || 'N/A'}</span>
                          <span className="font-semibold tabular-nums">${q.sell_ex_tax?.toLocaleString() ?? '?'}</span>
                          {q.category && <span className="text-slate-400">· {q.category}</span>}
                        </div>
                        <div className="flex items-center gap-3 text-[11px] text-slate-400">
                          {q.date_created && <span className="flex items-center gap-0.5"><Calendar className="h-2.5 w-2.5" />Quoted {fmtDate(q.date_created)}</span>}
                          {q.date_accepted && <span className="text-emerald-500">Accepted {fmtDate(q.date_accepted)}</span>}
                          {q.quantity && <span>{q.quantity.toLocaleString()} qty</span>}
                        </div>
                      </div>
                    ))}
                  </Section>
                )}

                {journey.jobs.length > 0 && (
                  <Section title="Jobs" icon={Briefcase}>
                    {journey.jobs.map((j: any) => (
                      <div key={j.id} className="text-xs text-slate-600 space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{j.job_no}</span>
                          <span className="text-slate-400">—</span>
                          <span>{j.customer_name || 'N/A'}</span>
                          {j.job_status && <StatusBadge variant={j.job_status?.toLowerCase().includes('complete') ? 'success' : 'warning'} size="sm">{j.job_status}</StatusBadge>}
                        </div>
                        <div className="flex items-center gap-3 text-[11px] text-slate-400">
                          {j.accepted_date && <span className="flex items-center gap-0.5"><Calendar className="h-2.5 w-2.5" />Accepted {fmtDate(j.accepted_date)}</span>}
                          {j.due_date && <span>Due {fmtDate(j.due_date)}</span>}
                        </div>
                      </div>
                    ))}
                  </Section>
                )}

                {journey.operations.length > 0 && (
                  <Section title="Operations" icon={Factory}>
                    {journey.operations.map((o: any) => (
                      <div key={o.id} className="text-xs text-slate-600">
                        {o.operation_name} ({o.department || 'N/A'})
                      </div>
                    ))}
                  </Section>
                )}

                {journey.sales_line_items.length > 0 && (
                  <Section title="Invoices" icon={Receipt}>
                    {journey.sales_line_items.map((s: any) => (
                      <div key={s.id} className="text-xs text-slate-600 flex items-center gap-2">
                        <span className="font-medium">{s.job_no}</span>
                        <span className="text-slate-400">—</span>
                        <span className="font-semibold tabular-nums">${s.total?.toLocaleString() ?? '?'}</span>
                        <span className="text-slate-400">{fmtDate(s.inv_date)}</span>
                      </div>
                    ))}
                  </Section>
                )}

                {journey.status_log.length > 0 && (
                  <Section title="Status Timeline" icon={Clock}>
                    {journey.status_log.slice(0, 10).map((s: any, i: number) => (
                      <div key={i} className="text-xs text-slate-600 flex gap-2">
                        <span className="text-slate-400 tabular-nums">{fmtDate(s.changed_at)}</span>
                        <span>{s.from_status} → {s.to_status}</span>
                      </div>
                    ))}
                  </Section>
                )}
              </div>
            )}
          </div>
        )}
      </CardContent>

      {showLink && (
        <ManualLinkDialog threadId={threadId} clientId={clientId} open={showLink} onOpenChange={setShowLink}
          onLinked={() => { setShowLink(false); refresh(); }} />
      )}
    </Card>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: typeof FileText; children: React.ReactNode }) {
  return (
    <div className="border-t border-slate-100 pt-2">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 mb-1.5">
        <Icon className="h-3 w-3" />{title}
      </div>
      <div className="space-y-1.5 pl-4">
        {children}
      </div>
    </div>
  );
}
