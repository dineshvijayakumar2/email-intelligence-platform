import React, { useMemo, useState } from 'react';
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  getFilteredRowModel, createColumnHelper, flexRender, type SortingState,
} from '@tanstack/react-table';
import { formatCurrency } from '../utils/numberFormat';
import { cn } from '@/lib/utils';
import { Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';

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

const col = createColumnHelper<OrderHistoryItem>();
const PAGE_SIZE = 15;

export const OrderHistoryTable: React.FC<Props> = ({ items, loading }) => {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'date', desc: true }]);
  const [globalFilter, setGlobalFilter] = useState('');
  const [page, setPage] = useState(1);

  const columns = useMemo(() => [
    col.accessor('date', {
      header: 'Date', size: 100, sortingFn: 'datetime',
      cell: info => {
        const v = info.getValue();
        return v ? <span className="text-slate-700">{new Date(v).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: '2-digit' })}</span> : <span className="text-slate-300">—</span>;
      },
    }),
    col.accessor('type', {
      header: 'Type', size: 60,
      cell: info => <span className="text-xs text-slate-500">{info.getValue() === 'quote' ? 'Quote' : 'Job'}</span>,
    }),
    col.accessor('ref_no', {
      header: 'Ref', size: 100,
      cell: info => <span className="text-xs font-mono text-slate-600">{info.getValue() || info.row.original.job_no || '—'}</span>,
    }),
    col.accessor('category', {
      header: 'Category',
      cell: info => <span className="text-slate-600">{info.getValue() || '—'}</span>,
    }),
    col.accessor('value', {
      header: 'Value', size: 100, meta: { align: 'right' },
      cell: info => info.getValue() != null ? <span className="tabular-nums font-medium">{formatCurrency(info.getValue())}</span> : <span className="text-slate-300">—</span>,
    }),
    col.accessor('status', {
      header: 'Status', size: 100,
      cell: info => {
        const v = info.getValue();
        if (!v) return <span className="text-slate-300">—</span>;
        return <span className="text-xs text-slate-500">{v}</span>;
      },
    }),
    col.accessor('contact_name', {
      header: 'Contact',
      cell: info => <span className="text-slate-600">{info.getValue() || info.row.original.contact_email || '—'}</span>,
    }),
  ], []);

  const table = useReactTable({
    data: items, columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  if (loading) return <div className="space-y-3 p-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-4 w-full" />)}</div>;
  if (!items.length) return <EmptyState title="No order history" />;

  const rows = table.getRowModel().rows;
  const totalRows = rows.length;
  const pagedRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const totalPages = Math.ceil(totalRows / PAGE_SIZE);

  return (
    <div>
      <div className="mb-2">
        <div className="relative inline-block">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search orders..."
            onChange={e => { setGlobalFilter(e.target.value); setPage(1); }}
            className="h-7 pl-7 pr-3 text-xs rounded border border-slate-200 bg-white focus:outline-none focus:ring-1 focus:ring-primary/20 w-44"
          />
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id} className="border-b bg-slate-50/50">
                {hg.headers.map(h => (
                  <th key={h.id} onClick={h.column.getCanSort() ? h.column.getToggleSortingHandler() : undefined}
                    className={cn('px-3 py-2 text-xs font-medium uppercase tracking-wider text-slate-500 whitespace-nowrap',
                      h.column.getCanSort() && 'cursor-pointer hover:text-slate-700',
                      (h.column.columnDef.meta as any)?.align === 'right' && 'text-right')}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {h.column.getCanSort() && <span className={cn('ml-1 text-[10px]', h.column.getIsSorted() ? 'opacity-100' : 'opacity-30')}>{h.column.getIsSorted() === 'asc' ? '▲' : h.column.getIsSorted() === 'desc' ? '▼' : '⇅'}</span>}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-50">
            {pagedRows.map(row => (
              <tr key={row.id} className="hover:bg-slate-50/50">
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} className={cn('px-3 py-2', (cell.column.columnDef.meta as any)?.align === 'right' && 'text-right')}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalRows > PAGE_SIZE && (
        <div className="flex items-center justify-between px-3 py-2 border-t">
          <span className="text-xs text-slate-500">{totalRows} orders</span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} className="p-1 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronLeft className="h-3.5 w-3.5" /></button>
            <span className="text-xs text-slate-600 px-2 tabular-nums">{page} / {totalPages}</span>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="p-1 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronRight className="h-3.5 w-3.5" /></button>
          </div>
        </div>
      )}
    </div>
  );
};
