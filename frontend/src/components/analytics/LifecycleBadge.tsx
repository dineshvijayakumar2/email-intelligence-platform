import React from 'react';
import { StatusBadge } from '@/components/ui/status-badge';

interface LifecycleBadgeProps {
  tier?: string | null;
}

// Maps raw QB customer_status values (e.g. "Active A Customer") to badge variants.
// Uses startsWith matching so "Active A Customer" and "Active B Customer" both resolve.
const VARIANT_RULES: Array<{ prefix: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple' }> = [
  { prefix: 'Active', variant: 'success' },
  { prefix: 'Champion', variant: 'success' },
  { prefix: 'New', variant: 'info' },
  { prefix: 'Prospect', variant: 'purple' },
  { prefix: 'At Risk', variant: 'warning' },
  { prefix: 'Dormant', variant: 'neutral' },
];

export const LifecycleBadge: React.FC<LifecycleBadgeProps> = ({ tier }) => {
  if (!tier) return null;
  const rule = VARIANT_RULES.find(r => tier.startsWith(r.prefix));
  const variant = rule?.variant || 'neutral';
  return <StatusBadge variant={variant} size="sm">{tier}</StatusBadge>;
};

export default LifecycleBadge;
