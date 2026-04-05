import React, { useMemo, useState } from 'react';
import { Tag, Typography, Input, Pagination, Skeleton, Empty } from 'antd';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  createColumnHelper,
  flexRender,
  type SortingState,
} from '@tanstack/react-table';
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
}

interface Props {
  items: OrderHistoryItem[];
  loading?: boolean;
}

const statusColor: Record<string, string> = {
  Accepted: 'green', Quoted: 'blue', Complete: 'green', 'R-Complete': 'green',
  'In Progress': 'orange', Invoiced: 'purple', Cancelled: 'red',
};

const col = createColumnHelper<OrderHistoryItem>();

export const OrderHistoryTable: React.FC<Props> = ({ items, loading }) => {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'date', desc: true }]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 15;

  const columns = useMemo(() => [
    col.accessor('date', {
      header: 'Date',
      size: 100,
      cell: info => {
        const v = info.getValue();
        return v ? new Date(v).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: '2-digit' }) : '-';
      },
      sortingFn: 'datetime',
    }),
    col.accessor('type', {
      header: 'Type',
      size: 70,
      cell: info => <Tag color={info.getValue() === 'quote' ? 'blue' : 'green'} style={{ fontSize: 11 }}>{info.getValue() === 'quote' ? 'Quote' : 'Job'}</Tag>,
    }),
    col.accessor('ref_no', {
      header: 'Ref',
      size: 110,
      cell: info => <Text code style={{ fontSize: 12 }}>{info.getValue() || info.row.original.job_no || '-'}</Text>,
    }),
    col.accessor('category', {
      header: 'Category',
      cell: info => info.getValue() || '-',
    }),
    col.accessor('value', {
      header: 'Value',
      size: 110,
      meta: { align: 'right' },
      cell: info => info.getValue() != null ? formatCurrency(info.getValue()) : '-',
    }),
    col.accessor('status', {
      header: 'Status',
      size: 110,
      cell: info => {
        const v = info.getValue();
        return v ? <Tag color={statusColor[v] || 'default'} style={{ fontSize: 11 }}>{v}</Tag> : '-';
      },
    }),
    col.accessor('contact_name', {
      header: 'Contact',
      cell: info => info.getValue() || info.row.original.contact_email || '-',
    }),
  ], []);

  const table = useReactTable({
    data: items,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (loading) return <Skeleton active paragraph={{ rows: 5 }} />;
  if (!items.length) return <Empty description="No order history" />;

  const rows = table.getRowModel().rows;
  const totalRows = rows.length;
  const pagedRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <Input.Search
          placeholder="Search orders..."
          allowClear
          size="small"
          style={{ width: 200 }}
          onSearch={v => { setGlobalFilter(v); setPage(1); }}
        />
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id} style={{ borderBottom: '1px solid var(--ant-color-border, #f0f0f0)', background: 'var(--ant-color-bg-container-secondary, rgba(0,0,0,0.02))' }}>
                {hg.headers.map(h => (
                  <th key={h.id} onClick={h.column.getCanSort() ? h.column.getToggleSortingHandler() : undefined}
                    style={{ padding: '8px 10px', textAlign: (h.column.columnDef.meta as any)?.align || 'left', fontWeight: 600, fontSize: 12, color: 'var(--ant-color-text-secondary, rgba(0,0,0,0.65))', cursor: h.column.getCanSort() ? 'pointer' : 'default', whiteSpace: 'nowrap' }}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {h.column.getCanSort() && <span style={{ marginLeft: 4, opacity: h.column.getIsSorted() ? 1 : 0.3, fontSize: 10 }}>{h.column.getIsSorted() === 'asc' ? '▲' : h.column.getIsSorted() === 'desc' ? '▼' : '⇅'}</span>}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {pagedRows.map(row => (
              <tr key={row.id} style={{ borderBottom: '1px solid var(--ant-color-border-secondary, #f5f5f5)' }}>
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
      {totalRows > PAGE_SIZE && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '12px 0' }}>
          <Pagination current={page} pageSize={PAGE_SIZE} total={totalRows} onChange={setPage} showSizeChanger={false} showTotal={t => `${t} orders`} size="small" />
        </div>
      )}
    </div>
  );
};
