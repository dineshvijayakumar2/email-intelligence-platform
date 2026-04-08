/**
 * Quickbase Data Views — Browse synced QB cache tables.
 * TanStack Query for data fetching, server-side sort via column headers.
 * Migrated from Ant Design to Tailwind CSS + native HTML.
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  RefreshCw, CheckCircle2, X as XCircle, ChevronDown,
  Search, ArrowUpDown, ArrowUp, ArrowDown,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { notify } from '@/lib/toast';
import { useClient } from '../../contexts/ClientContext';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import api from '../../services/apiClient';
import { useQBTable, useQBSyncStatus } from '../../hooks/queries';

const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// Type-safe column definition for our native table
// ---------------------------------------------------------------------------

interface ColDef {
  title: string;
  dataIndex?: string;
  key: string;
  width?: number;
  align?: 'left' | 'right' | 'center';
  ellipsis?: boolean;
  sorter?: boolean;
  render?: (value: any, record: any) => React.ReactNode;
}

// ---------------------------------------------------------------------------
// Inline helpers for rendering cells (replacing antd Tag/Tooltip/Text/etc.)
// ---------------------------------------------------------------------------

/** Simple pill badge — replaces antd <Tag> */
function TagPill({ children, color = 'slate' }: { children: React.ReactNode; color?: string }) {
  const colorMap: Record<string, string> = {
    green: 'bg-emerald-50 text-emerald-700',
    red: 'bg-red-50 text-red-700',
    blue: 'bg-blue-50 text-blue-700',
    purple: 'bg-purple-50 text-purple-700',
    gold: 'bg-amber-50 text-amber-700',
    orange: 'bg-orange-50 text-orange-700',
    cyan: 'bg-cyan-50 text-cyan-700',
    volcano: 'bg-rose-50 text-rose-700',
    geekblue: 'bg-indigo-50 text-indigo-700',
    slate: 'bg-slate-100 text-slate-600',
    default: 'bg-slate-100 text-slate-600',
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${colorMap[color] || colorMap.slate}`}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Column definitions — each column's key (= dataIndex) is also its sort key
// ---------------------------------------------------------------------------

const customerColumns: ColDef[] = [
  { title: 'Name', dataIndex: 'customer_name', key: 'customer_name', width: 200, ellipsis: true, sorter: true },
  { title: 'Code', dataIndex: 'customer_code', key: 'customer_code', width: 90, sorter: true },
  { title: 'Tier', dataIndex: 'customer_tier', key: 'customer_tier', width: 80, sorter: true,
    render: (v: string) => v ? <TagPill>{v}</TagPill> : '-' },
  { title: 'Status', dataIndex: 'customer_status', key: 'customer_status', width: 100, sorter: true,
    render: (v: string) => v ? <TagPill color={v === 'Active' ? 'green' : 'slate'}>{v}</TagPill> : '-' },
  { title: 'Account Manager', dataIndex: 'account_manager', key: 'account_manager', width: 160, ellipsis: true, sorter: true },
  { title: 'Industry', dataIndex: 'industry', key: 'industry', width: 140, ellipsis: true },
  { title: 'Total Invoiced', dataIndex: 'total_invoiced', key: 'total_invoiced', width: 130, align: 'right', sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'TY', dataIndex: 'invoiced_ty', key: 'invoiced_ty', width: 110, align: 'right', sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'LY', dataIndex: 'invoiced_ly', key: 'invoiced_ly', width: 110, align: 'right', sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Days Since Invoice', dataIndex: 'days_since_last_invoice', key: 'days_since_last_invoice', width: 130, align: 'right', sorter: true,
    render: (v: number) => v != null
      ? <span className={v > 180 ? 'text-red-600 font-medium' : v > 90 ? 'text-amber-600 font-medium' : 'text-slate-700'}>{v}d</span>
      : '-' },
  { title: 'Matched', dataIndex: 'matched_company_name', key: 'matched', width: 160, ellipsis: true,
    render: (v: string) => v
      ? <span className="flex items-center gap-1 text-slate-700" title={v}><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" /> <span className="truncate">{v}</span></span>
      : <span className="flex items-center gap-1 text-slate-400"><XCircle className="h-3.5 w-3.5 shrink-0" /> unmatched</span> },
];

const contactColumns: ColDef[] = [
  { title: 'First Name', dataIndex: 'first_name', key: 'first_name', width: 130, sorter: true },
  { title: 'Surname', dataIndex: 'surname', key: 'surname', width: 140, sorter: true },
  { title: 'Email', dataIndex: 'email', key: 'email', width: 220, ellipsis: true, sorter: true },
  { title: 'Phone', dataIndex: 'phone', key: 'phone', width: 140 },
  { title: 'Active', dataIndex: 'active', key: 'active', width: 70,
    render: (v: any) => v ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> : <XCircle className="h-3.5 w-3.5 text-slate-300" /> },
  { title: 'Recency (days)', dataIndex: 'contact_recency_days', key: 'contact_recency_days', width: 130, align: 'right', sorter: true,
    render: (v: number) => v != null ? `${v}d` : '-' },
  { title: 'Quotes Accepted', dataIndex: 'quotes_accepted_count', key: 'quotes_accepted_count', width: 130, align: 'right', sorter: true },
  { title: 'Last Quote', dataIndex: 'most_recent_quote_date', key: 'most_recent_quote_date', width: 130, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Matched', dataIndex: 'matched_contact_id', key: 'matched', width: 80,
    render: (v: string) => v
      ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
      : <XCircle className="h-3.5 w-3.5 text-slate-300" /> },
];

const quoteColumns: ColDef[] = [
  { title: 'Quote No', dataIndex: 'quote_no', key: 'quote_no', width: 110, sorter: true },
  { title: 'Contact', dataIndex: 'contact_name', key: 'contact_name', width: 160, ellipsis: true, sorter: true },
  { title: 'Email', dataIndex: 'contact_email', key: 'contact_email', width: 200, ellipsis: true },
  { title: 'AM', dataIndex: 'quote_am_name', key: 'quote_am_name', width: 140, ellipsis: true, sorter: true },
  { title: 'Category', dataIndex: 'category', key: 'category', width: 120,
    render: (v: string) => v ? <TagPill>{v}</TagPill> : '-' },
  { title: 'Sell (ex tax)', dataIndex: 'sell_ex_tax', key: 'sell_ex_tax', width: 120, align: 'right', sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Created', dataIndex: 'date_created', key: 'date_created', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Accepted', dataIndex: 'date_accepted', key: 'date_accepted', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Has Job', dataIndex: 'has_job', key: 'has_job', width: 80,
    render: (v: any) => v ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> : '-' },
  { title: 'Qty', dataIndex: 'total_quantity', key: 'total_quantity', width: 80, align: 'right' },
];

const jobColumns: ColDef[] = [
  { title: 'Job No', dataIndex: 'job_no', key: 'job_no', width: 100, sorter: true },
  { title: 'Quote No', dataIndex: 'quote_no', key: 'quote_no', width: 100 },
  { title: 'Status', dataIndex: 'job_status', key: 'job_status', width: 120, sorter: true,
    render: (v: string) => v ? <TagPill>{v}</TagPill> : '-' },
  { title: 'Retail Sale', dataIndex: 'retail_sale', key: 'retail_sale', width: 120, align: 'right', sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Margin', dataIndex: 'invoiced_margin', key: 'invoiced_margin', width: 110, align: 'right', sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Margin %', dataIndex: 'margin_pct', key: 'margin_pct', width: 100, align: 'right', sorter: true,
    render: (v: number) => v != null ? `${Number(v).toFixed(1)}%` : '-' },
  { title: 'Accepted', dataIndex: 'accepted_date', key: 'accepted_date', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Due', dataIndex: 'due_date', key: 'due_date', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Pieces', dataIndex: 'pieces_ordered', key: 'pieces_ordered', width: 80, align: 'right' },
  { title: 'Kinds', dataIndex: 'kinds_ordered', key: 'kinds_ordered', width: 80, align: 'right' },
  { title: 'Embellishments', key: 'embellishments', width: 220,
    render: (_: any, r: any) => {
      const flags = [
        { key: 'has_hot_foil', label: 'Hot Foil', color: 'red' },
        { key: 'has_spot_uv', label: 'Spot UV', color: 'blue' },
        { key: 'has_special_substrate', label: 'Special Sub', color: 'purple' },
        { key: 'has_digital_foil', label: 'Digital Foil', color: 'gold' },
        { key: 'has_de_emboss', label: 'De/Emboss', color: 'orange' },
        { key: 'has_raised_ink', label: 'Raised Ink', color: 'cyan' },
        { key: 'has_laser_cut', label: 'Laser Cut', color: 'volcano' },
        { key: 'has_white_ink', label: 'White Ink', color: 'geekblue' },
      ];
      const active = flags.filter(f => r[f.key] && r[f.key] !== '0' && String(r[f.key]).toLowerCase() !== 'no');
      if (!active.length) return <span className="text-slate-400 text-[11px]">-</span>;
      return (
        <div className="flex flex-wrap gap-1">
          {active.map(f => <TagPill key={f.key} color={f.color}>{f.label}</TagPill>)}
        </div>
      );
    } },
];

const sliColumns: ColDef[] = [
  { title: 'Invoice No', dataIndex: 'invoice_no', key: 'invoice_no', width: 110, sorter: true },
  { title: 'Customer', dataIndex: 'customer_name', key: 'customer_name', width: 200, ellipsis: true, sorter: true },
  { title: 'Job No', dataIndex: 'job_no', key: 'job_no', width: 100, sorter: true },
  { title: 'Job Title', dataIndex: 'job_title', key: 'job_title', width: 160, ellipsis: true },
  { title: 'AM', dataIndex: 'job_am_name', key: 'job_am_name', width: 140, ellipsis: true },
  { title: 'Product Group', dataIndex: 'product_group', key: 'product_group', width: 130, sorter: true,
    render: (v: string) => v ? <TagPill>{v}</TagPill> : '-' },
  { title: 'Industry', dataIndex: 'industry', key: 'industry', width: 130, ellipsis: true },
  { title: 'Subtotal', dataIndex: 'subtotal', key: 'subtotal', width: 110, align: 'right', sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Total', dataIndex: 'total', key: 'total', width: 110, align: 'right', sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Date', dataIndex: 'inv_date', key: 'inv_date', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
];

const operationsColumns: ColDef[] = [
  { title: 'Operation', dataIndex: 'operation_name', key: 'operation_name', width: 200, ellipsis: true, sorter: true },
  { title: 'Department', dataIndex: 'department', key: 'department', width: 130, sorter: true,
    render: (v: string) => v ? <TagPill>{v}</TagPill> : '-' },
  { title: 'Machine', dataIndex: 'machine', key: 'machine', width: 160, ellipsis: true, sorter: true },
  { title: 'Job No', dataIndex: 'job_no', key: 'job_no', width: 90 },
  { title: 'Customer', dataIndex: 'customer_name', key: 'customer_name', width: 180, ellipsis: true, sorter: true },
  { title: 'AM', dataIndex: 'am_job', key: 'am_job', width: 130, ellipsis: true },
  { title: 'Capability Tags', dataIndex: 'capability_tags', key: 'capability_tags', width: 200,
    render: (v: any) => {
      const tags = Array.isArray(v) ? v : (typeof v === 'string' && v ? v.split(',').map((s: string) => s.trim()) : []);
      if (!tags.length) return <span className="text-slate-400 text-[11px]">-</span>;
      return (
        <div className="flex flex-wrap gap-1">
          {tags.map((t: string) => <TagPill key={t} color="blue">{t}</TagPill>)}
        </div>
      );
    } },
  { title: 'Row Type', dataIndex: 'row_type', key: 'row_type', width: 110,
    render: (v: string) => {
      const colorMap: Record<string, string> = { production: 'green', outsource: 'orange', rush_charge: 'red', admin: 'slate', logistics: 'cyan', costing: 'purple' };
      return v ? <TagPill color={colorMap[v] || 'slate'}>{v}</TagPill> : '-';
    } },
  { title: 'Flags', key: 'flags', width: 120,
    render: (_: any, r: any) => (
      <div className="flex flex-wrap gap-1">
        {r.am_rush && <TagPill color="volcano">AM Rush</TagPill>}
        {r.factory_rush && <TagPill color="red">Factory Rush</TagPill>}
        {r.has_outsource_component && <TagPill color="orange">Outsource</TagPill>}
      </div>
    ) },
  { title: 'Date Accepted', dataIndex: 'date_accepted', key: 'date_accepted', width: 110, sorter: true,
    render: (v: string) => v ? new Date(v).toLocaleDateString() : '-' },
  { title: 'Cost+ Price', dataIndex: 'cost_plus_price', key: 'cost_plus_price', width: 110, align: 'right', sorter: true,
    render: (v: number) => v != null ? `$${Number(v).toLocaleString()}` : '-' },
  { title: 'Profit %', dataIndex: 'profit_pct', key: 'profit_pct', width: 90, align: 'right', sorter: true,
    render: (v: number) => v != null ? `${Number(v).toFixed(1)}%` : '-' },
];

const uniqueEmailColumns: ColDef[] = [
  { title: 'Email', dataIndex: 'email', key: 'email', width: 250, ellipsis: true, sorter: true },
  { title: 'Customer Name', dataIndex: 'customer_name', key: 'customer_name', width: 200, ellipsis: true, sorter: true },
  { title: 'First Name', dataIndex: 'first_name', key: 'first_name', width: 120, sorter: true },
  { title: 'Last Name', dataIndex: 'last_name', key: 'last_name', width: 120, sorter: true },
  { title: 'QB Customer ID', dataIndex: 'qb_customer_id', key: 'qb_customer_id', width: 120 },
  { title: 'Type', dataIndex: 'customer_type', key: 'customer_type', width: 160,
    render: (v: string) => v ? <TagPill>{v}</TagPill> : '-' },
  { title: 'Quality', dataIndex: 'quality', key: 'quality', width: 80, sorter: true,
    render: (v: string) => v
      ? <StatusBadge variant={v === 'good' ? 'success' : v === 'risky' ? 'warning' : v === 'bad' ? 'danger' : 'neutral'} size="sm">{v}</StatusBadge>
      : '-' },
  { title: 'Result', dataIndex: 'result', key: 'result', width: 90, sorter: true,
    render: (v: string) => v
      ? <StatusBadge variant={v === 'ok' ? 'success' : v === 'invalid' ? 'danger' : 'neutral'} size="sm">{v}</StatusBadge>
      : '-' },
  { title: 'Capabilities', dataIndex: 'capabilities_used', key: 'capabilities_used', width: 180, ellipsis: true },
  { title: 'Processes', dataIndex: 'processes_used', key: 'processes_used', width: 180, ellipsis: true },
  { title: 'Embellishments', dataIndex: 'embellishments_used', key: 'embellishments_used', width: 180, ellipsis: true },
];

// ---------------------------------------------------------------------------
// Table config
// ---------------------------------------------------------------------------

interface TableConfig {
  key: string;
  label: string;
  endpoint: string;
  responseKey: string;
  columns: ColDef[];
}

const TABLE_CONFIGS: TableConfig[] = [
  { key: 'customers', label: 'Customers', endpoint: 'customers', responseKey: 'customers', columns: customerColumns },
  { key: 'contacts', label: 'Contacts', endpoint: 'contacts', responseKey: 'contacts', columns: contactColumns },
  { key: 'quotes', label: 'Quotes', endpoint: 'quotes', responseKey: 'quotes', columns: quoteColumns },
  { key: 'jobs', label: 'Jobs', endpoint: 'jobs', responseKey: 'jobs', columns: jobColumns },
  { key: 'sales_line_items', label: 'Sales Line Items', endpoint: 'sales-line-items', responseKey: 'sales_line_items', columns: sliColumns },
  { key: 'operations', label: 'Operations', endpoint: 'operations', responseKey: 'operations', columns: operationsColumns },
  { key: 'unique_emails', label: 'Unique Emails', endpoint: 'unique-emails', responseKey: 'unique_emails', columns: uniqueEmailColumns },
];

// ---------------------------------------------------------------------------
// Native pagination component
// ---------------------------------------------------------------------------

function SimplePagination({ page, pageSize, total, onChange }: {
  page: number; pageSize: number; total: number; onChange: (p: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between px-1 py-2 text-xs text-slate-500">
      <span>{from}-{to} of {total.toLocaleString()}</span>
      <div className="flex items-center gap-1">
        <button
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
          className="rounded px-2 py-1 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Prev
        </button>
        <span className="px-2 tabular-nums">
          {page} / {totalPages}
        </span>
        <button
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
          className="rounded px-2 py-1 hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dropdown menu (replaces antd Dropdown.Button)
// ---------------------------------------------------------------------------

function SyncDropdownButton({ label, loading, onPrimary, onFull, primary = false }: {
  label: React.ReactNode;
  loading: boolean;
  onPrimary: () => void;
  onFull: () => void;
  primary?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  const baseCls = primary
    ? 'bg-primary text-white hover:bg-primary/90 disabled:opacity-60'
    : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 disabled:opacity-60';

  return (
    <div ref={ref} className="relative inline-flex">
      <button
        disabled={loading}
        onClick={onPrimary}
        className={`inline-flex items-center gap-1.5 rounded-l-md px-3 py-1 text-xs font-medium transition-colors ${baseCls}`}
      >
        {loading ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
        {label}
      </button>
      <button
        onClick={() => setOpen(o => !o)}
        className={`inline-flex items-center rounded-r-md border-l px-1.5 py-1 transition-colors ${baseCls} ${primary ? 'border-white/20' : 'border-slate-200'}`}
      >
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 min-w-[180px] rounded-md border border-slate-200 bg-white py-1 shadow-lg">
          <button
            onClick={() => { onFull(); setOpen(false); }}
            className="w-full px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
          >
            Full Sync (re-fetch all)
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Native table component for QB data
// ---------------------------------------------------------------------------

function NativeTable({ columns, data, loading, sortBy, sortDir, onSort }: {
  columns: ColDef[];
  data: any[];
  loading: boolean;
  sortBy?: string;
  sortDir?: string;
  onSort: (key: string, dir: string | undefined) => void;
}) {
  const handleHeaderClick = (col: ColDef) => {
    if (!col.sorter) return;
    const colKey = col.key;
    if (sortBy === colKey) {
      if (sortDir === 'asc') onSort(colKey, 'desc');
      else if (sortDir === 'desc') onSort(colKey, undefined); // clear
      else onSort(colKey, 'asc');
    } else {
      onSort(colKey, 'asc');
    }
  };

  const renderSortIcon = (col: ColDef) => {
    if (!col.sorter) return null;
    if (sortBy === col.key) {
      if (sortDir === 'asc') return <ArrowUp className="h-3 w-3 text-primary" />;
      if (sortDir === 'desc') return <ArrowDown className="h-3 w-3 text-primary" />;
    }
    return <ArrowUpDown className="h-3 w-3 text-slate-300" />;
  };

  return (
    <div className="relative overflow-x-auto">
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/60">
          <Spinner className="h-5 w-5 animate-spin text-primary" />
        </div>
      )}
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-200">
            {columns.map(col => (
              <th
                key={col.key}
                onClick={() => handleHeaderClick(col)}
                style={col.width ? { minWidth: col.width, width: col.width } : undefined}
                className={`text-xs font-bold uppercase tracking-wider text-slate-600 px-3 py-2 whitespace-nowrap ${
                  col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                } ${col.sorter ? 'cursor-pointer select-none hover:text-slate-900' : ''}`}
              >
                <span className="inline-flex items-center gap-1">
                  {col.title}
                  {renderSortIcon(col)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.length === 0 && !loading && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-sm text-slate-400">
                No data
              </td>
            </tr>
          )}
          {data.map((row, ri) => (
            <tr key={row.id || row.qb_record_id || ri} className="hover:bg-slate-50/60 transition-colors">
              {columns.map(col => {
                const raw = col.dataIndex ? row[col.dataIndex] : undefined;
                const cell = col.render ? col.render(raw, row) : (raw ?? '-');
                return (
                  <td
                    key={col.key}
                    style={col.width ? { minWidth: col.width, width: col.width } : undefined}
                    className={`px-3 py-1.5 text-slate-700 ${
                      col.align === 'right' ? 'text-right tabular-nums' : col.align === 'center' ? 'text-center' : 'text-left'
                    } ${col.ellipsis ? 'truncate max-w-0' : ''}`}
                  >
                    {cell}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reusable QB Table Tab component
// ---------------------------------------------------------------------------

const QBTableTab: React.FC<{
  config: TableConfig;
  clientId: string;
  tableLogs: Record<string, { synced_at: string | null; status: string }>;
  onSync: (tableKey: string, full: boolean) => void;
  syncing: boolean;
}> = ({ config, clientId, tableLogs, onSync, syncing }) => {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [sortBy, setSortBy] = useState<string | undefined>();
  const [sortDir, setSortDir] = useState<string | undefined>();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce search
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => { setDebouncedSearch(search); setPage(1); }, 400);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [search]);

  const query = useQBTable({
    clientId,
    endpoint: config.endpoint,
    responseKey: config.responseKey,
    page,
    pageSize: PAGE_SIZE,
    search: debouncedSearch || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
  });

  const handleSort = (key: string, dir: string | undefined) => {
    if (dir) {
      setSortBy(key);
      setSortDir(dir);
    } else {
      setSortBy(undefined);
      setSortDir(undefined);
    }
    setPage(1);
  };

  const log = tableLogs[config.key];

  return (
    <div>
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        {/* Search input */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder={`Search ${config.label.toLowerCase()}...`}
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-[280px] rounded-md border border-slate-200 bg-white py-1.5 pl-8 pr-3 text-xs text-slate-700 placeholder:text-slate-400 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <XCircle className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Right side controls */}
        <div className="flex items-center gap-3 flex-wrap">
          {log?.synced_at && (
            <span className="text-[11px] text-slate-400" title={`Status: ${log.status}`}>
              Last sync: {new Date(log.synced_at).toLocaleString()}
            </span>
          )}
          <span className="text-xs text-slate-500">{(query.data?.total || 0).toLocaleString()} records</span>
          <SyncDropdownButton
            label="Sync"
            loading={syncing}
            onPrimary={() => onSync(config.key, false)}
            onFull={() => onSync(config.key, true)}
          />
          <button
            onClick={() => query.refetch()}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>
      </div>

      <NativeTable
        columns={config.columns}
        data={query.data?.items || []}
        loading={query.isLoading}
        sortBy={sortBy}
        sortDir={sortDir}
        onSort={handleSort}
      />

      <SimplePagination
        page={page}
        pageSize={PAGE_SIZE}
        total={query.data?.total || 0}
        onChange={setPage}
      />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

const QuickbaseDataPage: React.FC = () => {
  const { clientId } = useClient();
  const [activeTab, setActiveTab] = useState('customers');
  const [qbSyncing, setQbSyncing] = useState(false);
  const [tableSyncing, setTableSyncing] = useState<Record<string, boolean>>({});

  // Sync status via TanStack Query
  const syncStatusQuery = useQBSyncStatus(clientId || null);
  const syncStatus = syncStatusQuery.data;
  const lastSyncAt = syncStatus?.last_sync_at;
  const recordCounts: Record<string, number> = syncStatus?.record_counts || {};
  const tableLogs = useMemo(() => {
    const logs: Record<string, { synced_at: string | null; status: string }> = {};
    for (const log of (syncStatus?.table_logs || [])) {
      logs[log.table_name] = { synced_at: log.synced_at, status: log.status };
    }
    return logs;
  }, [syncStatus]);

  const scheduleRefresh = () => {
    setTimeout(() => syncStatusQuery.refetch(), 5000);
    setTimeout(() => syncStatusQuery.refetch(), 15000);
    setTimeout(() => syncStatusQuery.refetch(), 30000);
  };

  const handleQBSync = async (full = false) => {
    if (!clientId) return;
    setQbSyncing(true);
    try {
      const params = full ? `client_id=${clientId}&full=true` : `client_id=${clientId}`;
      await api.post<any>(`/v1/quickbase/sync?${params}`);
      notify.success(full ? 'Full sync started' : 'Sync started');
      scheduleRefresh();
    } catch (err: any) {
      notify.error(err?.message || 'Sync failed');
    } finally {
      setQbSyncing(false);
    }
  };

  const handleTableSync = async (tableKey: string, full: boolean) => {
    if (!clientId) return;
    setTableSyncing(prev => ({ ...prev, [tableKey]: true }));
    try {
      const params = new URLSearchParams({ client_id: clientId, tables: tableKey });
      if (full) params.set('full', 'true');
      await api.post<any>(`/v1/quickbase/sync?${params}`);
      notify.success(`${full ? 'Full' : 'Incremental'} sync started for ${tableKey}`);
      scheduleRefresh();
    } catch (err: any) {
      notify.error(err?.message || `Sync failed for ${tableKey}`);
    }
    setTimeout(() => setTableSyncing(prev => ({ ...prev, [tableKey]: false })), 2000);
  };

  if (!clientId) {
    return (
      <PageShell maxWidth="1600px">
        <ContentSkeleton rows={5} />
      </PageShell>
    );
  }

  const activeConfig = TABLE_CONFIGS.find(c => c.key === activeTab)!;

  return (
    <PageShell maxWidth="1600px">
      <PageHeader
        title="Quickbase Synced Data"
        actions={
          <div className="flex items-center gap-3">
            {lastSyncAt && (
              <span className="text-xs text-slate-400">
                Last sync: {new Date(lastSyncAt).toLocaleString()}
              </span>
            )}
            <SyncDropdownButton
              label="Sync All"
              loading={qbSyncing}
              onPrimary={() => handleQBSync(false)}
              onFull={() => handleQBSync(true)}
              primary
            />
          </div>
        }
      />

      {/* Summary row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-3 mb-5">
        {TABLE_CONFIGS.map(config => {
          const log = tableLogs[config.key];
          const count = recordCounts[config.key] || 0;
          return (
            <div key={config.key} className="rounded-lg border bg-white shadow-sm p-3">
              <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wide mb-1">{config.label}</p>
              <p className="text-lg font-semibold text-slate-900 tabular-nums">{count.toLocaleString()}</p>
              {log?.synced_at ? (
                <p className="text-[10px] text-slate-400 mt-0.5">{new Date(log.synced_at).toLocaleString()}</p>
              ) : count > 0 ? (
                <p className="text-[10px] text-slate-400 mt-0.5 opacity-50">Sync log unavailable</p>
              ) : (
                <p className="text-[10px] text-slate-400 mt-0.5 opacity-50">Not synced</p>
              )}
            </div>
          );
        })}
      </div>

      {/* Tabs + table content */}
      <div className="rounded-lg border bg-white shadow-sm">
        {/* Underline tab bar */}
        <div className="border-b border-slate-200 px-4 overflow-x-auto">
          <nav className="flex gap-0 -mb-px" aria-label="Tabs">
            {TABLE_CONFIGS.map(config => {
              const isActive = activeTab === config.key;
              const count = recordCounts[config.key] || 0;
              return (
                <button
                  key={config.key}
                  onClick={() => setActiveTab(config.key)}
                  className={`whitespace-nowrap px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${
                    isActive
                      ? 'border-primary text-primary'
                      : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
                  }`}
                >
                  {config.label}
                  {count > 0 && (
                    <span className={`ml-1.5 inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                      isActive ? 'bg-primary/10 text-primary' : 'bg-slate-100 text-slate-500'
                    }`}>
                      {count.toLocaleString()}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Active tab content */}
        <div className="p-4">
          <QBTableTab
            key={activeConfig.key}
            config={activeConfig}
            clientId={clientId}
            tableLogs={tableLogs}
            onSync={handleTableSync}
            syncing={!!tableSyncing[activeConfig.key]}
          />
        </div>
      </div>
    </PageShell>
  );
};

export default QuickbaseDataPage;
