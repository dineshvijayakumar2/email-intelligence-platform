import React, { useMemo, useState } from 'react';
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  createColumnHelper, flexRender, type SortingState,
} from '@tanstack/react-table';
import { useQuery } from '@tanstack/react-query';
import { companiesApi } from '../services/analyticsService';
import { RefreshCw, User } from 'lucide-react';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { cn } from '@/lib/utils';
import { formatCurrency } from '../utils/numberFormat';

const col = createColumnHelper<any>();

const ContactCapabilitiesCard: React.FC<{ companyId: string }> = ({ companyId }) => {
  const [sorting, setSorting] = useState<SortingState>([]);
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['contact-capabilities', companyId],
    queryFn: () => companiesApi.getContactCapabilities(companyId),
    enabled: !!companyId, staleTime: 60_000,
  });

  const columns = useMemo(() => [
    col.accessor('contact_name', { header: 'Contact', size: 180,
      cell: info => (
        <span className="text-sm text-slate-800" title={info.row.original.contact_email}>
          {info.getValue() || info.row.original.contact_email}
        </span>
      ),
    }),
    col.accessor('primary_capability', { header: 'Primary', size: 130,
      cell: info => info.getValue() ? <span className="text-sm font-medium text-slate-700">{info.getValue()}</span> : <span className="text-slate-300">—</span>,
    }),
    col.accessor('capabilities', { header: 'Capabilities', enableSorting: false,
      cell: info => (
        <div className="flex flex-wrap gap-1">
          {(info.getValue() || []).map((c: any) => (
            <span key={c.tag} className="inline-flex items-center px-1.5 py-0 text-[11px] rounded bg-slate-100 text-slate-600" title={`${c.order_count} orders, ${formatCurrency(Number(c.total_revenue))}`}>
              {c.tag} ({c.order_count})
            </span>
          ))}
        </div>
      ),
    }),
  ], []);

  const table = useReactTable({
    data: data?.contacts || [], columns,
    state: { sorting }, onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(),
  });

  if (isLoading) return <div className="rounded-lg border bg-white shadow-sm p-4"><div className="flex items-center gap-2 mb-3"><User className="h-4 w-4 text-primary" /><span className="text-sm font-semibold">Contact Capabilities</span></div><ContentSkeleton rows={3} className="p-0" /></div>;
  if (!data?.contacts?.length) return <div className="rounded-lg border bg-white shadow-sm p-4"><div className="flex items-center gap-2"><User className="h-4 w-4 text-primary" /><span className="text-sm font-semibold">Contact Capabilities</span></div><p className="text-sm text-slate-400 mt-2">No contact capability data</p></div>;

  return (
    <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2"><User className="h-4 w-4 text-primary" /><span className="text-sm font-bold text-slate-900">Contact Capabilities</span></div>
        <button onClick={() => refetch()} className="p-1 rounded hover:bg-slate-100"><RefreshCw className="h-3.5 w-3.5 text-slate-400" /></button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id} className="border-b bg-slate-50/50">
                {hg.headers.map(h => (
                  <th key={h.id} onClick={h.column.getCanSort() ? h.column.getToggleSortingHandler() : undefined}
                    className={cn('px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-slate-500 whitespace-nowrap', h.column.getCanSort() && 'cursor-pointer hover:text-slate-700')}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {h.column.getCanSort() && <span className={cn('ml-1 text-[10px]', h.column.getIsSorted() ? 'opacity-100' : 'opacity-30')}>{h.column.getIsSorted() === 'asc' ? '▲' : h.column.getIsSorted() === 'desc' ? '▼' : '⇅'}</span>}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-50">
            {table.getRowModel().rows.map(row => (
              <tr key={row.id} className="hover:bg-slate-50/50">
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} className="px-3 py-2">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ContactCapabilitiesCard;
