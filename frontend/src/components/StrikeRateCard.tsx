import React, { useMemo, useState } from 'react';
import { Card, Statistic, Row, Col, Tag, Spin, Typography, Space, Button } from 'antd';
import { ReloadOutlined, RiseOutlined } from '@ant-design/icons';
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  createColumnHelper, flexRender, type SortingState,
} from '@tanstack/react-table';
import { useQuery } from '@tanstack/react-query';
import { companiesApi } from '../services/analyticsService';

const { Text } = Typography;
const col = createColumnHelper<any>();

const StrikeRateCard: React.FC<{ companyId: string }> = ({ companyId }) => {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'strike_rate_pct', desc: true }]);
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['strike-rate', companyId],
    queryFn: () => companiesApi.getStrikeRate(companyId),
    enabled: !!companyId, staleTime: 60_000,
  });

  const contactColumns = useMemo(() => [
    col.accessor('contact_name', {
      header: 'Contact',
      cell: info => info.getValue() || info.row.original.contact_email,
    }),
    col.accessor('total_quotes', { header: 'Quotes', size: 70, meta: { align: 'right' } }),
    col.accessor('converted', { header: 'Jobs', size: 60, meta: { align: 'right' } }),
    col.accessor('strike_rate_pct', {
      header: 'Rate', size: 70, meta: { align: 'right' },
      cell: info => <Text style={{ color: info.getValue() >= 60 ? '#52c41a' : info.getValue() >= 40 ? '#faad14' : '#ff4d4f' }}>{info.getValue()}%</Text>,
    }),
  ], []);

  const table = useReactTable({
    data: data?.by_contact || [], columns: contactColumns,
    state: { sorting }, onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(),
  });

  if (isLoading) return <Card className="glass-card" title="Strike Rate"><Spin /></Card>;
  if (!data?.company_total?.total_quotes) return <Card className="glass-card" title="Strike Rate"><Text type="secondary">No quote data available</Text></Card>;

  const { company_total, by_year } = data;
  const rateColor = company_total.strike_rate_pct >= 60 ? '#52c41a' : company_total.strike_rate_pct >= 40 ? '#faad14' : '#ff4d4f';

  return (
    <Card className="glass-card" title={<Space><RiseOutlined />Strike Rate</Space>} extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => refetch()}>Refresh</Button>}>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={8}><Statistic title="Conversion Rate" value={company_total.strike_rate_pct} suffix="%" valueStyle={{ color: rateColor, fontSize: 28 }} /></Col>
        <Col xs={8}><Statistic title="Total Quotes" value={company_total.total_quotes} /></Col>
        <Col xs={8}><Statistic title="Converted to Jobs" value={company_total.converted} /></Col>
      </Row>

      {by_year?.length > 1 && (
        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ fontSize: 12, marginBottom: 8, display: 'block' }}>Year-over-Year</Text>
          <Space wrap>{by_year.map((y: any) => <Tag key={y.year} color={y.strike_rate_pct >= 60 ? 'green' : y.strike_rate_pct >= 40 ? 'orange' : 'red'}>{y.year}: {y.strike_rate_pct}% ({y.converted}/{y.total_quotes})</Tag>)}</Space>
        </div>
      )}

      {table.getRowModel().rows.length > 0 && (
        <>
          <Text strong style={{ fontSize: 12, marginBottom: 8, display: 'block' }}>Per Contact</Text>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                {table.getHeaderGroups().map(hg => (
                  <tr key={hg.id} style={{ borderBottom: '1px solid var(--ant-color-border, #f0f0f0)', background: 'var(--ant-color-bg-container-secondary, rgba(0,0,0,0.02))' }}>
                    {hg.headers.map(h => (
                      <th key={h.id} onClick={h.column.getCanSort() ? h.column.getToggleSortingHandler() : undefined}
                        style={{ padding: '6px 10px', textAlign: (h.column.columnDef.meta as any)?.align || 'left', fontWeight: 600, fontSize: 12, color: 'var(--ant-color-text-secondary)', cursor: h.column.getCanSort() ? 'pointer' : 'default', whiteSpace: 'nowrap' }}>
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
                      <td key={cell.id} style={{ padding: '6px 10px', textAlign: (cell.column.columnDef.meta as any)?.align || 'left' }}>
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {data.computed_at && <Text type="secondary" style={{ fontSize: 11, marginTop: 8, display: 'block' }}>Computed: {new Date(data.computed_at).toLocaleString()}</Text>}
    </Card>
  );
};

export default StrikeRateCard;
