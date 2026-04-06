import React from 'react';
import { cn } from '@/lib/utils';
import { getEngagementColor, getEngagementLabel } from '../../services/analyticsService';

interface EngagementBadgeProps {
  score: number | null | undefined;
  showBar?: boolean;
  size?: 'small' | 'default';
}

export const EngagementBadge: React.FC<EngagementBadgeProps> = ({ score, showBar = false, size = 'default' }) => {
  if (score == null) {
    return <span className="inline-flex items-center px-2 py-0.5 text-xs rounded-full bg-slate-100 text-slate-500">N/A</span>;
  }

  const color = getEngagementColor(score);
  const label = getEngagementLabel(score);
  const rounded = Math.round(score);

  if (showBar) {
    const width = size === 'small' ? 100 : 120;
    return (
      <div className="inline-flex items-center gap-2" title={`${label} engagement (${rounded}/100)`}>
        <div className="relative h-1.5 rounded-full bg-slate-100 overflow-hidden" style={{ width }}>
          <div className="absolute inset-y-0 left-0 rounded-full transition-all" style={{ width: `${rounded}%`, backgroundColor: color }} />
        </div>
        <span className="text-xs font-medium tabular-nums" style={{ color }}>{label} {rounded}</span>
      </div>
    );
  }

  return (
    <span className="inline-flex items-center px-2 py-0.5 text-xs font-semibold rounded-full" style={{ backgroundColor: `${color}18`, color }}>
      {label} {rounded}
    </span>
  );
};
