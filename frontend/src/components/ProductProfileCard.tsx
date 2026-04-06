import React from 'react';
import { Typography, Tag, Empty, Skeleton, Space, Col, Card, Table } from 'antd';
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

/**
 * Renders multiple separate Col cards for the company detail grid.
 * Each widget is its own card — no single container.
 * Must be used inside a <Row> parent.
 */
export const ProductProfileCards: React.FC<Props> = ({
  categories, operations, capability_breakdown, process_tags, embellishment_tags, loading,
}) => {
  if (loading) return <Col xs={24} lg={12}><Card className="glass-card" size="small"><Skeleton active paragraph={{ rows: 3 }} /></Card></Col>;

  const hasCategories = categories.length > 0;
  const hasCapabilities = (capability_breakdown || []).length > 0;
  const hasProcesses = (process_tags || []).length > 0;
  const hasEmbellishments = (embellishment_tags || []).length > 0;
  const hasOperations = operations.length > 0;

  if (!hasCategories && !hasCapabilities && !hasProcesses && !hasEmbellishments && !hasOperations) {
    return null;
  }

  // Group operations by department
  const deptCounts: { department: string; count: number }[] = [];
  const deptMap: Record<string, number> = {};
  operations.forEach(op => {
    const dept = op.department || 'Other';
    deptMap[dept] = (deptMap[dept] || 0) + 1;
  });
  Object.entries(deptMap).sort((a, b) => b[1] - a[1]).forEach(([dept, count]) => {
    deptCounts.push({ department: dept, count });
  });

  return (
    <>
      {/* Revenue by Category */}
      {hasCategories && (
        <Col xs={24} lg={12}>
          <Card className="glass-card" size="small"
            title={<Text strong style={{ fontSize: 13 }}>Revenue by Category</Text>}
            bodyStyle={{ padding: 0 }}
          >
            <Table
              dataSource={categories}
              rowKey="category"
              size="small"
              pagination={false}
              showHeader={false}
              columns={[
                { dataIndex: 'category', render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text> },
                { dataIndex: 'revenue', align: 'right' as const, width: 100,
                  render: (v: number) => <Text strong style={{ fontSize: 12 }}>{formatCurrency(v)}</Text> },
              ]}
            />
          </Card>
        </Col>
      )}

      {/* Capabilities */}
      {hasCapabilities && (
        <Col xs={24} lg={12}>
          <Card className="glass-card" size="small"
            title={<Text strong style={{ fontSize: 13 }}>Capabilities <Text type="secondary" style={{ fontSize: 11, fontWeight: 400 }}>({capability_breakdown!.reduce((s, c) => s + c.operation_count, 0)} ops)</Text></Text>}
            bodyStyle={{ padding: 0 }}
          >
            <Table
              dataSource={capability_breakdown}
              rowKey="capability"
              size="small"
              pagination={false}
              showHeader={false}
              columns={[
                { dataIndex: 'capability', render: (v: string) => <Tag color="blue" style={{ fontSize: 11, margin: 0 }}>{v}</Tag> },
                { dataIndex: 'operation_count', align: 'right' as const, width: 50,
                  render: (v: number) => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text> },
              ]}
            />
          </Card>
        </Col>
      )}

      {/* Operations by Department */}
      {deptCounts.length > 0 && (
        <Col xs={24} lg={12}>
          <Card className="glass-card" size="small"
            title={<Text strong style={{ fontSize: 13 }}>Operations by Department <Text type="secondary" style={{ fontSize: 11, fontWeight: 400 }}>({operations.length})</Text></Text>}
            bodyStyle={{ padding: 0 }}
          >
            <Table
              dataSource={deptCounts}
              rowKey="department"
              size="small"
              pagination={false}
              showHeader={false}
              columns={[
                { dataIndex: 'department', render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text> },
                { dataIndex: 'count', align: 'right' as const, width: 50,
                  render: (v: number) => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text> },
              ]}
            />
          </Card>
        </Col>
      )}

      {/* Processes + Embellishments combined if both small */}
      {(hasProcesses || hasEmbellishments) && (
        <Col xs={24} lg={12}>
          <Card className="glass-card" size="small"
            title={<Text strong style={{ fontSize: 13 }}>Processes & Embellishments</Text>}
          >
            {hasProcesses && (
              <div style={{ marginBottom: hasEmbellishments ? 8 : 0 }}>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 3 }}>Processes ({process_tags!.length})</Text>
                <Space size={[4, 4]} wrap>
                  {process_tags!.map(t => <Tag key={t} color="cyan" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
                </Space>
              </div>
            )}
            {hasEmbellishments && (
              <div>
                <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 3 }}>Embellishments ({embellishment_tags!.length})</Text>
                <Space size={[4, 4]} wrap>
                  {embellishment_tags!.map(t => <Tag key={t} color="purple" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
                </Space>
              </div>
            )}
          </Card>
        </Col>
      )}
    </>
  );
};

// Keep old export name for backward compat
export const ProductProfileCard = ProductProfileCards;
