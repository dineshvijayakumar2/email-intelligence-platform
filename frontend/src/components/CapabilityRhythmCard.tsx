import React, { useMemo, useState } from 'react';
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  createColumnHelper, flexRender, type SortingState,
} from '@tanstack/react-table';
import { useQuery } from '@tanstack/react-query';
import { companiesApi } from '../services/analyticsService';
import { RefreshCw, Clock, AlertTriangle } from 'lucide-react';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { cn } from '@/lib/utils';

interface Props { companyId: string; }
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
    col.accessor('capability', { header: 'Capability', size: 160,
      cell: info => <span className="text-sm text-slate-800">{info.getValue()}</span>,
    }),
    col.accessor('order_count', { header: 'Orders', size: 60, meta: { align: 'right' },
      cell: info => <span className="tabular-nums">{info.getValue()}</span>,
    }),
    col.accessor('avg_interval_days', { header: 'Typical Interval', size: 90,
      cell: info => {
        const v = info.getValue();
        if (v == null) return <span className="text-slate-300">—</span>;
        const weeks = Math.round(v / 7);
        return <span className="text-slate-600">{weeks > 0 ? `~${weeks}w` : `${v}d`}</span>;
      },
    }),
    col.accessor('days_since_last', { header: 'Since Last', size: 75, meta: { align: 'right' },
      cell: info => {
        const v = info.getValue();
        const overdue = info.row.original.overdue;
        return <span className={cn('tabular-nums', overdue ? 'text-destructive font-medium' : 'text-slate-600')}>{v != null ? `${v}d` : '—'}</span>;
      },
    }),
    col.accessor('status', { header: 'Status', size: 100,
      cell: info => {
        const v = info.getValue();
        const r = info.row.original;
        const variant = v === 'overdue' ? 'danger' : v === 'due_soon' ? 'warning' : v === 'on_track' ? 'success' : 'neutral';
        const label = v === 'overdue' ? `${r.overdue_days}d overdue` : v === 'due_soon' ? 'Due soon' : v === 'on_track' ? 'On track' : 'Low data';
        return <StatusBadge variant={variant as any} size="sm">{label}</StatusBadge>;
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

  const overdueCount = data?.alerts?.length || 0;

  if (isLoading) return <div className="rounded-lg border bg-white shadow-sm p-4"><div className="flex items-center gap-2 mb-3"><Clock className="h-4 w-4 text-primary" /><span className="text-sm font-semibold">Ordering Rhythm</span></div><ContentSkeleton rows={3} className="p-0" /></div>;
  if (!data?.rhythms?.length) return <div className="rounded-lg border bg-white shadow-sm p-4"><div className="flex items-center gap-2"><Clock className="h-4 w-4 text-primary" /><span className="text-sm font-semibold">Ordering Rhythm</span></div><p className="text-sm text-slate-400 mt-2">No data available</p></div>;

  return (
    <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-primary" />
          <span className="text-sm font-bold text-slate-900">Ordering Rhythm</span>
          {overdueCount > 0 && <StatusBadge variant="danger" size="sm"><AlertTriangle className="h-3 w-3 mr-1 inline" />{overdueCount} overdue</StatusBadge>}
        </div>
        <button onClick={() => refetch()} className="p-1 rounded hover:bg-slate-100"><RefreshCw className="h-3.5 w-3.5 text-slate-400" /></button>
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
            {table.getRowModel().rows.map(row => (
              <tr key={row.id} className={cn(row.original.overdue && 'bg-red-50/30')}>
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
    </div>
  );
};

export default CapabilityRhythmCard;
