/**
 * Quickbase Configuration Page — Sprint 3
 *
 * Full-featured QB integration config: connection settings, table IDs,
 * and per-table field mappings with live QB field lookup.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Form, Input, InputNumber, Button, Table, Tabs, AutoComplete,
  Space, Typography, Alert, Divider, Spin, message, Tag, Tooltip, Switch, Row, Col, Dropdown,
} from 'antd';
import {
  PlusOutlined, DeleteOutlined, SyncOutlined, SaveOutlined, ArrowRightOutlined,
  HolderOutlined, CheckCircleFilled, DownOutlined,
} from '@ant-design/icons';
import api from '../../services/apiClient';
import { ClientSelector } from '../../components/analytics/ClientSelector';

const { Title, Text } = Typography;

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
// Page component
// ---------------------------------------------------------------------------

const QuickbaseConfigPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clientId, setClientId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [fieldMappings, setFieldMappings] = useState<FieldMappings>(initDefaultMappings);
  const [syncAuto, setSyncAuto] = useState(false);  // false = manual, true = automatic
  const [qbFields, setQbFields] = useState<QBFields>({});
  const [qbFieldsSyncedAt, setQbFieldsSyncedAt] = useState<QBFieldsSyncedAt>({});
  const [fetchingFields, setFetchingFields] = useState<FetchingFields>({});
  const [dragOver, setDragOver] = useState<Record<string, boolean>>({});
  const [fieldSearch, setFieldSearch] = useState<Record<string, string>>({});
  const [qbStatus, setQbStatus] = useState<QBSyncStatus | null>(null);
  const [qbSyncing, setQbSyncing] = useState(false);
  const [tableSyncing, setTableSyncing] = useState<Record<string, boolean>>({});

  // -------------------------------------------------------------------------
  // Data loading
  // -------------------------------------------------------------------------

  const loadConfig = useCallback(async (id: string) => {
    setLoading(true);
    try {
      const cfg = await api.get<any>(`/v1/quickbase/config?client_id=${id}`);

      const hasAutoSync = cfg.sync_interval_hours != null;
      setSyncAuto(hasAutoSync);
      form.setFieldsValue({
        realm_hostname: cfg.realm_hostname,
        app_id: cfg.app_id,
        user_token: cfg.user_token || '',
        customers_table_id: cfg.customers_table_id,
        contacts_table_id: cfg.contacts_table_id,
        quotes_table_id: cfg.quotes_table_id,
        jobs_table_id: cfg.jobs_table_id,
        sales_line_items_table_id: cfg.sales_line_items_table_id,
        operations_table_id: cfg.operations_table_id,
        unique_emails_table_id: cfg.unique_emails_table_id,
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
        // No config yet — pre-fill Carbon8 defaults
        setSyncAuto(false);
        form.setFieldsValue({
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
          sync_interval_hours: 6,
        });
        setFieldMappings(initDefaultMappings());
      } else {
        message.error(err?.message || 'Failed to load Quickbase config');
      }
    } finally {
      setLoading(false);
    }
  }, [form]);

  // Resolve initial client ID on mount (localStorage → assigned → admin list)
  useEffect(() => {
    const stored = localStorage.getItem('analytics_client_id');
    if (stored) { setClientId(stored); return; }
    (async () => {
      try {
        const assigned = await api.get<any>('/auth/me/clients');
        const id = Array.isArray(assigned) ? assigned[0]?.client_id : null;
        if (id) { setClientId(id); return; }
      } catch { /* ignore */ }
      try {
        const all = await api.get<any>('/clients/');
        const id = all?.clients?.[0]?.id || all?.[0]?.id || null;
        if (id) setClientId(id);
        else { message.warning('No client found — using defaults'); setLoading(false); }
      } catch { setLoading(false); }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadQBStatus = useCallback(async (id: string) => {
    try {
      const status = await api.get<QBSyncStatus>(`/v1/quickbase/sync-status?client_id=${id}`);
      setQbStatus(status);
    } catch {
      // No config yet — status stays null
    }
  }, []);

  const handleQBSync = async (full = false) => {
    if (!clientId) return;
    setQbSyncing(true);
    try {
      const params = full ? `client_id=${clientId}&full=true` : `client_id=${clientId}`;
      await api.post<any>(`/v1/quickbase/sync?${params}`);
      message.success(full ? 'Full sync started — re-fetching all records' : 'Sync started — fetching recent changes');
      setTimeout(() => loadQBStatus(clientId), 3000);
    } catch (err: any) {
      message.error(err?.message || 'Sync failed');
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
      message.success('Re-matching started — matching QB records to email companies/contacts');
      setTimeout(() => loadQBStatus(clientId), 5000);
    } catch (err: any) {
      message.error(err?.message || 'Re-match failed');
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
      message.success(`${full ? 'Full' : 'Incremental'} sync started for ${tableKey}`);
      setTimeout(() => loadQBStatus(clientId), 3000);
    } catch (err: any) {
      message.error(err?.message || 'Sync failed');
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
  // Save
  // -------------------------------------------------------------------------

  const handleSaveAll = async () => {
    let values: any;
    try {
      values = await form.validateFields();
    } catch {
      return; // form shows validation errors
    }

    if (!clientId) {
      message.error('No client ID found');
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
        ...values,
        sync_interval_hours: syncAuto ? (values.sync_interval_hours ?? 6) : null,
        field_mappings,
      });

      message.success('Quickbase configuration saved');
    } catch (err: any) {
      message.error(err?.message || 'Failed to save config');
    } finally {
      setSaving(false);
    }
  };

  // -------------------------------------------------------------------------
  // Field fetch from QB
  // -------------------------------------------------------------------------

  const handleFetchFields = async (tableKey: string, force = false) => {
    if (!clientId) {
      message.error('No client ID');
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

      if (force) message.success(`Refreshed ${fetched.length} fields from QB`);
    } catch (err: any) {
      // Silently skip on background load (no config yet); show error on manual fetch
      if (force) message.error(err?.message || 'Failed to fetch QB fields');
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
  // Mapping table columns factory
  // -------------------------------------------------------------------------

  const buildColumns = (tableKey: string) => [
    {
      title: 'QB Field ID',
      dataIndex: 'fieldId',
      key: 'fieldId',
      width: 120,
      render: (_: string, record: MappingRow) => (
        <Input
          value={record.fieldId}
          size="small"
          style={{ width: 100 }}
          onChange={e => {
            const newId = e.target.value;
            const match = (qbFields[tableKey] || []).find(f => String(f.id) === newId);
            updateRow(tableKey, record.key, {
              fieldId: newId,
              fieldName: match ? match.label : '',
            });
          }}
        />
      ),
    },
    {
      title: 'QB Field Name',
      dataIndex: 'fieldName',
      key: 'fieldName',
      render: (val: string) => (
        <Text type={val ? undefined : 'secondary'} style={{ fontSize: 13 }}>
          {val || <span style={{ fontStyle: 'italic' }}>— unknown field ID —</span>}
        </Text>
      ),
    },
    {
      title: '',
      key: 'arrow',
      width: 40,
      render: () => <ArrowRightOutlined style={{ color: '#999' }} />,
    },
    {
      title: 'Destination Column',
      dataIndex: 'destColumn',
      key: 'destColumn',
      width: 220,
      render: (_: string, record: MappingRow) => (
        <AutoComplete
          value={record.destColumn}
          size="small"
          style={{ width: 200 }}
          options={(DEST_COLUMNS[tableKey] || []).map(col => ({ value: col }))}
          filterOption={(input, option) =>
            (option?.value as string)?.toLowerCase().includes(input.toLowerCase())
          }
          onChange={val => updateRow(tableKey, record.key, { destColumn: val })}
          placeholder="Select or type column"
        />
      ),
    },
    {
      title: '',
      key: 'action',
      width: 50,
      render: (_: any, record: MappingRow) => (
        <Button
          type="text"
          size="small"
          danger
          icon={<DeleteOutlined />}
          onClick={() => deleteRow(tableKey, record.key)}
        />
      ),
    },
  ];

  // -------------------------------------------------------------------------
  // Tab items — two-panel layout: field palette (left) + mapping table (right)
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

  const tabItems = TABLES.map(t => {
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
          message.info(`Field "${data.fieldName}" is already mapped`);
          return;
        }
        addFieldToMapping(t.key, data.fieldId, data.fieldName);
      } catch { /* ignore */ }
    };

    const mappedCount = mappedIds.size;
    const unmappedCount = allFields.filter(f => !mappedIds.has(String(f.id))).length;

    return {
      key: t.key,
      label: (
        <span>
          {t.label}
          {allFields.length > 0 && (
            <Tag
              color={unmappedCount > 0 ? 'blue' : 'green'}
              style={{ marginLeft: 6, fontSize: 11, lineHeight: '16px', padding: '0 5px' }}
            >
              {mappedCount}/{allFields.length}
            </Tag>
          )}
        </span>
      ),
      children: (
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>

          {/* ── LEFT PANEL: QB field palette ── */}
          <div style={{
            width: 260,
            flexShrink: 0,
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 8,
            overflow: 'hidden',
            background: 'rgba(255,255,255,0.03)',
          }}>
            {/* Panel header */}
            <div style={{
              padding: '10px 14px',
              borderBottom: '1px solid rgba(255,255,255,0.08)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'rgba(255,255,255,0.04)',
            }}>
              <div>
                <Text strong style={{ fontSize: 13 }}>QB Fields</Text>
                {qbFieldsSyncedAt[t.key] && (
                  <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', marginTop: 1 }}>
                    Synced {new Date(qbFieldsSyncedAt[t.key]!).toLocaleString()}
                  </div>
                )}
              </div>
              <Tooltip title={allFields.length > 0 ? 'Re-fetch from QB and update cache' : 'Fetch from QB and cache'}>
                <Button
                  size="small"
                  type="text"
                  icon={<SyncOutlined spin={fetchingFields[t.key]} />}
                  loading={fetchingFields[t.key]}
                  onClick={() => handleFetchFields(t.key, true)}
                  style={{ fontSize: 12 }}
                >
                  {allFields.length > 0 ? 'Refresh' : 'Fetch'}
                </Button>
              </Tooltip>
            </div>

            {/* Search */}
            {allFields.length > 0 && (
              <div style={{ padding: '8px 10px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <Input
                  size="small"
                  placeholder="Search fields…"
                  allowClear
                  value={fieldSearch[t.key] || ''}
                  onChange={e => setFieldSearch(prev => ({ ...prev, [t.key]: e.target.value }))}
                />
              </div>
            )}

            {/* Field list */}
            {allFields.length === 0 ? (
              <div style={{
                padding: '32px 16px',
                textAlign: 'center',
                color: 'rgba(255,255,255,0.3)',
              }}>
                <SyncOutlined style={{ fontSize: 24, marginBottom: 8, display: 'block' }} />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Click Fetch to load<br />available QB fields
                </Text>
              </div>
            ) : availableFields.length === 0 ? (
              <div style={{ padding: '20px 16px', textAlign: 'center' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>No fields match "{fieldSearch[t.key]}"</Text>
              </div>
            ) : (
              <div style={{ maxHeight: 420, overflowY: 'auto', padding: '6px 0' }}>
                {availableFields.map(f => {
                  const isMapped = mappedIds.has(String(f.id));
                  return (
                    <Tooltip
                      key={f.id}
                      title={isMapped ? 'Already mapped' : 'Drag or click to add'}
                      placement="right"
                      mouseEnterDelay={0.6}
                    >
                      <div
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
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          padding: '6px 14px',
                          cursor: isMapped ? 'default' : 'grab',
                          opacity: isMapped ? 0.4 : 1,
                          transition: 'background 0.15s',
                          userSelect: 'none',
                        }}
                        onMouseEnter={e => {
                          if (!isMapped) (e.currentTarget as HTMLDivElement).style.background = 'rgba(24,144,255,0.1)';
                        }}
                        onMouseLeave={e => {
                          (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                        }}
                      >
                        {isMapped
                          ? <CheckCircleFilled style={{ fontSize: 13, color: '#52c41a', flexShrink: 0 }} />
                          : <HolderOutlined style={{ fontSize: 13, color: 'rgba(255,255,255,0.3)', flexShrink: 0 }} />
                        }
                        <span style={{ fontSize: 12, minWidth: 0 }}>
                          <Text type="secondary" style={{ fontSize: 11, marginRight: 4 }}>#{f.id}</Text>
                          <Text style={{ fontSize: 12 }}>{f.label}</Text>
                        </span>
                      </div>
                    </Tooltip>
                  );
                })}
              </div>
            )}
          </div>

          {/* ── RIGHT PANEL: mapping table + drop zone ── */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              onDragOver={e => {
                e.preventDefault();
                if (!isOver) setDragOver(prev => ({ ...prev, [t.key]: true }));
              }}
              onDragLeave={e => {
                // only fire when leaving the container itself
                if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                  setDragOver(prev => ({ ...prev, [t.key]: false }));
                }
              }}
              onDrop={onDrop}
              style={{
                borderRadius: 8,
                border: isOver
                  ? '2px dashed #1677ff'
                  : '2px dashed transparent',
                background: isOver ? 'rgba(22,119,255,0.06)' : 'transparent',
                transition: 'border-color 0.2s, background 0.2s',
                padding: isOver ? 4 : 0,
              }}
            >
              <Table
                dataSource={fieldMappings[t.key] || []}
                columns={buildColumns(t.key)}
                rowKey="key"
                size="small"
                pagination={false}
                scroll={{ y: 360 }}
                locale={{
                  emptyText: (
                    <div style={{ padding: '32px 0', color: 'rgba(255,255,255,0.3)' }}>
                      <ArrowRightOutlined style={{ fontSize: 20, marginBottom: 8, display: 'block', transform: 'rotate(270deg)' }} />
                      <div style={{ fontSize: 13 }}>
                        {availableFields.length > 0
                          ? 'Drag fields from the left panel — or click them to add'
                          : 'Fetch QB fields first, then drag them here'}
                      </div>
                    </div>
                  ),
                }}
              />
            </div>
            <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Button
                size="small"
                icon={<PlusOutlined />}
                onClick={() => addRow(t.key)}
              >
                Add Row Manually
              </Button>
              {mappedIds.size > 0 && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {mappedIds.size} field{mappedIds.size !== 1 ? 's' : ''} mapped
                </Text>
              )}
            </div>
          </div>
        </div>
      ),
    };
  });

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <Space align="center" size={16}>
          <Title level={3} style={{ margin: 0 }}>Quickbase Configuration</Title>
          <ClientSelector value={clientId || ''} onChange={id => setClientId(id)} />
        </Space>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          loading={saving}
          onClick={handleSaveAll}
        >
          Save All
        </Button>
      </div>

      {/* QB Synced Data Status */}
      {qbStatus && (
        <Card
          className="glass-card"
          style={{ marginBottom: 16 }}
          title={<span style={{ fontSize: 14 }}>Quickbase Synced Data</span>}
          extra={
            <Space>
              {qbStatus.last_sync_at && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Last sync: {new Date(qbStatus.last_sync_at).toLocaleString()}
                </Text>
              )}
              <Dropdown.Button
                type="primary"
                icon={<DownOutlined />}
                loading={qbSyncing}
                onClick={() => handleQBSync(false)}
                size="small"
                menu={{
                  items: [
                    { key: 'full', label: 'Full Sync (re-fetch all)', onClick: () => handleQBSync(true) },
                  ],
                }}
              >
                <SyncOutlined spin={qbSyncing} /> Sync
              </Dropdown.Button>
              <Button
                icon={<ArrowRightOutlined />}
                loading={rematching}
                onClick={handleRematch}
                size="small"
              >
                Re-match
              </Button>
            </Space>
          }
        >
          <Row gutter={[16, 12]}>
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
                <Col key={key} xs={12} sm={8} md={6} lg={4}>
                  <div style={{
                    padding: '10px 14px',
                    borderRadius: 8,
                    border: `1px solid ${hasError ? 'rgba(255,77,79,0.3)' : 'rgba(255,255,255,0.08)'}`,
                    background: hasError ? 'rgba(255,77,79,0.06)' : 'rgba(255,255,255,0.03)',
                  }}>
                    <Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 2 }}>
                      {label}
                    </Text>
                    <div style={{ fontSize: 20, fontWeight: 600, lineHeight: 1.2 }}>
                      {(qbStatus.record_counts[key] ?? 0).toLocaleString()}
                    </div>
                    {log?.table_id && (
                      <Tooltip title="QB Table ID (cross-ref: Field Definitions)">
                        <Tag style={{ fontSize: 10, marginTop: 4, cursor: 'default' }}>
                          {log.table_id}
                        </Tag>
                      </Tooltip>
                    )}
                    {log?.synced_at ? (
                      <div style={{ fontSize: 10, color: hasError ? '#ff4d4f' : 'rgba(255,255,255,0.3)', marginTop: 3 }}>
                        {hasError ? (log.error_message || 'Error') : new Date(log.synced_at).toLocaleString()}
                      </div>
                    ) : (
                      <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.2)', marginTop: 3 }}>
                        Not synced yet
                      </div>
                    )}
                    <Dropdown.Button
                      size="small"
                      icon={<DownOutlined />}
                      loading={tableSyncing[key]}
                      onClick={() => handleTableSync(key, false)}
                      style={{ marginTop: 8, width: '100%', fontSize: 11 }}
                      menu={{
                        items: [
                          { key: 'full', label: 'Full Sync (re-fetch all)', onClick: () => handleTableSync(key, true) },
                        ],
                      }}
                    >
                      <SyncOutlined spin={tableSyncing[key]} /> Sync
                    </Dropdown.Button>
                  </div>
                </Col>
              );
            })}
          </Row>
        </Card>
      )}

      {/* Info alert */}
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
        message="Field mappings override the default Carbon8 field mappings. Only configure if your QB schema differs from the defaults."
      />

      {/* Single Form wraps both Connection + Table IDs so all fields register together */}
      <Form form={form} layout="vertical">
        {/* Connection Settings */}
        <Card title="Connection Settings" className="glass-card" style={{ marginBottom: 24 }}>
          <Space wrap size={16} style={{ width: '100%' }}>
            <Form.Item
              label="Realm Hostname"
              name="realm_hostname"
              rules={[{ required: true, message: 'Realm hostname is required' }]}
              style={{ marginBottom: 0, minWidth: 220 }}
            >
              <Input placeholder="dc.quickbase.com" style={{ width: 220 }} />
            </Form.Item>
            <Form.Item
              label="App ID"
              name="app_id"
              rules={[{ required: true, message: 'App ID is required' }]}
              style={{ marginBottom: 0, minWidth: 140 }}
            >
              <Input placeholder="buzfemk4f" style={{ width: 140 }} />
            </Form.Item>
            <Form.Item
              label="User Token"
              name="user_token"
              extra="Clear to remove token and disable sync"
              style={{ marginBottom: 0, minWidth: 260 }}
            >
              <Input.Password
                placeholder="QB user token"
                style={{ width: 260 }}
                visibilityToggle
              />
            </Form.Item>
            <Form.Item
              label="Sync Mode"
              style={{ marginBottom: 0 }}
            >
              <Space>
                <Switch
                  checked={syncAuto}
                  onChange={setSyncAuto}
                  checkedChildren="Auto"
                  unCheckedChildren="Manual"
                />
                {syncAuto && (
                  <Form.Item
                    name="sync_interval_hours"
                    noStyle
                    rules={[{ required: true, message: 'Interval required' }]}
                  >
                    <InputNumber
                      min={1} max={168} step={1}
                      style={{ width: 90 }}
                      placeholder="6"
                    />
                  </Form.Item>
                )}
              </Space>
            </Form.Item>
          </Space>
          <div style={{ marginTop: 12 }}>
            <Button
              size="small"
              onClick={async () => {
                if (!clientId) { message.error('No client ID'); return; }
                try {
                  await api.get<any>(`/v1/quickbase/config?client_id=${clientId}`);
                  message.success('Connection config found');
                } catch {
                  message.error('No QB config found for this client');
                }
              }}
            >
              Test Connection
            </Button>
          </div>
        </Card>

        {/* Table IDs */}
        <Card title="Table IDs" className="glass-card" style={{ marginBottom: 24 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
            {TABLES.map(t => (
              <Form.Item
                key={t.key}
                label={t.label}
                name={t.configField}
                rules={[{ required: true, message: `${t.label} table ID is required` }]}
                style={{ marginBottom: 0, flex: '1 1 180px' }}
              >
                <Input placeholder="QB table ID" style={{ width: '100%' }} />
              </Form.Item>
            ))}
          </div>
        </Card>
      </Form>

      {/* Field Mappings */}
      <Card title="Field Mappings" className="glass-card">
        <Divider style={{ marginTop: 0, marginBottom: 16 }} />
        <Tabs items={tabItems} type="card" />
      </Card>
    </div>
  );
};

export default QuickbaseConfigPage;
