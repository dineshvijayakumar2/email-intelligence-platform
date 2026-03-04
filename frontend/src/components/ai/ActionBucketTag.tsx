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
  buying_signal:      { label: 'Buying Signal',      color: 'green' },
  expansion_signal:   { label: 'Expansion Signal',   color: 'blue' },
  churn_risk:         { label: 'Churn Risk',         color: 'red' },
  competitor_threat:  { label: 'Competitor Threat',   color: 'volcano' },
  missed_opportunity: { label: 'Missed Opportunity',  color: 'magenta' },
  stakeholder_entry:  { label: 'Stakeholder Entry',   color: 'purple' },
  silent_champion:    { label: 'Silent Champion',     color: 'orange' },
  unresolved_block:   { label: 'Unresolved Block',    color: 'gold' },
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
