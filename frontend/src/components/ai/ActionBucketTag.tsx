/**
 * ActionBucketTag — Confidence-based colored tag with justification tooltip.
 * Zero antd.
 */

import React from 'react';
import { StatusBadge } from '@/components/ui/status-badge';

const BUCKET_DISPLAY: Record<string, { label: string; variant: 'danger' | 'warning' | 'success' | 'info' | 'neutral' | 'purple' }> = {
  response_urgency:    { label: 'Response Urgency',   variant: 'danger' },
  deal_at_risk:        { label: 'Deal at Risk',       variant: 'warning' },
  retention_risk:      { label: 'Retention Risk',     variant: 'danger' },
  revenue_opportunity: { label: 'Revenue Opportunity', variant: 'success' },
  new_relationship:    { label: 'New Relationship',   variant: 'info' },
  account_neglect:     { label: 'Account Neglect',    variant: 'warning' },
};

interface ActionBucketTagProps {
  bucket: string;
  confidence: number;
  justification?: string;
}

export const ActionBucketTag: React.FC<ActionBucketTagProps> = ({
  bucket,
  confidence,
  justification,
}) => {
  if (confidence < 0.5) return null;

  const display = BUCKET_DISPLAY[bucket] || { label: bucket, variant: 'neutral' as const };
  const isReview = confidence < 0.8;

  return (
    <span title={justification ? `${justification} (${Math.round(confidence * 100)}%)` : undefined}>
      <StatusBadge
        variant={isReview ? 'neutral' : display.variant}
        size="sm"
      >
        {isReview ? `${display.label} (Review)` : display.label}
      </StatusBadge>
    </span>
  );
};

export default ActionBucketTag;
