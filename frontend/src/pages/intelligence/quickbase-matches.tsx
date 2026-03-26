/**
 * QB Match Review — Map QB customers to SB companies via searchable selector.
 * Fuzzy candidates are pre-suggested; user can pick any SB company or skip.
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Card, Table, Button, Tag, Space, Typography, Statistic, Row, Col,
  Spin, message, Tabs, Badge, Select,
} from 'antd';
import {
  CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
  ReloadOutlined, QuestionCircleOutlined, ArrowRightOutlined,
} from '@ant-design/icons';
import api from '../../services/apiClient';
import { ClientSelector } from '../../components/analytics/ClientSelector';

const { Title, Text } = Typography;
const PAGE_SIZE = 30;

interface MatchCandidate {
  id: string;
  sb_company_id: string;
  sb_company_name: string;
  qb_record_id: string;
  qb_customer_id: string;
  qb_name: string;
  match_score: number;
  match_method: string;
  reviewed: boolean;
  accepted: boolean | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

interface CompanyOption {
  id: string;
  company_name: string;
}

interface HealthData {
  qb_configured: boolean;
  qb_customers: { total: number; matched: number; unmatched: number; match_rate_pct: number };
  qb_contacts: { total: number; matched: number; unmatched: number; match_rate_pct: number };
  company_enrichment: { total: number; enriched: number; not_enriched: number; coverage_pct: number };
  active_companies: { total: number; with_qb_data: number; coverage_pct: number };
}

export default function QuickbaseMatchesPage() {
  const [clientId, setClientId] = useState<string>('');
  const [health, setHealth] = useState<HealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const [pendingCandidates, setPendingCandidates] = useState<MatchCandidate[]>([]);
  const [pendingTotal, setPendingTotal] = useState(0);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [pendingPage, setPendingPage] = useState(1);

  const [reviewedCandidates, setReviewedCandidates] = useState<MatchCandidate[]>([]);
  const [reviewedTotal, setReviewedTotal] = useState(0);
  const [reviewedLoading, setReviewedLoading] = useState(false);
  const [reviewedPage, setReviewedPage] = useState(1);

  const [rematchLoading, setRematchLoading] = useState(false);

  // Company options for the searchable selector (loaded once per client)
  const [companyOptions, setCompanyOptions] = useState<CompanyOption[]>([]);
  const companyOptionsLoaded = useRef(false);

  // Per-row selection overrides: candidateId → selected sb_company_id
  const [rowSelections, setRowSelections] = useState<Record<string, string>>({});
  const [savingRow, setSavingRow] = useState<string | null>(null);

  // ── Data loading ──────────────────────────────────────────────────────────

  const loadHealth = useCallback(async () => {
    if (!clientId) return;
    setHealthLoading(true);
    try {
      const data = await api.get(`/v1/quickbase/health?client_id=${clientId}`) as HealthData;
      setHealth(data);
    } catch { /* silent */ }
    setHealthLoading(false);
  }, [clientId]);

  const loadPending = useCallback(async () => {
    if (!clientId) return;
    setPendingLoading(true);
    try {
      const offset = (pendingPage - 1) * PAGE_SIZE;
      const data = await api.get(
        `/v1/quickbase/match-candidates?client_id=${clientId}&reviewed=false&limit=${PAGE_SIZE}&offset=${offset}`
      ) as { candidates: MatchCandidate[]; total: number };
      setPendingCandidates(data.candidates || []);
      setPendingTotal(data.total || 0);
    } catch { /* silent */ }
    setPendingLoading(false);
  }, [clientId, pendingPage]);

  const loadReviewed = useCallback(async () => {
    if (!clientId) return;
    setReviewedLoading(true);
    try {
      const offset = (reviewedPage - 1) * PAGE_SIZE;
      const data = await api.get(
        `/v1/quickbase/match-candidates?client_id=${clientId}&reviewed=true&limit=${PAGE_SIZE}&offset=${offset}`
      ) as { candidates: MatchCandidate[]; total: number };
      setReviewedCandidates(data.candidates || []);
      setReviewedTotal(data.total || 0);
    } catch { /* silent */ }
    setReviewedLoading(false);
  }, [clientId, reviewedPage]);

  const loadCompanies = useCallback(async () => {
    if (!clientId || companyOptionsLoaded.current) return;
    try {
      const data = await api.get(
        `/v1/quickbase/companies-lookup?client_id=${clientId}&limit=500`
      ) as { companies: CompanyOption[] };
      setCompanyOptions(data.companies || []);
      companyOptionsLoaded.current = true;
    } catch { /* silent */ }
  }, [clientId]);

  useEffect(() => { loadHealth(); }, [loadHealth]);
  useEffect(() => { loadPending(); }, [loadPending]);
  useEffect(() => { loadReviewed(); }, [loadReviewed]);
  useEffect(() => {
    companyOptionsLoaded.current = false;
    setCompanyOptions([]);
    loadCompanies();
  }, [clientId, loadCompanies]);

  // Build Select options once (memoized)
  const selectOptions = useMemo(() =>
    companyOptions.map(c => ({ value: c.id, label: c.company_name })),
    [companyOptions]
  );

  // ── Actions ───────────────────────────────────────────────────────────────

  const handleConfirm = async (candidate: MatchCandidate) => {
    const overrideId = rowSelections[candidate.id];
    const targetId = overrideId || candidate.sb_company_id;
    setSavingRow(candidate.id);
    try {
      const params = new URLSearchParams({ accepted: 'true' });
      if (overrideId && overrideId !== candidate.sb_company_id) {
        params.set('sb_company_id', overrideId);
      }
      await api.post(`/v1/quickbase/match-candidates/${candidate.id}/review?${params}`);
      const targetName = overrideId
        ? companyOptions.find(c => c.id === overrideId)?.company_name || 'selected company'
        : candidate.sb_company_name;
      message.success(`Linked "${candidate.qb_name}" → "${targetName}"`);
      // Remove from local state immediately for snappy UX
      setPendingCandidates(prev => prev.filter(c => c.id !== candidate.id));
      setPendingTotal(prev => prev - 1);
      setRowSelections(prev => { const n = { ...prev }; delete n[candidate.id]; return n; });
      loadHealth();
    } catch {
      message.error('Failed to save mapping');
    }
    setSavingRow(null);
  };

  const handleSkip = async (candidateId: string) => {
    setSavingRow(candidateId);
    try {
      await api.post(`/v1/quickbase/match-candidates/${candidateId}/review?accepted=false`);
      setPendingCandidates(prev => prev.filter(c => c.id !== candidateId));
      setPendingTotal(prev => prev - 1);
    } catch {
      message.error('Failed to skip');
    }
    setSavingRow(null);
  };

  const handleRematch = async () => {
    if (!clientId) return;
    setRematchLoading(true);
    try {
      await api.post(`/v1/quickbase/rematch?client_id=${clientId}`);
      message.success('Re-matching started in background');
      setTimeout(() => {
        loadHealth();
        loadPending();
        setRematchLoading(false);
      }, 5000);
    } catch {
      message.error('Rematch failed');
      setRematchLoading(false);
    }
  };

  const scoreColor = (score: number) => {
    if (score >= 95) return 'green';
    if (score >= 90) return 'lime';
    if (score >= 85) return 'gold';
    return 'orange';
  };

  // ── Table columns ─────────────────────────────────────────────────────────

  const pendingColumns = [
    {
      title: 'QB Customer',
      dataIndex: 'qb_name',
      key: 'qb_name',
      width: 200,
      ellipsis: true,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: 'Score',
      dataIndex: 'match_score',
      key: 'match_score',
      width: 80,
      align: 'center' as const,
      sorter: (a: MatchCandidate, b: MatchCandidate) => a.match_score - b.match_score,
      defaultSortOrder: 'descend' as const,
      render: (v: number) => <Tag color={scoreColor(v)}>{v?.toFixed(0)}%</Tag>,
    },
    {
      title: 'Map to SB Company',
      key: 'sb_select',
      width: 320,
      render: (_: any, record: MatchCandidate) => (
        <Select
          showSearch
          size="small"
          style={{ width: '100%' }}
          placeholder="Search company..."
          value={rowSelections[record.id] || record.sb_company_id}
          onChange={(val) => setRowSelections(prev => ({ ...prev, [record.id]: val }))}
          options={selectOptions}
          filterOption={(input, option) =>
            (option?.label as string || '').toLowerCase().includes(input.toLowerCase())
          }
          optionFilterProp="label"
          virtual
        />
      ),
    },
    {
      title: '',
      key: 'actions',
      width: 150,
      render: (_: any, record: MatchCandidate) => (
        <Space size={4}>
          <Button
            type="primary"
            size="small"
            icon={<CheckCircleOutlined />}
            loading={savingRow === record.id}
            onClick={() => handleConfirm(record)}
          >
            Confirm
          </Button>
          <Button
            size="small"
            type="text"
            onClick={() => handleSkip(record.id)}
            disabled={savingRow === record.id}
          >
            Skip
          </Button>
        </Space>
      ),
    },
  ];

  const reviewedColumns = [
    {
      title: 'QB Customer',
      dataIndex: 'qb_name',
      key: 'qb_name',
      width: 200,
      ellipsis: true,
    },
    {
      title: 'SB Company',
      dataIndex: 'sb_company_name',
      key: 'sb_company_name',
      width: 220,
      ellipsis: true,
    },
    {
      title: 'Score',
      dataIndex: 'match_score',
      key: 'match_score',
      width: 80,
      align: 'center' as const,
      render: (v: number) => <Tag color={scoreColor(v)}>{v?.toFixed(0)}%</Tag>,
    },
    {
      title: 'Decision',
      dataIndex: 'accepted',
      key: 'accepted',
      width: 100,
      render: (v: boolean) =>
        v ? <Tag color="success">Linked</Tag> : <Tag color="default">Skipped</Tag>,
    },
    {
      title: 'Reviewed',
      dataIndex: 'reviewed_at',
      key: 'reviewed_at',
      width: 140,
      render: (v: string) => v ? new Date(v).toLocaleDateString() : '-',
    },
  ];

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: '16px 24px', maxWidth: 1400, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>QB ↔ Company Match Review</Title>
        <Space>
          <ClientSelector value={clientId} onChange={setClientId} />
          <Button
            icon={<SyncOutlined spin={rematchLoading} />}
            onClick={handleRematch}
            loading={rematchLoading}
            disabled={!clientId}
          >
            Run Re-Match
          </Button>
          <Button
            icon={<ReloadOutlined />}
            disabled={!clientId}
            onClick={() => { loadHealth(); loadPending(); loadReviewed(); }}
          >
            Refresh
          </Button>
        </Space>
      </div>

      {!clientId && (
        <Card style={{ textAlign: 'center', marginTop: 40 }}>
          <Text type="secondary">Select a client above to view match data</Text>
        </Card>
      )}

      {clientId && health && !health.qb_configured && (
        <Card style={{ textAlign: 'center', marginTop: 40 }}>
          <Text type="secondary">QuickBase is not configured for this client. Set up QB integration on the <a href="/manage/quickbase">QB Config</a> page first.</Text>
        </Card>
      )}

      {clientId && (!health || health.qb_configured) && <>
      {/* Match Health Stats */}
      <Spin spinning={healthLoading}>
        <Row gutter={16} style={{ marginBottom: 20 }}>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="QB Customers Matched"
                value={health?.qb_customers.matched || 0}
                suffix={<Text type="secondary">/ {health?.qb_customers.total || 0}</Text>}
                valueStyle={{ color: '#3f8600' }}
              />
              <Text type="secondary">{health?.qb_customers.match_rate_pct || 0}% match rate</Text>
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="QB Contacts Matched"
                value={health?.qb_contacts.matched || 0}
                suffix={<Text type="secondary">/ {health?.qb_contacts.total || 0}</Text>}
                valueStyle={{ color: '#3f8600' }}
              />
              <Text type="secondary">{health?.qb_contacts.match_rate_pct || 0}% match rate</Text>
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="QB → SB Enriched"
                value={health?.company_enrichment.enriched || 0}
                suffix={<Text type="secondary">/ {health?.company_enrichment.total || 0} QB</Text>}
                valueStyle={{ color: '#1677ff' }}
              />
              <Text type="secondary">{health?.company_enrichment.coverage_pct || 0}% of QB customers linked</Text>
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small">
              <Statistic
                title="Active + QB Data"
                value={health?.active_companies.with_qb_data || 0}
                suffix={<Text type="secondary">/ {health?.active_companies.total || 0}</Text>}
                valueStyle={{ color: '#722ed1' }}
              />
              <Text type="secondary">{health?.active_companies.coverage_pct || 0}% of active</Text>
            </Card>
          </Col>
        </Row>
      </Spin>

      {/* Tabs: Pending / Reviewed */}
      <Tabs
        defaultActiveKey="pending"
        items={[
          {
            key: 'pending',
            label: (
              <span>
                <QuestionCircleOutlined /> Pending Review{' '}
                <Badge count={pendingTotal} size="small" style={{ marginLeft: 4 }} />
              </span>
            ),
            children: (
              <Card size="small">
                <Table
                  dataSource={pendingCandidates}
                  columns={pendingColumns}
                  rowKey="id"
                  loading={pendingLoading}
                  size="small"
                  scroll={{ x: 'max-content' }}
                  pagination={{
                    current: pendingPage,
                    pageSize: PAGE_SIZE,
                    total: pendingTotal,
                    onChange: setPendingPage,
                    showTotal: (t) => `${t} candidates`,
                    size: 'small',
                  }}
                />
              </Card>
            ),
          },
          {
            key: 'reviewed',
            label: (
              <span>
                <CheckCircleOutlined /> Reviewed{' '}
                <Badge count={reviewedTotal} size="small" style={{ marginLeft: 4 }} />
              </span>
            ),
            children: (
              <Card size="small">
                <Table
                  dataSource={reviewedCandidates}
                  columns={reviewedColumns}
                  rowKey="id"
                  loading={reviewedLoading}
                  size="small"
                  scroll={{ x: 'max-content' }}
                  pagination={{
                    current: reviewedPage,
                    pageSize: PAGE_SIZE,
                    total: reviewedTotal,
                    onChange: setReviewedPage,
                    showTotal: (t) => `${t} reviewed`,
                    size: 'small',
                  }}
                />
              </Card>
            ),
          },
        ]}
      />
      </>}
    </div>
  );
}
