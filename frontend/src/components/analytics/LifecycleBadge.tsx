import { Tag } from 'antd';
import { LIFECYCLE_CONFIG } from '../../types/strategic-digest';
import type { LifecycleTier } from '../../types/strategic-digest';

interface LifecycleBadgeProps {
  tier?: string | null;
}

export const LifecycleBadge: React.FC<LifecycleBadgeProps> = ({ tier }) => {
  if (!tier) return null;
  const cfg = LIFECYCLE_CONFIG[tier as LifecycleTier];
  if (!cfg) return <Tag>{tier.replace(/_/g, ' ')}</Tag>;
  return <Tag color={cfg.color}>{cfg.label}</Tag>;
};

export default LifecycleBadge;
