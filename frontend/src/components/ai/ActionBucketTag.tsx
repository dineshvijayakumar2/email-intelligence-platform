/**
 * ActionBucketTag — Confidence-based colored tag with justification tooltip.
 *
 * Layer 3 confidence gating:
 *  - >= 0.8: full tag
 *  - 0.5-0.8: "Review" tag (muted)
 *  - < 0.5: hidden
 */

import React from 'react';
import { Tag, Tooltip } from 'antd';

const BUCKET_DISPLAY: Record<string, { label: string; color: string }> = {
  response_urgency:   { label: 'Response Urgency',    color: 'red' },
  deal_at_risk:       { label: 'Deal at Risk',        color: 'orange' },
  retention_risk:     { label: 'Retention Risk',      color: 'red' },
  revenue_opportunity:{ label: 'Revenue Opportunity',  color: 'green' },
  new_relationship:   { label: 'New Relationship',    color: 'blue' },
  account_neglect:    { label: 'Account Neglect',     color: 'gold' },
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
  // Confidence gating: hide below 0.5
  if (confidence < 0.5) return null;

  const display = BUCKET_DISPLAY[bucket] || { label: bucket, color: 'default' };
  const isReview = confidence < 0.8;

  const tag = (
    <Tag
      color={isReview ? 'default' : display.color}
      style={isReview ? { opacity: 0.7, borderStyle: 'dashed' } : undefined}
    >
      {isReview ? `${display.label} (Review)` : display.label}
    </Tag>
  );

  if (justification) {
    return (
      <Tooltip title={`${justification} (${Math.round(confidence * 100)}%)`}>
        {tag}
      </Tooltip>
    );
  }

  return tag;
};

export default ActionBucketTag;
