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
}

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  prefix,
  suffix,
  precision,
  loading = false,
  valueStyle,
}) => {
  if (loading) {
    return (
      <div className="glass-card" style={{ padding: 20, textAlign: 'center' }}>
        <Skeleton active paragraph={{ rows: 1 }} />
      </div>
    );
  }

  return (
    <div className="glass-card" style={{ padding: 20, textAlign: 'center' }}>
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
