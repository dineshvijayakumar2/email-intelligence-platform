import React, { useState } from 'react';
import { Typography, Tag, Empty, Skeleton, Space, Button } from 'antd';
import { DownOutlined, RightOutlined } from '@ant-design/icons';
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

const MAX_COLLAPSED = 6;

export const ProductProfileCard: React.FC<Props> = ({
  categories, operations, capability_breakdown, process_tags, embellishment_tags, loading,
}) => {
  const [expanded, setExpanded] = useState(false);

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

  // Group operations by department
  const deptMap: Record<string, string[]> = {};
  operations.forEach(op => {
    const dept = op.department || 'Other';
    if (!deptMap[dept]) deptMap[dept] = [];
    deptMap[dept].push(op.operation);
  });

  return (
    <div>
      {/* Collapsed: summary line */}
      {!expanded && (
        <div>
          {/* Capabilities as primary summary */}
          {hasCapabilities && (
            <div style={{ marginBottom: 8 }}>
              <Space size={[4, 4]} wrap>
                {capability_breakdown!.slice(0, MAX_COLLAPSED).map(c => (
                  <Tag key={c.capability} color="blue" style={{ fontSize: 11, margin: 0 }}>
                    {c.capability} ({c.operation_count})
                  </Tag>
                ))}
                {capability_breakdown!.length > MAX_COLLAPSED && (
                  <Text type="secondary" style={{ fontSize: 11 }}>+{capability_breakdown!.length - MAX_COLLAPSED} more</Text>
                )}
              </Space>
            </div>
          )}

          {/* Categories as inline stats */}
          {hasCategories && (
            <div style={{ marginBottom: 8 }}>
              <Space size={[6, 4]} wrap>
                {categories.slice(0, 4).map(c => (
                  <span key={c.category} style={{ fontSize: 12 }}>
                    <Text type="secondary">{c.category}:</Text>{' '}
                    <Text strong>{formatCurrency(c.revenue)}</Text>
                  </span>
                ))}
                {categories.length > 4 && (
                  <Text type="secondary" style={{ fontSize: 11 }}>+{categories.length - 4} more</Text>
                )}
              </Space>
            </div>
          )}

          {/* Process + embellishment tags inline */}
          {(hasProcesses || hasEmbellishments) && (
            <Space size={[3, 3]} wrap>
              {(process_tags || []).slice(0, 4).map(t => <Tag key={t} color="cyan" style={{ fontSize: 10, margin: 0 }}>{t}</Tag>)}
              {(embellishment_tags || []).slice(0, 3).map(t => <Tag key={t} color="purple" style={{ fontSize: 10, margin: 0 }}>{t}</Tag>)}
              {((process_tags || []).length + (embellishment_tags || []).length) > 7 && (
                <Text type="secondary" style={{ fontSize: 10 }}>
                  +{(process_tags || []).length + (embellishment_tags || []).length - 7} more
                </Text>
              )}
            </Space>
          )}
        </div>
      )}

      {/* Expanded: full detail */}
      {expanded && (
        <div>
          {/* Categories with revenue */}
          {hasCategories && (
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Revenue by Category</Text>
              {categories.map(c => (
                <div key={c.category} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                  <Text style={{ fontSize: 12 }}>{c.category}</Text>
                  <Text strong style={{ fontSize: 12 }}>{formatCurrency(c.revenue)}</Text>
                </div>
              ))}
            </div>
          )}

          {/* Capabilities */}
          {hasCapabilities && (
            <div style={{ marginBottom: 10 }}>
              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Capabilities</Text>
              <Space size={[4, 4]} wrap>
                {capability_breakdown!.map(c => (
                  <Tag key={c.capability} color="blue" style={{ fontSize: 11, margin: 0 }}>
                    {c.capability} ({c.operation_count})
                  </Tag>
                ))}
              </Space>
            </div>
          )}

          {/* Processes */}
          {hasProcesses && (
            <div style={{ marginBottom: 10 }}>
              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Processes</Text>
              <Space size={[4, 4]} wrap>
                {process_tags!.map(t => <Tag key={t} color="cyan" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
              </Space>
            </div>
          )}

          {/* Embellishments */}
          {hasEmbellishments && (
            <div style={{ marginBottom: 10 }}>
              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Embellishments</Text>
              <Space size={[4, 4]} wrap>
                {embellishment_tags!.map(t => <Tag key={t} color="purple" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
              </Space>
            </div>
          )}

          {/* Operations by department */}
          {hasOperations && (
            <div>
              <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Operations ({operations.length})</Text>
              {Object.entries(deptMap).map(([dept, ops]) => (
                <div key={dept} style={{ marginBottom: 4 }}>
                  <Text style={{ fontSize: 11, fontWeight: 500 }}>{dept}: </Text>
                  <Space size={[3, 3]} wrap style={{ display: 'inline-flex' }}>
                    {ops.map(op => <Tag key={op} color="geekblue" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>{op}</Tag>)}
                  </Space>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Toggle */}
      <Button
        type="link"
        size="small"
        onClick={() => setExpanded(!expanded)}
        icon={expanded ? <DownOutlined /> : <RightOutlined />}
        style={{ padding: 0, marginTop: 8, fontSize: 12 }}
      >
        {expanded ? 'Show less' : 'Show all details'}
      </Button>
    </div>
  );
};
