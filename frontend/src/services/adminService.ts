/**
 * Admin Data View Service
 *
 * API client for the admin table browser endpoints.
 */

import api from './apiClient';

// ============================================================================
// TYPES
// ============================================================================

export interface TableInfo {
  table_name: string;
  display_name: string;
  row_count: number;
  searchable: boolean;
}

export interface TableListResponse {
  tables: TableInfo[];
}

export interface TableDataResponse {
  table_name: string;
  display_name: string;
  columns: string[];
  data: Record<string, any>[];
  total: number;
  limit: number;
  offset: number;
}

export interface TableDataParams {
  search?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

// ============================================================================
// SERVICE
// ============================================================================

const API_PREFIX = '/v1/admin';

export const adminService = {
  async listTables(): Promise<TableListResponse> {
    const result = await api.get<TableListResponse>(
      `${API_PREFIX}/tables`,
      { timeout: 30000, retries: 1 }
    );
    return result || { tables: [] };
  },

  async getTableData(
    tableName: string,
    params: TableDataParams = {}
  ): Promise<TableDataResponse> {
    const queryParams = new URLSearchParams();
    if (params.search) queryParams.set('search', params.search);
    if (params.sort_by) queryParams.set('sort_by', params.sort_by);
    if (params.sort_dir) queryParams.set('sort_dir', params.sort_dir);
    if (params.limit !== undefined) queryParams.set('limit', String(params.limit));
    if (params.offset !== undefined) queryParams.set('offset', String(params.offset));

    const qs = queryParams.toString();
    const url = `${API_PREFIX}/tables/${tableName}${qs ? '?' + qs : ''}`;

    const result = await api.get<TableDataResponse>(url, { timeout: 20000 });
    return result || {
      table_name: tableName,
      display_name: tableName,
      columns: [],
      data: [],
      total: 0,
      limit: 50,
      offset: 0,
    };
  },
};

export default adminService;
