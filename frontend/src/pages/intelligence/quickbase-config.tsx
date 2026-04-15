/**
 * Quickbase Configuration Page — Sprint 3
 *
 * Full-featured QB integration config: connection settings, table IDs,
 * and per-table field mappings with live QB field lookup.
 *
 * Migrated from Ant Design to Tailwind CSS + native HTML.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Plus, Trash2, RefreshCw, Save, ArrowRight, GripVertical,
  CheckCircle2, ChevronDown, Info,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { toast } from '@/lib/toast';
import api from '../../services/apiClient';
import { useClient } from '../../contexts/ClientContext';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// Verified against live qb_sync_config row — March 2026
const DEFAULT_MAPPINGS: Record<string, Record<string, string>> = {
  customers: {
    "3": "qb_record_id", "6": "customer_code", "7": "customer_name",
    "9": "active", "16": "account_manager", "17": "customer_tier",
    "36": "recency_days", "59": "industry", "67": "customer_status",
    "68": "days_since_last_invoice", "101": "total_invoiced",
    "92": "customer_key_id",
    "103": "invoiced_ty", "104": "invoiced_ly",
  },
  contacts: {
    "3": "qb_record_id", "7": "qb_customer_id", "11": "first_name",
    "12": "surname", "13": "phone", "15": "email", "16": "active",
    "25": "quotes_accepted_count", "27": "most_recent_quote_date",
    "53": "contact_recency_days",
  },
  quotes: {
    "3": "qb_record_id", "7": "quote_no", "8": "qb_customer_id",
    "9": "quote_am_name", "12": "sell_ex_tax", "13": "date_created",
    "14": "date_accepted", "36": "category", "40": "contact_name",
    "41": "contact_email", "51": "job_no", "57": "has_job",
    "65": "quantity", "67": "kinds", "68": "total_quantity",
  },
  jobs: {
    "3": "qb_record_id", "7": "job_no", "9": "qb_customer_id",
    "10": "quote_no", "11": "retail_sale", "17": "invoiced_margin",
    "18": "margin_pct", "21": "factory_rush_level", "22": "due_date",
    "23": "accepted_date", "24": "job_status", "62": "pieces_ordered",
    "63": "kinds_ordered", "64": "total_qty_ordered",
    "85": "has_hot_foil", "86": "has_spot_uv",
    "87": "has_special_substrate", "88": "has_digital_foil",
    "89": "has_de_emboss", "90": "has_raised_ink",
    "91": "has_laser_cut", "92": "has_white_ink",
  },
  sales_line_items: {
    "3": "qb_record_id", "7": "invoice_id", "9": "job_am_name",
    "11": "invoice_no", "12": "job_no", "16": "customer_name",
    "17": "qb_customer_id", "19": "inv_date", "21": "subtotal",
    "22": "total", "24": "job_title", "56": "product_group", "60": "industry",
  },
  operations: {
    "3": "qb_record_id", "6": "operation_id", "7": "job_no", "8": "quote_no",
    "9": "operation_name", "10": "machine", "11": "department",
    "12": "date_accepted", "13": "date_due", "14": "qb_customer_id",
    "15": "customer_code", "16": "customer_name", "17": "am_job",
    "18": "am_customer", "19": "job_title", "20": "quantity",
    "21": "production_status", "22": "cost_price", "23": "cost_plus_price",
    "24": "profit_amount", "25": "profit_pct", "26": "finishing_type",
    "27": "first_invoice_no", "28": "first_invoice_date",
    "44": "qb_process_tag", "45": "qb_capability_tag",
    "46": "qb_machine_tier_tag", "47": "qb_row_type_tag",
    "48": "qb_blank_reason_tag", "52": "qb_embellishment_tag",
  },
  unique_emails: {
    "3": "qb_record_id", "6": "email", "23": "qb_customer_id",
    "24": "customer_name", "44": "first_name", "45": "last_name",
    "46": "hide", "49": "quality", "50": "result", "51": "free",
    "53": "email_invalid", "70": "customer_type", "72": "customer_id_text",
    "128": "embellishments_used", "130": "processes_used", "131": "capabilities_used",
  },
};

const DEST_COLUMNS: Record<string, string[]> = {
  customers: [
    'qb_record_id', 'customer_code', 'customer_name', 'active',
    'account_manager', 'customer_tier', 'recency_days', 'industry',
    'customer_status', 'days_since_last_invoice', 'total_invoiced',
    'invoiced_ty', 'invoiced_ly', 'customer_key_id',
  ],
  contacts: [
    'qb_record_id', 'qb_customer_id', 'first_name', 'surname', 'phone',
    'email', 'active', 'quotes_accepted_count', 'most_recent_quote_date',
    'contact_recency_days',
  ],
  quotes: [
    'qb_record_id', 'quote_no', 'qb_customer_id', 'quote_am_name',
    'sell_ex_tax', 'date_created', 'date_accepted', 'category',
    'contact_name', 'contact_email', 'job_no', 'has_job', 'quantity',
    'kinds', 'total_quantity',
  ],
  jobs: [
    'qb_record_id', 'job_no', 'qb_customer_id', 'quote_no', 'retail_sale',
    'invoiced_margin', 'margin_pct', 'factory_rush_level', 'due_date',
    'accepted_date', 'job_status', 'pieces_ordered', 'kinds_ordered',
    'total_qty_ordered', 'has_hot_foil', 'has_spot_uv',
    'has_special_substrate', 'has_digital_foil', 'has_de_emboss',
    'has_raised_ink', 'has_laser_cut', 'has_white_ink',
  ],
  sales_line_items: [
    'qb_record_id', 'invoice_id', 'job_am_name', 'invoice_no', 'job_no',
    'customer_name', 'qb_customer_id', 'inv_date', 'subtotal', 'total',
    'job_title', 'product_group', 'industry',
  ],
  operations: [
    'qb_record_id', 'operation_id', 'job_no', 'quote_no', 'operation_name',
    'machine', 'department', 'date_accepted', 'date_due', 'qb_customer_id',
    'customer_code', 'customer_name', 'am_job', 'am_customer', 'job_title',
    'quantity', 'production_status', 'cost_price', 'cost_plus_price',
    'profit_amount', 'profit_pct', 'finishing_type', 'first_invoice_no',
    'first_invoice_date', 'capability_tags', 'has_coating', 'has_sewing',
    'has_outsource_component', 'am_rush', 'factory_rush', 'row_type', 'contact_email',
    'qb_process_tag', 'qb_capability_tag', 'qb_machine_tier_tag',
    'qb_row_type_tag', 'qb_blank_reason_tag', 'qb_embellishment_tag',
  ],
  unique_emails: [
    'qb_record_id', 'email', 'qb_customer_id', 'customer_name',
    'first_name', 'last_name', 'hide', 'quality', 'result', 'free',
    'email_invalid', 'customer_type', 'customer_id_text',
    'embellishments_used', 'processes_used', 'capabilities_used',
  ],
};

const TABLES = [
  { key: 'customers', label: 'Customers', configField: 'customers_table_id' },
  { key: 'contacts', label: 'Contacts', configField: 'contacts_table_id' },
  { key: 'quotes', label: 'Quotes', configField: 'quotes_table_id' },
  { key: 'jobs', label: 'Jobs', configField: 'jobs_table_id' },
  { key: 'sales_line_items', label: 'Sales Line Items', configField: 'sales_line_items_table_id' },
  { key: 'operations', label: 'Operations', configField: 'operations_table_id' },
  { key: 'unique_emails', label: 'Unique Emails', configField: 'unique_emails_table_id' },
  { key: 'job_status_log', label: 'Job Status Log', configField: 'audit_logs_table_id' },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MappingRow {
  key: string;
  fieldId: string;
  fieldName: string;
  destColumn: string;
}

type FieldMappings = Record<string, MappingRow[]>;
type QBFieldEntry = { id: number; label: string; type?: string };
type QBFields = Record<string, QBFieldEntry[]>;
type QBFieldsSyncedAt = Record<string, string | null>;
type FetchingFields = Record<string, boolean>;

interface QBTableSyncLog {
  table_name: string;
  table_id: string | null;
  record_count: number;
  synced_at: string | null;
  status: string;
  error_message: string | null;
}

interface QBSyncStatus {
  last_sync_at: string | null;
  is_active: boolean;
  record_counts: Record<string, number>;
  table_logs: QBTableSyncLog[];
}

interface FormFields {
  realm_hostname: string;
  app_id: string;
  user_token: string;
  customers_table_id: string;
  contacts_table_id: string;
  quotes_table_id: string;
  jobs_table_id: string;
  sales_line_items_table_id: string;
  operations_table_id: string;
  unique_emails_table_id: string;
  audit_logs_table_id: string;
  sync_interval_hours: number;
}

const INITIAL_FORM: FormFields = {
  realm_hostname: '',
  app_id: '',
  user_token: '',
  customers_table_id: '',
  contacts_table_id: '',
  quotes_table_id: '',
  jobs_table_id: '',
  sales_line_items_table_id: '',
  operations_table_id: '',
  unique_emails_table_id: '',
  audit_logs_table_id: '',
  sync_interval_hours: 6,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mappingToRows(mapping: Record<string, string>): MappingRow[] {
  return Object.entries(mapping).map(([fieldId, destColumn], i) => ({
    key: `${fieldId}-${i}`,
    fieldId,
    fieldName: '',
    destColumn,
  }));
}

function rowsToMapping(rows: MappingRow[]): Record<string, string> {
  const result: Record<string, string> = {};
  rows.forEach(r => {
    if (r.fieldId && r.destColumn) result[r.fieldId] = r.destColumn;
  });
  return result;
}

function initDefaultMappings(): FieldMappings {
  const mappings: FieldMappings = {};
  TABLES.forEach(t => {
    mappings[t.key] = mappingToRows(DEFAULT_MAPPINGS[t.key] || {});
  });
  return mappings;
}

// ---------------------------------------------------------------------------
// AutoComplete component (native replacement for antd AutoComplete)
// ---------------------------------------------------------------------------

function AutoCompleteInput({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (val: string) => void;
  options: string[];
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const filtered = options.filter(opt =>
    opt.toLowerCase().includes((value || '').toLowerCase())
  );

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={wrapperRef} className="relative">
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        className="w-[200px] rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-800 outline-none focus:border-primary focus:ring-1 focus:ring-primary/30"
        onChange={e => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => { setFocused(true); setOpen(true); }}
        onBlur={() => setFocused(false)}
      />
      {open && filtered.length > 0 && (
        <div className="absolute top-full left-0 z-50 mt-1 max-h-48 w-[200px] overflow-y-auto rounded border border-slate-200 bg-white shadow-lg">
          {filtered.map(opt => (
            <button
              key={opt}
              type="button"
              className="w-full px-2 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
              onMouseDown={e => {
                e.preventDefault();
                onChange(opt);
                setOpen(false);
              }}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SyncDropdown component (native replacement for antd Dropdown.Button)
// ---------------------------------------------------------------------------

function SyncDropdown({
  loading,
  onSync,
  onFullSync,
  size = 'sm',
  className,
}: {
  loading: boolean;
  onSync: () => void;
  onFullSync: () => void;
  size?: 'sm' | 'xs';
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const btnClass = size === 'xs'
    ? 'px-2 py-1 text-[11px]'
    : 'px-3 py-1.5 text-xs';

  return (
    <div ref={ref} className={`relative inline-flex ${className || ''}`}>
      <button
        type="button"
        disabled={loading}
        onClick={onSync}
        className={`${btnClass} inline-flex items-center gap-1.5 rounded-l border border-primary bg-primary font-medium text-white hover:bg-primary/90 disabled:opacity-60`}
      >
        {loading ? <Spinner className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
        Sync
      </button>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={`${btnClass} inline-flex items-center rounded-r border border-l-0 border-primary bg-primary text-white hover:bg-primary/90`}
      >
        <ChevronDown className="h-3 w-3" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 min-w-[180px] rounded border border-slate-200 bg-white shadow-lg">
          <button
            type="button"
            className="w-full px-3 py-2 text-left text-xs text-slate-700 hover:bg-slate-50"
            onClick={() => { onFullSync(); setOpen(false); }}
          >
            Full Sync (re-fetch all)
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

const QuickbaseConfigPage: React.FC = () => {
  const { clientId } = useClient();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formFields, setFormFields] = useState<FormFields>(INITIAL_FORM);
  const [formErrors, setFormErrors] = useState<Partial<Record<keyof FormFields, string>>>({});
  const [fieldMappings, setFieldMappings] = useState<FieldMappings>(initDefaultMappings);
  const [syncAuto, setSyncAuto] = useState(false);
  const [qbFields, setQbFields] = useState<QBFields>({});
  const [qbFieldsSyncedAt, setQbFieldsSyncedAt] = useState<QBFieldsSyncedAt>({});
  const [fetchingFields, setFetchingFields] = useState<FetchingFields>({});
  const [dragOver, setDragOver] = useState<Record<string, boolean>>({});
  const [fieldSearch, setFieldSearch] = useState<Record<string, string>>({});
  const [qbStatus, setQbStatus] = useState<QBSyncStatus | null>(null);
  const [qbSyncing, setQbSyncing] = useState(false);
  const [tableSyncing, setTableSyncing] = useState<Record<string, boolean>>({});
  const [activeTab, setActiveTab] = useState(TABLES[0].key);
  const [showPassword, setShowPassword] = useState(false);

  // Form field updater
  const updateField = <K extends keyof FormFields>(key: K, value: FormFields[K]) => {
    setFormFields(prev => ({ ...prev, [key]: value }));
    // Clear error when user types
    if (formErrors[key]) {
      setFormErrors(prev => { const n = { ...prev }; delete n[key]; return n; });
    }
  };

  // -------------------------------------------------------------------------
  // Data loading
  // -------------------------------------------------------------------------

  const loadConfig = useCallback(async (id: string) => {
    setLoading(true);
    try {
      const cfg = await api.get<any>(`/v1/quickbase/config?client_id=${id}`);

      const hasAutoSync = cfg.sync_interval_hours != null;
      setSyncAuto(hasAutoSync);
      setFormFields({
        realm_hostname: cfg.realm_hostname || '',
        app_id: cfg.app_id || '',
        user_token: cfg.user_token || '',
        customers_table_id: cfg.customers_table_id || '',
        contacts_table_id: cfg.contacts_table_id || '',
        quotes_table_id: cfg.quotes_table_id || '',
        jobs_table_id: cfg.jobs_table_id || '',
        sales_line_items_table_id: cfg.sales_line_items_table_id || '',
        operations_table_id: cfg.operations_table_id || '',
        unique_emails_table_id: cfg.unique_emails_table_id || '',
        audit_logs_table_id: cfg.audit_logs_table_id || '',
        sync_interval_hours: cfg.sync_interval_hours ?? 6,
      });

      // Load field mappings from config, falling back to defaults per table
      const saved: Record<string, Record<string, string>> = cfg.field_mappings || {};
      const loaded: FieldMappings = {};
      TABLES.forEach(t => {
        // Merge: defaults first, then saved overrides on top (so new default fields always show)
        const tableMapping = {
          ...(DEFAULT_MAPPINGS[t.key] || {}),
          ...(saved[t.key] || {}),
        };
        loaded[t.key] = mappingToRows(tableMapping);
      });
      setFieldMappings(loaded);
    } catch (err: any) {
      if (err?.status === 404 || err?.response?.status === 404) {
        // No config yet -- pre-fill Carbon8 defaults
        setSyncAuto(false);
        setFormFields({
          realm_hostname: 'dc.quickbase.com',
          app_id: 'buzfemk4f',
          user_token: '',
          customers_table_id: 'buzhzbv39',
          contacts_table_id: 'bu4ctqehy',
          quotes_table_id: 'buz9p6tzu',
          jobs_table_id: 'buziry2ri',
          sales_line_items_table_id: 'bu4cwdinf',
          operations_table_id: 'bvqsudnif',
          unique_emails_table_id: 'bvmtc5re6',
          audit_logs_table_id: 'bu9yjc3ne',
          sync_interval_hours: 6,
        });
        setFieldMappings(initDefaultMappings());
      } else {
        toast.error(err?.message || 'Failed to load Quickbase config');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const loadQBStatus = useCallback(async (id: string) => {
    try {
      const status = await api.get<QBSyncStatus>(`/v1/quickbase/sync-status?client_id=${id}`);
      setQbStatus(status);
    } catch {
      // No config yet -- status stays null
    }
  }, []);

  const handleQBSync = async (full = false) => {
    if (!clientId) return;
    setQbSyncing(true);
    try {
      const params = full ? `client_id=${clientId}&full=true` : `client_id=${clientId}`;
      await api.post<any>(`/v1/quickbase/sync?${params}`);
      toast.success(full ? 'Full sync started -- re-fetching all records' : 'Sync started -- fetching recent changes');
      setTimeout(() => loadQBStatus(clientId), 3000);
    } catch (err: any) {
      toast.error(err?.message || 'Sync failed');
    } finally {
      setQbSyncing(false);
    }
  };

  const [rematching, setRematching] = useState(false);

  const handleRematch = async () => {
    if (!clientId) return;
    setRematching(true);
    try {
      await api.post<any>(`/v1/quickbase/rematch?client_id=${clientId}`);
      toast.success('Re-matching started -- matching QB records to email companies/contacts');
      setTimeout(() => loadQBStatus(clientId), 5000);
    } catch (err: any) {
      toast.error(err?.message || 'Re-match failed');
    } finally {
      setRematching(false);
    }
  };

  const handleTableSync = async (tableKey: string, full = false) => {
    if (!clientId) return;
    setTableSyncing(prev => ({ ...prev, [tableKey]: true }));
    try {
      const params = new URLSearchParams({ client_id: clientId, tables: tableKey });
      if (full) params.set('full', 'true');
      await api.post<any>(`/v1/quickbase/sync?${params}`);
      toast.success(`${full ? 'Full' : 'Incremental'} sync started for ${tableKey}`);
      setTimeout(() => loadQBStatus(clientId), 3000);
    } catch (err: any) {
      toast.error(err?.message || 'Sync failed');
    } finally {
      setTableSyncing(prev => ({ ...prev, [tableKey]: false }));
    }
  };

  // When clientId resolves or changes: reset stale state, load config + fields + status
  useEffect(() => {
    if (!clientId) return;
    setQbFields({});
    setQbFieldsSyncedAt({});
    setQbStatus(null);
    loadConfig(clientId);
    TABLES.forEach(t => handleFetchFields(t.key, false));
    loadQBStatus(clientId);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  // -------------------------------------------------------------------------
  // Validation
  // -------------------------------------------------------------------------

  const validateForm = (): boolean => {
    const errors: Partial<Record<keyof FormFields, string>> = {};
    if (!formFields.realm_hostname) errors.realm_hostname = 'Realm hostname is required';
    if (!formFields.app_id) errors.app_id = 'App ID is required';
    TABLES.forEach(t => {
      const field = t.configField as keyof FormFields;
      if (!formFields[field]) errors[field] = `${t.label} table ID is required`;
    });
    if (syncAuto && !formFields.sync_interval_hours) {
      errors.sync_interval_hours = 'Interval required';
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // -------------------------------------------------------------------------
  // Save
  // -------------------------------------------------------------------------

  const handleSaveAll = async () => {
    if (!validateForm()) return;

    if (!clientId) {
      toast.error('No client ID found');
      return;
    }

    setSaving(true);
    try {
      // Convert row arrays back to mapping objects
      const field_mappings: Record<string, Record<string, string>> = {};
      TABLES.forEach(t => {
        field_mappings[t.key] = rowsToMapping(fieldMappings[t.key] || []);
      });

      await api.put<any>(`/v1/quickbase/config?client_id=${clientId}`, {
        ...formFields,
        sync_interval_hours: syncAuto ? (formFields.sync_interval_hours ?? 6) : null,
        field_mappings,
      });

      toast.success('Quickbase configuration saved');
    } catch (err: any) {
      toast.error(err?.message || 'Failed to save config');
    } finally {
      setSaving(false);
    }
  };

  // -------------------------------------------------------------------------
  // Field fetch from QB
  // -------------------------------------------------------------------------

  const handleFetchFields = async (tableKey: string, force = false) => {
    if (!clientId) {
      toast.error('No client ID');
      return;
    }
    setFetchingFields(prev => ({ ...prev, [tableKey]: true }));
    try {
      const url = `/v1/quickbase/fields?client_id=${clientId}&table=${tableKey}${force ? '&force=true' : ''}`;
      const resp = await api.get<any>(url);
      const fetched: QBFieldEntry[] = resp?.fields || [];
      const syncedAt: string | null = resp?.synced_at || null;

      setQbFields(prev => ({ ...prev, [tableKey]: fetched }));
      setQbFieldsSyncedAt(prev => ({ ...prev, [tableKey]: syncedAt }));

      // Only update fieldName for rows already in the mapping
      setFieldMappings(prev => {
        const existing = [...(prev[tableKey] || [])];
        const updated = existing.map(row => {
          const match = fetched.find(f => String(f.id) === row.fieldId);
          return match ? { ...row, fieldName: match.label } : row;
        });
        return { ...prev, [tableKey]: updated };
      });

      if (force) toast.success(`Refreshed ${fetched.length} fields from QB`);
    } catch (err: any) {
      // Silently skip on background load (no config yet); show error on manual fetch
      if (force) toast.error(err?.message || 'Failed to fetch QB fields');
    } finally {
      setFetchingFields(prev => ({ ...prev, [tableKey]: false }));
    }
  };

  // -------------------------------------------------------------------------
  // Row editing helpers
  // -------------------------------------------------------------------------

  const updateRow = (tableKey: string, rowKey: string, changes: Partial<MappingRow>) => {
    setFieldMappings(prev => ({
      ...prev,
      [tableKey]: prev[tableKey].map(r =>
        r.key === rowKey ? { ...r, ...changes } : r
      ),
    }));
  };

  const deleteRow = (tableKey: string, rowKey: string) => {
    setFieldMappings(prev => ({
      ...prev,
      [tableKey]: prev[tableKey].filter(r => r.key !== rowKey),
    }));
  };

  const addRow = (tableKey: string) => {
    const newRow: MappingRow = {
      key: `new-${Date.now()}`,
      fieldId: '',
      fieldName: '',
      destColumn: '',
    };
    setFieldMappings(prev => ({
      ...prev,
      [tableKey]: [...(prev[tableKey] || []), newRow],
    }));
  };

  // -------------------------------------------------------------------------
  // Add field to mapping from palette
  // -------------------------------------------------------------------------

  const addFieldToMapping = (tableKey: string, fieldId: string, fieldName: string) => {
    setFieldMappings(prev => ({
      ...prev,
      [tableKey]: [...(prev[tableKey] || []), {
        key: `add-${fieldId}-${Date.now()}`,
        fieldId,
        fieldName,
        destColumn: '',
      }],
    }));
  };

  // -------------------------------------------------------------------------
  // Render: Loading
  // -------------------------------------------------------------------------

  if (loading) {
    return (
      <PageShell>
        <ContentSkeleton rows={8} />
      </PageShell>
    );
  }

  // -------------------------------------------------------------------------
  // Render: Tab content builder
  // -------------------------------------------------------------------------

  const renderTabContent = (tableKey: string) => {
    const t = TABLES.find(tb => tb.key === tableKey)!;
    const mappedIds = new Set((fieldMappings[t.key] || []).map(r => r.fieldId));
    const allFields = [...(qbFields[t.key] || [])].sort((a, b) => a.id - b.id);
    const searchTerm = (fieldSearch[t.key] || '').toLowerCase();
    const availableFields = searchTerm
      ? allFields.filter(f => f.label.toLowerCase().includes(searchTerm) || String(f.id).includes(searchTerm))
      : allFields;
    const isOver = dragOver[t.key] ?? false;

    const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(prev => ({ ...prev, [t.key]: false }));
      try {
        const data = JSON.parse(e.dataTransfer.getData('application/json'));
        if (data.tableKey !== t.key) return;
        if (mappedIds.has(data.fieldId)) {
          toast.info(`Field "${data.fieldName}" is already mapped`);
          return;
        }
        addFieldToMapping(t.key, data.fieldId, data.fieldName);
      } catch { /* ignore */ }
    };

    const rows = fieldMappings[t.key] || [];

    return (
      <div className="flex gap-4 items-start">

        {/* -- LEFT PANEL: QB field palette -- */}
        <div className="w-[260px] flex-shrink-0 rounded-lg border bg-white shadow-sm overflow-hidden">
          {/* Panel header */}
          <div className="flex items-center justify-between border-b bg-slate-50 px-3.5 py-2.5">
            <div>
              <span className="text-[13px] font-semibold text-slate-800">QB Fields</span>
              {qbFieldsSyncedAt[t.key] && (
                <div className="text-[11px] text-slate-400 mt-0.5">
                  Synced {new Date(qbFieldsSyncedAt[t.key]!).toLocaleString('en-AU')}
                </div>
              )}
            </div>
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-50"
              disabled={fetchingFields[t.key]}
              onClick={() => handleFetchFields(t.key, true)}
              title={allFields.length > 0 ? 'Re-fetch from QB and update cache' : 'Fetch from QB and cache'}
            >
              {fetchingFields[t.key]
                ? <Spinner className="h-3 w-3 animate-spin" />
                : <RefreshCw className="h-3 w-3" />
              }
              {allFields.length > 0 ? 'Refresh' : 'Fetch'}
            </button>
          </div>

          {/* Search */}
          {allFields.length > 0 && (
            <div className="border-b px-2.5 py-2">
              <input
                type="text"
                placeholder="Search fields..."
                className="w-full rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 outline-none placeholder:text-slate-400 focus:border-primary focus:ring-1 focus:ring-primary/30"
                value={fieldSearch[t.key] || ''}
                onChange={e => setFieldSearch(prev => ({ ...prev, [t.key]: e.target.value }))}
              />
            </div>
          )}

          {/* Field list */}
          {allFields.length === 0 ? (
            <div className="py-8 px-4 text-center">
              <RefreshCw className="mx-auto mb-2 h-6 w-6 text-slate-300" />
              <p className="text-xs text-slate-400">
                Click Fetch to load<br />available QB fields
              </p>
            </div>
          ) : availableFields.length === 0 ? (
            <div className="py-5 px-4 text-center">
              <p className="text-xs text-slate-400">No fields match "{fieldSearch[t.key]}"</p>
            </div>
          ) : (
            <div className="max-h-[420px] overflow-y-auto py-1.5">
              {availableFields.map(f => {
                const isMapped = mappedIds.has(String(f.id));
                return (
                  <div
                    key={f.id}
                    draggable={!isMapped}
                    onClick={() => {
                      if (!isMapped) addFieldToMapping(t.key, String(f.id), f.label);
                    }}
                    onDragStart={e => {
                      e.dataTransfer.setData('application/json', JSON.stringify({
                        tableKey: t.key,
                        fieldId: String(f.id),
                        fieldName: f.label,
                      }));
                      e.dataTransfer.effectAllowed = 'copy';
                    }}
                    className={`flex items-center gap-2 px-3.5 py-1.5 select-none transition-colors ${
                      isMapped
                        ? 'opacity-40 cursor-default'
                        : 'cursor-grab hover:bg-primary/5'
                    }`}
                    title={isMapped ? 'Already mapped' : 'Drag or click to add'}
                  >
                    {isMapped
                      ? <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0 text-emerald-500" />
                      : <GripVertical className="h-3.5 w-3.5 flex-shrink-0 text-slate-300" />
                    }
                    <span className="text-xs min-w-0">
                      <span className="text-[11px] text-slate-400 mr-1">#{f.id}</span>
                      <span className="text-slate-700">{f.label}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* -- RIGHT PANEL: mapping table + drop zone -- */}
        <div className="flex-1 min-w-0">
          <div
            onDragOver={e => {
              e.preventDefault();
              if (!isOver) setDragOver(prev => ({ ...prev, [t.key]: true }));
            }}
            onDragLeave={e => {
              if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                setDragOver(prev => ({ ...prev, [t.key]: false }));
              }
            }}
            onDrop={onDrop}
            className={`rounded-lg transition-all ${
              isOver
                ? 'border-2 border-dashed border-primary bg-primary/5 p-1'
                : 'border-2 border-dashed border-transparent'
            }`}
          >
            {rows.length === 0 ? (
              <div className="py-8 text-center text-slate-400">
                <ArrowRight className="mx-auto mb-2 h-5 w-5 -rotate-90" />
                <p className="text-[13px]">
                  {availableFields.length > 0
                    ? 'Drag fields from the left panel -- or click them to add'
                    : 'Fetch QB fields first, then drag them here'}
                </p>
              </div>
            ) : (
              <div className="max-h-[360px] overflow-y-auto rounded-lg border bg-white shadow-sm">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b bg-slate-50">
                      <th className="px-3 py-2 text-xs font-bold uppercase tracking-wider text-slate-600 w-[120px]">
                        QB Field ID
                      </th>
                      <th className="px-3 py-2 text-xs font-bold uppercase tracking-wider text-slate-600">
                        QB Field Name
                      </th>
                      <th className="px-3 py-2 w-10"></th>
                      <th className="px-3 py-2 text-xs font-bold uppercase tracking-wider text-slate-600 w-[220px]">
                        Destination Column
                      </th>
                      <th className="px-3 py-2 w-10"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {rows.map(record => (
                      <tr key={record.key} className="hover:bg-slate-50/50">
                        <td className="px-3 py-1.5">
                          <input
                            type="text"
                            value={record.fieldId}
                            className="w-[100px] rounded border border-slate-200 bg-white px-2 py-1 text-xs text-slate-800 outline-none focus:border-primary focus:ring-1 focus:ring-primary/30"
                            onChange={e => {
                              const newId = e.target.value;
                              const match = (qbFields[t.key] || []).find(f => String(f.id) === newId);
                              updateRow(t.key, record.key, {
                                fieldId: newId,
                                fieldName: match ? match.label : '',
                              });
                            }}
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          {record.fieldName ? (
                            <span className="text-[13px] text-slate-700">{record.fieldName}</span>
                          ) : (
                            <span className="text-[13px] italic text-slate-400">-- unknown field ID --</span>
                          )}
                        </td>
                        <td className="px-3 py-1.5">
                          <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                        </td>
                        <td className="px-3 py-1.5">
                          <AutoCompleteInput
                            value={record.destColumn}
                            options={DEST_COLUMNS[t.key] || []}
                            onChange={val => updateRow(t.key, record.key, { destColumn: val })}
                            placeholder="Select or type column"
                          />
                        </td>
                        <td className="px-3 py-1.5">
                          <button
                            type="button"
                            className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500"
                            onClick={() => deleteRow(t.key, record.key)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div className="mt-2.5 flex items-center gap-2">
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
              onClick={() => addRow(t.key)}
            >
              <Plus className="h-3 w-3" />
              Add Row Manually
            </button>
            {mappedIds.size > 0 && (
              <span className="text-xs text-slate-400">
                {mappedIds.size} field{mappedIds.size !== 1 ? 's' : ''} mapped
              </span>
            )}
          </div>
        </div>
      </div>
    );
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <PageShell>
      <PageHeader
        title="Quickbase Configuration"
        actions={
          <button
            type="button"
            disabled={saving}
            onClick={handleSaveAll}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-60"
          >
            {saving ? <Spinner className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save All
          </button>
        }
      />

      {/* QB Synced Data Status */}
      {qbStatus && (
        <div className="mb-4 rounded-lg border bg-white shadow-sm">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <span className="text-sm font-semibold text-slate-800">Quickbase Synced Data</span>
            <div className="flex items-center gap-3">
              {qbStatus.last_sync_at && (
                <span className="text-xs text-slate-400">
                  Last sync: {new Date(qbStatus.last_sync_at).toLocaleString('en-AU')}
                </span>
              )}
              <SyncDropdown
                loading={qbSyncing}
                onSync={() => handleQBSync(false)}
                onFullSync={() => handleQBSync(true)}
                size="sm"
              />
              <button
                type="button"
                disabled={rematching}
                onClick={handleRematch}
                className="inline-flex items-center gap-1.5 rounded border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-60"
              >
                {rematching ? <Spinner className="h-3 w-3 animate-spin" /> : <ArrowRight className="h-3 w-3" />}
                Re-match
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-7">
            {[
              { label: 'Customers', key: 'customers' },
              { label: 'Contacts', key: 'contacts' },
              { label: 'Quotes', key: 'quotes' },
              { label: 'Jobs', key: 'jobs' },
              { label: 'Sales Line Items', key: 'sales_line_items' },
              { label: 'Operations', key: 'operations' },
              { label: 'Unique Emails', key: 'unique_emails' },
            ].map(({ label, key }) => {
              const log = qbStatus.table_logs.find(l => l.table_name === key);
              const hasError = log?.status === 'error';
              return (
                <div
                  key={key}
                  className={`rounded-lg border p-2.5 ${
                    hasError
                      ? 'border-red-200 bg-red-50/50'
                      : 'border-slate-100 bg-slate-50/50'
                  }`}
                >
                  <span className="text-[11px] text-slate-500 block mb-0.5">{label}</span>
                  <div className="text-xl font-semibold text-slate-800 leading-tight">
                    {(qbStatus.record_counts[key] ?? 0).toLocaleString('en-AU')}
                  </div>
                  {log?.table_id && (
                    <StatusBadge
                      variant="neutral"
                      size="sm"
                      className="mt-1 cursor-default"
                      title="QB Table ID (cross-ref: Field Definitions)"
                    >
                      {log.table_id}
                    </StatusBadge>
                  )}
                  {log?.synced_at ? (
                    <div className={`text-[10px] mt-1 ${hasError ? 'text-red-500' : 'text-slate-400'}`}>
                      {hasError ? (log.error_message || 'Error') : new Date(log.synced_at).toLocaleString('en-AU')}
                    </div>
                  ) : (
                    <div className="text-[10px] text-slate-300 mt-1">Not synced yet</div>
                  )}
                  <div className="mt-2">
                    <SyncDropdown
                      loading={tableSyncing[key] || false}
                      onSync={() => handleTableSync(key, false)}
                      onFullSync={() => handleTableSync(key, true)}
                      size="xs"
                      className="w-full"
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Info alert */}
      <div className="mb-6 flex items-start gap-2.5 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
        <Info className="mt-0.5 h-4 w-4 flex-shrink-0 text-blue-500" />
        <span className="text-sm text-blue-700">
          Field mappings override the default Carbon8 field mappings. Only configure if your QB schema differs from the defaults.
        </span>
      </div>

      {/* Connection Settings */}
      <div className="mb-6 rounded-lg border bg-white shadow-sm">
        <div className="border-b px-4 py-3">
          <span className="text-sm font-semibold text-slate-800">Connection Settings</span>
        </div>
        <div className="flex flex-wrap gap-4 p-4">
          {/* Realm Hostname */}
          <div className="min-w-[220px]">
            <label className="mb-1 block text-xs font-medium text-slate-600">
              Realm Hostname <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={formFields.realm_hostname}
              placeholder="dc.quickbase.com"
              className={`w-[220px] rounded border bg-white px-3 py-1.5 text-sm text-slate-800 outline-none focus:ring-1 focus:ring-primary/30 ${
                formErrors.realm_hostname ? 'border-red-300 focus:border-red-400' : 'border-slate-200 focus:border-primary'
              }`}
              onChange={e => updateField('realm_hostname', e.target.value)}
            />
            {formErrors.realm_hostname && (
              <p className="mt-0.5 text-[11px] text-red-500">{formErrors.realm_hostname}</p>
            )}
          </div>

          {/* App ID */}
          <div className="min-w-[140px]">
            <label className="mb-1 block text-xs font-medium text-slate-600">
              App ID <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={formFields.app_id}
              placeholder="buzfemk4f"
              className={`w-[140px] rounded border bg-white px-3 py-1.5 text-sm text-slate-800 outline-none focus:ring-1 focus:ring-primary/30 ${
                formErrors.app_id ? 'border-red-300 focus:border-red-400' : 'border-slate-200 focus:border-primary'
              }`}
              onChange={e => updateField('app_id', e.target.value)}
            />
            {formErrors.app_id && (
              <p className="mt-0.5 text-[11px] text-red-500">{formErrors.app_id}</p>
            )}
          </div>

          {/* User Token */}
          <div className="min-w-[260px]">
            <label className="mb-1 block text-xs font-medium text-slate-600">User Token</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={formFields.user_token}
                placeholder="QB user token"
                className="w-[260px] rounded border border-slate-200 bg-white px-3 py-1.5 pr-8 text-sm text-slate-800 outline-none focus:border-primary focus:ring-1 focus:ring-primary/30"
                onChange={e => updateField('user_token', e.target.value)}
              />
              <button
                type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-600"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
            <p className="mt-0.5 text-[11px] text-slate-400">Clear to remove token and disable sync</p>
          </div>

          {/* Sync Mode */}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Sync Mode</label>
            <div className="flex items-center gap-3">
              <label className="relative inline-flex cursor-pointer items-center">
                <input
                  type="checkbox"
                  role="switch"
                  checked={syncAuto}
                  onChange={e => setSyncAuto(e.target.checked)}
                  className="peer sr-only"
                />
                <div className="h-6 w-11 rounded-full bg-slate-200 after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-white after:shadow after:transition-all after:content-[''] peer-checked:bg-primary peer-checked:after:translate-x-full peer-focus:ring-2 peer-focus:ring-primary/30" />
                <span className="ml-2 text-xs font-medium text-slate-600">
                  {syncAuto ? 'Auto' : 'Manual'}
                </span>
              </label>
              {syncAuto && (
                <div>
                  <input
                    type="number"
                    min={1}
                    max={168}
                    step={1}
                    value={formFields.sync_interval_hours}
                    placeholder="6"
                    className={`w-[90px] rounded border bg-white px-3 py-1.5 text-sm text-slate-800 outline-none focus:ring-1 focus:ring-primary/30 ${
                      formErrors.sync_interval_hours ? 'border-red-300 focus:border-red-400' : 'border-slate-200 focus:border-primary'
                    }`}
                    onChange={e => updateField('sync_interval_hours', Number(e.target.value) || 0)}
                  />
                  {formErrors.sync_interval_hours && (
                    <p className="mt-0.5 text-[11px] text-red-500">{formErrors.sync_interval_hours}</p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="border-t px-4 py-3">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
            onClick={async () => {
              if (!clientId) { toast.error('No client ID'); return; }
              try {
                await api.get<any>(`/v1/quickbase/config?client_id=${clientId}`);
                toast.success('Connection config found');
              } catch {
                toast.error('No QB config found for this client');
              }
            }}
          >
            Test Connection
          </button>
        </div>
      </div>

      {/* Table IDs */}
      <div className="mb-6 rounded-lg border bg-white shadow-sm">
        <div className="border-b px-4 py-3">
          <span className="text-sm font-semibold text-slate-800">Table IDs</span>
        </div>
        <div className="flex flex-wrap gap-4 p-4">
          {TABLES.map(t => {
            const field = t.configField as keyof FormFields;
            return (
              <div key={t.key} className="flex-1 min-w-[180px]">
                <label className="mb-1 block text-xs font-medium text-slate-600">
                  {t.label} <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formFields[field] as string}
                  placeholder="QB table ID"
                  className={`w-full rounded border bg-white px-3 py-1.5 text-sm text-slate-800 outline-none focus:ring-1 focus:ring-primary/30 ${
                    formErrors[field] ? 'border-red-300 focus:border-red-400' : 'border-slate-200 focus:border-primary'
                  }`}
                  onChange={e => updateField(field, e.target.value)}
                />
                {formErrors[field] && (
                  <p className="mt-0.5 text-[11px] text-red-500">{formErrors[field]}</p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Field Mappings */}
      <div className="rounded-lg border bg-white shadow-sm">
        <div className="border-b px-4 py-3">
          <span className="text-sm font-semibold text-slate-800">Field Mappings</span>
        </div>
        <div className="px-4 pt-3">
          {/* Tab bar */}
          <div className="flex gap-0 border-b border-slate-200 overflow-x-auto">
            {TABLES.map(t => {
              const mappedIds = new Set((fieldMappings[t.key] || []).map(r => r.fieldId));
              const allFields = qbFields[t.key] || [];
              const unmappedCount = allFields.filter(f => !mappedIds.has(String(f.id))).length;
              const mappedCount = mappedIds.size;
              const isActive = activeTab === t.key;

              return (
                <button
                  key={t.key}
                  type="button"
                  className={`whitespace-nowrap px-4 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? 'border-b-2 border-primary text-primary'
                      : 'border-b-2 border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                  onClick={() => setActiveTab(t.key)}
                >
                  {t.label}
                  {allFields.length > 0 && (
                    <StatusBadge
                      variant={unmappedCount > 0 ? 'info' : 'success'}
                      size="sm"
                      className="ml-1.5"
                    >
                      {mappedCount}/{allFields.length}
                    </StatusBadge>
                  )}
                </button>
              );
            })}
          </div>
        </div>
        <div className="p-4">
          {renderTabContent(activeTab)}
        </div>
      </div>
    </PageShell>
  );
};

export default QuickbaseConfigPage;
