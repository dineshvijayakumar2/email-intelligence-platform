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

interface Props {
  companyId: string;
}

const MAX_OPS_COLLAPSED = 5;
const MAX_CONTACTS_COLLAPSED = 3;

export const RecommendationsPanel: React.FC<Props> = ({ companyId }) => {
  const [crossContact, setCrossContact] = useState<CrossContactRec[]>([]);
  const [relatedProduct, setRelatedProduct] = useState<RelatedProductRec[]>([]);
  const [loading, setLoading] = useState(true);
  const [computedAt, setComputedAt] = useState<string | undefined>();
  const [expandedContacts, setExpandedContacts] = useState<Set<string>>(new Set());
  const [showAllContacts, setShowAllContacts] = useState(false);

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

  if (loading) return <Skeleton active paragraph={{ rows: 3 }} />;

  const hasAny = crossContact.length > 0 || relatedProduct.length > 0;

  if (!hasAny) {
    return (
      <Empty
        description={<span>No recommendations yet. <Text type="secondary" style={{ fontSize: 12 }}>Requires QB operations sync and 2+ contacts.</Text></span>}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  const toggleContact = (id: string) => {
    setExpandedContacts(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const visibleContacts = showAllContacts ? crossContact : crossContact.slice(0, MAX_CONTACTS_COLLAPSED);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
        {computedAt && (
          <Text type="secondary" style={{ fontSize: 11 }}>
            Computed {new Date(computedAt).toLocaleString()}
          </Text>
        )}
        <Button size="small" icon={<ReloadOutlined />} onClick={() => load(true)} style={{ marginLeft: 'auto' }}>Refresh</Button>
      </div>

      {/* Cross-Contact Gaps — compact view */}
      {crossContact.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <TeamOutlined style={{ color: '#667eea' }} />
            <Text strong style={{ fontSize: 13 }}>Cross-Contact Gaps</Text>
            <Tag color="purple" style={{ fontSize: 11 }}>{crossContact.length}</Tag>
          </div>

          {visibleContacts.map(rec => {
            const isExpanded = expandedContacts.has(rec.contact_id || rec.contact_name);
            const totalOps = rec.missing_operations.length;
            const visibleOps = isExpanded ? rec.missing_operations : rec.missing_operations.slice(0, MAX_OPS_COLLAPSED);

            return (
              <div key={rec.contact_id || rec.contact_name} style={{
                padding: '8px 10px', marginBottom: 6, borderRadius: 6,
                background: 'rgba(102,126,234,0.04)', border: '1px solid rgba(102,126,234,0.1)',
              }}>
                <div
                  style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: totalOps > MAX_OPS_COLLAPSED ? 'pointer' : 'default' }}
                  onClick={() => totalOps > MAX_OPS_COLLAPSED && toggleContact(rec.contact_id || rec.contact_name)}
                >
                  {totalOps > MAX_OPS_COLLAPSED && (
                    isExpanded ? <DownOutlined style={{ fontSize: 10, color: '#667eea' }} /> : <RightOutlined style={{ fontSize: 10, color: '#667eea' }} />
                  )}
                  <Text strong style={{ fontSize: 12 }}>{rec.contact_name}</Text>
                  {rec.departments.map(d => (
                    <Tag key={d} color="blue" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>{d}</Tag>
                  ))}
                  <Text type="secondary" style={{ fontSize: 11, marginLeft: 'auto' }}>
                    {totalOps} operation{totalOps !== 1 ? 's' : ''}
                  </Text>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 6 }}>
                  {visibleOps.map(op => (
                    <Tag key={op} color="orange" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>{op}</Tag>
                  ))}
                  {!isExpanded && totalOps > MAX_OPS_COLLAPSED && (
                    <Tag
                      style={{ fontSize: 10, margin: 0, padding: '0 6px', cursor: 'pointer', background: 'rgba(250,140,22,0.1)', border: '1px dashed #fa8c16', color: '#fa8c16' }}
                      onClick={() => toggleContact(rec.contact_id || rec.contact_name)}
                    >
                      +{totalOps - MAX_OPS_COLLAPSED} more
                    </Tag>
                  )}
                </div>
              </div>
            );
          })}

          {crossContact.length > MAX_CONTACTS_COLLAPSED && (
            <Button
              type="link"
              size="small"
              onClick={() => setShowAllContacts(!showAllContacts)}
              style={{ padding: 0, fontSize: 12 }}
            >
              {showAllContacts ? 'Show less' : `Show all ${crossContact.length} contacts`}
            </Button>
          )}
        </div>
      )}

      {/* Product Opportunities — compact */}
      {relatedProduct.length > 0 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <BulbOutlined style={{ color: '#fa8c16' }} />
            <Text strong style={{ fontSize: 13 }}>Product Opportunities</Text>
            <Tag color="orange" style={{ fontSize: 11 }}>{relatedProduct.length}</Tag>
          </div>
          {relatedProduct.slice(0, 5).map((rec, i) => (
            <div key={i} style={{
              padding: '6px 10px', marginBottom: 4, borderRadius: 6,
              background: 'rgba(82,196,26,0.04)', border: '1px solid rgba(82,196,26,0.1)',
            }}>
              <Text style={{ fontSize: 12 }}>{rec.message}</Text>
              <div style={{ marginTop: 4, display: 'flex', gap: 6, alignItems: 'center' }}>
                <Tag color="green" style={{ fontSize: 10, margin: 0 }}>Try: {rec.recommended_operation}</Tag>
                <Text type="secondary" style={{ fontSize: 10 }}>
                  {Math.round(rec.confidence * 100)}% · {rec.supporting_count} customers
                </Text>
              </div>
            </div>
          ))}
          {relatedProduct.length > 5 && (
            <Text type="secondary" style={{ fontSize: 11 }}>+{relatedProduct.length - 5} more opportunities</Text>
          )}
        </div>
      )}
    </div>
  );
};
