/**
 * Intelligence Config — Capability taxonomy, classifier rules, rush settings, cache.
 * Route: /manage/intelligence-config (admin only)
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Card, Tabs, Table, Tag, Button, Input, Select, Space, Typography,
  Alert, Spin, message, Popconfirm, Form, InputNumber, Row, Col,
  Badge, Tooltip, Upload, Modal,
} from 'antd';
import {
  SyncOutlined, CheckCircleFilled, WarningOutlined, UploadOutlined,
  DeleteOutlined, ReloadOutlined, InfoCircleOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  getCapabilityTags, getClassifierRules, importClassifierRules,
  getRushSettings, updateRushSettings,
  triggerReclassify, getReclassifyStatus,
  getCacheStatus, clearCache,
  type CapabilityTag, type ClassifierRule, type RushSettings, type ReclassifyStatus,
} from '../../services/intelligenceConfigService';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const FLAG_COLORS: Record<string, string> = {
  has_coating:             'blue',
  has_sewing:              'purple',
  has_outsource_component: 'orange',
};

const ROW_TYPE_COLORS: Record<string, string> = {
  production:  'green',
  process:     'cyan',
  outsource:   'orange',
  logistics:   'blue',
  leadtime:    'volcano',
  costing:     'gold',
  rush_charge: 'red',
  admin:       'default',
  constraint:  'geekblue',
};

// ─────────────────────────────────────────────────────────────────────────────
// Tab 1: Capability Tags
// ─────────────────────────────────────────────────────────────────────────────

function CapabilityTagsTab() {
  const [tags, setTags] = useState<CapabilityTag[]>([]);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCapabilityTags()
      .then(r => { setTags(r.tags); setVersion(r.version); })
      .catch(() => message.error('Failed to load capability tags'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin />;

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message="8 MVP Capability Tags"
        description="These are the top-level product categories used for recommendations and customer profiles. Phase 2A will expand these into ~30 granular sub-tags."
        style={{ marginBottom: 16 }}
      />
      <Row gutter={[16, 16]}>
        {tags.map(tag => (
          <Col xs={24} sm={12} md={8} key={tag.tag_id}>
            <Card size="small" style={{ borderLeft: `4px solid ${tag.color}` }}>
              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                <Text strong style={{ color: tag.color }}>{tag.name}</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>{tag.description}</Text>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>
      <Text type="secondary" style={{ display: 'block', marginTop: 16, fontSize: 12 }}>
        Config version: {version} — Tag editing will be available in Phase 2A.
      </Text>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 2: Classifier Rules
// ─────────────────────────────────────────────────────────────────────────────

function ClassifierRulesTab() {
  const [rules, setRules] = useState<ClassifierRule[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [version, setVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [tagFilter, setTagFilter] = useState<string>('');
  const [deptFilter, setDeptFilter] = useState<string>('');
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [csvText, setCsvText] = useState('');
  const [replaceMode, setReplaceMode] = useState(false);
  const [importing, setImporting] = useState(false);

  const PAGE_SIZE = 50;

  const load = useCallback(() => {
    setLoading(true);
    getClassifierRules({ page, page_size: PAGE_SIZE, tag: tagFilter || undefined, dept: deptFilter || undefined })
      .then(r => { setRules(r.rules); setTotal(r.total); setVersion(r.version); })
      .catch(() => message.error('Failed to load classifier rules'))
      .finally(() => setLoading(false));
  }, [page, tagFilter, deptFilter]);

  useEffect(() => { load(); }, [load]);

  const handleImport = async () => {
    if (!csvText.trim()) { message.warning('Paste CSV data first'); return; }
    setImporting(true);
    try {
      const result = await importClassifierRules({ csv_text: csvText, replace: replaceMode });
      message.success(`Imported ${result.imported} rules — ${result.total_rules} total`);
      setImportModalOpen(false);
      setCsvText('');
      load();
    } catch {
      message.error('Import failed — check CSV format');
    } finally {
      setImporting(false);
    }
  };

  const columns: ColumnsType<ClassifierRule> = [
    { title: 'Department', dataIndex: 'dept', width: 160, ellipsis: true,
      render: v => <Text style={{ fontSize: 12 }}>{v || <Text type="secondary">—</Text>}</Text> },
    { title: 'Operation', dataIndex: 'op', ellipsis: true,
      render: v => <Text style={{ fontSize: 12 }}>{v}</Text> },
    { title: 'Machine', dataIndex: 'machine', width: 180, ellipsis: true,
      render: v => <Text style={{ fontSize: 12 }}>{v || <Text type="secondary">—</Text>}</Text> },
    { title: 'Count', dataIndex: 'count', width: 70, align: 'right',
      render: v => <Text type="secondary" style={{ fontSize: 12 }}>{v?.toLocaleString()}</Text> },
    { title: 'MVP Tag', dataIndex: 'tag', width: 160,
      render: v => v ? <Tag color="blue" style={{ fontSize: 11 }}>{v}</Tag> : <Text type="secondary">—</Text> },
    { title: 'Flags', dataIndex: 'flags', width: 200,
      render: (flags: string[]) => (
        <Space size={2} wrap>
          {(flags || []).map(f => (
            <Tag key={f} color={FLAG_COLORS[f] || 'default'} style={{ fontSize: 10, margin: 1 }}>
              {f.replace('has_', '').replace(/_/g, ' ')}
            </Tag>
          ))}
        </Space>
      ),
    },
    { title: 'Row Type', dataIndex: 'row_type', width: 110,
      render: v => v ? <Tag color={ROW_TYPE_COLORS[v] || 'default'} style={{ fontSize: 11 }}>{v}</Tag> : null },
  ];

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 12 }}>
        <Space>
          <Input.Search
            placeholder="Filter by department..."
            value={deptFilter}
            onChange={e => { setDeptFilter(e.target.value); setPage(1); }}
            style={{ width: 200 }}
            allowClear
          />
          <Select
            placeholder="Filter by tag"
            value={tagFilter || undefined}
            onChange={v => { setTagFilter(v || ''); setPage(1); }}
            allowClear
            style={{ width: 180 }}
            options={[
              'Flat Sheets', 'Soft Cover Books', 'Hard Cover Books', 'Wide Format',
              'Embellishment', 'Specialty Finishing', 'Design Services', 'Display / Installation',
            ].map(t => ({ value: t, label: t }))}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            {total.toLocaleString()} rules · v{version}
          </Text>
        </Space>
        <Button
          icon={<UploadOutlined />}
          onClick={() => setImportModalOpen(true)}
        >
          Import CSV
        </Button>
      </Row>

      <Table
        dataSource={rules}
        columns={columns}
        rowKey={(r, i) => `${r.dept}-${r.op}-${r.machine}-${i}`}
        loading={loading}
        size="small"
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          onChange: setPage,
          showSizeChanger: false,
          showTotal: (t) => `${t.toLocaleString()} rules`,
        }}
        scroll={{ x: 900 }}
      />

      <Modal
        title="Import Classifier Rules"
        open={importModalOpen}
        onCancel={() => setImportModalOpen(false)}
        onOk={handleImport}
        confirmLoading={importing}
        okText="Import"
        width={700}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Alert
            type="info"
            message="CSV Format"
            description={
              <Text style={{ fontSize: 12, fontFamily: 'monospace' }}>
                Department,Operation,Machine,Count,MVP Tag,Flags,Row Type<br />
                Coating,Cello,Celloglazer - Autobond,588,,has_coating,process<br />
                <br />
                Flags: comma-separated (has_coating, has_sewing, has_outsource_component)<br />
                Paste directly from Excel or CSV export.
              </Text>
            }
          />
          <TextArea
            rows={10}
            placeholder="Paste CSV here (including header row)..."
            value={csvText}
            onChange={e => setCsvText(e.target.value)}
            style={{ fontFamily: 'monospace', fontSize: 12 }}
          />
          <Space>
            <Select
              value={replaceMode}
              onChange={setReplaceMode}
              style={{ width: 220 }}
              options={[
                { value: false, label: 'Merge — update matching rows' },
                { value: true,  label: 'Replace all — overwrite everything' },
              ]}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              Match key: (Department, Operation, Machine)
            </Text>
          </Space>
        </Space>
      </Modal>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 3: Rush Settings
// ─────────────────────────────────────────────────────────────────────────────

function RushSettingsTab() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getRushSettings()
      .then(r => form.setFieldsValue(r.settings))
      .catch(() => message.error('Failed to load rush settings'))
      .finally(() => setLoading(false));
  }, [form]);

  const onSave = async (values: RushSettings) => {
    setSaving(true);
    try {
      await updateRushSettings(values);
      message.success('Rush settings saved');
    } catch {
      message.error('Failed to save rush settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Spin />;

  return (
    <div style={{ maxWidth: 600 }}>
      <Alert
        type="info"
        showIcon
        message="Rush Detection Settings"
        description="These thresholds control how rush patterns are surfaced in recommendations and customer profiles."
        style={{ marginBottom: 24 }}
      />
      <Form form={form} layout="vertical" onFinish={onSave}>
        <Form.Item
          name="am_rush_pattern"
          label="AM Rush Pattern"
          tooltip="Operation names starting with this text are flagged as am_rush=TRUE"
          rules={[{ required: true }]}
        >
          <Input style={{ fontFamily: 'monospace' }} />
        </Form.Item>
        <Form.Item
          name="rush_pct_threshold"
          label="Rush % Threshold"
          tooltip="Companies where rush jobs exceed this % are flagged in recommendations"
          rules={[{ required: true }]}
        >
          <InputNumber min={0} max={100} addonAfter="%" style={{ width: 160 }} />
        </Form.Item>
        <Form.Item
          name="gap_count_threshold"
          label="Factory Rush Gap Threshold"
          tooltip="Companies with this many factory_rush=TRUE but am_rush=FALSE jobs are flagged (got rush free)"
          rules={[{ required: true }]}
        >
          <InputNumber min={0} addonAfter="jobs" style={{ width: 160 }} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={saving}>Save Settings</Button>
        </Form.Item>
      </Form>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Tab 4: Cache
// ─────────────────────────────────────────────────────────────────────────────

function CacheTab() {
  const [entries, setEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [reclassifyStatus, setReclassifyStatus] = useState<ReclassifyStatus>({ status: 'idle' });
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadEntries = () => {
    getCacheStatus({ cache_type: 'capability_profile' })
      .then(r => setEntries(r.entries))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const loadStatus = () => {
    getReclassifyStatus().then(setReclassifyStatus).catch(() => {});
  };

  useEffect(() => {
    loadEntries();
    loadStatus();
  }, []);

  // Poll reclassify status while running
  useEffect(() => {
    if (reclassifyStatus.status === 'running') {
      pollRef.current = setInterval(loadStatus, 3000);
    } else {
      if (pollRef.current) clearInterval(pollRef.current);
      if (reclassifyStatus.status === 'complete') loadEntries();
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [reclassifyStatus.status]);

  const handleReclassify = async () => {
    setTriggering(true);
    try {
      await triggerReclassify();
      message.success('Reclassification started');
      setReclassifyStatus({ status: 'running' });
    } catch {
      message.error('Failed to start reclassification');
    } finally {
      setTriggering(false);
    }
  };

  const handleClearCache = async () => {
    try {
      const r = await clearCache();
      message.success(`Cleared ${r.deleted} cache entries`);
      loadEntries();
    } catch {
      message.error('Failed to clear cache');
    }
  };

  const statusBadge = () => {
    if (reclassifyStatus.status === 'running') return <Badge status="processing" text="Running..." />;
    if (reclassifyStatus.status === 'complete') return (
      <Badge status="success" text={`Complete — ${reclassifyStatus.updated?.toLocaleString()} operations updated`} />
    );
    if (reclassifyStatus.status === 'error') return <Badge status="error" text={`Error: ${reclassifyStatus.error}`} />;
    return <Badge status="default" text="Idle" />;
  };

  const columns: ColumnsType<any> = [
    { title: 'Company', dataIndex: ['customer_companies', 'company_name'], ellipsis: true },
    { title: 'Cache Type', dataIndex: 'cache_type', render: v => <Tag>{v}</Tag> },
    { title: 'Computed At', dataIndex: 'computed_at',
      render: v => v ? new Date(v).toLocaleString() : '—' },
  ];

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col>
          <Card size="small" style={{ minWidth: 280 }}>
            <Space direction="vertical" size={8}>
              <Text strong>Reclassify Operations</Text>
              <Paragraph type="secondary" style={{ fontSize: 12, margin: 0 }}>
                Re-tags all qb_operations rows using current classifier rules.
                Run after importing updated rules. Does not re-fetch from QB.
              </Paragraph>
              <Space>
                {statusBadge()}
              </Space>
              <Button
                type="primary"
                icon={<SyncOutlined spin={reclassifyStatus.status === 'running'} />}
                onClick={handleReclassify}
                loading={triggering}
                disabled={reclassifyStatus.status === 'running'}
              >
                Reclassify All Operations
              </Button>
            </Space>
          </Card>
        </Col>
        <Col>
          <Card size="small" style={{ minWidth: 240 }}>
            <Space direction="vertical" size={8}>
              <Text strong>Intelligence Cache</Text>
              <Paragraph type="secondary" style={{ fontSize: 12, margin: 0 }}>
                Clears computed capability profiles. Profiles rebuild automatically on next request.
              </Paragraph>
              <Popconfirm
                title="Clear all intelligence cache?"
                description="Profiles will recompute on next view. This is safe to do anytime."
                onConfirm={handleClearCache}
                okText="Clear"
                cancelText="Cancel"
              >
                <Button danger icon={<DeleteOutlined />}>Clear Cache</Button>
              </Popconfirm>
            </Space>
          </Card>
        </Col>
      </Row>

      <Text strong style={{ display: 'block', marginBottom: 8 }}>
        Cached Capability Profiles ({entries.length} companies)
      </Text>
      <Table
        dataSource={entries}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 20, showSizeChanger: false }}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────────────────────

export default function IntelligenceConfigPage() {
  const tabs = [
    { key: 'tags',       label: 'Capability Tags',    children: <CapabilityTagsTab /> },
    { key: 'rules',      label: 'Classifier Rules',   children: <ClassifierRulesTab /> },
    { key: 'rush',       label: 'Rush Settings',      children: <RushSettingsTab /> },
    { key: 'cache',      label: 'Cache & Rebuild',    children: <CacheTab /> },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Title level={3} style={{ marginBottom: 4 }}>Intelligence Configuration</Title>
      <Paragraph type="secondary" style={{ marginBottom: 24 }}>
        Manage capability taxonomy, classifier rules, and computed profile cache.
        Changes to classifier rules take effect after clicking <strong>Reclassify All Operations</strong> in the Cache tab.
      </Paragraph>
      <Card>
        <Tabs items={tabs} defaultActiveKey="tags" />
      </Card>
    </div>
  );
}
