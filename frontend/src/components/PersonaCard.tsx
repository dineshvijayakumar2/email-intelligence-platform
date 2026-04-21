import React from 'react';
import { useContactPersona } from '@/hooks/queries';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { UserCheck, Activity, TrendingUp } from 'lucide-react';

const PERSONA_CONFIG: Record<string, { label: string; variant: 'success' | 'info' | 'warning' | 'danger' | 'neutral' | 'purple' }> = {
  champion:            { label: 'Champion',          variant: 'success' },
  active_relationship: { label: 'Active',            variant: 'info' },
  prospect:            { label: 'Prospect',          variant: 'purple' },
  inactive_buyer:      { label: 'Inactive Buyer',    variant: 'warning' },
  dormant:             { label: 'Dormant',           variant: 'danger' },
  unknown:             { label: 'Unknown',           variant: 'neutral' },
};

function ScoreBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  const color = pct >= 70 ? 'bg-success' : pct >= 40 ? 'bg-warning' : pct >= 20 ? 'bg-orange-400' : 'bg-destructive';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-semibold tabular-nums text-slate-700 w-7 text-right">{value}</span>
    </div>
  );
}

interface Props { contactId: string; }

const PersonaCard: React.FC<Props> = ({ contactId }) => {
  const { data: persona, isLoading } = useContactPersona(contactId);

  if (isLoading) {
    return (
      <div className="rounded-lg border bg-white shadow-sm p-4">
        <div className="flex items-center gap-2 mb-3">
          <UserCheck className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">Persona</span>
        </div>
        <ContentSkeleton rows={3} className="p-0" />
      </div>
    );
  }

  if (!persona) return null;

  const cfg = PERSONA_CONFIG[persona.persona_classification] || PERSONA_CONFIG.unknown;

  return (
    <div className="rounded-lg border bg-white shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <UserCheck className="h-4 w-4 text-primary" />
          <span className="text-sm font-bold text-slate-900">Persona</span>
        </div>
        <StatusBadge variant={cfg.variant} size="default">{cfg.label}</StatusBadge>
      </div>

      <div className="space-y-3">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-slate-500">Engagement Score</span>
          </div>
          <ScoreBar value={persona.engagement_score || 0} />
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div className="flex items-center gap-1.5">
            <Activity className="h-3 w-3 text-slate-400" />
            <span className="text-slate-500">30d</span>
            <span className="font-medium tabular-nums ml-auto">{persona.email_velocity_30d ?? 0}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Activity className="h-3 w-3 text-slate-400" />
            <span className="text-slate-500">90d</span>
            <span className="font-medium tabular-nums ml-auto">{persona.email_velocity_90d ?? 0}</span>
          </div>
          {persona.quote_count > 0 && (
            <>
              <div className="flex items-center gap-1.5">
                <TrendingUp className="h-3 w-3 text-slate-400" />
                <span className="text-slate-500">Quotes</span>
                <span className="font-medium tabular-nums ml-auto">{persona.quote_count}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <TrendingUp className="h-3 w-3 text-slate-400" />
                <span className="text-slate-500">Strike</span>
                <span className="font-medium tabular-nums ml-auto">{persona.strike_rate != null ? `${Math.round(persona.strike_rate * 100)}%` : '—'}</span>
              </div>
            </>
          )}
        </div>

        {persona.email_days_since_last != null && (
          <div className="text-xs text-slate-400 pt-1 border-t">
            Last email {persona.email_days_since_last === 0 ? 'today' : `${persona.email_days_since_last}d ago`}
          </div>
        )}
      </div>
    </div>
  );
};

export default PersonaCard;
