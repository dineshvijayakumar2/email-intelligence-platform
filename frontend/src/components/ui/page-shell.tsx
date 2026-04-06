import * as React from 'react';
import { cn } from '@/lib/utils';

interface PageShellProps {
  children: React.ReactNode;
  className?: string;
  /** Max width — default 1400px */
  maxWidth?: string;
}

/**
 * Consistent page container — replaces <div className="glass-page-bg">.
 * Provides padding, max-width, and centered layout.
 */
export function PageShell({ children, className, maxWidth = '1400px' }: PageShellProps) {
  return (
    <div
      className={cn('px-6 py-5 mx-auto w-full', className)}
      style={{ maxWidth }}
    >
      {children}
    </div>
  );
}

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

/**
 * Consistent page header with title, optional description, and action buttons.
 */
export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div className={cn('flex items-center justify-between mb-5', className)}>
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {description && (
          <p className="text-sm text-slate-500 mt-0.5">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
