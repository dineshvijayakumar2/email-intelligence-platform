/**
 * DataTable — TanStack Table wrapper with server-side pagination + sorting.
 * Drop-in replacement for AnalyticsTable on pages that need proper filtering.
 * Keeps Ant Design styling (Skeleton, Empty, Pagination) for visual consistency.
 */

import React from 'react';
import { Pagination, Skeleton, Empty } from 'antd';
import {
  flexRender,
  type Table as TanStackTable,
} from '@tanstack/react-table';

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
      <div className="glass-table-container" style={{ padding: 24 }}>
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    );
  }

  const rows = table.getRowModel().rows;

  if (!rows.length) {
    return (
      <div className="glass-table-container" style={{ padding: 24 }}>
        <Empty description={emptyText || 'No data available'} />
      </div>
    );
  }

  return (
    <div className="glass-table-container">
      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 14,
          }}
        >
          <thead>
            {table.getHeaderGroups().map(headerGroup => (
              <tr key={headerGroup.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                {headerGroup.headers.map(header => {
                  const canSort = header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                      style={{
                        padding: '10px 12px',
                        textAlign: (header.column.columnDef.meta as any)?.align || 'left',
                        fontWeight: 500,
                        fontSize: 13,
                        color: 'rgba(255,255,255,0.65)',
                        cursor: canSort ? 'pointer' : 'default',
                        userSelect: canSort ? 'none' : undefined,
                        width: header.column.columnDef.size || undefined,
                        minWidth: header.column.columnDef.minSize || undefined,
                        maxWidth: header.column.columnDef.maxSize || undefined,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {canSort && (
                        <span style={{ marginLeft: 4, opacity: sorted ? 1 : 0.3 }}>
                          {sorted === 'asc' ? '↑' : sorted === 'desc' ? '↓' : '↕'}
                        </span>
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {rows.map(row => (
              <tr
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                style={{
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  cursor: onRowClick ? 'pointer' : 'default',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.03)'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
              >
                {row.getVisibleCells().map(cell => (
                  <td
                    key={cell.id}
                    style={{
                      padding: '10px 12px',
                      textAlign: (cell.column.columnDef.meta as any)?.align || 'left',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      maxWidth: cell.column.columnDef.maxSize || undefined,
                    }}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > pageSize && onPageChange && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '16px 16px 8px' }}>
          <Pagination
            current={currentPage}
            pageSize={pageSize}
            total={total}
            onChange={onPageChange}
            showSizeChanger={false}
            showTotal={(t) => `${t} total`}
          />
        </div>
      )}
    </div>
  );
}
