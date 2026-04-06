import React from 'react';
import { Typography, Tag, Empty, Skeleton, Space, Row, Col, Table } from 'antd';
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

  // Group operations by department for a count table
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
    <Row gutter={[12, 12]}>
      {/* Revenue by Category */}
      {hasCategories && (
        <Col xs={24} md={hasCapabilities ? 12 : 24}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>Revenue by Category</Text>
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
        </Col>
      )}

      {/* Capabilities with operation counts */}
      {hasCapabilities && (
        <Col xs={24} md={hasCategories ? 12 : 24}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
            Capabilities ({capability_breakdown!.reduce((s, c) => s + c.operation_count, 0)} operations)
          </Text>
          <Table
            dataSource={capability_breakdown}
            rowKey="capability"
            size="small"
            pagination={false}
            showHeader={false}
            columns={[
              { dataIndex: 'capability', render: (v: string) => <Tag color="blue" style={{ fontSize: 11, margin: 0 }}>{v}</Tag> },
              { dataIndex: 'operation_count', align: 'right' as const, width: 60,
                render: (v: number) => <Text type="secondary" style={{ fontSize: 12 }}>{v}</Text> },
            ]}
          />
        </Col>
      )}

      {/* Operations by Department */}
      {deptCounts.length > 0 && (
        <Col xs={24} md={8}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
            Operations by Department ({operations.length})
          </Text>
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
        </Col>
      )}

      {/* Processes */}
      {hasProcesses && (
        <Col xs={24} md={8}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
            Processes ({process_tags!.length})
          </Text>
          <Space size={[4, 4]} wrap>
            {process_tags!.map(t => <Tag key={t} color="cyan" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
          </Space>
        </Col>
      )}

      {/* Embellishments */}
      {hasEmbellishments && (
        <Col xs={24} md={8}>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
            Embellishments ({embellishment_tags!.length})
          </Text>
          <Space size={[4, 4]} wrap>
            {embellishment_tags!.map(t => <Tag key={t} color="purple" style={{ fontSize: 11, margin: 0 }}>{t}</Tag>)}
          </Space>
        </Col>
      )}
    </Row>
  );
};
