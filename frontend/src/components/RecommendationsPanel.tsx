import React, { useState, useEffect } from 'react';
import { Typography, Alert, Tag, List, Button, Skeleton, Empty, Divider } from 'antd';
import { BulbOutlined, TeamOutlined, ReloadOutlined } from '@ant-design/icons';
import { companiesApi } from '../services/analyticsService';

const { Text } = Typography;

interface CrossContactRec {
  type: 'cross_contact';
  contact_id: string;
  contact_name: string;
  missing_operations: string[];
  departments: string[];
  reason: string;
}

interface RelatedProductRec {
  type: 'related_product';
  current_operation: string;
  recommended_operation: string;
  confidence: number;
  supporting_count: number;
  message: string;
}

interface Props {
  companyId: string;
}

export const RecommendationsPanel: React.FC<Props> = ({ companyId }) => {
  const [crossContact, setCrossContact] = useState<CrossContactRec[]>([]);
  const [relatedProduct, setRelatedProduct] = useState<RelatedProductRec[]>([]);
  const [loading, setLoading] = useState(true);
  const [computedAt, setComputedAt] = useState<string | undefined>();

  const load = async (force = false) => {
    setLoading(true);
    const data = await companiesApi.getRecommendations(companyId, force);
    setCrossContact(data.cross_contact_recs || []);
    setRelatedProduct(data.related_product_recs || []);
    setComputedAt(data.computed_at);
    setLoading(false);
  };

  useEffect(() => { load(); }, [companyId]);

  if (loading) return <Skeleton active paragraph={{ rows: 3 }} />;

  const hasAny = crossContact.length > 0 || relatedProduct.length > 0;

  if (!hasAny) {
    return (
      <Empty
        description={
          <span>
            No recommendations yet.{' '}
            <Text type="secondary" style={{ fontSize: 12 }}>
              Requires QB operations sync and ≥ 2 contacts.
            </Text>
          </span>
        }
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        {computedAt && (
          <Text type="secondary" style={{ fontSize: 11 }}>
            Computed {new Date(computedAt).toLocaleString()}
          </Text>
        )}
        <Button
          size="small"
          icon={<ReloadOutlined />}
          onClick={() => load(true)}
          style={{ marginLeft: 'auto' }}
        >
          Refresh
        </Button>
      </div>

      {crossContact.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
            <TeamOutlined style={{ color: '#667eea' }} />
            <Text strong style={{ fontSize: 13 }}>Cross-Contact Gaps</Text>
            <Tag color="purple" style={{ fontSize: 11 }}>{crossContact.length}</Tag>
          </div>
          <List
            size="small"
            dataSource={crossContact}
            renderItem={(rec) => (
              <List.Item style={{ padding: '8px 0', flexDirection: 'column', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <Text strong style={{ fontSize: 13 }}>{rec.contact_name}</Text>
                  {rec.departments.map(d => (
                    <Tag key={d} color="blue" style={{ fontSize: 11, margin: 0 }}>{d}</Tag>
                  ))}
                </div>
                <Text type="secondary" style={{ fontSize: 12 }}>{rec.reason}</Text>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                  {rec.missing_operations.map(op => (
                    <Tag key={op} color="orange" style={{ fontSize: 11, margin: 0 }}>{op}</Tag>
                  ))}
                </div>
              </List.Item>
            )}
          />
        </div>
      )}

      {crossContact.length > 0 && relatedProduct.length > 0 && <Divider style={{ margin: '12px 0' }} />}

      {relatedProduct.length > 0 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
            <BulbOutlined style={{ color: '#fa8c16' }} />
            <Text strong style={{ fontSize: 13 }}>Product Opportunities</Text>
            <Tag color="orange" style={{ fontSize: 11 }}>{relatedProduct.length}</Tag>
          </div>
          <List
            size="small"
            dataSource={relatedProduct}
            renderItem={(rec) => (
              <List.Item style={{ padding: '6px 0' }}>
                <Alert
                  type="info"
                  style={{ width: '100%', padding: '6px 10px' }}
                  message={
                    <div>
                      <Text style={{ fontSize: 12 }}>{rec.message}</Text>
                      <div style={{ marginTop: 4 }}>
                        <Tag color="green" style={{ fontSize: 11 }}>Try: {rec.recommended_operation}</Tag>
                        <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
                          {Math.round(rec.confidence * 100)}% confidence · {rec.supporting_count} customers
                        </Text>
                      </div>
                    </div>
                  }
                  showIcon={false}
                />
              </List.Item>
            )}
          />
        </div>
      )}
    </div>
  );
};
