import { useEffect, useState } from 'react';
import {
  Card,
  Form,
  Select,
  TimePicker,
  Checkbox,
  Button,
  message,
  Spin,
  Typography,
  Space,
  Divider,
} from 'antd';
import { ClockCircleOutlined, GlobalOutlined, DollarOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import api from '../services/apiClient';
import { ClientSelector } from '../components/analytics/ClientSelector';
import { CURRENCY_OPTIONS } from '../utils/numberFormat';

const { Title, Text } = Typography;

interface BusinessHoursSettings {
  timezone: string;
  business_hours_start: number;
  business_hours_end: number;
  business_days: number[];
}

const WEEKDAYS = [
  { label: 'Monday', value: 1 },
  { label: 'Tuesday', value: 2 },
  { label: 'Wednesday', value: 3 },
  { label: 'Thursday', value: 4 },
  { label: 'Friday', value: 5 },
  { label: 'Saturday', value: 6 },
  { label: 'Sunday', value: 7 },
];

// Common timezones grouped by region
const TIMEZONE_OPTIONS = [
  { label: 'UTC', value: 'UTC' },
  { label: 'Asia/Kolkata (IST, UTC+5:30)', value: 'Asia/Kolkata' },
  { label: 'Asia/Dubai (GST, UTC+4)', value: 'Asia/Dubai' },
  { label: 'Asia/Singapore (SGT, UTC+8)', value: 'Asia/Singapore' },
  { label: 'Asia/Tokyo (JST, UTC+9)', value: 'Asia/Tokyo' },
  { label: 'Asia/Shanghai (CST, UTC+8)', value: 'Asia/Shanghai' },
  { label: 'Europe/London (GMT/BST)', value: 'Europe/London' },
  { label: 'Europe/Paris (CET/CEST)', value: 'Europe/Paris' },
  { label: 'Europe/Berlin (CET/CEST)', value: 'Europe/Berlin' },
  { label: 'America/New_York (EST/EDT)', value: 'America/New_York' },
  { label: 'America/Chicago (CST/CDT)', value: 'America/Chicago' },
  { label: 'America/Denver (MST/MDT)', value: 'America/Denver' },
  { label: 'America/Los_Angeles (PST/PDT)', value: 'America/Los_Angeles' },
  { label: 'Australia/Sydney (AEST/AEDT)', value: 'Australia/Sydney' },
  { label: 'Pacific/Auckland (NZST/NZDT)', value: 'Pacific/Auckland' },
];

export default function SettingsPage() {
  const [form] = Form.useForm();
  const [clientForm] = Form.useForm();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clientId, setClientId] = useState('');
  const [clientSaving, setClientSaving] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  // Load client locale settings when clientId changes
  useEffect(() => {
    if (!clientId) return;
    loadClientLocale(clientId);
  }, [clientId]);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await api.get<BusinessHoursSettings>('/auth/me/settings');
      form.setFieldsValue({
        timezone: data.timezone,
        business_hours_start: dayjs().hour(data.business_hours_start).minute(0),
        business_hours_end: dayjs().hour(data.business_hours_end).minute(0),
        business_days: data.business_days,
      });
    } catch (err) {
      message.error('Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const loadClientLocale = async (cid: string) => {
    try {
      const data = await api.get<any>(`/v1/clients/${cid}`);
      clientForm.setFieldsValue({
        client_timezone: data.timezone || 'Australia/Sydney',
        currency_code: data.currency_code || 'AUD',
      });
    } catch (err) {
      // silently fail — defaults remain
    }
  };

  const handleSave = async (values: any) => {
    try {
      setSaving(true);
      const payload: Partial<BusinessHoursSettings> = {
        timezone: values.timezone,
        business_hours_start: values.business_hours_start?.hour() ?? 9,
        business_hours_end: values.business_hours_end?.hour() ?? 18,
        business_days: values.business_days,
      };
      await api.patch<BusinessHoursSettings>('/auth/me/settings', payload);
      message.success('Business hours settings saved');
    } catch (err) {
      message.error('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleClientLocaleSave = async (values: any) => {
    if (!clientId) {
      message.warning('Select a client first');
      return;
    }
    try {
      setClientSaving(true);
      await api.patch(`/v1/clients/${clientId}`, {
        timezone: values.client_timezone,
        currency_code: values.currency_code,
      });
      message.success('Client locale settings saved');
    } catch (err) {
      message.error('Failed to save client settings');
    } finally {
      setClientSaving(false);
    }
  };

  // Detect browser timezone for suggestion
  const detectedTz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      <Title level={3}>Settings</Title>

      {/* ── Business Hours ─────────────────────────────────────────── */}
      <Card style={{ marginBottom: 24 }}>
        <Space direction="vertical" size="small" style={{ width: '100%', marginBottom: 16 }}>
          <Title level={5} style={{ margin: 0 }}>
            <GlobalOutlined style={{ marginRight: 8 }} />
            Timezone & Business Hours
          </Title>
          <Text type="secondary">
            Response time metrics will be calculated using only the hours that fall within your
            configured business hours. Wall-clock times are always stored alongside.
          </Text>
        </Space>

        <Divider style={{ margin: '12px 0 24px' }} />

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          initialValues={{
            timezone: 'UTC',
            business_hours_start: dayjs().hour(9).minute(0),
            business_hours_end: dayjs().hour(18).minute(0),
            business_days: [1, 2, 3, 4, 5],
          }}
        >
          <Form.Item
            label="Timezone"
            name="timezone"
            extra={`Detected: ${detectedTz}`}
          >
            <Select
              showSearch
              options={TIMEZONE_OPTIONS}
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase()) ||
                (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
              }
              placeholder="Select timezone"
            />
          </Form.Item>

          <Space size="large">
            <Form.Item label="Start" name="business_hours_start">
              <TimePicker format="HH:mm" minuteStep={30} allowClear={false} />
            </Form.Item>
            <Form.Item label="End" name="business_hours_end">
              <TimePicker format="HH:mm" minuteStep={30} allowClear={false} />
            </Form.Item>
          </Space>

          <Form.Item label="Business Days" name="business_days">
            <Checkbox.Group options={WEEKDAYS} />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button type="primary" htmlType="submit" loading={saving} icon={<ClockCircleOutlined />}>
              Save Business Hours
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {/* ── Client Locale Settings ─────────────────────────────────── */}
      <Card>
        <Space direction="vertical" size="small" style={{ width: '100%', marginBottom: 16 }}>
          <Title level={5} style={{ margin: 0 }}>
            <DollarOutlined style={{ marginRight: 8 }} />
            Client Locale (Admin)
          </Title>
          <Text type="secondary">
            Set the timezone and currency used for AI analysis, digests, and financial figures
            for each client. These affect how the AI interprets and formats numbers in all prompts.
          </Text>
        </Space>

        <Divider style={{ margin: '12px 0 24px' }} />

        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>Client</Text>
          <ClientSelector value={clientId} onChange={setClientId} style={{ width: '100%' }} />
        </div>

        <Form
          form={clientForm}
          layout="vertical"
          onFinish={handleClientLocaleSave}
          initialValues={{ client_timezone: 'Australia/Sydney', currency_code: 'AUD' }}
        >
          <Form.Item label="Client Timezone" name="client_timezone">
            <Select
              showSearch
              options={TIMEZONE_OPTIONS}
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase()) ||
                (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
              }
              placeholder="Select client timezone"
              disabled={!clientId}
            />
          </Form.Item>

          <Form.Item
            label="Currency"
            name="currency_code"
            extra="Used for all financial figures in AI prompts, digests, and insights."
          >
            <Select
              showSearch
              options={CURRENCY_OPTIONS}
              filterOption={(input, option) =>
                (option?.label as string)?.toLowerCase().includes(input.toLowerCase()) ||
                (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
              }
              placeholder="Select currency"
              disabled={!clientId}
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              loading={clientSaving}
              icon={<DollarOutlined />}
              disabled={!clientId}
            >
              Save Client Locale
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
