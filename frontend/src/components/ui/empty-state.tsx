import * as React from 'react';
import { cn } from '@/lib/utils';
import { Skeleton } from './skeleton';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

/**
 * Designed empty state — replaces antd <Empty>.
 * Shows icon, title, description, and optional action button.
 */
export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn(
      'flex flex-col items-center justify-center py-12 px-4 text-center',
      className,
    )}>
      {icon && (
        <div className="mb-3 text-slate-300">
          {icon}
        </div>
      )}
      <h3 className="text-sm font-medium text-slate-600 mb-1">{title}</h3>
      {description && (
        <p className="text-xs text-slate-400 max-w-[280px] mb-4">{description}</p>
      )}
      {action}
    </div>
  );
}

/**
 * Skeleton placeholder — shows what content will look like while loading.
 * Use instead of a spinner for premium feel.
 */
export function ContentSkeleton({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-3 p-4', className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      ))}
    </div>
  );
}
