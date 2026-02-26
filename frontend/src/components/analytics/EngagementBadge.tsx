import React from 'react';
import { Tag, Progress, Tooltip } from 'antd';
import { getEngagementColor, getEngagementLabel } from '../../services/analyticsService';

interface EngagementBadgeProps {
  score: number | null | undefined;
  showBar?: boolean;
  size?: 'small' | 'default';
}

export const EngagementBadge: React.FC<EngagementBadgeProps> = ({
  score,
  showBar = false,
  size = 'default',
}) => {
  if (score == null) {
    return <Tag>N/A</Tag>;
  }

  const color = getEngagementColor(score);
  const label = getEngagementLabel(score);
  const rounded = Math.round(score);

  if (showBar) {
    return (
      <Tooltip title={`${label} engagement (${rounded}/100)`}>
        <Progress
          percent={rounded}
          size="small"
          strokeColor={color}
          format={() => `${label} ${rounded}`}
          style={{ width: size === 'small' ? 110 : 130 }}
        />
      </Tooltip>
    );
  }

  return (
    <Tag color={color} style={{ fontWeight: 600 }}>
      {label} {rounded}
    </Tag>
  );
};
