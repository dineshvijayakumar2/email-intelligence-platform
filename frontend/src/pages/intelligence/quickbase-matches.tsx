/**
 * QB Match Review — Map QB customers to SB companies via searchable selector.
 * Fuzzy candidates are pre-suggested; user can type to search all SB companies (server-side).
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Table, Button, Tag, Space, Typography, Statistic, Row, Col,
  Spin, message, Badge, Select,
} from 'antd';
import {
  CheckCircleOutlined, SyncOutlined,
  ReloadOutlined, SearchOutlined,
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
}

interface HealthData {
  qb_configured: boolean;
  qb_customers: { total: number; matched: number; unmatched: number; match_rate_pct: number };
  qb_contacts: { total: number; matched: number; unmatched: number; match_rate_pct: number };
  company_enrichment: { total: number; enriched: number; not_enriched: number; coverage_pct: number };
  active_companies: { total: number; with_qb_data: number; coverage_pct: number };
}

// ── Server-side search Select for SB companies ──────────────────────────────

interface CompanyOption { value: string; label: string }

function CompanySearchSelect({
  clientId,
  defaultValue,
  defaultLabel,
  onChange,
}: {
  clientId: string;
  defaultValue: string;
  defaultLabel: string;
  onChange: (id: string, name: string) => void;
}) {
  const [options, setOptions] = useState<CompanyOption[]>(
    defaultValue ? [{ value: defaultValue, label: defaultLabel }] : []
  );
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearch = (query: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query || query.length < 2) {
      if (defaultValue) setOptions([{ value: defaultValue, label: defaultLabel }]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await api.get(
          `/v1/quickbase/companies-lookup?client_id=${clientId}&search=${encodeURIComponent(query)}&limit=30`
        ) as { companies: { id: string; company_name: string }[] };
        const results = (data.companies || []).map(c => ({
          value: c.id,
          label: c.company_name,
        }));
        if (defaultValue && !results.find(r => r.value === defaultValue)) {
          results.unshift({ value: defaultValue, label: defaultLabel });
        }
        setOptions(results);
      } catch { /* silent */ }
      setSearching(false);
    }, 300);
  };

  return (
    <Select
      showSearch
      size="small"
      style={{ width: '100%' }}
      placeholder="Type to search companies..."
      suffixIcon={<SearchOutlined />}
      value={defaultValue || undefined}
      loading={searching}
      options={options}
      filterOption={false}
      onSearch={handleSearch}
      onChange={(val) => {
        const opt = options.find(o => o.value === val);
        onChange(val, opt?.label || '');
      }}
      notFoundContent={searching ? <Spin size="small" /> : <Text type="secondary">Type 2+ chars to search</Text>}
    />
  );
}

// ── Main page ───────────────────────────────────────────────────────────────

export default function QuickbaseMatchesPage() {
  const [clientId, setClientId] = useState<string>('');
  const [health, setHealth] = useState<HealthData | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);

  const [candidates, setCandidates] = useState<MatchCandidate[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);

  const [rematchLoading, setRematchLoading] = useState(false);
  const [rowSelections, setRowSelections] = useState<Record<string, { id: string; name: string }>>({});
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

  const loadCandidates = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    try {
      const offset = (page - 1) * PAGE_SIZE;
      const data = await api.get(
        `/v1/quickbase/match-candidates?client_id=${clientId}&reviewed=false&limit=${PAGE_SIZE}&offset=${offset}`
      ) as { candidates: MatchCandidate[]; total: number };
      setCandidates(data.candidates || []);
      setTotal(data.total || 0);
    } catch { /* silent */ }
    setLoading(false);
  }, [clientId, page]);

  useEffect(() => { loadHealth(); }, [loadHealth]);
  useEffect(() => { loadCandidates(); }, [loadCandidates]);

  // ── Actions ───────────────────────────────────────────────────────────────

  const handleConfirm = async (candidate: MatchCandidate) => {
    const override = rowSelections[candidate.id];
    const targetName = override?.name || candidate.sb_company_name;
    setSavingRow(candidate.id);
    try {
      const params = new URLSearchParams({ accepted: 'true' });
      if (override && override.id !== candidate.sb_company_id) {
        params.set('sb_company_id', override.id);
      }
      await api.post(`/v1/quickbase/match-candidates/${candidate.id}/review?${params}`);
      message.success(`Linked "${candidate.qb_name}" → "${targetName}"`);
      setCandidates(prev => prev.filter(c => c.id !== candidate.id));
      setTotal(prev => prev - 1);
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
      setCandidates(prev => prev.filter(c => c.id !== candidateId));
      setTotal(prev => prev - 1);
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
        loadCandidates();
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

  const columns = [
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
        <CompanySearchSelect
          clientId={clientId}
          defaultValue={rowSelections[record.id]?.id || record.sb_company_id}
          defaultLabel={rowSelections[record.id]?.name || record.sb_company_name}
          onChange={(id, name) => setRowSelections(prev => ({ ...prev, [record.id]: { id, name } }))}
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
            onClick={() => { loadHealth(); loadCandidates(); }}
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

      {/* Candidates table */}
      <Card
        size="small"
        title={<span>Fuzzy Match Candidates <Badge count={total} size="small" style={{ marginLeft: 8 }} /></span>}
      >
        <Table
          dataSource={candidates}
          columns={columns}
          rowKey="id"
          loading={loading}
          size="small"
          scroll={{ x: 'max-content' }}
          pagination={{
            current: page,
            pageSize: PAGE_SIZE,
            total,
            onChange: setPage,
            showTotal: (t) => `${t} candidates`,
            size: 'small',
          }}
          locale={{ emptyText: total === 0 && !loading ? 'No fuzzy candidates — run Re-Match to generate' : undefined }}
        />
      </Card>
      </>}
    </div>
  );
}
