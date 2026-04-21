/**
 * DataTable — TanStack Table wrapper with Tailwind styling.
 * Server-side pagination + sortable column headers.
 * Zero antd dependency.
 */

import React from 'react';
import {
  flexRender,
  type Table as TanStackTable,
} from '@tanstack/react-table';
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/ui/empty-state';
import { ChevronLeft, ChevronRight, Database } from 'lucide-react';

interface DataTableProps<T> {
  table: TanStackTable<T>;
  total: number;
  loading?: boolean;
  pageSize?: number;
  currentPage?: number;
  onPageChange?: (page: number) => void;
  onRowClick?: (record: T) => void;
  emptyText?: string;
}

export function DataTable<T>({
  table,
  total,
  loading = false,
  pageSize = 20,
  currentPage = 1,
  onPageChange,
  onRowClick,
  emptyText,
}: DataTableProps<T>) {
  if (loading) {
    return (
      <div className="rounded-lg border bg-white shadow-sm p-6 space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex gap-4">
            <Skeleton className="h-4 w-1/4" />
            <Skeleton className="h-4 w-1/6" />
            <Skeleton className="h-4 w-1/5" />
            <Skeleton className="h-4 w-1/6" />
          </div>
        ))}
      </div>
    );
  }

  const rows = table.getRowModel().rows;

  if (!rows.length) {
    return (
      <div className="rounded-lg border bg-white shadow-sm">
        <EmptyState
          icon={<Database className="h-10 w-10" />}
          title={emptyText || 'No data available'}
        />
      </div>
    );
  }

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map(headerGroup => (
              <tr key={headerGroup.id} className="border-b bg-slate-50/50">
                {headerGroup.headers.map(header => {
                  const canSort = header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  const align = (header.column.columnDef.meta as any)?.align || 'left';
                  return (
                    <th
                      key={header.id}
                      onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                      className={cn(
                        'px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-slate-500 whitespace-nowrap',
                        canSort && 'cursor-pointer select-none hover:text-slate-700',
                        align === 'right' && 'text-right',
                        align === 'center' && 'text-center',
                      )}
                      style={{
                        width: header.column.columnDef.size || undefined,
                        minWidth: header.column.columnDef.minSize || undefined,
                      }}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {canSort && (
                        <span className={cn('ml-1 text-[10px]', sorted ? 'opacity-100' : 'opacity-30')}>
                          {sorted === 'asc' ? '▲' : sorted === 'desc' ? '▼' : '⇅'}
                        </span>
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map(row => (
              <tr
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                className={cn(
                  'transition-colors',
                  onRowClick && 'cursor-pointer hover:bg-slate-50',
                )}
              >
                {row.getVisibleCells().map(cell => {
                  const align = (cell.column.columnDef.meta as any)?.align || 'left';
                  const wrap = (cell.column.columnDef.meta as any)?.wrap;
                  return (
                    <td
                      key={cell.id}
                      className={cn(
                        'px-3 py-2.5 text-sm text-slate-700',
                        wrap ? 'break-words' : 'whitespace-nowrap',
                        align === 'right' && 'text-right',
                        align === 'center' && 'text-center',
                      )}
                      style={{
                        maxWidth: cell.column.columnDef.maxSize || undefined,
                        minWidth: cell.column.columnDef.minSize || undefined,
                      }}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > pageSize && onPageChange && (
        <div className="flex items-center justify-between px-4 py-3 border-t bg-slate-50/30">
          <span className="text-xs text-slate-500">
            {((currentPage - 1) * pageSize + 1).toLocaleString('en-AU')}–{Math.min(currentPage * pageSize, total).toLocaleString('en-AU')} of {total.toLocaleString('en-AU')}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPageChange(currentPage - 1)}
              disabled={currentPage <= 1}
              className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="text-xs text-slate-600 px-2 tabular-nums">
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => onPageChange(currentPage + 1)}
              disabled={currentPage >= totalPages}
              className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
