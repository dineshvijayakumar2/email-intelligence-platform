import React from 'react';
import { Typography, Tag, Empty, Skeleton } from 'antd';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { formatCurrency } from '../utils/numberFormat';

const { Text } = Typography;

interface Category {
  category: string;
  revenue: number;
}

interface Operation {
  operation: string;
  department?: string;
}

interface Props {
  categories: Category[];
  operations: Operation[];
  loading?: boolean;
}

const COLORS = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#43e97b', '#fa709a', '#fee140'];

const formatTooltipValue = (value: number) => formatCurrency(value);

export const ProductProfileCard: React.FC<Props> = ({ categories, operations, loading }) => {
  if (loading) return <Skeleton active paragraph={{ rows: 4 }} />;

  const hasCategories = categories.length > 0;
  const hasOperations = operations.length > 0;

  if (!hasCategories && !hasOperations) {
    return <Empty description="No product data — QB sync needed" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  // Group operations by department for display
  const deptMap: Record<string, string[]> = {};
  operations.forEach(op => {
    const dept = op.department || 'Other';
    if (!deptMap[dept]) deptMap[dept] = [];
    deptMap[dept].push(op.operation);
  });

  return (
    <div>
      {hasCategories && (
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
            Revenue by Category
          </Text>
          <ResponsiveContainer width="100%" height={Math.min(categories.length * 36 + 20, 220)}>
            <BarChart
              data={categories}
              layout="vertical"
              margin={{ top: 0, right: 60, left: 0, bottom: 0 }}
            >
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="category"
                width={140}
                tick={{ fontSize: 12 }}
              />
              <Tooltip
                formatter={formatTooltipValue}
                contentStyle={{ fontSize: 12, borderRadius: 6 }}
              />
              <Bar dataKey="revenue" radius={[0, 4, 4, 0]}>
                {categories.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {hasOperations && (
        <div>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
            Operations Used ({operations.length})
          </Text>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {Object.entries(deptMap).map(([dept, ops]) =>
              ops.map(op => (
                <Tag key={`${dept}-${op}`} color="geekblue" style={{ fontSize: 11, margin: 0 }}>
                  {op}
                </Tag>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
