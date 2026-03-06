import React from 'react';
import { Statistic, Skeleton } from 'antd';

interface MetricCardProps {
  title: string;
  value: number | string | null | undefined;
  prefix?: React.ReactNode;
  suffix?: string;
  precision?: number;
  loading?: boolean;
  valueStyle?: React.CSSProperties;
  onClick?: () => void;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  prefix,
  suffix,
  precision,
  loading = false,
  valueStyle,
  onClick,
}) => {
  if (loading) {
    return (
      <div className="glass-card" style={{ padding: 20, textAlign: 'center' }}>
        <Skeleton active paragraph={{ rows: 1 }} />
      </div>
    );
  }

  return (
    <div
      className="glass-card"
      style={{ padding: 20, textAlign: 'center', ...(onClick ? { cursor: 'pointer' } : {}) }}
      onClick={onClick}
    >
      <Statistic
        title={title}
        value={value ?? 0}
        prefix={prefix}
        suffix={suffix}
        precision={precision}
        valueStyle={{ fontSize: 28, fontWeight: 600, ...valueStyle }}
      />
    </div>
  );
};
