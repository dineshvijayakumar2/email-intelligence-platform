import React from 'react';
import { Table, Tag, Typography } from 'antd';
import { formatCurrency } from '../utils/numberFormat';

const { Text } = Typography;

interface OrderHistoryItem {
  type: 'quote' | 'job';
  date?: string;
  ref_no?: string;
  category?: string;
  value?: number;
  status?: string;
  contact_name?: string;
  contact_email?: string;
  job_no?: string;
  due_date?: string;
  quote_no?: string;
}

interface Props {
  items: OrderHistoryItem[];
  loading?: boolean;
}

const statusColor: Record<string, string> = {
  Accepted: 'green',
  Quoted: 'blue',
  Complete: 'green',
  'In Progress': 'orange',
  Invoiced: 'purple',
  Cancelled: 'red',
};

const columns = [
  {
    title: 'Date',
    dataIndex: 'date',
    key: 'date',
    width: 100,
    render: (v: string) => v ? new Date(v).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: '2-digit' }) : '-',
  },
  {
    title: 'Type',
    dataIndex: 'type',
    key: 'type',
    width: 70,
    render: (v: string) => (
      <Tag color={v === 'quote' ? 'blue' : 'green'} style={{ fontSize: 11 }}>
        {v === 'quote' ? 'Quote' : 'Job'}
      </Tag>
    ),
  },
  {
    title: 'Ref',
    key: 'ref',
    width: 110,
    render: (_: any, r: OrderHistoryItem) => (
      <Text code style={{ fontSize: 12 }}>{r.ref_no || r.job_no || '-'}</Text>
    ),
  },
  {
    title: 'Category',
    dataIndex: 'category',
    key: 'category',
    ellipsis: true,
    render: (v: string) => v || '-',
  },
  {
    title: 'Value',
    dataIndex: 'value',
    key: 'value',
    width: 110,
    align: 'right' as const,
    render: (v: number) => v != null ? formatCurrency(v) : '-',
  },
  {
    title: 'Status',
    dataIndex: 'status',
    key: 'status',
    width: 110,
    render: (v: string) => v ? (
      <Tag color={statusColor[v] || 'default'} style={{ fontSize: 11 }}>{v}</Tag>
    ) : '-',
  },
  {
    title: 'Contact',
    key: 'contact',
    ellipsis: true,
    render: (_: any, r: OrderHistoryItem) => r.contact_name || r.contact_email || '-',
  },
];

export const OrderHistoryTable: React.FC<Props> = ({ items, loading }) => (
  <Table
    columns={columns}
    dataSource={items}
    rowKey={(r, i) => `${r.type}-${r.ref_no || i}`}
    size="small"
    loading={loading}
    pagination={items.length > 15 ? { pageSize: 15, size: 'small' } : false}
  />
);
