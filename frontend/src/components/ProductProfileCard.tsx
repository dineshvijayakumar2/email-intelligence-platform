import React from 'react';
import { Typography, Tag, Empty, Skeleton, Space, Row, Col } from 'antd';
import { formatCurrency } from '../utils/numberFormat';

const { Text } = Typography;

interface Category { category: string; revenue: number; }
interface Operation { operation: string; department?: string; }
interface CapabilityBreakdown { capability: string; operation_count: number; }

interface Props {
  categories: Category[];
  operations: Operation[];
  capability_breakdown?: CapabilityBreakdown[];
  process_tags?: string[];
  embellishment_tags?: string[];
  loading?: boolean;
}

export const ProductProfileCard: React.FC<Props> = ({
  categories, operations, capability_breakdown, process_tags, embellishment_tags, loading,
}) => {
  if (loading) return <Skeleton active paragraph={{ rows: 3 }} />;

  const hasCategories = categories.length > 0;
  const hasCapabilities = (capability_breakdown || []).length > 0;
  const hasProcesses = (process_tags || []).length > 0;
  const hasEmbellishments = (embellishment_tags || []).length > 0;
  const hasOperations = operations.length > 0;
  const hasAny = hasCategories || hasCapabilities || hasProcesses || hasEmbellishments || hasOperations;

  if (!hasAny) {
    return <Empty description="No product data — QB sync needed" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  // Max revenue for bar width calculation
  const maxRevenue = hasCategories ? Math.max(...categories.map(c => c.revenue)) : 0;

  return (
    <div>
      {/* Revenue by Category — inline bar */}
      {hasCategories && (
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 6 }}>Revenue by Category</Text>
          {categories.map(c => (
            <div key={c.category} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
              <Text style={{ fontSize: 12, width: 160, flexShrink: 0 }} ellipsis>{c.category}</Text>
              <div style={{ flex: 1, height: 14, background: 'rgba(102,126,234,0.08)', borderRadius: 3 }}>
                <div style={{
                  width: `${maxRevenue > 0 ? (c.revenue / maxRevenue) * 100 : 0}%`,
                  height: '100%', borderRadius: 3,
                  background: 'linear-gradient(90deg, #667eea, #764ba2)',
                  minWidth: 2,
                }} />
              </div>
              <Text strong style={{ fontSize: 11, flexShrink: 0, width: 70, textAlign: 'right' }}>
                {formatCurrency(c.revenue)}
              </Text>
            </div>
          ))}
        </div>
      )}

      {/* Capability breakdown — always show all */}
      {hasCapabilities && (
        <div style={{ marginBottom: 8 }}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
            Capabilities ({capability_breakdown!.reduce((s, c) => s + c.operation_count, 0)} operations)
          </Text>
          <Space size={[4, 4]} wrap>
            {capability_breakdown!.map(c => (
              <Tag key={c.capability} color="blue" style={{ fontSize: 11, margin: 0 }}>
                {c.capability} ({c.operation_count})
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {/* Processes — always show all */}
      {hasProcesses && (
        <div style={{ marginBottom: 8 }}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Processes</Text>
          <Space size={[4, 4]} wrap>
            {process_tags!.map(t => <Tag key={t} color="cyan" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
          </Space>
        </div>
      )}

      {/* Embellishments — always show all */}
      {hasEmbellishments && (
        <div style={{ marginBottom: 8 }}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Embellishments</Text>
          <Space size={[4, 4]} wrap>
            {embellishment_tags!.map(t => <Tag key={t} color="purple" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
          </Space>
        </div>
      )}
    </div>
  );
};
