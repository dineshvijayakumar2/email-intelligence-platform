import React from 'react';
import { Table, Pagination, Skeleton, Empty } from 'antd';
import type { ColumnsType } from 'antd/es/table';

interface AnalyticsTableProps<T> {
  columns: ColumnsType<T>;
  data: T[];
  total: number;
  loading?: boolean;
  pageSize?: number;
  currentPage?: number;
  onPageChange?: (page: number, pageSize: number) => void;
  onRowClick?: (record: T) => void;
  rowKey?: string | ((record: T) => string);
  size?: 'small' | 'middle' | 'large';
}

export function AnalyticsTable<T extends Record<string, any>>({
  columns,
  data,
  total,
  loading = false,
  pageSize = 20,
  currentPage = 1,
  onPageChange,
  onRowClick,
  rowKey = 'id',
  size = 'middle',
}: AnalyticsTableProps<T>) {
  if (loading) {
    return (
      <div className="glass-table-container" style={{ padding: 24 }}>
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="glass-table-container" style={{ padding: 24 }}>
        <Empty description="No data available" />
      </div>
    );
  }

  return (
    <div className="glass-table-container">
      <Table<T>
        columns={columns}
        dataSource={data}
        rowKey={rowKey}
        size={size}
        pagination={false}
        onRow={onRowClick ? (record) => ({
          onClick: () => onRowClick(record),
          style: { cursor: 'pointer' },
        }) : undefined}
      />
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
