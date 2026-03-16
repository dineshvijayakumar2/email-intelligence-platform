/**
 * AI Playground — Test and tune AI prompts against real endpoints.
 *
 * No new backend endpoints — calls the same APIs as the intelligence pages.
 * Shows: prompt used → context sent → raw LLM output for rapid iteration.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Card, Row, Col, Typography, Select, Button, Input, Space, Tag,
  Spin, Alert, Tabs, Descriptions, message, Empty, DatePicker, InputNumber,
} from 'antd';
import {
  ExperimentOutlined, SendOutlined, SaveOutlined, UndoOutlined,
  CodeOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { ClientSelector } from '../../components/analytics/ClientSelector';
import { MailboxSelector } from '../../components/MailboxSelector';
import api from '../../services/apiClient';
import { intelligenceApi, digestApi, bucketApi } from '../../services/aiService';
import { strategicDigestApi, insightsApi } from '../../services/strategicDigestService';

const { Title, Text } = Typography;
const { TextArea } = Input;

type TestType =
  | 'email_analysis'
  | 'daily_digest'
  | 'weekly_digest'
  | 'strategic_digest'
  | 'insight_company'
  | 'insight_contact'
  | 'insight_thread'
  | 'rebucket';

const TEST_OPTIONS: { value: TestType; label: string; needs: string; promptKeys: string[] }[] = [
  { value: 'email_analysis', label: 'Email Analysis', needs: 'mailbox', promptKeys: ['email_analysis_system', 'email_analysis_user'] },
  { value: 'daily_digest', label: 'Daily Digest', needs: 'mailbox', promptKeys: ['daily_digest'] },
  { value: 'weekly_digest', label: 'Weekly Digest', needs: 'mailbox', promptKeys: ['weekly_digest'] },
  { value: 'strategic_digest', label: 'Strategic Digest', needs: 'client', promptKeys: ['strategic_digest'] },
  { value: 'insight_company', label: 'Company Insight', needs: 'entity_id', promptKeys: ['insight_company'] },
  { value: 'insight_contact', label: 'Contact Insight', needs: 'entity_id', promptKeys: ['insight_contact'] },
  { value: 'insight_thread', label: 'Thread Insight', needs: 'entity_id', promptKeys: ['insight_thread'] },
  { value: 'rebucket', label: 'Re-bucket Signals', needs: 'mailbox', promptKeys: [] },
];

const PlaygroundPage: React.FC = () => {
  const [clientId, setClientId] = useState('');
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';
  const [entityId, setEntityId] = useState('');

  const [testType, setTestType] = useState<TestType>('email_analysis');
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);

  // Parameters (passed to endpoints)
  const [dateFrom, setDateFrom] = useState(dayjs().subtract(7, 'day').format('YYYY-MM-DD'));
  const [dateTo, setDateTo] = useState(dayjs().format('YYYY-MM-DD'));
  const [maxEmails, setMaxEmails] = useState(5);
  const [periodType, setPeriodType] = useState<'weekly' | 'monthly' | 'quarterly'>('weekly');

  // Prompts
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [overrides, setOverrides] = useState<Record<string, { prompt_text: string; updated_at?: string }>>({});
  const [selectedPromptKey, setSelectedPromptKey] = useState('');
  const [activePrompt, setActivePrompt] = useState('');
  const [editedPrompt, setEditedPrompt] = useState('');
  const [isEdited, setIsEdited] = useState(false);
  const [promptUpdatedAt, setPromptUpdatedAt] = useState<string | null>(null);

  // Results
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [elapsed, setElapsed] = useState(0);

  // Load default prompts + client overrides
  const loadPrompts = useCallback(async () => {
    try {
      const [defaultsResp, overridesResp] = await Promise.all([
        api.get<{ defaults: any[] }>('/v1/ai/prompts/defaults'),
        clientId ? api.get<{ prompts: any[] }>(`/v1/ai/prompts?client_id=${clientId}`) : null,
      ]);

      const defMap: Record<string, string> = {};
      for (const d of defaultsResp?.defaults || []) {
        defMap[d.prompt_key] = d.prompt_text;
      }
      setDefaults(defMap);

      // Apply client overrides (with timestamps)
      const ovMap: Record<string, { prompt_text: string; updated_at?: string }> = {};
      for (const o of overridesResp?.prompts || []) {
        ovMap[o.prompt_key] = { prompt_text: o.prompt_text, updated_at: o.updated_at };
      }
      setOverrides(ovMap);

      // Select first prompt key for this test type
      const cfg = TEST_OPTIONS.find(t => t.value === testType);
      const firstKey = selectedPromptKey && cfg?.promptKeys.includes(selectedPromptKey)
        ? selectedPromptKey
        : cfg?.promptKeys[0] || '';
      setSelectedPromptKey(firstKey);
      const ov = ovMap[firstKey];
      const prompt = ov?.prompt_text || defMap[firstKey] || '';
      setActivePrompt(prompt);
      setEditedPrompt(prompt);
      setIsEdited(false);
      setPromptUpdatedAt(ov?.updated_at || null);
    } catch { /* silent */ }
  }, [clientId, testType]);

  useEffect(() => { loadPrompts(); }, [loadPrompts]);

  const handlePromptChange = (val: string) => {
    setEditedPrompt(val);
    setIsEdited(val !== activePrompt);
  };

  const handlePromptKeySwitch = (key: string) => {
    setSelectedPromptKey(key);
    const ov = overrides[key];
    const prompt = ov?.prompt_text || defaults[key] || '';
    setActivePrompt(prompt);
    setEditedPrompt(prompt);
    setIsEdited(false);
    setPromptUpdatedAt(ov?.updated_at || null);
  };

  const handleSavePrompt = async () => {
    if (!clientId) { message.warning('Select a client first'); return; }
    if (!selectedPromptKey) return;
    setSaving(true);
    try {
      await api.put('/v1/ai/prompts', {
        client_id: clientId,
        prompt_key: selectedPromptKey,
        prompt_text: editedPrompt,
        description: `Updated from Playground`,
        version: 'v1.0',
      });
      message.success(`Prompt "${selectedPromptKey}" saved`);
      setActivePrompt(editedPrompt);
      setIsEdited(false);
      setPromptUpdatedAt(new Date().toISOString());
    } catch {
      message.error('Failed to save prompt');
    }
    setSaving(false);
  };

  const handleResetPrompt = () => {
    setEditedPrompt(defaults[selectedPromptKey] || '');
    setIsEdited(true);
  };

  const handleRun = async () => {
    setRunning(true);
    setResult(null);
    setError('');
    const start = Date.now();

    try {
      let output: any = null;

      switch (testType) {
        case 'email_analysis':
          if (!mailboxId) throw new Error('Select a mailbox');
          output = await intelligenceApi.analyze(mailboxId, {
            max_emails: maxEmails,
            date_from: dateFrom,
            date_to: dateTo,
          });
          // Wait then fetch results
          await new Promise(r => setTimeout(r, 8000));
          const intel = await intelligenceApi.list(mailboxId, { page_size: maxEmails });
          output = { trigger: output, results: intel.items?.slice(0, maxEmails), params: { maxEmails, dateFrom, dateTo } };
          break;

        case 'daily_digest':
          if (!mailboxId) throw new Error('Select a mailbox');
          output = await digestApi.get(mailboxId, dateTo, clientId || undefined, true, 'daily');
          break;

        case 'weekly_digest':
          if (!mailboxId) throw new Error('Select a mailbox');
          output = await digestApi.get(mailboxId, dateTo, clientId || undefined, true, 'weekly');
          break;

        case 'strategic_digest':
          if (!clientId) throw new Error('Select a client');
          await strategicDigestApi.generate(clientId, periodType);
          for (let i = 0; i < 120; i++) {
            await new Promise(r => setTimeout(r, 5000));
            const prog = await strategicDigestApi.getProgress(clientId);
            if (prog.phase === 'completed') {
              output = await strategicDigestApi.get(clientId, periodType);
              break;
            }
            if (prog.phase === 'failed') throw new Error(prog.message || 'Generation failed');
          }
          if (!output) throw new Error('Timed out waiting for digest');
          break;

        case 'insight_company':
          if (!entityId) throw new Error('Enter a company ID');
          output = await insightsApi.company(entityId, true, clientId || undefined);
          break;

        case 'insight_contact':
          if (!entityId) throw new Error('Enter a contact ID');
          output = await insightsApi.contact(entityId, true, clientId || undefined);
          break;

        case 'insight_thread':
          if (!entityId) throw new Error('Enter a thread ID');
          output = await insightsApi.thread(entityId, true, clientId || undefined);
          break;

        case 'rebucket':
          if (!mailboxId) throw new Error('Select a mailbox');
          output = await bucketApi.rebucket(mailboxId);
          await new Promise(r => setTimeout(r, 3000));
          const summary = await bucketApi.getSummary(mailboxId);
          output = { trigger: output, summary };
          break;
      }

      setResult(output);
      setElapsed(Date.now() - start);
    } catch (err: any) {
      setError(err?.message || 'Test failed');
      setElapsed(Date.now() - start);
    } finally {
      setRunning(false);
    }
  };

  const testConfig = TEST_OPTIONS.find(t => t.value === testType);
  const hasPrompt = (testConfig?.promptKeys.length || 0) > 0;

  return (
    <div style={{ padding: 24, maxWidth: 1600, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>
          <ExperimentOutlined style={{ color: '#667eea', marginRight: 8 }} />
          AI Playground
        </Title>
        <Space wrap>
          <ClientSelector value={clientId} onChange={setClientId} />
          <Select
            value={testType}
            onChange={(v) => { setTestType(v); setResult(null); setError(''); }}
            style={{ width: 200 }}
            options={TEST_OPTIONS.map(t => ({ value: t.value, label: t.label }))}
          />
          {testConfig?.needs === 'mailbox' && (
            <MailboxSelector value={mailboxIds} onChange={setMailboxIds} mode="single" style={{ width: 250 }} />
          )}
          {testConfig?.needs === 'entity_id' && (
            <Input
              placeholder="Entity UUID"
              value={entityId}
              onChange={e => setEntityId(e.target.value)}
              style={{ width: 320 }}
            />
          )}
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleRun}
            loading={running}
          >
            Run Test
          </Button>
        </Space>
      </div>

      {/* Parameters Row */}
      <Card className="glass-card" size="small" style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          {(testConfig?.needs === 'mailbox' && ['email_analysis'].includes(testType)) && (
            <>
              <div>
                <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Date From</Text>
                <DatePicker value={dayjs(dateFrom)} onChange={d => d && setDateFrom(d.format('YYYY-MM-DD'))} size="small" />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Date To</Text>
                <DatePicker value={dayjs(dateTo)} onChange={d => d && setDateTo(d.format('YYYY-MM-DD'))} size="small" />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Max Emails</Text>
                <InputNumber value={maxEmails} onChange={v => setMaxEmails(v || 5)} min={1} max={50} size="small" style={{ width: 80 }} />
              </div>
            </>
          )}
          {['daily_digest', 'weekly_digest'].includes(testType) && (
            <div>
              <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Digest Date</Text>
              <DatePicker value={dayjs(dateTo)} onChange={d => d && setDateTo(d.format('YYYY-MM-DD'))} size="small" />
            </div>
          )}
          {testType === 'strategic_digest' && (
            <div>
              <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>Period</Text>
              <Select value={periodType} onChange={setPeriodType} size="small" style={{ width: 120 }}
                options={[
                  { value: 'weekly', label: 'Weekly' },
                  { value: 'monthly', label: 'Monthly' },
                  { value: 'quarterly', label: 'Quarterly' },
                ]}
              />
            </div>
          )}
          {promptUpdatedAt && (
            <Tag icon={<ClockCircleOutlined />} color="blue" style={{ marginLeft: 'auto' }}>
              Prompt updated: {new Date(promptUpdatedAt).toLocaleString()}
            </Tag>
          )}
          {!promptUpdatedAt && !overrides[selectedPromptKey] && selectedPromptKey && (
            <Tag color="default" style={{ marginLeft: 'auto' }}>Using default prompt</Tag>
          )}
        </Space>
      </Card>

      {error && <Alert type="error" message={error} showIcon closable onClose={() => setError('')} style={{ marginBottom: 16 }} />}

      <Row gutter={[16, 16]}>
        {/* Left: Prompt Editor */}
        <Col xs={24} lg={hasPrompt ? 12 : 0}>
          {hasPrompt && (
            <Card
              title={
                <Space>
                  <CodeOutlined />
                  {(testConfig?.promptKeys.length || 0) > 1 ? (
                    <Select
                      value={selectedPromptKey}
                      onChange={handlePromptKeySwitch}
                      size="small"
                      style={{ width: 220 }}
                      options={testConfig?.promptKeys.map(k => ({
                        value: k,
                        label: k.replace(/_/g, ' '),
                      }))}
                    />
                  ) : (
                    <Text strong>{selectedPromptKey.replace(/_/g, ' ')}</Text>
                  )}
                  {isEdited && <Tag color="orange">Unsaved</Tag>}
                  {overrides[selectedPromptKey] && <Tag color="blue">Custom</Tag>}
                </Space>
              }
              extra={
                <Space>
                  <Button size="small" icon={<UndoOutlined />} onClick={handleResetPrompt}>
                    Reset to Default
                  </Button>
                  <Button size="small" type="primary" icon={<SaveOutlined />} onClick={handleSavePrompt} loading={saving} disabled={!isEdited}>
                    Save
                  </Button>
                </Space>
              }
              className="glass-card"
              bodyStyle={{ padding: 0 }}
            >
              <TextArea
                value={editedPrompt}
                onChange={e => handlePromptChange(e.target.value)}
                rows={24}
                style={{ fontFamily: 'monospace', fontSize: 11, border: 'none', borderRadius: 0, resize: 'vertical' }}
              />
              <div style={{ padding: '8px 12px', background: '#fafafa', borderTop: '1px solid #f0f0f0', fontSize: 11 }}>
                <Text type="secondary">{editedPrompt.length} chars</Text>
              </div>
            </Card>
          )}
        </Col>

        {/* Right: Output */}
        <Col xs={24} lg={hasPrompt ? 12 : 24}>
          <Card
            title={
              <Space>
                <Text strong>Output</Text>
                {elapsed > 0 && <Tag>{(elapsed / 1000).toFixed(1)}s</Tag>}
                {running && <Spin size="small" />}
              </Space>
            }
            className="glass-card"
          >
            {running && !result && (
              <div style={{ textAlign: 'center', padding: 48 }}>
                <Spin size="large" />
                <div style={{ marginTop: 16 }}><Text type="secondary">Running {testConfig?.label}...</Text></div>
                {testType === 'strategic_digest' && (
                  <div style={{ marginTop: 8 }}><Text type="secondary">This may take a few minutes</Text></div>
                )}
              </div>
            )}

            {!running && !result && !error && (
              <Empty description="Click 'Run Test' to execute" />
            )}

            {result && (
              <Tabs
                defaultActiveKey="formatted"
                items={[
                  {
                    key: 'formatted',
                    label: 'Formatted',
                    children: <FormattedOutput data={result} testType={testType} />,
                  },
                  {
                    key: 'raw',
                    label: 'Raw JSON',
                    children: (
                      <pre style={{
                        background: '#1e1e1e', color: '#d4d4d4', padding: 16,
                        borderRadius: 8, maxHeight: 600, overflow: 'auto',
                        fontSize: 11, lineHeight: 1.5,
                      }}>
                        {JSON.stringify(result, null, 2)}
                      </pre>
                    ),
                  },
                ]}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
};


// Formatted output renderer
const FormattedOutput: React.FC<{ data: any; testType: TestType }> = ({ data, testType }) => {
  if (!data) return <Empty />;

  // For digest types, show the key sections
  if (['daily_digest', 'weekly_digest'].includes(testType)) {
    return (
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {data.summary && (
          <Card size="small" title="Summary">
            <Text>{data.summary}</Text>
          </Card>
        )}
        {data.headline && (
          <Card size="small" title="Headline">
            {typeof data.headline === 'string' ? (
              <Text>{data.headline}</Text>
            ) : (
              <Descriptions size="small" column={1}>
                {Object.entries(data.headline).map(([k, v]) => (
                  <Descriptions.Item key={k} label={k.replace(/_/g, ' ')}>{String(v || '-')}</Descriptions.Item>
                ))}
              </Descriptions>
            )}
          </Card>
        )}
        {data.action_items?.length > 0 && (
          <Card size="small" title={`Action Items (${data.action_items.length})`}>
            {data.action_items.map((item: any, i: number) => (
              <div key={i} style={{ marginBottom: 8, padding: '4px 0', borderBottom: '1px solid #f5f5f5' }}>
                <Tag color="red">P{item.priority || i + 1}</Tag>
                <Text strong>{item.customer || item.contact_name || ''}</Text>
                <div><Text>{item.action || JSON.stringify(item)}</Text></div>
              </div>
            ))}
          </Card>
        )}
        {data.urgent_today?.length > 0 && (
          <Card size="small" title={`Urgent Today (${data.urgent_today.length})`}>
            {data.urgent_today.map((item: any, i: number) => (
              <div key={i} style={{ marginBottom: 8, padding: '4px 0', borderBottom: '1px solid #f5f5f5' }}>
                <Tag color="red">{item.customer}</Tag> <Text type="secondary">{item.am}</Text>
                <div><Text>{item.action}</Text></div>
                <div><Text type="secondary" style={{ fontSize: 11 }}>{item.reason} | {item.revenue_context}</Text></div>
              </div>
            ))}
          </Card>
        )}
        {data.at_risk?.length > 0 && (
          <Card size="small" title={`At Risk (${data.at_risk.length})`}>
            {data.at_risk.map((item: any, i: number) => (
              <div key={i} style={{ marginBottom: 8 }}>
                <Tag color="orange">{item.customer}</Tag> <Tag>{item.tier}</Tag>
                <div><Text>{item.specific_risk || item.risk || JSON.stringify(item)}</Text></div>
              </div>
            ))}
          </Card>
        )}
        {data.stats && (
          <Card size="small" title="Context Stats">
            <Space wrap>
              {Object.entries(data.stats).map(([k, v]) => (
                <Tag key={k}>{k.replace(/_/g, ' ')}: {String(v)}</Tag>
              ))}
            </Space>
          </Card>
        )}
      </Space>
    );
  }

  // For email analysis, show the classified results
  if (testType === 'email_analysis' && data.results) {
    return (
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text type="secondary">{data.results.length} emails classified</Text>
        {data.results.map((r: any, i: number) => (
          <Card key={i} size="small">
            <Space wrap>
              <Tag color="blue">{r.intent}</Tag>
              <Tag color={r.urgency === 'critical' ? 'red' : r.urgency === 'high' ? 'orange' : 'default'}>{r.urgency}</Tag>
              <Tag>{r.sentiment}</Tag>
              {r.business_signal && <Tag color="purple">{r.business_signal}</Tag>}
              {r.confidence && <Tag>conf: {Math.round(r.confidence * 100)}%</Tag>}
            </Space>
            <div style={{ marginTop: 4 }}><Text>{r.summary || r.email_subject}</Text></div>
            {r.suggested_action && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.suggested_action}</Text></div>}
          </Card>
        ))}
      </Space>
    );
  }

  // For insights, show structured output
  if (testType.startsWith('insight_')) {
    const insight = data.insight || data;
    return (
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        {insight.headline && <Title level={5}>{insight.headline}</Title>}
        {insight.health_summary && <Text>{insight.health_summary}</Text>}
        {insight.key_insight && <Text>{insight.key_insight}</Text>}
        {insight.engagement_summary && <Text>{insight.engagement_summary}</Text>}
        {insight.thread_summary && <Text>{insight.thread_summary}</Text>}
        <Descriptions size="small" column={2} bordered>
          {Object.entries(insight).filter(([k]) => !['headline', 'health_summary', 'key_insight', 'engagement_summary', 'thread_summary'].includes(k)).map(([k, v]) => (
            <Descriptions.Item key={k} label={k.replace(/_/g, ' ')}>
              {Array.isArray(v) ? v.join(', ') : String(v ?? '-')}
            </Descriptions.Item>
          ))}
        </Descriptions>
      </Space>
    );
  }

  // Default: show as key-value
  return (
    <Descriptions size="small" column={1} bordered>
      {Object.entries(data).map(([k, v]) => (
        <Descriptions.Item key={k} label={k}>
          {typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v ?? '-')}
        </Descriptions.Item>
      ))}
    </Descriptions>
  );
};

export default PlaygroundPage;
