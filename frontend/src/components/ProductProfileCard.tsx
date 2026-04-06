import React, { useState } from 'react';
import { Typography, Tag, Empty, Skeleton, Space } from 'antd';
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

interface CapabilityBreakdown {
  capability: string;
  operation_count: number;
}

interface Props {
  categories: Category[];
  operations: Operation[];
  capability_breakdown?: CapabilityBreakdown[];
  process_tags?: string[];
  embellishment_tags?: string[];
  loading?: boolean;
}

const COLORS = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#43e97b', '#fa709a', '#fee140'];
const MAX_OPS_COLLAPSED = 10;

const formatTooltipValue = (value: number) => formatCurrency(value);

export const ProductProfileCard: React.FC<Props> = ({
  categories, operations, capability_breakdown, process_tags, embellishment_tags, loading,
}) => {
  const [showAllOps, setShowAllOps] = useState(false);

  if (loading) return <Skeleton active paragraph={{ rows: 4 }} />;

  const hasCategories = categories.length > 0;
  const hasOperations = operations.length > 0;
  const hasCapabilities = (capability_breakdown || []).length > 0;
  const hasProcesses = (process_tags || []).length > 0;
  const hasEmbellishments = (embellishment_tags || []).length > 0;
  const hasAny = hasCategories || hasOperations || hasCapabilities || hasProcesses || hasEmbellishments;

  if (!hasAny) {
    return <Empty description="No product data — QB sync needed" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  // Group operations by department
  const deptMap: Record<string, string[]> = {};
  operations.forEach(op => {
    const dept = op.department || 'Other';
    if (!deptMap[dept]) deptMap[dept] = [];
    deptMap[dept].push(op.operation);
  });

  return (
    <div>
      {/* Revenue by Category */}
      {hasCategories && (
        <div style={{ marginBottom: 14 }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>Revenue by Category</Text>
          <ResponsiveContainer width="100%" height={Math.min(categories.length * 36 + 20, 220)}>
            <BarChart data={categories} layout="vertical" margin={{ top: 0, right: 60, left: 0, bottom: 0 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="category" width={140} tick={{ fontSize: 12 }} />
              <Tooltip formatter={formatTooltipValue} contentStyle={{ fontSize: 12, borderRadius: 6 }} />
              <Bar dataKey="revenue" radius={[0, 4, 4, 0]}>
                {categories.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Capabilities breakdown */}
      {hasCapabilities && (
        <div style={{ marginBottom: 10 }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Capabilities</Text>
          <Space size={[4, 4]} wrap>
            {capability_breakdown!.map(c => (
              <Tag key={c.capability} color="blue" style={{ fontSize: 11, margin: 0 }}>
                {c.capability} ({c.operation_count})
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {/* Process tags */}
      {hasProcesses && (
        <div style={{ marginBottom: 10 }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Processes</Text>
          <Space size={[4, 4]} wrap>
            {process_tags!.map(t => <Tag key={t} color="cyan" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
          </Space>
        </div>
      )}

      {/* Embellishment tags */}
      {hasEmbellishments && (
        <div style={{ marginBottom: 10 }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>Embellishments</Text>
          <Space size={[4, 4]} wrap>
            {embellishment_tags!.map(t => <Tag key={t} color="purple" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
          </Space>
        </div>
      )}

      {/* Operations by department — collapsible */}
      {hasOperations && (
        <div>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
            Operations ({operations.length})
          </Text>
          {Object.entries(deptMap).map(([dept, ops]) => {
            const visibleOps = showAllOps ? ops : ops.slice(0, MAX_OPS_COLLAPSED);
            return (
              <div key={dept} style={{ marginBottom: 6 }}>
                <Text style={{ fontSize: 11, fontWeight: 500 }}>{dept}: </Text>
                <Space size={[3, 3]} wrap style={{ display: 'inline-flex' }}>
                  {visibleOps.map(op => (
                    <Tag key={op} color="geekblue" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>{op}</Tag>
                  ))}
                  {!showAllOps && ops.length > MAX_OPS_COLLAPSED && (
                    <Tag
                      style={{ fontSize: 10, margin: 0, cursor: 'pointer', background: 'rgba(24,144,255,0.08)', border: '1px dashed #4facfe', color: '#4facfe' }}
                      onClick={() => setShowAllOps(true)}
                    >
                      +{ops.length - MAX_OPS_COLLAPSED} more
                    </Tag>
                  )}
                </Space>
              </div>
            );
          })}
          {showAllOps && operations.length > MAX_OPS_COLLAPSED && (
            <Text type="secondary" style={{ fontSize: 11, cursor: 'pointer', color: '#667eea' }} onClick={() => setShowAllOps(false)}>
              Show less
            </Text>
          )}
        </div>
      )}
    </div>
  );
};
