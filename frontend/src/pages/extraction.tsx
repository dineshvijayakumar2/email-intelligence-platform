import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Typography, Form, Select, Radio, Slider, Switch, Button, Tag, Progress, message, Divider } from 'antd';
import { RocketOutlined, StopOutlined } from '@ant-design/icons';
import { mailboxService, Mailbox } from '../services/mailboxService';
import { AnalyticsTable } from '../components/analytics/AnalyticsTable';
import { extractionApi, clearAnalyticsCache } from '../services/analyticsService';
import type { ExtractionJobResponse, ExtractionProgressResponse, ExtractionMode } from '../types/analytics';

const { Text, Title } = Typography;
const PAGE_SIZE = 20;

export const ExtractionManagement: React.FC = () => {
  const isMountedRef = useRef(true);
  const [form] = Form.useForm();
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [jobs, setJobs] = useState<ExtractionJobResponse[]>([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [activeProgress, setActiveProgress] = useState<Record<string, ExtractionProgressResponse>>({});
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    isMountedRef.current = true;
    loadMailboxes();
    loadJobs();
    return () => {
      isMountedRef.current = false;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  useEffect(() => { loadJobs(); }, [page]);

  const loadMailboxes = async () => {
    const mbs = await mailboxService.getMailboxes();
    if (isMountedRef.current) setMailboxes(mbs);
  };

  const loadJobs = async () => {
    setLoading(true);
    const result = await extractionApi.listJobs({ limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
    if (isMountedRef.current) {
      setJobs(result.jobs);
      setJobsTotal(result.total);
      setLoading(false);

      // Start polling for active jobs
      const activeJobs = result.jobs.filter(j => ['pending', 'processing'].includes(j.status));
      if (activeJobs.length > 0) startPolling(activeJobs.map(j => j.id));
      else stopPolling();
    }
  };

  const startPolling = (jobIds: string[]) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      const updates: Record<string, ExtractionProgressResponse> = {};
      for (const id of jobIds) {
        const p = await extractionApi.getProgress(id);
        if (p) updates[id] = p;
      }
      if (isMountedRef.current) {
        setActiveProgress(updates);
        // Refresh jobs list if any completed
        const completed = Object.values(updates).some(p => !['pending', 'processing'].includes(p.status));
        if (completed) { loadJobs(); clearAnalyticsCache(); }
      }
    }, 3000);
  };

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const handleSubmit = async (values: any) => {
    setSubmitting(true);
    const result = await extractionApi.run({
      mailbox_id: values.mailbox_id,
      mode: values.mode,
      lookback_days: values.lookback_days,
      exclude_mailing_lists: values.exclude_mailing_lists,
      exclude_noreply: values.exclude_noreply,
      exclude_internal: values.exclude_internal,
    });
    if (result) {
      message.success(`Extraction started! Job ID: ${result.id}`);
      form.resetFields();
      loadJobs();
    } else {
      message.error('Failed to start extraction');
    }
    setSubmitting(false);
  };

  const handleCancel = async (jobId: string) => {
    const result = await extractionApi.cancelJob(jobId);
    if (result) { message.success('Job cancelled'); loadJobs(); }
    else message.error('Failed to cancel job');
  };

  const mode = Form.useWatch('mode', form);

  const jobColumns = [
    {
      title: 'Status', dataIndex: 'status', key: 'status', width: 110,
      render: (v: string, record: ExtractionJobResponse) => {
        const progress = activeProgress[record.id];
        if (progress && ['pending', 'processing'].includes(v)) {
          const pct = progress.total_steps ? Math.round(((progress.current_step_number || 0) / progress.total_steps) * 100) : 0;
          return <Progress percent={pct} size="small" status="active" style={{ width: 80 }} />;
        }
        const color = v === 'completed' ? 'green' : v === 'failed' ? 'red' : v === 'processing' ? 'blue' : 'default';
        return <Tag color={color}>{v}</Tag>;
      },
    },
    {
      title: 'Step', key: 'step', width: 180,
      render: (_: any, r: ExtractionJobResponse) => {
        const p = activeProgress[r.id];
        return p?.current_step || r.current_step || '-';
      },
    },
    { title: 'Mode', dataIndex: 'extraction_mode', key: 'mode', width: 100, render: (v: string) => <Tag>{v || 'full'}</Tag> },
    { title: 'Emails', dataIndex: 'emails_in_scope', key: 'emails', width: 80 },
    { title: 'Started', dataIndex: 'started_at', key: 'started', width: 160, render: (v: string) => v ? new Date(v).toLocaleString() : '-' },
    { title: 'Completed', dataIndex: 'completed_at', key: 'completed', width: 160, render: (v: string) => v ? new Date(v).toLocaleString() : '-' },
    {
      title: '', key: 'actions', width: 80,
      render: (_: any, r: ExtractionJobResponse) => (
        ['pending', 'processing'].includes(r.status)
          ? <Button size="small" danger icon={<StopOutlined />} onClick={() => handleCancel(r.id)}>Cancel</Button>
          : null
      ),
    },
  ];

  return (
    <div className="glass-page-bg" style={{ padding: 24 }}>
      <div className="fade-in-up" style={{ marginBottom: 24 }}>
        <Text type="secondary">Run contact extraction jobs and monitor progress</Text>
      </div>

      {/* Trigger Form */}
      <div className="glass-card fade-in-up stagger-1" style={{ padding: 20, marginBottom: 24 }}>
        <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 16 }}>Run Extraction</Text>
        <Form form={form} layout="inline" onFinish={handleSubmit} initialValues={{ mode: 'full', lookback_days: 7, exclude_mailing_lists: true, exclude_noreply: true, exclude_internal: true }} style={{ flexWrap: 'wrap', gap: 12 }}>
          <Form.Item name="mailbox_id" rules={[{ required: true, message: 'Select a mailbox' }]}>
            <Select placeholder="Select mailbox" style={{ width: 220 }} options={mailboxes.map(m => ({ value: m.id, label: m.name }))} />
          </Form.Item>
          <Form.Item name="mode">
            <Radio.Group>
              <Radio.Button value="full">Full</Radio.Button>
              <Radio.Button value="incremental">Incremental</Radio.Button>
            </Radio.Group>
          </Form.Item>
          {mode === 'incremental' && (
            <Form.Item name="lookback_days" label="Days">
              <Slider min={1} max={365} style={{ width: 120 }} />
            </Form.Item>
          )}
          <Form.Item name="exclude_mailing_lists" valuePropName="checked"><Switch checkedChildren="Excl Lists" unCheckedChildren="Incl Lists" /></Form.Item>
          <Form.Item name="exclude_noreply" valuePropName="checked"><Switch checkedChildren="Excl NoReply" unCheckedChildren="Incl NoReply" /></Form.Item>
          <Form.Item name="exclude_internal" valuePropName="checked"><Switch checkedChildren="Excl Internal" unCheckedChildren="Incl Internal" /></Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<RocketOutlined />} loading={submitting}>Run Extraction</Button>
          </Form.Item>
        </Form>
      </div>

      {/* Job History */}
      <div className="fade-in-up stagger-2">
        <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 12 }}>Extraction History</Text>
        <AnalyticsTable
          columns={jobColumns}
          data={jobs}
          total={jobsTotal}
          loading={loading}
          pageSize={PAGE_SIZE}
          currentPage={page}
          onPageChange={setPage}
          rowKey="id"
        />
      </div>
    </div>
  );
};
