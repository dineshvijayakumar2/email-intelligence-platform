import React from 'react';
import { ContentSkeleton } from '@/components/ui/empty-state';

interface ChartCardProps {
  title: string;
  children: React.ReactNode;
  loading?: boolean;
  height?: number;
  extra?: React.ReactNode;
}

export const ChartCard: React.FC<ChartCardProps> = ({
  title,
  children,
  loading = false,
  height = 300,
  extra,
}) => {
  return (
    <div className="rounded-lg border bg-white shadow-sm p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        {extra}
      </div>
      {loading ? (
        <ContentSkeleton rows={6} />
      ) : (
        <div style={{ height }}>{children}</div>
      )}
    </div>
  );
};
