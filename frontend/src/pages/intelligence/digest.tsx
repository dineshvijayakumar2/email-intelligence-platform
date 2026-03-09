/**
 * Daily Digest Page — Sprint 3 Session 7
 *
 * Shows AI-generated daily intelligence digest with bucket summary,
 * action items, and highlights.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Card, Row, Col, Typography, Select, DatePicker, Spin, Empty,
  Tag, List, Space, Alert, Button,
} from 'antd';
import {
  CalendarOutlined, BulbOutlined, ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { digestApi, bucketApi } from '../../services/aiService';
import { MailboxSelector } from '../../components/MailboxSelector';
import type { DailyDigest, BucketSummary } from '../../types/ai';

const { Title, Text, Paragraph } = Typography;

const BUCKET_COLORS: Record<string, string> = {
  buying_signal: 'green', expansion_signal: 'blue', churn_risk: 'red',
  competitor_threat: 'red', missed_opportunity: 'orange', stakeholder_entry: 'purple',
  silent_champion: 'gold', unresolved_block: 'yellow',
};

const BUCKET_LABELS: Record<string, string> = {
  buying_signal: 'Buying Signal', expansion_signal: 'Expansion', churn_risk: 'Churn Risk',
  competitor_threat: 'Competitor', missed_opportunity: 'Missed Opp', stakeholder_entry: 'Stakeholder',
  silent_champion: 'Silent Champ', unresolved_block: 'Unresolved',
};

const DigestPage: React.FC = () => {
  const isMountedRef = useRef(true);
  const [loading, setLoading] = useState(false);
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';
  const [selectedDate, setSelectedDate] = useState<string>(dayjs().format('YYYY-MM-DD'));
  const [digestType, setDigestType] = useState<'daily' | 'weekly'>('daily');
  const [digest, setDigest] = useState<DailyDigest | null>(null);
  const [bucketSummary, setBucketSummary] = useState<BucketSummary | null>(null);
  const [error, setError] = useState<string>('');

  const loadDigest = useCallback(async (force = false) => {
    if (!mailboxId) return;
    setLoading(true);
    setError('');
    try {
      const [digestData, summaryData] = await Promise.all([
        digestApi.get(mailboxId, selectedDate, undefined, force, digestType),
        bucketApi.getSummary(mailboxId),
      ]);
      if (!isMountedRef.current) return;
      setDigest(digestData);
      setBucketSummary(summaryData);
      if (!digestData) setError('No digest available. Try analyzing emails first.');
    } catch (err: any) {
      if (isMountedRef.current) setError(err?.message || 'Failed to load digest');
    } finally {
      if (isMountedRef.current) setLoading(false);
    }
  }, [mailboxId, selectedDate, digestType]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => { isMountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (mailboxId) loadDigest();
  }, [mailboxId, selectedDate, digestType, loadDigest]);

  return (
    <div style={{ padding: '24px', maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>
          {digestType === 'weekly' ? 'Weekly' : 'Daily'} Intelligence Digest
        </Title>
        <Space>
          <MailboxSelector value={mailboxIds} onChange={setMailboxIds} mode="single" />
          <Select
            value={digestType}
            onChange={setDigestType}
            style={{ width: 110 }}
            options={[
              { value: 'daily', label: 'Daily' },
              { value: 'weekly', label: 'Weekly' },
            ]}
          />
          <DatePicker
            value={dayjs(selectedDate)}
            onChange={(d) => d && setSelectedDate(d.format('YYYY-MM-DD'))}
            allowClear={false}
          />
          <Button icon={<ReloadOutlined />} onClick={() => loadDigest(true)} loading={loading}>
            Regenerate
          </Button>
        </Space>
      </div>

      {!mailboxId && (
        <Card className="glass-card">
          <Empty description="Select a mailbox to view the daily digest" />
        </Card>
      )}

      {error && <Alert message={error} type="warning" showIcon style={{ marginBottom: 16 }} />}

      {loading && (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}><Text type="secondary">Generating digest...</Text></div>
        </div>
      )}

      {!loading && mailboxId && digest && (
        <>
          {/* Bucket Summary Bar */}
          {bucketSummary && (
            <Card className="glass-card" size="small" style={{ marginBottom: 16 }}>
              <Space wrap>
                {Object.entries(BUCKET_LABELS).map(([key, label]) => {
                  const count = (bucketSummary as any)[key] || 0;
                  if (count === 0) return null;
                  return (
                    <Tag key={key} color={BUCKET_COLORS[key]} style={{ fontSize: 13, padding: '4px 10px' }}>
                      {label}: {count}
                    </Tag>
                  );
                })}
                <Tag style={{ fontSize: 13, padding: '4px 10px' }}>
                  Total: {bucketSummary.total || 0}
                </Tag>
              </Space>
            </Card>
          )}

          {/* Digest Summary */}
          <Card
            className="glass-card"
            style={{ marginBottom: 16 }}
            title={
              <Space>
                <BulbOutlined style={{ color: '#667eea' }} />
                <span>Executive Summary</span>
                <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
                  {selectedDate} | {digest.emails_analyzed || 0} emails analyzed
                </Text>
              </Space>
            }
          >
            <Paragraph style={{ fontSize: 15, lineHeight: 1.8, marginBottom: 0 }}>
              {digest.summary || 'No summary available.'}
            </Paragraph>
          </Card>

          <Row gutter={[16, 16]}>
            {/* Action Items */}
            <Col xs={24} lg={14}>
              <Card className="glass-card" title="Action Items">
                {digest.action_items && digest.action_items.length > 0 ? (
                  <List
                    dataSource={digest.action_items}
                    renderItem={(item: any) => (
                      <List.Item>
                        <Space direction="vertical" style={{ width: '100%' }} size={2}>
                          <Space>
                            <Tag color={item.priority <= 2 ? 'red' : item.priority <= 3 ? 'orange' : 'blue'}>
                              P{item.priority}
                            </Tag>
                            {item.bucket && (
                              <Tag color={BUCKET_COLORS[item.bucket] || 'default'}>
                                {BUCKET_LABELS[item.bucket] || item.bucket}
                              </Tag>
                            )}
                            {item.contact_name && <Text type="secondary">{item.contact_name}</Text>}
                          </Space>
                          <Text>{item.action}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description="No action items" />
                )}
              </Card>
            </Col>

            {/* Highlights */}
            <Col xs={24} lg={10}>
              <Card className="glass-card" title="Highlights">
                {digest.highlights && digest.highlights.length > 0 ? (
                  <List
                    dataSource={digest.highlights}
                    renderItem={(item: any) => (
                      <List.Item>
                        <Space direction="vertical" size={2}>
                          <Tag color="geekblue">{item.label || item.type || 'Info'}</Tag>
                          <Text>{item.detail || item.description}</Text>
                        </Space>
                      </List.Item>
                    )}
                  />
                ) : (
                  <Empty description="No highlights" />
                )}
              </Card>
            </Col>
          </Row>

          {/* Stats Row */}
          {digest.stats && Object.keys(digest.stats).length > 0 && (
            <Card className="glass-card" size="small" style={{ marginTop: 16 }}>
              <Space wrap size="large">
                {Object.entries(digest.stats).map(([key, value]) => (
                  <div key={key} style={{ textAlign: 'center' }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>{key.replace(/_/g, ' ')}</Text>
                    <div><Text strong>{String(value)}</Text></div>
                  </div>
                ))}
              </Space>
            </Card>
          )}
        </>
      )}
    </div>
  );
};

export default DigestPage;
