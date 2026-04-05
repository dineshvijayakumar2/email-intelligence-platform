import React, { useMemo, useState } from 'react';
import { Card, Tag, Spin, Typography, Space, Button, Tooltip } from 'antd';
import { ReloadOutlined, UserOutlined } from '@ant-design/icons';
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  createColumnHelper, flexRender, type SortingState,
} from '@tanstack/react-table';
import { useQuery } from '@tanstack/react-query';
import { companiesApi } from '../services/analyticsService';

const { Text } = Typography;

const TAG_COLORS: Record<string, string> = {
  'Flat Sheets': '#3B82F6', 'Soft Cover Books': '#10B981', 'Hard Cover Books': '#8B5CF6',
  'Wide Format': '#F59E0B', 'Embellishment': '#EC4899', 'Specialty Finishing': '#EF4444',
  'Design Services': '#6366F1', 'Display / Installation': '#14B8A6',
};

const col = createColumnHelper<any>();

const ContactCapabilitiesCard: React.FC<{ companyId: string }> = ({ companyId }) => {
  const [sorting, setSorting] = useState<SortingState>([]);
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['contact-capabilities', companyId],
    queryFn: () => companiesApi.getContactCapabilities(companyId),
    enabled: !!companyId, staleTime: 60_000,
  });

  const columns = useMemo(() => [
    col.accessor('contact_name', {
      header: 'Contact', size: 180,
      cell: info => (
        <Tooltip title={info.row.original.contact_email}>
          <Space size={4}><UserOutlined style={{ fontSize: 11, color: '#999' }} /><span>{info.getValue() || info.row.original.contact_email}</span></Space>
        </Tooltip>
      ),
    }),
    col.accessor('primary_capability', {
      header: 'Primary', size: 140,
      cell: info => info.getValue() ? <Tag color={TAG_COLORS[info.getValue()] || 'blue'} style={{ fontSize: 11 }}>{info.getValue()}</Tag> : '—',
    }),
    col.accessor('capabilities', {
      header: 'Capabilities', enableSorting: false,
      cell: info => (
        <Space size={2} wrap>
          {(info.getValue() || []).map((c: any) => (
            <Tooltip key={c.tag} title={`${c.order_count} orders, $${Number(c.total_revenue).toLocaleString()}, last: ${c.last_order || '—'}`}>
              <Tag color={TAG_COLORS[c.tag] || 'default'} style={{ fontSize: 10, padding: '0 4px', cursor: 'help' }}>{c.tag} ({c.order_count})</Tag>
            </Tooltip>
          ))}
        </Space>
      ),
    }),
  ], []);

  const table = useReactTable({
    data: data?.contacts || [], columns,
    state: { sorting }, onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(),
  });

  if (isLoading) return <Card className="glass-card" title="Contact Capabilities"><Spin /></Card>;
  if (!data?.contacts?.length) return <Card className="glass-card" title="Contact Capabilities"><Text type="secondary">No contact capability data — requires classified operations with contact_email</Text></Card>;

  return (
    <Card className="glass-card" title={<Space><UserOutlined />Contact Capabilities</Space>} extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => refetch()}>Refresh</Button>}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id} style={{ borderBottom: '1px solid var(--ant-color-border, #f0f0f0)', background: 'var(--ant-color-bg-container-secondary, rgba(0,0,0,0.02))' }}>
                {hg.headers.map(h => (
                  <th key={h.id} onClick={h.column.getCanSort() ? h.column.getToggleSortingHandler() : undefined}
                    style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 600, fontSize: 12, color: 'var(--ant-color-text-secondary)', cursor: h.column.getCanSort() ? 'pointer' : 'default', whiteSpace: 'nowrap' }}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {h.column.getCanSort() && <span style={{ marginLeft: 4, opacity: h.column.getIsSorted() ? 1 : 0.3, fontSize: 10 }}>{h.column.getIsSorted() === 'asc' ? '▲' : h.column.getIsSorted() === 'desc' ? '▼' : '⇅'}</span>}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map(row => (
              <tr key={row.id} style={{ borderBottom: '1px solid var(--ant-color-border-secondary, #f5f5f5)' }}>
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} style={{ padding: '8px 10px' }}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.computed_at && <Text type="secondary" style={{ fontSize: 11, marginTop: 8, display: 'block' }}>Computed: {new Date(data.computed_at).toLocaleString()}</Text>}
    </Card>
  );
};

export default ContactCapabilitiesCard;
