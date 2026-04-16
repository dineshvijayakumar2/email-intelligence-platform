import { useEffect, useState } from 'react';
import { Link2, FileText, Briefcase, Factory, Receipt, Clock, Plus } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/status-badge';
import { cn } from '@/lib/utils';
import {
  getThreadJourney,
  type ThreadJourney,
  type ThreadQBLink,
} from '@/services/journeyService';
import { ManualLinkDialog } from './ManualLinkDialog';

interface Props {
  threadId: string;
  clientId: string;
}

const linkTypeConfig: Record<string, { icon: typeof FileText; label: string; variant: 'info' | 'success' | 'warning' }> = {
  quote: { icon: FileText, label: 'Quote', variant: 'info' },
  job: { icon: Briefcase, label: 'Job', variant: 'success' },
};

export function ThreadJourneyPanel({ threadId, clientId }: Props) {
  const [journey, setJourney] = useState<ThreadJourney | null>(null);
  const [loading, setLoading] = useState(true);
  const [showLink, setShowLink] = useState(false);

  useEffect(() => {
    setLoading(true);
    getThreadJourney(threadId, clientId)
      .then(setJourney)
      .catch(() => setJourney(null))
      .finally(() => setLoading(false));
  }, [threadId, clientId]);

  if (loading) {
    return (
      <Card>
        <CardHeader><CardTitle className="text-sm">Journey</CardTitle></CardHeader>
        <CardContent><div className="text-xs text-slate-400">Loading...</div></CardContent>
      </Card>
    );
  }

  if (!journey || journey.links.length === 0) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm">Journey</CardTitle>
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setShowLink(true)}>
            <Plus className="h-3 w-3 mr-1" />Link
          </Button>
        </CardHeader>
        <CardContent>
          <div className="text-xs text-slate-400 text-center py-4">
            No QB references found. Link manually or run extraction.
          </div>
        </CardContent>
        {showLink && (
          <ManualLinkDialog
            threadId={threadId}
            clientId={clientId}
            open={showLink}
            onOpenChange={setShowLink}
            onLinked={() => {
              setShowLink(false);
              getThreadJourney(threadId, clientId).then(setJourney);
            }}
          />
        )}
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm flex items-center gap-1.5">
          <Link2 className="h-4 w-4 text-primary" />
          Journey ({journey.links.length} link{journey.links.length !== 1 ? 's' : ''})
        </CardTitle>
        <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => setShowLink(true)}>
          <Plus className="h-3 w-3 mr-1" />Link
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {journey.links.map((link) => {
          const cfg = linkTypeConfig[link.link_type] || linkTypeConfig.quote;
          const Icon = cfg.icon;
          return (
            <div key={link.id} className="flex items-center gap-2 text-sm">
              <Icon className="h-3.5 w-3.5 text-slate-400 shrink-0" />
              <StatusBadge variant={cfg.variant} size="sm">{cfg.label}</StatusBadge>
              <span className="font-mono text-xs text-slate-600">{link.qb_reference || link.qb_record_id}</span>
              {!link.verified && (
                <span className="text-[10px] text-amber-500 italic">unverified</span>
              )}
              <span className="text-[10px] text-slate-400 ml-auto">{link.source}</span>
            </div>
          );
        })}

        {journey.quotes.length > 0 && (
          <Section title="Quotes" icon={FileText}>
            {journey.quotes.map((q: any) => (
              <div key={q.id} className="text-xs text-slate-600 pl-5">
                {q.quote_no} — {q.contact_name || 'N/A'} — ${q.sell_ex_tax?.toLocaleString() ?? '?'}
              </div>
            ))}
          </Section>
        )}

        {journey.jobs.length > 0 && (
          <Section title="Jobs" icon={Briefcase}>
            {journey.jobs.map((j: any) => (
              <div key={j.id} className="text-xs text-slate-600 pl-5">
                {j.job_no} — {j.customer_name || 'N/A'}
              </div>
            ))}
          </Section>
        )}

        {journey.operations.length > 0 && (
          <Section title="Operations" icon={Factory}>
            {journey.operations.map((o: any) => (
              <div key={o.id} className="text-xs text-slate-600 pl-5">
                {o.operation_name} ({o.department || 'N/A'})
              </div>
            ))}
          </Section>
        )}

        {journey.sales_line_items.length > 0 && (
          <Section title="Invoices" icon={Receipt}>
            {journey.sales_line_items.map((s: any) => (
              <div key={s.id} className="text-xs text-slate-600 pl-5">
                {s.job_no} — ${s.total?.toLocaleString() ?? '?'} — {s.inv_date}
              </div>
            ))}
          </Section>
        )}

        {journey.status_log.length > 0 && (
          <Section title="Status Timeline" icon={Clock}>
            {journey.status_log.slice(0, 10).map((s: any, i: number) => (
              <div key={i} className="text-xs text-slate-600 pl-5 flex gap-2">
                <span className="text-slate-400">{new Date(s.changed_at).toLocaleDateString()}</span>
                <span>{s.from_status} → {s.to_status}</span>
              </div>
            ))}
          </Section>
        )}
      </CardContent>

      {showLink && (
        <ManualLinkDialog
          threadId={threadId}
          clientId={clientId}
          open={showLink}
          onOpenChange={setShowLink}
          onLinked={() => {
            setShowLink(false);
            getThreadJourney(threadId, clientId).then(setJourney);
          }}
        />
      )}
    </Card>
  );
}

function Section({ title, icon: Icon, children }: { title: string; icon: typeof FileText; children: React.ReactNode }) {
  return (
    <div className="border-t border-slate-100 pt-2">
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500 mb-1">
        <Icon className="h-3 w-3" />{title}
      </div>
      {children}
    </div>
  );
}
