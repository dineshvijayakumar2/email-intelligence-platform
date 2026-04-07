import * as React from 'react';
import { cn } from '@/lib/utils';
import { ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { Skeleton } from './skeleton';

interface KPICardProps {
  title: string;
  value: string | number;
  /** Show trend arrow with delta text, e.g. "+12%" */
  delta?: string;
  /** 'up' = green, 'down' = red, 'neutral' = gray */
  trend?: 'up' | 'down' | 'neutral';
  /** Optional subtitle text below value */
  subtitle?: string;
  /** Prefix before value, e.g. "$" */
  prefix?: string;
  /** Suffix after value, e.g. "%" */
  suffix?: string;
  /** Click handler */
  onClick?: () => void;
  /** Loading state */
  loading?: boolean;
  /** Danger border (for "at risk" emphasis) */
  danger?: boolean;
  className?: string;
}

export function KPICard({
  title, value, delta, trend, subtitle, prefix, suffix,
  onClick, loading, danger, className,
}: KPICardProps) {
  if (loading) {
    return (
      <div className={cn(
        'rounded-lg border bg-white p-4 shadow-sm',
        className,
      )}>
        <Skeleton className="h-3 w-20 mb-2" />
        <Skeleton className="h-7 w-16 mb-1" />
        <Skeleton className="h-3 w-24" />
      </div>
    );
  }

  const TrendIcon = trend === 'up' ? ArrowUp : trend === 'down' ? ArrowDown : Minus;
  const trendColor = trend === 'up' ? 'text-emerald-600' : trend === 'down' ? 'text-red-600' : 'text-slate-400';

  return (
    <div
      className={cn(
        'rounded-lg border bg-white p-4 shadow-sm transition-all',
        danger && 'border-red-300 bg-red-50/50',
        onClick && 'cursor-pointer hover:shadow-md hover:border-primary/30',
        className,
      )}
      onClick={onClick}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-1">
        {title}
      </p>
      <div className="flex items-baseline gap-1">
        {prefix && <span className="text-sm text-slate-500">{prefix}</span>}
        <span className="text-2xl font-semibold tabular-nums text-slate-900">
          {typeof value === 'number' ? new Intl.NumberFormat('en-AU').format(value) : value}
        </span>
        {suffix && <span className="text-sm text-slate-500">{suffix}</span>}
      </div>
      {(delta || subtitle) && (
        <div className="mt-1 flex items-center gap-1.5">
          {delta && trend && (
            <span className={cn('inline-flex items-center gap-0.5 text-xs font-medium', trendColor)}>
              <TrendIcon className="h-3 w-3" />
              {delta}
            </span>
          )}
          {subtitle && (
            <span className="text-xs text-slate-400">{subtitle}</span>
          )}
        </div>
      )}
    </div>
  );
}

/** Horizontal strip of KPI cards */
export function KPIStrip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('grid grid-cols-2 md:grid-cols-4 gap-3', className)}>
      {children}
    </div>
  );
}
