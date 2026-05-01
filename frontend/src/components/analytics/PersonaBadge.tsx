import React from 'react';
import { StatusBadge } from '@/components/ui/status-badge';

const PERSONA_VARIANTS: Record<string, { variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'purple'; label: string }> = {
  champion: { variant: 'success', label: 'Champion' },
  active_buyer: { variant: 'info', label: 'Active Buyer' },
  active_relationship: { variant: 'info', label: 'Active' },
  warm_lead: { variant: 'purple', label: 'Warm Lead' },
  prospect: { variant: 'purple', label: 'Prospect' },
  inactive_buyer: { variant: 'warning', label: 'Inactive Buyer' },
  dormant: { variant: 'danger', label: 'Dormant' },
  shared_mailbox: { variant: 'neutral', label: 'Shared' },
};

export const PersonaBadge: React.FC<{ classification?: string | null }> = ({ classification }) => {
  if (!classification || classification === 'unknown') return null;
  const config = PERSONA_VARIANTS[classification];
  if (!config) return null;
  return <StatusBadge variant={config.variant} size="sm">{config.label}</StatusBadge>;
};

export default PersonaBadge;
