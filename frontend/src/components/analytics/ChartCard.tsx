import React from 'react';
import { Typography, Skeleton } from 'antd';

const { Text } = Typography;

interface ChartCardProps {
  title: string;
  children: React.ReactNode;
  loading?: boolean;
  height?: number;
  extra?: React.ReactNode;
}

export const ChartCard: React.FC<ChartCardProps> = ({
  title,
  children,
  loading = false,
  height = 300,
  extra,
}) => {
  return (
    <div className="glass-card" style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Text strong style={{ fontSize: 16 }}>{title}</Text>
        {extra}
      </div>
      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : (
        <div style={{ height }}>
          {children}
        </div>
      )}
    </div>
  );
};
