import React, { useState, useEffect } from 'react';
import { Typography, Tag, Button, Skeleton, Empty, Space } from 'antd';
import { TeamOutlined, BulbOutlined, ReloadOutlined, DownOutlined, RightOutlined } from '@ant-design/icons';
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

interface Props { companyId: string; }

export const RecommendationsPanel: React.FC<Props> = ({ companyId }) => {
  const [crossContact, setCrossContact] = useState<CrossContactRec[]>([]);
  const [relatedProduct, setRelatedProduct] = useState<RelatedProductRec[]>([]);
  const [loading, setLoading] = useState(true);
  const [computedAt, setComputedAt] = useState<string | undefined>();
  const [expanded, setExpanded] = useState(false);
  const [expandedContact, setExpandedContact] = useState<string | null>(null);

  const load = async (force = false) => {
    setLoading(true);
    try {
      const data = await companiesApi.getRecommendations(companyId, force);
      setCrossContact(data?.cross_contact_recs || []);
      setRelatedProduct(data?.related_product_recs || []);
      setComputedAt(data?.computed_at);
    } catch { /* handled */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, [companyId]);

  if (loading) return <Skeleton active paragraph={{ rows: 2 }} />;

  const hasAny = crossContact.length > 0 || relatedProduct.length > 0;

  if (!hasAny) {
    return <Empty description="No recommendations yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  // Total missing operations across all contacts
  const totalOps = crossContact.reduce((sum, r) => sum + r.missing_operations.length, 0);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        {computedAt && <Text type="secondary" style={{ fontSize: 11 }}>Computed {new Date(computedAt).toLocaleString()}</Text>}
        <Button size="small" icon={<ReloadOutlined />} onClick={() => load(true)} style={{ marginLeft: 'auto' }}>Refresh</Button>
      </div>

      {/* Collapsed: one-line summary */}
      {!expanded && (
        <div>
          {crossContact.length > 0 && (
            <div style={{ marginBottom: 6 }}>
              <Space size={6} wrap>
                <TeamOutlined style={{ color: '#667eea' }} />
                <Text style={{ fontSize: 12 }}>
                  <Text strong>{crossContact.length}</Text> contact{crossContact.length !== 1 ? 's' : ''} with gaps
                  ({totalOps} operations)
                </Text>
              </Space>
            </div>
          )}
          {relatedProduct.length > 0 && (
            <div>
              <Space size={6} wrap>
                <BulbOutlined style={{ color: '#fa8c16' }} />
                <Text style={{ fontSize: 12 }}>
                  <Text strong>{relatedProduct.length}</Text> product opportunit{relatedProduct.length !== 1 ? 'ies' : 'y'}
                </Text>
                {relatedProduct.slice(0, 2).map((r, i) => (
                  <Tag key={i} color="green" style={{ fontSize: 10, margin: 0 }}>{r.recommended_operation}</Tag>
                ))}
                {relatedProduct.length > 2 && <Text type="secondary" style={{ fontSize: 10 }}>+{relatedProduct.length - 2}</Text>}
              </Space>
            </div>
          )}
        </div>
      )}

      {/* Expanded: full detail */}
      {expanded && (
        <div>
          {/* Cross-Contact Gaps */}
          {crossContact.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <TeamOutlined style={{ color: '#667eea' }} />
                <Text strong style={{ fontSize: 13 }}>Cross-Contact Gaps</Text>
                <Tag color="purple" style={{ fontSize: 11 }}>{crossContact.length}</Tag>
              </div>
              {crossContact.map(rec => {
                const id = rec.contact_id || rec.contact_name;
                const isOpen = expandedContact === id;
                return (
                  <div key={id} style={{
                    padding: '6px 8px', marginBottom: 4, borderRadius: 4,
                    background: 'rgba(102,126,234,0.04)', border: '1px solid rgba(102,126,234,0.08)',
                  }}>
                    <div
                      style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                      onClick={() => setExpandedContact(isOpen ? null : id)}
                    >
                      {isOpen ? <DownOutlined style={{ fontSize: 9 }} /> : <RightOutlined style={{ fontSize: 9 }} />}
                      <Text strong style={{ fontSize: 12 }}>{rec.contact_name}</Text>
                      <Space size={3}>
                        {rec.departments.slice(0, 3).map(d => (
                          <Tag key={d} color="blue" style={{ fontSize: 10, margin: 0, padding: '0 3px' }}>{d}</Tag>
                        ))}
                      </Space>
                      <Text type="secondary" style={{ fontSize: 11, marginLeft: 'auto' }}>
                        {rec.missing_operations.length} ops
                      </Text>
                    </div>
                    {isOpen && (
                      <div style={{ marginTop: 4, paddingLeft: 16 }}>
                        <Space size={[3, 3]} wrap>
                          {rec.missing_operations.map(op => (
                            <Tag key={op} color="orange" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>{op}</Tag>
                          ))}
                        </Space>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Product Opportunities */}
          {relatedProduct.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <BulbOutlined style={{ color: '#fa8c16' }} />
                <Text strong style={{ fontSize: 13 }}>Product Opportunities</Text>
                <Tag color="orange" style={{ fontSize: 11 }}>{relatedProduct.length}</Tag>
              </div>
              {relatedProduct.map((rec, i) => (
                <div key={i} style={{ padding: '4px 8px', marginBottom: 3, borderRadius: 4, background: 'rgba(82,196,26,0.04)' }}>
                  <Text style={{ fontSize: 12 }}>{rec.message}</Text>
                  <div style={{ marginTop: 2 }}>
                    <Tag color="green" style={{ fontSize: 10, margin: 0 }}>Try: {rec.recommended_operation}</Tag>
                    <Text type="secondary" style={{ fontSize: 10, marginLeft: 4 }}>
                      {Math.round(rec.confidence * 100)}% · {rec.supporting_count} customers
                    </Text>
                  </div>
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
        style={{ padding: 0, marginTop: 6, fontSize: 12 }}
      >
        {expanded ? 'Show less' : 'Show details'}
      </Button>
    </div>
  );
};
