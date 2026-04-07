/**
 * Admin Data View — Raw table browser. Zero antd.
 */
import React, { useState, useEffect, useMemo, useRef } from 'react';
import { adminService, TableInfo, TableDataResponse } from '../services/adminService';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { ContentSkeleton, EmptyState } from '@/components/ui/empty-state';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import { Search, RefreshCw, Download, Database, ChevronLeft, ChevronRight } from 'lucide-react';

const PAGE_SIZE_OPTIONS = [25, 50, 100, 250];

const AdminDataViewPage: React.FC = () => {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [tablesLoading, setTablesLoading] = useState(true);
  const [selectedTable, setSelectedTable] = useState('');
  const [tableData, setTableData] = useState<TableDataResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [pageSize, setPageSize] = useState(50);
  const [currentPage, setCurrentPage] = useState(1);
  const [sortBy, setSortBy] = useState('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [refreshKey, setRefreshKey] = useState(0);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchIdRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setTablesLoading(true);
      try {
        const result = await adminService.listTables();
        if (!cancelled && result?.tables?.length) setTables(result.tables);
      } catch (err: any) { if (!cancelled) toast.error(err?.message || 'Failed to load tables'); }
      finally { if (!cancelled) setTablesLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!selectedTable) return;
    const thisId = ++fetchIdRef.current;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const result = await adminService.getTableData(selectedTable, {
          search: searchText || undefined, sort_by: sortBy || undefined,
          sort_dir: sortDir, limit: pageSize, offset: (currentPage - 1) * pageSize,
        });
        if (!cancelled && fetchIdRef.current === thisId) setTableData(result);
      } catch (err: any) { if (!cancelled) toast.error(err?.message || 'Failed to load data'); }
      finally { if (!cancelled && fetchIdRef.current === thisId) setLoading(false); }
    };
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(load, searchText ? 400 : 0);
    return () => { cancelled = true; if (searchTimerRef.current) clearTimeout(searchTimerRef.current); };
  }, [selectedTable, searchText, sortBy, sortDir, pageSize, currentPage, refreshKey]);

  const handleTableSelect = (name: string) => {
    setSelectedTable(name); setSearchText(''); setCurrentPage(1); setSortBy(''); setSortDir('desc'); setTableData(null);
  };

  const handleSort = (col: string) => {
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortBy(col); setSortDir('desc'); }
    setCurrentPage(1);
  };

  const handleRefresh = async () => {
    setTablesLoading(true);
    try { const r = await adminService.listTables(); if (r?.tables?.length) setTables(r.tables); }
    catch (err: any) { toast.error(err?.message || 'Failed to refresh'); }
    finally { setTablesLoading(false); }
    if (selectedTable) setRefreshKey(k => k + 1);
  };

  const handleExportCSV = () => {
    if (!tableData?.data?.length || !tableData?.columns?.length) { toast.warning('No data'); return; }
    const header = tableData.columns.join(',');
    const rows = tableData.data.map(row => tableData.columns.map(col => {
      const val = row[col]; if (val == null) return '';
      const str = typeof val === 'object' ? JSON.stringify(val) : String(val);
      return str.includes(',') || str.includes('"') ? `"${str.replace(/"/g, '""')}"` : str;
    }).join(','));
    const blob = new Blob(['\uFEFF' + [header, ...rows].join('\n')], { type: 'text/csv' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
    a.download = `${selectedTable}_${new Date().toISOString().split('T')[0]}.csv`; a.click();
    toast.success(`Exported ${tableData.data.length} rows`);
  };

  const selectedInfo = tables.find(t => t.table_name === selectedTable);
  const totalPages = tableData ? Math.ceil(tableData.total / pageSize) : 0;

  return (
    <PageShell maxWidth="1600px">
      <PageHeader title="Admin Data View" description={`Browse raw database tables — ${tables.length} tables available`} />

      {/* Controls */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <select value={selectedTable} onChange={e => handleTableSelect(e.target.value)} disabled={tablesLoading}
          className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 min-w-[300px]">
          <option value="">Select a table...</option>
          {tables.map(t => <option key={t.table_name} value={t.table_name}>{t.display_name} ({t.row_count >= 0 ? t.row_count.toLocaleString('en-AU') : '?'} rows)</option>)}
        </select>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input type="text" placeholder={selectedInfo?.searchable ? 'Search...' : 'Search not available'} value={searchText}
            onChange={e => { setSearchText(e.target.value); setCurrentPage(1); }}
            disabled={!selectedTable || !selectedInfo?.searchable}
            className="h-9 pl-8 pr-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-56 disabled:opacity-50" />
        </div>
        <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}
          className="h-9 px-2 text-sm rounded-md border border-slate-200 bg-white">
          {PAGE_SIZE_OPTIONS.map(s => <option key={s} value={s}>{s} rows</option>)}
        </select>
        <div className="ml-auto flex items-center gap-2">
          <button onClick={handleExportCSV} disabled={!tableData?.data?.length}
            className="h-9 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 disabled:opacity-30 inline-flex items-center gap-1.5">
            <Download className="h-3.5 w-3.5" />CSV
          </button>
          <button onClick={handleRefresh} disabled={loading || tablesLoading}
            className="h-9 px-3 text-sm rounded-md border border-slate-200 hover:bg-slate-50 inline-flex items-center gap-1.5">
            <RefreshCw className={cn('h-3.5 w-3.5', (loading || tablesLoading) && 'animate-spin')} />
          </button>
        </div>
      </div>

      {selectedTable && tableData && (
        <p className="text-xs text-slate-500 mb-2">{tableData.total.toLocaleString('en-AU')} total rows{searchText && ` (filtered by "${searchText}")`}</p>
      )}

      {/* Table */}
      {selectedTable ? (
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
          {loading && !tableData ? <ContentSkeleton rows={8} /> : tableData?.data?.length ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-slate-50/50">
                      {tableData.columns.map(col => (
                        <th key={col} onClick={() => handleSort(col)}
                          className="px-3 py-2 text-left font-bold uppercase tracking-wider text-slate-600 whitespace-nowrap cursor-pointer hover:text-slate-800"
                          style={{ minWidth: col === 'id' ? 250 : col.includes('_at') ? 170 : 140 }}>
                          {col.replace(/_/g, ' ')}
                          {sortBy === col && <span className="ml-1">{sortDir === 'asc' ? '▲' : '▼'}</span>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {tableData.data.map((row, i) => (
                      <tr key={row.id || i} className="hover:bg-slate-50/50">
                        {tableData.columns.map(col => {
                          const val = row[col];
                          return (
                            <td key={col} className="px-3 py-1.5 text-slate-600 whitespace-nowrap max-w-[300px] truncate" title={val != null ? String(typeof val === 'object' ? JSON.stringify(val) : val) : undefined}>
                              {val == null ? <span className="text-slate-300 italic">null</span>
                                : typeof val === 'boolean' ? <span className={val ? 'text-success' : 'text-slate-400'}>{String(val)}</span>
                                : typeof val === 'object' ? <span className="font-mono text-slate-400">{JSON.stringify(val).slice(0, 80)}</span>
                                : String(val).length > 100 ? String(val).slice(0, 100) + '...'
                                : String(val)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center justify-between px-4 py-3 border-t bg-slate-50/30">
                <span className="text-xs text-slate-500">{((currentPage - 1) * pageSize + 1).toLocaleString('en-AU')}–{Math.min(currentPage * pageSize, tableData.total).toLocaleString('en-AU')} of {tableData.total.toLocaleString('en-AU')}</span>
                <div className="flex items-center gap-1">
                  <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage <= 1} className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
                  <span className="text-xs text-slate-600 px-2 tabular-nums">{currentPage} / {totalPages}</span>
                  <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage >= totalPages} className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
                </div>
              </div>
            </>
          ) : (
            <EmptyState icon={<Database className="h-10 w-10" />} title="No data" description="This table is empty or search returned no results" />
          )}
        </div>
      ) : (
        <div className="rounded-lg border bg-white shadow-sm">
          <EmptyState icon={<Database className="h-12 w-12" />} title="Select a table" description="Choose a table from the dropdown to browse data" />
        </div>
      )}
    </PageShell>
  );
};

export default AdminDataViewPage;
