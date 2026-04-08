/**
 * AI Usage & Monitoring Page — Sprint 3
 *
 * Real-time cost tracking, monitoring metrics, and AI control switches.
 * Admin-level controls for budget caps, kill switches, and feature toggles.
 *
 * Migrated from Ant Design to Tailwind CSS + Lucide icons.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  DollarSign, Zap, AlertTriangle, RefreshCw, PauseCircle, PlayCircle,
  Clock, CheckCircle2, X, AlertCircle, Mail, Building2,
  Wrench, Search, RotateCw,
} from 'lucide-react';
import { Spinner } from '@/lib/icons';
import { toast } from '@/lib/toast';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { useClient } from '../../contexts/ClientContext';
import * as vectorApi from '../../services/vectorService';
import { controlsApi, intelligenceApi } from '../../services/aiService';
import { modelsApi } from '../../services/strategicDigestService';
import { MailboxSelector } from '../../components/MailboxSelector';
import api from '../../services/apiClient';
import { formatTime } from '../../utils/dateUtils';
import {
  useAICosts, useAIMonitoring, useAIControls, useAIRecentLogs,
  useAIModels, useAIApiKeys, useClientAISettings,
} from '../../hooks/queries';
import type { UsageSummary, MonitoringStats, AIControlSettings, UsageLogEntry } from '../../types/ai';
import type { AIModel } from '../../types/strategic-digest';

/* ------------------------------------------------------------------ */
/* Toggle Switch — native checkbox styled as switch                    */
/* ------------------------------------------------------------------ */
const Toggle: React.FC<{
  checked: boolean;
  onChange: (val: boolean) => void;
  disabled?: boolean;
  size?: 'sm' | 'default';
}> = ({ checked, onChange, disabled, size = 'default' }) => {
  const w = size === 'sm' ? 'w-8' : 'w-10';
  const h = size === 'sm' ? 'h-4' : 'h-5';
  const dot = size === 'sm' ? 'h-3 w-3' : 'h-4 w-4';
  const translate = size === 'sm' ? 'translate-x-4' : 'translate-x-5';
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={`
        relative inline-flex ${w} ${h} shrink-0 cursor-pointer rounded-full
        border-2 border-transparent transition-colors duration-200 ease-in-out
        focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2
        ${checked ? 'bg-indigo-600' : 'bg-slate-200'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
      `}
    >
      <span className="sr-only">Toggle</span>
      <span
        className={`
          pointer-events-none inline-block ${dot} transform rounded-full bg-white shadow ring-0
          transition duration-200 ease-in-out
          ${checked ? translate : 'translate-x-0'}
        `}
      />
    </button>
  );
};

const UsagePage: React.FC = () => {
  const { clientId } = useClient();
  const [autoRefresh, setAutoRefresh] = useState(true);

  // API keys form state (replaces Form.useForm())
  const [anthropicKey, setAnthropicKey] = useState('');
  const [googleKey, setGoogleKey] = useState('');
  const [openaiKey, setOpenaiKey] = useState('');
  const [apiKeysSaving, setApiKeysSaving] = useState(false);

  // Re-analyze state
  const [reanalyzeMailbox, setReanalyzeMailbox] = useState<string[]>([]);
  const [reanalyzeVersion, setReanalyzeVersion] = useState('v1.2');
  const [reanalyzeMax, setReanalyzeMax] = useState(500);
  const [reanalyzeIncludeFailed, setReanalyzeIncludeFailed] = useState(false);
  const [reanalyzeLoading, setReanalyzeLoading] = useState(false);

  // All data via TanStack Query — auto-refresh every 60s when enabled
  const costsQuery = useAICosts(clientId, 30);
  const monitoringQuery = useAIMonitoring(clientId);
  const controlsQuery = useAIControls();
  const logsQuery = useAIRecentLogs(30);
  const modelsQuery = useAIModels();
  const apiKeysQuery = useAIApiKeys(clientId);
  const clientSettingsQuery = useClientAISettings(clientId);

  const costs = costsQuery.data || null;
  const monitoring = monitoringQuery.data || null;
  const controls = controlsQuery.data || null;
  const recentLogs = logsQuery.data?.items || [];
  const models = modelsQuery.data?.models || [];
  const apiKeys = apiKeysQuery.data || null;
  const loading = costsQuery.isLoading;

  // Derive model selections from client settings -> controls -> defaults
  const clientSettings = clientSettingsQuery.data || {};
  const cheapModel = clientSettings['ai_cheap_model'] || controls?.cheap_model || 'haiku';
  const strategicModel = clientSettings['ai_strategic_model'] || controls?.strategic_model || 'sonnet';

  // Manual refresh handler
  const loadData = () => {
    costsQuery.refetch();
    monitoringQuery.refetch();
    controlsQuery.refetch();
    logsQuery.refetch();
    apiKeysQuery.refetch();
    clientSettingsQuery.refetch();
  };

  // Control update handler
  const handleControlChange = async (key: string, value: any) => {
    try {
      const result = await controlsApi.update({ [key]: value });
      if (result?.settings) {
        controlsQuery.refetch();
        toast.success(`Updated ${key.replace(/_/g, ' ')}`);
      }
    } catch {
      toast.error('Failed to update setting');
    }
  };

  const handleResetSpend = async () => {
    const result = await controlsApi.resetSessionSpend();
    if (result) {
      toast.success(`Session spend reset (was $${result.previous_spend_usd})`);
      loadData();
    }
  };

  const handleApiKeysSave = async () => {
    if (!anthropicKey && !googleKey && !openaiKey) {
      toast.warning('Enter at least one key to update');
      return;
    }
    setApiKeysSaving(true);
    try {
      const result = await api.put<any>('/v1/ai/api-keys', {
        anthropic_api_key: anthropicKey || undefined,
        google_api_key: googleKey || undefined,
        openai_api_key: openaiKey || undefined,
        client_id: clientId || undefined,
      });
      toast.success(`Keys updated: ${result.updated?.join(', ')}`);
      setAnthropicKey('');
      setGoogleKey('');
      setOpenaiKey('');
      apiKeysQuery.refetch();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to update keys');
    } finally {
      setApiKeysSaving(false);
    }
  };

  const handleReanalyze = async () => {
    const mailboxId = reanalyzeMailbox[0];
    if (!mailboxId) { toast.warning('Select a mailbox'); return; }
    if (!reanalyzeVersion.trim()) { toast.warning('Enter a prompt version to target'); return; }
    setReanalyzeLoading(true);
    try {
      const result = await intelligenceApi.reanalyze(mailboxId, reanalyzeVersion, reanalyzeMax, reanalyzeIncludeFailed);
      if (result?.status === 'no_candidates') {
        toast.info(result.message);
      } else if (result) {
        toast.success(`${result.message} — ${result.emails_queued} emails queued`);
      }
    } catch (err: any) {
      toast.error(err?.message || 'Re-analysis failed');
    } finally {
      setReanalyzeLoading(false);
    }
  };

  const handleModelChange = async (type: 'cheap' | 'strategic', value: string) => {
    const newCheap = type === 'cheap' ? value : cheapModel;
    const newStrategic = type === 'strategic' ? value : strategicModel;
    try {
      await modelsApi.updateDefaults(newCheap, newStrategic, clientId || undefined);
      clientSettingsQuery.refetch();
      toast.success(`${type === 'cheap' ? 'Fast' : 'Strategic'} model set to ${value}`);
    } catch (err) {
      toast.error('Failed to update model');
    }
  };

  const showSkeleton = loading || !costs;

  const budgetUsedPct = controls
    ? Math.min((controls.session_spend_usd / controls.daily_budget_usd) * 100, 100)
    : 0;

  const budgetColor = budgetUsedPct >= 90 ? 'text-red-500' : budgetUsedPct >= 70 ? 'text-amber-500' : 'text-emerald-500';
  const budgetBarColor = budgetUsedPct >= 90 ? 'bg-red-500' : budgetUsedPct >= 70 ? 'bg-amber-500' : 'bg-emerald-500';

  /* ------------------------------------------------------------------ */
  /* Pagination state for Recent API Calls table                        */
  /* ------------------------------------------------------------------ */
  const [logPage, setLogPage] = useState(1);
  const logsPerPage = 15;
  const totalLogPages = Math.ceil(recentLogs.length / logsPerPage);
  const pagedLogs = recentLogs.slice((logPage - 1) * logsPerPage, logPage * logsPerPage);

  return (
    <PageShell>
      {/* Header */}
      <PageHeader
        title="AI Usage & Monitoring"
        actions={
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">Auto-refresh</span>
            <Toggle checked={autoRefresh} onChange={setAutoRefresh} size="sm" />
            <button
              onClick={loadData}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        }
      />

      {/* Credit Balance / API Error Alert */}
      {monitoring && monitoring.total_failures_24h > 0 && monitoring.api_failure_rate > 50 && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-4 flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-800">API Errors Detected</p>
            <p className="text-xs text-red-700 mt-1">
              High API failure rate in the last 24 hours. This may indicate insufficient Anthropic credits or an API key issue. Check your Anthropic account balance and update the API key if needed.
            </p>
          </div>
        </div>
      )}

      {/* Budget Alert */}
      {controls && controls.session_spend_usd >= controls.daily_budget_usd * 0.8 && (() => {
        const isOver = controls.session_spend_usd >= controls.daily_budget_usd;
        const borderCls = isOver ? 'border-red-200 bg-red-50' : 'border-amber-200 bg-amber-50';
        const iconCls = isOver ? 'text-red-500' : 'text-amber-500';
        const titleCls = isOver ? 'text-red-800' : 'text-amber-800';
        const bodyCls = isOver ? 'text-red-700' : 'text-amber-700';
        return (
          <div className={`mb-4 rounded-lg border ${borderCls} p-4 flex items-start gap-3`}>
            <AlertTriangle className={`h-5 w-5 ${iconCls} mt-0.5 shrink-0`} />
            <div>
              <p className={`text-sm font-semibold ${titleCls}`}>Budget Warning</p>
              <p className={`text-xs ${bodyCls} mt-1`}>
                Session spend (${controls.session_spend_usd.toFixed(4)}) is approaching the daily budget cap (${controls.daily_budget_usd.toFixed(2)}). API calls will be blocked when the cap is reached.
              </p>
            </div>
          </div>
        );
      })()}

      {!clientId && (
        <div className="rounded-lg border bg-white shadow-sm mb-6 p-12 text-center">
          <p className="text-sm text-slate-400">Select a client to view AI usage</p>
        </div>
      )}

      {/* Row 1: Key Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {/* Total Spend (30d) */}
        <div className="rounded-lg border bg-white shadow-sm p-4">
          {showSkeleton ? <ContentSkeleton rows={1} /> : (
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1">Total Spend (30d)</p>
              <div className="flex items-center gap-2">
                <DollarSign className="h-4 w-4 text-indigo-500" />
                <span className="text-xl font-semibold text-indigo-500">
                  ${(costs?.total_cost_usd || 0).toFixed(4)}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Session Spend */}
        <div className="rounded-lg border bg-white shadow-sm p-4">
          {showSkeleton ? <ContentSkeleton rows={2} /> : (
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1">Session Spend</p>
              <div className="flex items-center gap-2 mb-2">
                <DollarSign className={`h-4 w-4 ${budgetColor}`} />
                <span className={`text-xl font-semibold ${budgetColor}`}>
                  ${(controls?.session_spend_usd || 0).toFixed(4)}
                </span>
              </div>
              {/* Progress bar */}
              <div className="w-full bg-slate-100 rounded-full h-1.5">
                <div
                  className={`${budgetBarColor} h-1.5 rounded-full transition-all`}
                  style={{ width: `${Math.round(budgetUsedPct)}%` }}
                />
              </div>
              <p className="text-[10px] text-slate-400 mt-1">
                {Math.round(budgetUsedPct)}% of ${controls?.daily_budget_usd || 0}
              </p>
            </div>
          )}
        </div>

        {/* Requests (24h) */}
        <div className="rounded-lg border bg-white shadow-sm p-4">
          {showSkeleton ? <ContentSkeleton rows={1} /> : (
            <div>
              <p className="text-xs font-medium text-slate-500 mb-1">Requests (24h)</p>
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-slate-500" />
                <span className="text-xl font-semibold text-slate-900">
                  {(monitoring?.total_requests_24h || 0).toLocaleString('en-AU')}
                </span>
              </div>
              <p className="text-[10px] text-slate-400 mt-1">
                {(monitoring?.total_failures_24h || 0).toLocaleString('en-AU')} failures
              </p>
            </div>
          )}
        </div>

        {/* Daily Credit Remaining */}
        <div className="rounded-lg border bg-white shadow-sm p-4">
          {showSkeleton ? <ContentSkeleton rows={1} /> : (() => {
            const dailyRemaining = Math.max((controls?.daily_budget_usd || 0) - (controls?.session_spend_usd || 0), 0);
            const monthlyRemaining = Math.max((controls?.monthly_budget_usd || 0) - (costs?.total_cost_usd || 0), 0);
            const dailyPct = controls?.daily_budget_usd ? (dailyRemaining / controls.daily_budget_usd) * 100 : 100;
            const creditColor = dailyPct <= 10 ? 'text-red-500' : dailyPct <= 30 ? 'text-amber-500' : 'text-emerald-500';
            return (
              <div>
                <p className="text-xs font-medium text-slate-500 mb-1">Daily Credit Remaining</p>
                <div className="flex items-center gap-2">
                  <DollarSign className={`h-4 w-4 ${creditColor}`} />
                  <span className={`text-xl font-semibold ${creditColor}`}>
                    ${dailyRemaining.toFixed(4)}
                  </span>
                </div>
                <p className="text-[10px] text-slate-400 mt-1">
                  Monthly: ${monthlyRemaining.toFixed(2)} / ${controls?.monthly_budget_usd?.toFixed(2) || '0'}
                </p>
              </div>
            );
          })()}
        </div>
      </div>

      {/* Row 2: Controls + Monitoring */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* AI Controls */}
        <div className="rounded-lg border bg-white shadow-sm">
          <div className="flex items-center justify-between border-b px-5 py-3">
            <div className="flex items-center gap-2">
              <span className={`inline-block h-2 w-2 rounded-full ${controls?.ai_enabled ? 'bg-emerald-500' : 'bg-red-500'}`} />
              <h3 className="text-sm font-semibold text-slate-900">
                AI Controls{!controls?.ai_enabled && ' (DISABLED)'}
              </h3>
            </div>
            <button
              onClick={handleResetSpend}
              className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 shadow-sm hover:bg-slate-50 transition"
            >
              Reset Spend
            </button>
          </div>
          <div className="p-5 space-y-4">
            {/* Master Kill Switch */}
            <div className={`flex items-center justify-between rounded-lg p-3 ${controls?.ai_enabled ? 'bg-emerald-50' : 'bg-red-50'}`}>
              <div>
                <p className="text-sm font-semibold text-slate-800">Master AI Switch</p>
                <p className="text-[11px] text-slate-500">Disables ALL AI API calls immediately</p>
              </div>
              <Toggle
                checked={controls?.ai_enabled ?? false}
                onChange={(val) => handleControlChange('ai_enabled', val)}
              />
            </div>

            <hr className="border-slate-100" />

            {/* Feature Toggles */}
            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Feature Toggles</h4>
            <div className="flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-700">Email Analysis (Haiku)</span>
                <Toggle
                  checked={controls?.email_analysis_enabled ?? false}
                  onChange={(val) => handleControlChange('email_analysis_enabled', val)}
                  size="sm"
                  disabled={!controls?.ai_enabled}
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-700">Daily Digest (Sonnet)</span>
                <Toggle
                  checked={controls?.digest_enabled ?? false}
                  onChange={(val) => handleControlChange('digest_enabled', val)}
                  size="sm"
                  disabled={!controls?.ai_enabled}
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-700">Relationship Summaries (Sonnet)</span>
                <Toggle
                  checked={controls?.relationship_summary_enabled ?? false}
                  onChange={(val) => handleControlChange('relationship_summary_enabled', val)}
                  size="sm"
                  disabled={!controls?.ai_enabled}
                />
              </div>
            </div>

            <hr className="border-slate-100" />

            {/* Model Selection */}
            {models.length > 0 && (
              <>
                <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">AI Model Selection</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[11px] text-slate-500 mb-1">Fast tasks (email analysis, insights)</p>
                    <select
                      value={cheapModel}
                      onChange={(e) => handleModelChange('cheap', e.target.value)}
                      disabled={!controls?.ai_enabled}
                      className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {models.map(m => (
                        <option key={m.name} value={m.name} disabled={!m.available}>
                          {m.label} {m.cost_input_per_mtok === 0 ? '(free)' : `($${m.cost_input_per_mtok}/MTok)`}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-500 mb-1">Strategic tasks (digest, reports)</p>
                    <select
                      value={strategicModel}
                      onChange={(e) => handleModelChange('strategic', e.target.value)}
                      disabled={!controls?.ai_enabled}
                      className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {models.map(m => (
                        <option key={m.name} value={m.name} disabled={!m.available}>
                          {m.label} {m.cost_input_per_mtok === 0 ? '(free)' : `($${m.cost_input_per_mtok}/MTok)`}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <hr className="border-slate-100" />
              </>
            )}

            {/* Budget Controls */}
            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Budget Limits</h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[11px] text-slate-500 mb-1">Daily Cap (USD)</p>
                <input
                  type="number"
                  defaultValue={controls?.daily_budget_usd}
                  min={0.01}
                  max={100}
                  step={0.5}
                  className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
                  onBlur={(e) => {
                    const val = parseFloat(e.target.value);
                    if (!isNaN(val) && val > 0) handleControlChange('daily_budget_usd', val);
                  }}
                />
              </div>
              <div>
                <p className="text-[11px] text-slate-500 mb-1">Monthly Cap (USD)</p>
                <input
                  type="number"
                  defaultValue={controls?.monthly_budget_usd}
                  min={1}
                  max={500}
                  step={1}
                  className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
                  onBlur={(e) => {
                    const val = parseFloat(e.target.value);
                    if (!isNaN(val) && val > 0) handleControlChange('monthly_budget_usd', val);
                  }}
                />
              </div>
            </div>

            <hr className="border-slate-100" />

            {/* Batch Controls */}
            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Processing Limits</h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-[11px] text-slate-500 mb-1">Emails per batch</p>
                <input
                  type="number"
                  defaultValue={controls?.batch_size}
                  min={1}
                  max={25}
                  step={1}
                  className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
                  onBlur={(e) => {
                    const val = parseInt(e.target.value);
                    if (!isNaN(val) && val > 0) handleControlChange('batch_size', val);
                  }}
                />
              </div>
              <div>
                <p className="text-[11px] text-slate-500 mb-1">Max emails per run</p>
                <input
                  type="number"
                  defaultValue={controls?.max_emails_per_run}
                  min={10}
                  max={5000}
                  step={50}
                  className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
                  onBlur={(e) => {
                    const val = parseInt(e.target.value);
                    if (!isNaN(val) && val > 0) handleControlChange('max_emails_per_run', val);
                  }}
                />
              </div>
            </div>

            <hr className="border-slate-100" />

            {/* API Keys */}
            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">API Keys</h4>
            <div className="flex flex-col gap-1.5 mb-3">
              <div className="flex justify-between text-xs">
                <span className="text-slate-700">Anthropic (Claude)</span>
                <span className={apiKeys?.anthropic_set ? 'text-emerald-600' : 'text-red-500'}>
                  {apiKeys?.anthropic_set ? apiKeys.anthropic_masked : 'Not set'}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-700">Google (Gemini)</span>
                <span className={apiKeys?.google_set ? 'text-emerald-600' : 'text-slate-400'}>
                  {apiKeys?.google_set ? apiKeys.google_masked : 'Not set'}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-slate-700">OpenAI (GPT-4o)</span>
                <span className={apiKeys?.openai_set ? 'text-emerald-600' : 'text-slate-400'}>
                  {apiKeys?.openai_set ? apiKeys.openai_masked : 'Not set'}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div>
                <label className="block text-[11px] text-slate-500 mb-1">Anthropic API Key</label>
                <input
                  type="password"
                  placeholder="sk-ant-..."
                  value={anthropicKey}
                  onChange={(e) => setAnthropicKey(e.target.value)}
                  className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-500 mb-1">Google API Key</label>
                <input
                  type="password"
                  placeholder="AIza..."
                  value={googleKey}
                  onChange={(e) => setGoogleKey(e.target.value)}
                  className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-500 mb-1">OpenAI API Key</label>
                <input
                  type="password"
                  placeholder="sk-..."
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
                />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleApiKeysSave}
                disabled={apiKeysSaving}
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition disabled:opacity-50"
              >
                {apiKeysSaving && <Spinner className="h-3 w-3 animate-spin" />}
                Update Keys
              </button>
              <span className="text-[10px] text-slate-400">Runtime only — add to .env for persistence</span>
            </div>
          </div>
        </div>

        {/* Monitoring Health */}
        <div className="rounded-lg border bg-white shadow-sm">
          <div className="border-b px-5 py-3">
            <h3 className="text-sm font-semibold text-slate-900">Health Monitoring (24h)</h3>
          </div>
          <div className="p-5">
            <div className="grid grid-cols-2 gap-4 mb-4">
              {/* API Failure Rate */}
              <div>
                <p className="text-xs font-medium text-slate-500 mb-1">API Failure Rate</p>
                <div className="flex items-center gap-2">
                  {monitoring && monitoring.api_failure_rate > 0.1
                    ? <AlertTriangle className="h-4 w-4 text-red-500" />
                    : <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  }
                  <span className={`text-lg font-semibold ${monitoring && monitoring.api_failure_rate > 0.1 ? 'text-red-500' : 'text-emerald-500'}`}>
                    {((monitoring?.api_failure_rate || 0) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
              {/* Parse Failure Rate */}
              <div>
                <p className="text-xs font-medium text-slate-500 mb-1">Parse Failure Rate</p>
                <div className="flex items-center gap-2">
                  {monitoring && monitoring.parse_failure_rate > 0.05
                    ? <AlertCircle className="h-4 w-4 text-amber-500" />
                    : <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  }
                  <span className={`text-lg font-semibold ${monitoring && monitoring.parse_failure_rate > 0.05 ? 'text-amber-500' : 'text-emerald-500'}`}>
                    {((monitoring?.parse_failure_rate || 0) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
              {/* Avg Retry Count */}
              <div>
                <p className="text-xs font-medium text-slate-500 mb-1">Avg Retry Count</p>
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-slate-400" />
                  <span className="text-lg font-semibold text-slate-900">
                    {(monitoring?.avg_retry_count || 0).toFixed(2)}
                  </span>
                </div>
              </div>
              {/* Total Failures */}
              <div>
                <p className="text-xs font-medium text-slate-500 mb-1">Total Failures (24h)</p>
                <span className={`text-lg font-semibold ${(monitoring?.total_failures_24h || 0) > 0 ? 'text-red-500' : 'text-emerald-500'}`}>
                  {(monitoring?.total_failures_24h || 0).toLocaleString('en-AU')}
                </span>
              </div>
            </div>

            <hr className="border-slate-100 my-4" />

            {/* Cost by Operation */}
            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-3">Cost by Operation (30d)</h4>
            {costs?.by_operation && Object.entries(costs.by_operation).length > 0 ? (
              <div className="flex flex-col gap-2 mb-4">
                {Object.entries(costs.by_operation).map(([op, data]) => (
                  <div key={op} className="flex items-center justify-between">
                    <StatusBadge variant="neutral">{op}</StatusBadge>
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-slate-400">{data.count} calls</span>
                      <span className="text-xs font-semibold text-slate-900">${data.cost.toFixed(4)}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400 mb-4">No usage data yet</p>
            )}

            <hr className="border-slate-100 my-4" />

            <h4 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-3">Cost by Model (30d)</h4>
            {costs?.by_model && Object.entries(costs.by_model).length > 0 ? (
              <div className="flex flex-col gap-2">
                {Object.entries(costs.by_model).map(([model, data]) => {
                  const short = model.includes('haiku') ? 'Haiku' : model.includes('sonnet') ? 'Sonnet' : model;
                  return (
                    <div key={model} className="flex items-center justify-between">
                      <StatusBadge variant={short === 'Haiku' ? 'info' : 'purple'}>{short}</StatusBadge>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-slate-400">{data.count} calls</span>
                        <span className="text-xs font-semibold text-slate-900">${data.cost.toFixed(4)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-xs text-slate-400">No usage data yet</p>
            )}
          </div>
        </div>
      </div>

      {/* Row 3: Re-analyze */}
      <div className="rounded-lg border bg-white shadow-sm mb-6">
        <div className="flex items-center gap-2 border-b px-5 py-3">
          <RotateCw className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-900">Re-analyze Emails</h3>
        </div>
        <div className="p-5">
          <p className="text-xs text-slate-500 mb-4">
            Reset emails analyzed with an older prompt version so they are re-processed with the current prompt.
            Runs in the background — check Recent API Calls below for progress.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 items-end">
            <div>
              <p className="text-[11px] text-slate-500 mb-1">Mailbox</p>
              <MailboxSelector value={reanalyzeMailbox} onChange={setReanalyzeMailbox} mode="single" />
            </div>
            <div>
              <p className="text-[11px] text-slate-500 mb-1">Old prompt version</p>
              <input
                type="text"
                value={reanalyzeVersion}
                onChange={(e) => setReanalyzeVersion(e.target.value)}
                placeholder="e.g. v1.3"
                className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
              />
            </div>
            <div>
              <p className="text-[11px] text-slate-500 mb-1">Max emails</p>
              <input
                type="number"
                value={reanalyzeMax}
                min={10}
                max={5000}
                step={100}
                onChange={(e) => setReanalyzeMax(parseInt(e.target.value) || 500)}
                className="w-full rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 shadow-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400"
              />
            </div>
            <div className="flex items-center gap-2 pt-4">
              <input
                id="include-failed"
                type="checkbox"
                checked={reanalyzeIncludeFailed}
                onChange={(e) => setReanalyzeIncludeFailed(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="include-failed" className="text-xs text-slate-700">Include failed</label>
            </div>
            <div className="pt-4">
              <button
                onClick={handleReanalyze}
                disabled={!reanalyzeMailbox[0] || reanalyzeLoading}
                className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {reanalyzeLoading ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <RotateCw className="h-3.5 w-3.5" />}
                Start Re-analysis
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Row 4: Recent API Calls */}
      <div className="rounded-lg border bg-white shadow-sm mb-6">
        <div className="border-b px-5 py-3">
          <h3 className="text-sm font-semibold text-slate-900">Recent API Calls</h3>
        </div>
        <div className="p-5">
          {showSkeleton ? <ContentSkeleton rows={5} /> : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px]">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="text-left text-xs font-bold uppercase tracking-wider text-slate-600 px-3 py-2 w-[160px]">Time</th>
                      <th className="text-left text-xs font-bold uppercase tracking-wider text-slate-600 px-3 py-2 w-[140px]">Operation</th>
                      <th className="text-left text-xs font-bold uppercase tracking-wider text-slate-600 px-3 py-2 w-[200px]">Model</th>
                      <th className="text-left text-xs font-bold uppercase tracking-wider text-slate-600 px-3 py-2 w-[140px]">Tokens (in/out)</th>
                      <th className="text-left text-xs font-bold uppercase tracking-wider text-slate-600 px-3 py-2 w-[100px]">Cost</th>
                      <th className="text-left text-xs font-bold uppercase tracking-wider text-slate-600 px-3 py-2 w-[90px]">Latency</th>
                      <th className="text-center text-xs font-bold uppercase tracking-wider text-slate-600 px-3 py-2 w-[80px]">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50">
                    {pagedLogs.map((r, idx) => {
                      const modelShort = r.model?.includes('haiku') ? 'Haiku' : r.model?.includes('sonnet') ? 'Sonnet' : r.model || '-';
                      return (
                        <tr key={r.id || `${r.created_at}-${idx}`} className="hover:bg-slate-25">
                          <td className="px-3 py-2 text-xs text-slate-600">{r.created_at ? formatTime(r.created_at) : '-'}</td>
                          <td className="px-3 py-2">
                            <StatusBadge variant="neutral" size="sm">{r.operation || 'unknown'}</StatusBadge>
                          </td>
                          <td className="px-3 py-2">
                            <StatusBadge variant={modelShort === 'Haiku' ? 'info' : 'purple'} size="sm">{modelShort}</StatusBadge>
                          </td>
                          <td className="px-3 py-2 text-xs text-slate-600">
                            {(r.input_tokens || 0).toLocaleString('en-AU')} / {(r.output_tokens || 0).toLocaleString('en-AU')}
                          </td>
                          <td className="px-3 py-2 text-xs font-semibold text-slate-900">
                            ${(r.estimated_cost_usd || 0).toFixed(4)}
                          </td>
                          <td className="px-3 py-2 text-xs text-slate-600">
                            {r.processing_time_ms ? `${(r.processing_time_ms / 1000).toFixed(1)}s` : '-'}
                          </td>
                          <td className="px-3 py-2 text-center">
                            {r.success
                              ? <CheckCircle2 className="h-4 w-4 text-emerald-500 mx-auto" />
                              : (
                                <span title={r.error_detail || r.error_type || 'Failed'}>
                                  <X className="h-4 w-4 text-red-500 mx-auto" />
                                </span>
                              )
                            }
                          </td>
                        </tr>
                      );
                    })}
                    {pagedLogs.length === 0 && (
                      <tr>
                        <td colSpan={7} className="px-3 py-8 text-center text-xs text-slate-400">No recent API calls</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {/* Pagination */}
              {totalLogPages > 1 && (
                <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
                  <span className="text-[11px] text-slate-400">
                    {recentLogs.length.toLocaleString('en-AU')} total entries
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      disabled={logPage <= 1}
                      onClick={() => setLogPage(p => p - 1)}
                      className="rounded px-2 py-1 text-[11px] text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                    >
                      Prev
                    </button>
                    <span className="text-[11px] text-slate-500 px-2">{logPage} / {totalLogPages}</span>
                    <button
                      disabled={logPage >= totalLogPages}
                      onClick={() => setLogPage(p => p + 1)}
                      className="rounded px-2 py-1 text-[11px] text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Row 5: Embedding Coverage & Management */}
      <EmbeddingManagement clientId={clientId} />
    </PageShell>
  );
};


// ---------------------------------------------------------------------------
// Embedding Coverage & Management (moved from Semantic Search page)
// ---------------------------------------------------------------------------

const EmbeddingManagement: React.FC<{ clientId: string }> = ({ clientId }) => {
  const [stats, setStats] = useState<vectorApi.VectorStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [reembedStatus, setReembedStatus] = useState<vectorApi.ReembedStatus | null>(null);
  const [backfillRunning, setBackfillRunning] = useState(false);
  const [backfillTotal, setBackfillTotal] = useState(0);
  const backfillCancelRef = useRef(false);

  const loadStats = useCallback(async () => {
    if (!clientId) return;
    setStatsLoading(true);
    try {
      const s = await vectorApi.getVectorStats(clientId);
      setStats(s);
    } catch { /* keep previous */ } finally {
      setStatsLoading(false);
    }
  }, [clientId]);

  // Load stats + check for in-progress embedding when clientId is available
  useEffect(() => {
    if (!clientId) return;
    loadStats();
    vectorApi.getReembedStatus(clientId).then(status => {
      if (status?.status === 'running') {
        setReembedStatus(status);
      }
    }).catch(() => {});
  }, [clientId, loadStats]);

  // Poll reembed status + live stats refresh while embedding is running
  useEffect(() => {
    if (reembedStatus?.status !== 'running') return;
    let pollCount = 0;
    const interval = setInterval(async () => {
      try {
        const status = await vectorApi.getReembedStatus(clientId);
        setReembedStatus(status);
        pollCount++;
        if (pollCount % 5 === 0 && clientId) {
          vectorApi.getVectorStats(clientId).then(s => setStats(s)).catch(() => {});
        }
        if (status.status !== 'running') {
          clearInterval(interval);
          loadStats();
          if (status.status === 'complete') toast.success(`Embedding complete: ${status.result?.total_embedded} records`);
          else if (status.status === 'error') toast.error(`Embedding failed: ${status.error}`);
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(interval);
  }, [reembedStatus?.status, clientId, loadStats]);

  const handleReembed = async (tables?: string[]) => {
    try {
      const resp = await vectorApi.triggerReembed(clientId, tables);
      if (resp.status === 'already_running') toast.info('Embedding already in progress');
      else toast.success(`Embedding ${tables ? tables.join(' + ') : 'all tables'} in background`);
      setReembedStatus({ status: 'running', started_at: Date.now() / 1000 });
    } catch (err: any) {
      toast.error(err?.message || 'Failed to start embedding');
    }
  };

  const handleStopReembed = async () => {
    try {
      await vectorApi.stopReembed(clientId);
      toast.info('Stopping — already embedded records are kept');
      setReembedStatus(prev => prev ? { ...prev, status: 'stopped' } : null);
      loadStats();
    } catch (err: any) {
      toast.error(err?.message || 'Failed to stop');
    }
  };

  const handleBackfill = async () => {
    setBackfillRunning(true);
    setBackfillTotal(0);
    backfillCancelRef.current = false;
    let total = 0;
    try {
      while (!backfillCancelRef.current) {
        const resp = await vectorApi.backfillSearchText(2000);
        if (!resp) break;
        total += resp.updated || 0;
        setBackfillTotal(total);
        if (resp.done || resp.updated === 0) {
          toast.success(`Search index built: ${total.toLocaleString('en-AU')} emails indexed`);
          break;
        }
      }
      if (backfillCancelRef.current) toast.info(`Stopped — ${total.toLocaleString('en-AU')} indexed`);
    } catch (err: any) {
      toast.error(err?.message || 'Backfill failed');
    } finally {
      setBackfillRunning(false);
    }
  };

  if (!clientId) return null;

  return (
    <div className="rounded-lg border bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b px-5 py-3">
        <Zap className="h-4 w-4 text-indigo-500" />
        <h3 className="text-sm font-semibold text-slate-900">Embedding Coverage & Management</h3>
      </div>
      <div className="p-5">
        {statsLoading ? <ContentSkeleton rows={3} /> : stats ? (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
              {[
                { label: 'Emails', icon: <Mail className="h-4 w-4 text-slate-400" />, data: stats.emails },
                { label: 'Companies', icon: <Building2 className="h-4 w-4 text-slate-400" />, data: stats.companies },
                { label: 'Operations', icon: <Wrench className="h-4 w-4 text-slate-400" />, data: stats.operations },
              ].map(s => {
                const pct = s.data.total > 0 ? Math.round((s.data.embedded / s.data.total) * 100) : 0;
                const barColor = pct === 100 ? 'bg-emerald-500' : 'bg-indigo-500';
                return (
                  <div key={s.label} className="rounded-lg border bg-white shadow-sm p-4">
                    <div className="flex items-center gap-2 mb-1">
                      {s.icon}
                      <span className="text-xs font-medium text-slate-500">{s.label}</span>
                    </div>
                    <div className="flex items-baseline gap-1.5 mb-2">
                      <span className="text-lg font-semibold text-slate-900">
                        {s.data.embedded.toLocaleString('en-AU')}
                      </span>
                      <span className="text-xs text-slate-400">
                        / {s.data.total.toLocaleString('en-AU')}
                      </span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-1.5">
                      <div
                        className={`${barColor} h-1.5 rounded-full transition-all`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-slate-400 mt-1">{pct}%</p>
                  </div>
                );
              })}
            </div>
            <div className="flex flex-wrap gap-2">
              {reembedStatus?.status === 'running' ? (
                <button
                  onClick={handleStopReembed}
                  className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 shadow-sm hover:bg-red-100 transition"
                >
                  <Spinner className="h-3.5 w-3.5 animate-spin" />
                  Stop Embedding
                </button>
              ) : (
                <>
                  <button
                    onClick={() => handleReembed(['emails'])}
                    className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-indigo-700 transition"
                  >
                    <Mail className="h-3.5 w-3.5" />
                    Embed Emails
                  </button>
                  <button
                    onClick={() => handleReembed(['companies'])}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition"
                  >
                    <Building2 className="h-3.5 w-3.5" />
                    Embed Companies
                  </button>
                  <button
                    onClick={() => handleReembed(['operations'])}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition"
                  >
                    <Wrench className="h-3.5 w-3.5" />
                    Embed Operations
                  </button>
                  <button
                    onClick={() => handleReembed()}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition"
                  >
                    <Zap className="h-3.5 w-3.5" />
                    Embed All
                  </button>
                </>
              )}
              <button
                onClick={loadStats}
                className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Refresh Stats
              </button>
              {backfillRunning ? (
                <button
                  onClick={() => { backfillCancelRef.current = true; }}
                  className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 shadow-sm hover:bg-red-100 transition"
                >
                  <Spinner className="h-3.5 w-3.5 animate-spin" />
                  Stop Indexing ({backfillTotal.toLocaleString('en-AU')})
                </button>
              ) : (
                <button
                  onClick={handleBackfill}
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition"
                >
                  <Search className="h-3.5 w-3.5" />
                  Build Search Index
                </button>
              )}
              {reembedStatus?.status === 'complete' && reembedStatus.result && (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {reembedStatus.result.total_embedded} embedded
                </span>
              )}
            </div>
          </>
        ) : (
          <div className="py-12 text-center">
            <p className="text-sm text-slate-400">Select a client to view embedding stats</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default UsagePage;
