import React, { useMemo, useState } from 'react';
import { Card, Tag, Spin, Typography, Space, Button, Badge, Alert } from 'antd';
import { ReloadOutlined, ClockCircleOutlined, WarningOutlined } from '@ant-design/icons';
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  createColumnHelper, flexRender, type SortingState,
} from '@tanstack/react-table';
import { useQuery } from '@tanstack/react-query';
import { companiesApi } from '../services/analyticsService';

const { Text } = Typography;

interface Props { companyId: string; }

const STATUS_CONFIG: Record<string, { color: string; badge: 'success' | 'warning' | 'error' | 'default' }> = {
  on_track: { color: 'green', badge: 'success' },
  due_soon: { color: 'orange', badge: 'warning' },
  overdue: { color: 'red', badge: 'error' },
  insufficient_data: { color: 'default', badge: 'default' },
};

const col = createColumnHelper<any>();

const CapabilityRhythmCard: React.FC<Props> = ({ companyId }) => {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'days_since_last', desc: true }]);
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['capability-rhythm', companyId],
    queryFn: () => companiesApi.getCapabilityRhythm(companyId),
    enabled: !!companyId,
    staleTime: 60_000,
  });

  const columns = useMemo(() => [
    col.accessor('capability', {
      header: 'Capability', size: 160,
      cell: info => <Tag color="blue" style={{ fontSize: 11 }}>{info.getValue()}</Tag>,
    }),
    col.accessor('order_count', { header: 'Orders', size: 65, meta: { align: 'right' } }),
    col.accessor('avg_interval_days', {
      header: 'Avg Interval', size: 100,
      cell: info => {
        const v = info.getValue();
        if (v == null) return <Text type="secondary">—</Text>;
        const weeks = Math.round(v / 7);
        return weeks > 0 ? `~${weeks} weeks` : `${v} days`;
      },
    }),
    col.accessor('last_order_date', {
      header: 'Last Order', size: 100,
      cell: info => info.getValue() ? new Date(info.getValue()).toLocaleDateString() : '—',
    }),
    col.accessor('days_since_last', {
      header: 'Days Since', size: 80, meta: { align: 'right' },
      cell: info => <Text type={info.row.original.overdue ? 'danger' : undefined}>{info.getValue() != null ? `${info.getValue()}d` : '—'}</Text>,
    }),
    col.accessor('status', {
      header: 'Status', size: 110,
      cell: info => {
        const v = info.getValue();
        const r = info.row.original;
        const cfg = STATUS_CONFIG[v] || STATUS_CONFIG.insufficient_data;
        return <Badge status={cfg.badge} text={<Text style={{ fontSize: 11, color: r.overdue ? '#ff4d4f' : undefined }}>{v === 'overdue' ? `${r.overdue_days}d overdue` : v === 'due_soon' ? 'Due soon' : v === 'on_track' ? 'On track' : 'Low data'}</Text>} />;
      },
    }),
  ], []);

  const table = useReactTable({
    data: data?.rhythms || [],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (isLoading) return <Card className="glass-card" title="Ordering Rhythm"><Spin /></Card>;
  if (!data?.rhythms?.length) return <Card className="glass-card" title="Ordering Rhythm"><Text type="secondary">No classified operations with dates available</Text></Card>;

  const overdueCount = data.alerts?.length || 0;

  return (
    <Card className="glass-card"
      title={<Space><ClockCircleOutlined /> Ordering Rhythm {overdueCount > 0 && <Tag color="red" icon={<WarningOutlined />}>{overdueCount} overdue</Tag>}</Space>}
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => refetch()}>Refresh</Button>}>
      {overdueCount > 0 && (
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message={<span>{data.alerts.map((a: any) => <Tag key={a.capability} color={a.severity === 'danger' ? 'red' : 'orange'} style={{ fontSize: 11 }}>{a.capability}: {a.overdue_days}d overdue</Tag>)}</span>} />
      )}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id} style={{ borderBottom: '1px solid var(--ant-color-border, #f0f0f0)', background: 'var(--ant-color-bg-container-secondary, rgba(0,0,0,0.02))' }}>
                {hg.headers.map(h => (
                  <th key={h.id} onClick={h.column.getCanSort() ? h.column.getToggleSortingHandler() : undefined}
                    style={{ padding: '8px 10px', textAlign: (h.column.columnDef.meta as any)?.align || 'left', fontWeight: 600, fontSize: 12, color: 'var(--ant-color-text-secondary)', cursor: h.column.getCanSort() ? 'pointer' : 'default', whiteSpace: 'nowrap' }}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {h.column.getCanSort() && <span style={{ marginLeft: 4, opacity: h.column.getIsSorted() ? 1 : 0.3, fontSize: 10 }}>{h.column.getIsSorted() === 'asc' ? '▲' : h.column.getIsSorted() === 'desc' ? '▼' : '⇅'}</span>}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map(row => (
              <tr key={row.id} style={{ borderBottom: '1px solid var(--ant-color-border-secondary, #f5f5f5)', background: row.original.overdue ? 'rgba(255,77,79,0.04)' : undefined }}>
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} style={{ padding: '8px 10px', textAlign: (cell.column.columnDef.meta as any)?.align || 'left' }}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
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

export default CapabilityRhythmCard;
