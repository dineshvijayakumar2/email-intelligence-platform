import React from 'react';
import { LIFECYCLE_CONFIG } from '../../types/strategic-digest';
import type { LifecycleTier } from '../../types/strategic-digest';
import { StatusBadge } from '@/components/ui/status-badge';

interface LifecycleBadgeProps {
  tier?: string | null;
}

const VARIANT_MAP: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple'> = {
  champion: 'success',
  active: 'info',
  at_risk: 'warning',
  dormant: 'neutral',
  new_customer: 'purple',
  prospect: 'cyan' as any,
};

export const LifecycleBadge: React.FC<LifecycleBadgeProps> = ({ tier }) => {
  if (!tier) return null;
  const cfg = LIFECYCLE_CONFIG[tier as LifecycleTier];
  const label = cfg?.label || tier.replace(/_/g, ' ');
  const variant = VARIANT_MAP[tier] || 'neutral';
  return <StatusBadge variant={variant} size="sm">{label}</StatusBadge>;
};

export default LifecycleBadge;
