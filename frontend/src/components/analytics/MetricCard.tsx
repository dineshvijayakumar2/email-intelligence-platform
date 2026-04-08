import React from 'react';
import { ContentSkeleton } from '@/components/ui/empty-state';

interface MetricCardProps {
  title: string;
  value: number | string | null | undefined;
  prefix?: React.ReactNode;
  suffix?: string;
  precision?: number;
  loading?: boolean;
  valueStyle?: React.CSSProperties;
  onClick?: () => void;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  prefix,
  suffix,
  precision,
  loading = false,
  onClick,
}) => {
  if (loading) {
    return (
      <div className="rounded-lg border bg-white shadow-sm p-5 text-center">
        <ContentSkeleton rows={1} />
      </div>
    );
  }

  const formatted = precision != null && typeof value === 'number'
    ? value.toFixed(precision)
    : (value ?? 0);

  return (
    <div
      className={`rounded-lg border bg-white shadow-sm p-5 text-center ${onClick ? 'cursor-pointer hover:border-primary/30 transition-colors' : ''}`}
      onClick={onClick}
    >
      <p className="text-xs font-medium text-slate-500 mb-1">{title}</p>
      <p className="text-2xl font-semibold tabular-nums text-slate-900">
        {prefix}{formatted}{suffix}
      </p>
    </div>
  );
};
