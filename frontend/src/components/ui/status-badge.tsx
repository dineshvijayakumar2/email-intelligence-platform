import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

/**
 * StatusBadge — filled semantic chips.
 *
 * Uses semantic token colors from tailwind.config.ts.
 * Never use raw Tailwind colors (red-100, blue-200) — always use
 * the semantic variants so the app can be rethemed in one place.
 */
const statusBadgeVariants = cva(
  'inline-flex items-center rounded-full font-medium transition-colors whitespace-nowrap',
  {
    variants: {
      variant: {
        success:  'bg-success-subtle text-success',
        warning:  'bg-warning-subtle text-warning',
        danger:   'bg-destructive-subtle text-destructive',
        info:     'bg-primary-subtle text-primary',
        neutral:  'bg-slate-100 text-slate-600',
        purple:   'bg-accent-subtle text-accent',
      },
      size: {
        sm: 'px-2 py-0 text-[10px] leading-5',
        default: 'px-2.5 py-0.5 text-xs',
        lg: 'px-3 py-1 text-sm',
      },
    },
    defaultVariants: {
      variant: 'neutral',
      size: 'default',
    },
  }
);

export interface StatusBadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof statusBadgeVariants> {}

export function StatusBadge({ className, variant, size, ...props }: StatusBadgeProps) {
  return (
    <span className={cn(statusBadgeVariants({ variant, size }), className)} {...props} />
  );
}
