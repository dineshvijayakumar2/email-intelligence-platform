/**
 * AI Playground — Test and tune AI prompts against real endpoints.
 *
 * No new backend endpoints — calls the same APIs as the intelligence pages.
 * Shows: prompt used -> context sent -> raw LLM output for rapid iteration.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  FlaskConical, Send, Save, RotateCcw, Code, Clock,
} from 'lucide-react';
import dayjs from 'dayjs';
import { useClient } from '../../contexts/ClientContext';
import { MailboxSelector } from '../../components/MailboxSelector';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { StatusBadge } from '@/components/ui/status-badge';
import { EmptyState } from '@/components/ui/empty-state';
import { Spinner } from '@/lib/icons';
import { notify } from '@/lib/toast';
import api from '../../services/apiClient';
import { intelligenceApi, digestApi, bucketApi } from '../../services/aiService';
import { strategicDigestApi, insightsApi } from '../../services/strategicDigestService';

type TestType =
  | 'email_analysis'
  | 'daily_digest'
  | 'weekly_digest'
  | 'strategic_digest'
  | 'insight_company'
  | 'insight_contact'
  | 'insight_thread'
  | 'rebucket';

const TEST_OPTIONS: { value: TestType; label: string; needs: string; promptKeys: string[] }[] = [
  { value: 'email_analysis', label: 'Email Analysis', needs: 'mailbox', promptKeys: ['email_analysis_system', 'email_analysis_user'] },
  { value: 'daily_digest', label: 'Daily Digest', needs: 'mailbox', promptKeys: ['daily_digest'] },
  { value: 'weekly_digest', label: 'Weekly Digest', needs: 'mailbox', promptKeys: ['weekly_digest'] },
  { value: 'strategic_digest', label: 'Strategic Digest', needs: 'client', promptKeys: ['strategic_digest'] },
  { value: 'insight_company', label: 'Company Insight', needs: 'entity_id', promptKeys: ['insight_company'] },
  { value: 'insight_contact', label: 'Contact Insight', needs: 'entity_id', promptKeys: ['insight_contact'] },
  { value: 'insight_thread', label: 'Thread Insight', needs: 'entity_id', promptKeys: ['insight_thread'] },
  { value: 'rebucket', label: 'Re-bucket Signals', needs: 'mailbox', promptKeys: [] },
];

// Per-key hints shown below the prompt editor so editors know what context the LLM receives.
const PROMPT_HINTS: Record<string, { label: string; variant: 'info' | 'warning' | 'purple' | 'neutral'; detail: string; requiredVars?: string[] }> = {
  email_analysis_system: {
    label: 'System prompt',
    variant: 'info',
    detail: 'No variables needed. Sets classification rules and persona. Data is passed separately.',
  },
  email_analysis_user: {
    label: 'User template',
    variant: 'warning',
    detail: 'Must keep {emails_json} — replaced at runtime with the JSON batch of emails to classify.',
    requiredVars: ['{emails_json}'],
  },
  daily_digest: {
    label: 'System prompt',
    variant: 'info',
    detail: 'No variables needed. Backend auto-injects: time window, email stats, business context (QB), relationship context (90d), signal emails, priority emails, active threads.',
  },
  weekly_digest: {
    label: 'System prompt',
    variant: 'info',
    detail: 'No variables needed. Same auto-injected data as daily digest, covering the full prior week.',
  },
  strategic_digest: {
    label: 'System prompt — agent',
    variant: 'purple',
    detail: 'No variables needed. LangGraph agent uses tool calls to look up customer data, quotes, threads at runtime. Define analysis approach and output schema here.',
  },
  insight_company: {
    label: 'System prompt',
    variant: 'info',
    detail: 'No variables needed. Auto-injected: company revenue (TY/LY), QB profile, email stats (30/90d), engagement score, open threads.',
  },
  insight_contact: {
    label: 'System prompt',
    variant: 'info',
    detail: 'No variables needed. Auto-injected: contact email history, response times, quote behaviour, engagement score.',
  },
  insight_thread: {
    label: 'System prompt',
    variant: 'info',
    detail: 'No variables needed. Auto-injected: thread messages, participants, quote/job context, hours since last reply, SLA status.',
  },
};

/** Suggest the next minor version: "v1.3" -> "v1.4", anything unparseable -> "v1.0" */
function bumpVersion(current?: string): string {
  const m = (current || '').match(/^v(\d+)\.(\d+)$/);
  if (!m) return 'v1.0';
  return `v${m[1]}.${parseInt(m[2], 10) + 1}`;
}

const PlaygroundPage: React.FC = () => {
  const { clientId } = useClient();
  const [mailboxIds, setMailboxIds] = useState<string[]>([]);
  const mailboxId = mailboxIds[0] || '';
  const [entityId, setEntityId] = useState('');

  const [testType, setTestType] = useState<TestType>('email_analysis');
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);

  // Parameters (passed to endpoints)
  const [dateFrom, setDateFrom] = useState(dayjs().subtract(7, 'day').format('YYYY-MM-DD'));
  const [dateTo, setDateTo] = useState(dayjs().format('YYYY-MM-DD'));
  const [maxEmails, setMaxEmails] = useState(5);
  const [periodType, setPeriodType] = useState<'weekly' | 'monthly' | 'quarterly'>('weekly');

  // Prompts
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [overrides, setOverrides] = useState<Record<string, { prompt_text: string; updated_at?: string; version?: string }>>({});
  const [selectedPromptKey, setSelectedPromptKey] = useState('');
  const [activePrompt, setActivePrompt] = useState('');
  const [editedPrompt, setEditedPrompt] = useState('');
  const [isEdited, setIsEdited] = useState(false);
  const [promptUpdatedAt, setPromptUpdatedAt] = useState<string | null>(null);
  const [saveVersion, setSaveVersion] = useState('v1.0');

  // Results
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');
  const [elapsed, setElapsed] = useState(0);

  // Output tabs
  const [outputTab, setOutputTab] = useState<'formatted' | 'raw'>('formatted');

  // Load default prompts + client overrides
  const loadPrompts = useCallback(async () => {
    try {
      const [defaultsResp, overridesResp] = await Promise.all([
        api.get<{ defaults: any[] }>('/v1/ai/prompts/defaults'),
        clientId ? api.get<{ prompts: any[] }>(`/v1/ai/prompts?client_id=${clientId}`) : null,
      ]);

      const defMap: Record<string, string> = {};
      for (const d of defaultsResp?.defaults || []) {
        defMap[d.prompt_key] = d.prompt_text;
      }
      setDefaults(defMap);

      // Apply client overrides (with timestamps + version)
      const ovMap: Record<string, { prompt_text: string; updated_at?: string; version?: string }> = {};
      for (const o of overridesResp?.prompts || []) {
        ovMap[o.prompt_key] = { prompt_text: o.prompt_text, updated_at: o.updated_at, version: o.version };
      }
      setOverrides(ovMap);

      // Select first prompt key for this test type
      const cfg = TEST_OPTIONS.find(t => t.value === testType);
      const firstKey = selectedPromptKey && cfg?.promptKeys.includes(selectedPromptKey)
        ? selectedPromptKey
        : cfg?.promptKeys[0] || '';
      setSelectedPromptKey(firstKey);
      const ov = ovMap[firstKey];
      const prompt = ov?.prompt_text || defMap[firstKey] || '';
      setActivePrompt(prompt);
      setEditedPrompt(prompt);
      setIsEdited(false);
      setPromptUpdatedAt(ov?.updated_at || null);
      setSaveVersion(bumpVersion(ov?.version));
    } catch { /* silent */ }
  }, [clientId, testType]);

  useEffect(() => { loadPrompts(); }, [loadPrompts]);

  const handlePromptChange = (val: string) => {
    setEditedPrompt(val);
    setIsEdited(val !== activePrompt);
  };

  const handlePromptKeySwitch = (key: string) => {
    setSelectedPromptKey(key);
    const ov = overrides[key];
    const prompt = ov?.prompt_text || defaults[key] || '';
    setActivePrompt(prompt);
    setEditedPrompt(prompt);
    setIsEdited(false);
    setPromptUpdatedAt(ov?.updated_at || null);
    setSaveVersion(bumpVersion(ov?.version));
  };

  const handleSavePrompt = async () => {
    if (!clientId) { notify.warning('Select a client first'); return; }
    if (!selectedPromptKey) return;
    // Validate required template variables
    const hint = PROMPT_HINTS[selectedPromptKey];
    for (const v of hint?.requiredVars || []) {
      if (!editedPrompt.includes(v)) {
        notify.error(`Prompt must include ${v} — it is replaced at runtime with the email data.`);
        return;
      }
    }
    setSaving(true);
    try {
      await api.put('/v1/ai/prompts', {
        client_id: clientId,
        prompt_key: selectedPromptKey,
        prompt_text: editedPrompt,
        description: `Updated from Playground`,
        version: saveVersion,
      });
      notify.success(`Prompt "${selectedPromptKey}" saved as ${saveVersion}`);
      setActivePrompt(editedPrompt);
      setIsEdited(false);
      setPromptUpdatedAt(new Date().toISOString());
      setOverrides(prev => ({ ...prev, [selectedPromptKey]: { prompt_text: editedPrompt, updated_at: new Date().toISOString(), version: saveVersion } }));
    } catch {
      notify.error('Failed to save prompt');
    }
    setSaving(false);
  };

  const handleResetPrompt = () => {
    setEditedPrompt(defaults[selectedPromptKey] || '');
    setIsEdited(true);
  };

  const handleRun = async () => {
    setRunning(true);
    setResult(null);
    setError('');
    const start = Date.now();

    try {
      let output: any = null;

      switch (testType) {
        case 'email_analysis':
          if (!mailboxId) throw new Error('Select a mailbox');
          output = await intelligenceApi.analyze(mailboxId, {
            max_emails: maxEmails,
            date_from: dateFrom,
            date_to: dateTo,
          });
          // Wait then fetch results
          await new Promise(r => setTimeout(r, 8000));
          const intel = await intelligenceApi.list(mailboxId, { page_size: maxEmails });
          output = { trigger: output, results: intel.items?.slice(0, maxEmails), params: { maxEmails, dateFrom, dateTo } };
          break;

        case 'daily_digest':
          if (!mailboxId) throw new Error('Select a mailbox');
          output = await digestApi.get(mailboxId, dateTo, clientId || undefined, true, 'daily');
          break;

        case 'weekly_digest':
          if (!mailboxId) throw new Error('Select a mailbox');
          output = await digestApi.get(mailboxId, dateTo, clientId || undefined, true, 'weekly');
          break;

        case 'strategic_digest':
          if (!clientId) throw new Error('Select a client');
          await strategicDigestApi.generate(clientId, periodType);
          for (let i = 0; i < 120; i++) {
            await new Promise(r => setTimeout(r, 5000));
            const prog = await strategicDigestApi.getProgress(clientId);
            if (prog.phase === 'completed') {
              output = await strategicDigestApi.get(clientId, periodType);
              break;
            }
            if (prog.phase === 'failed') throw new Error(prog.message || 'Generation failed');
          }
          if (!output) throw new Error('Timed out waiting for digest');
          break;

        case 'insight_company':
          if (!entityId) throw new Error('Enter a company ID');
          output = await insightsApi.company(entityId, true, clientId || undefined);
          break;

        case 'insight_contact':
          if (!entityId) throw new Error('Enter a contact ID');
          output = await insightsApi.contact(entityId, true, clientId || undefined);
          break;

        case 'insight_thread':
          if (!entityId) throw new Error('Enter a thread ID');
          output = await insightsApi.thread(entityId, true, clientId || undefined);
          break;

        case 'rebucket':
          if (!mailboxId) throw new Error('Select a mailbox');
          output = await bucketApi.rebucket(mailboxId);
          await new Promise(r => setTimeout(r, 3000));
          const summary = await bucketApi.getSummary(mailboxId);
          output = { trigger: output, summary };
          break;
      }

      setResult(output);
      setElapsed(Date.now() - start);
    } catch (err: any) {
      setError(err?.message || 'Test failed');
      setElapsed(Date.now() - start);
    } finally {
      setRunning(false);
    }
  };

  const testConfig = TEST_OPTIONS.find(t => t.value === testType);
  const hasPrompt = (testConfig?.promptKeys.length || 0) > 0;

  return (
    <PageShell maxWidth="1600px">
      {/* Header */}
      <PageHeader
        title="AI Playground"
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={testType}
              onChange={(e) => { setTestType(e.target.value as TestType); setResult(null); setError(''); }}
              className="h-8 px-2 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              {TEST_OPTIONS.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            {testConfig?.needs === 'mailbox' && (
              <MailboxSelector value={mailboxIds} onChange={setMailboxIds} mode="single" />
            )}
            {testConfig?.needs === 'entity_id' && (
              <input
                type="text"
                placeholder="Entity UUID"
                value={entityId}
                onChange={e => setEntityId(e.target.value)}
                className="h-8 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-80"
              />
            )}
            <button
              onClick={handleRun}
              disabled={running}
              className="inline-flex items-center gap-1.5 h-8 px-4 text-sm font-medium rounded-md bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {running ? <Spinner className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              Run Test
            </button>
          </div>
        }
      />

      {/* Parameters Row */}
      <div className="rounded-lg border bg-white shadow-sm p-3 mb-4">
        <div className="flex items-center gap-4 flex-wrap">
          {(testConfig?.needs === 'mailbox' && ['email_analysis'].includes(testType)) && (
            <>
              <div>
                <label className="block text-[11px] text-slate-500 mb-0.5">Date From</label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={e => setDateFrom(e.target.value)}
                  className="h-7 px-2 text-xs rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-500 mb-0.5">Date To</label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={e => setDateTo(e.target.value)}
                  className="h-7 px-2 text-xs rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
                />
              </div>
              <div>
                <label className="block text-[11px] text-slate-500 mb-0.5">Max Emails</label>
                <input
                  type="number"
                  value={maxEmails}
                  onChange={e => setMaxEmails(Math.max(1, Math.min(50, parseInt(e.target.value) || 5)))}
                  min={1}
                  max={50}
                  className="h-7 px-2 text-xs rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-20"
                />
              </div>
            </>
          )}
          {['daily_digest', 'weekly_digest'].includes(testType) && (
            <div>
              <label className="block text-[11px] text-slate-500 mb-0.5">Digest Date</label>
              <input
                type="date"
                value={dateTo}
                onChange={e => setDateTo(e.target.value)}
                className="h-7 px-2 text-xs rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
          )}
          {testType === 'strategic_digest' && (
            <div>
              <label className="block text-[11px] text-slate-500 mb-0.5">Period</label>
              <select
                value={periodType}
                onChange={e => setPeriodType(e.target.value as 'weekly' | 'monthly' | 'quarterly')}
                className="h-7 px-2 text-xs rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-28"
              >
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
              </select>
            </div>
          )}
          <div className="ml-auto">
            {promptUpdatedAt && (
              <StatusBadge variant="info" size="sm">
                <Clock className="h-3 w-3 mr-1" />
                Prompt updated: {new Date(promptUpdatedAt).toLocaleString()}
              </StatusBadge>
            )}
            {!promptUpdatedAt && !overrides[selectedPromptKey] && selectedPromptKey && (
              <StatusBadge variant="neutral" size="sm">Using default prompt</StatusBadge>
            )}
          </div>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 p-3 mb-4 rounded-lg border border-red-200 bg-red-50 text-red-700 text-sm">
          <span className="font-medium">Error:</span>
          <span className="flex-1">{error}</span>
          <button onClick={() => setError('')} className="text-red-400 hover:text-red-600 text-lg leading-none">&times;</button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left: Prompt Editor */}
        {hasPrompt && (
          <div className="rounded-lg border bg-white shadow-sm flex flex-col">
            {/* Card header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Code className="h-4 w-4 text-slate-400" />
                {(testConfig?.promptKeys.length || 0) > 1 ? (
                  <select
                    value={selectedPromptKey}
                    onChange={e => handlePromptKeySwitch(e.target.value)}
                    className="h-7 px-2 text-xs rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-52"
                  >
                    {testConfig?.promptKeys.map(k => (
                      <option key={k} value={k}>{k.replace(/_/g, ' ')}</option>
                    ))}
                  </select>
                ) : (
                  <span className="text-sm font-medium text-slate-700">{selectedPromptKey.replace(/_/g, ' ')}</span>
                )}
                {isEdited && <StatusBadge variant="warning" size="sm">Unsaved</StatusBadge>}
                {overrides[selectedPromptKey] && <StatusBadge variant="info" size="sm">Custom</StatusBadge>}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleResetPrompt}
                  className="inline-flex items-center gap-1 h-7 px-2 text-xs rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors"
                >
                  <RotateCcw className="h-3 w-3" />
                  Reset to Default
                </button>
                <input
                  type="text"
                  value={saveVersion}
                  onChange={e => setSaveVersion(e.target.value)}
                  placeholder="v1.0"
                  className="h-7 px-2 text-[11px] font-mono rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 w-[72px]"
                />
                <button
                  onClick={handleSavePrompt}
                  disabled={!isEdited || saving}
                  className="inline-flex items-center gap-1 h-7 px-3 text-xs font-medium rounded-md bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  {saving ? <Spinner className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
                  Save
                </button>
              </div>
            </div>
            {/* Prompt textarea */}
            <textarea
              value={editedPrompt}
              onChange={e => handlePromptChange(e.target.value)}
              rows={24}
              className="flex-1 w-full px-4 py-3 font-mono text-[11px] leading-relaxed resize-y border-none focus:outline-none"
            />
            {/* Footer with hints */}
            <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 border-t border-slate-100 rounded-b-lg">
              <span className="text-[11px] text-slate-400">{editedPrompt.length} chars</span>
              {PROMPT_HINTS[selectedPromptKey] && (
                <>
                  <StatusBadge variant={PROMPT_HINTS[selectedPromptKey].variant} size="sm">
                    {PROMPT_HINTS[selectedPromptKey].label}
                  </StatusBadge>
                  <span className="text-[11px] text-slate-500">
                    {PROMPT_HINTS[selectedPromptKey].detail}
                  </span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Right: Output */}
        <div className={`rounded-lg border bg-white shadow-sm ${!hasPrompt ? 'lg:col-span-2' : ''}`}>
          {/* Card header */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100">
            <span className="text-sm font-medium text-slate-700">Output</span>
            {elapsed > 0 && (
              <StatusBadge variant="neutral" size="sm">{(elapsed / 1000).toFixed(1)}s</StatusBadge>
            )}
            {running && <Spinner className="h-4 w-4 animate-spin text-primary" />}
          </div>
          {/* Card body */}
          <div className="p-4">
            {running && !result && (
              <div className="text-center py-12">
                <Spinner className="h-8 w-8 animate-spin text-primary mx-auto" />
                <p className="mt-4 text-sm text-slate-500">Running {testConfig?.label}...</p>
                {testType === 'strategic_digest' && (
                  <p className="mt-2 text-xs text-slate-400">This may take a few minutes</p>
                )}
              </div>
            )}

            {!running && !result && !error && (
              <EmptyState
                icon={<FlaskConical className="h-10 w-10" />}
                title="Click 'Run Test' to execute"
              />
            )}

            {result && (
              <div>
                {/* Tab bar */}
                <div className="flex border-b border-slate-200 mb-4">
                  <button
                    onClick={() => setOutputTab('formatted')}
                    className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                      outputTab === 'formatted'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    Formatted
                  </button>
                  <button
                    onClick={() => setOutputTab('raw')}
                    className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                      outputTab === 'raw'
                        ? 'border-primary text-primary'
                        : 'border-transparent text-slate-500 hover:text-slate-700'
                    }`}
                  >
                    Raw JSON
                  </button>
                </div>

                {outputTab === 'formatted' && (
                  <FormattedOutput data={result} testType={testType} />
                )}
                {outputTab === 'raw' && (
                  <pre className="bg-slate-900 text-slate-200 p-4 rounded-lg max-h-[600px] overflow-auto text-[11px] leading-relaxed">
                    {JSON.stringify(result, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </PageShell>
  );
};


// Formatted output renderer
const FormattedOutput: React.FC<{ data: any; testType: TestType }> = ({ data, testType }) => {
  if (!data) return <EmptyState title="No data" />;

  // For digest types, show the key sections
  if (['daily_digest', 'weekly_digest'].includes(testType)) {
    return (
      <div className="space-y-3">
        {data.summary && (
          <div className="rounded-lg border bg-white shadow-sm p-3">
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Summary</h4>
            <p className="text-sm text-slate-700">{data.summary}</p>
          </div>
        )}
        {data.headline && (
          <div className="rounded-lg border bg-white shadow-sm p-3">
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Headline</h4>
            {typeof data.headline === 'string' ? (
              <p className="text-sm text-slate-700">{data.headline}</p>
            ) : (
              <div className="grid grid-cols-1 gap-1">
                {Object.entries(data.headline).map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-sm py-0.5">
                    <span className="text-slate-500 min-w-[120px]">{k.replace(/_/g, ' ')}</span>
                    <span className="text-slate-700">{String(v || '-')}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        {data.action_items?.length > 0 && (
          <div className="rounded-lg border bg-white shadow-sm p-3">
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              Action Items ({data.action_items.length})
            </h4>
            {data.action_items.map((item: any, i: number) => (
              <div key={i} className="py-2 border-b border-slate-50 last:border-0">
                <div className="flex items-center gap-2 mb-1">
                  <StatusBadge variant="danger" size="sm">P{item.priority || i + 1}</StatusBadge>
                  <span className="text-sm font-medium text-slate-700">{item.customer || item.contact_name || ''}</span>
                </div>
                <p className="text-sm text-slate-600">{item.action || JSON.stringify(item)}</p>
              </div>
            ))}
          </div>
        )}
        {data.urgent_today?.length > 0 && (
          <div className="rounded-lg border bg-white shadow-sm p-3">
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              Urgent Today ({data.urgent_today.length})
            </h4>
            {data.urgent_today.map((item: any, i: number) => (
              <div key={i} className="py-2 border-b border-slate-50 last:border-0">
                <div className="flex items-center gap-2 mb-1">
                  <StatusBadge variant="danger" size="sm">{item.customer}</StatusBadge>
                  <span className="text-xs text-slate-400">{item.am}</span>
                </div>
                <p className="text-sm text-slate-600">{item.action}</p>
                <p className="text-[11px] text-slate-400">{item.reason} | {item.revenue_context}</p>
              </div>
            ))}
          </div>
        )}
        {data.at_risk?.length > 0 && (
          <div className="rounded-lg border bg-white shadow-sm p-3">
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              At Risk ({data.at_risk.length})
            </h4>
            {data.at_risk.map((item: any, i: number) => (
              <div key={i} className="py-2 border-b border-slate-50 last:border-0">
                <div className="flex items-center gap-2 mb-1">
                  <StatusBadge variant="warning" size="sm">{item.customer}</StatusBadge>
                  <StatusBadge variant="neutral" size="sm">{item.tier}</StatusBadge>
                </div>
                <p className="text-sm text-slate-600">{item.specific_risk || item.risk || JSON.stringify(item)}</p>
              </div>
            ))}
          </div>
        )}
        {data.stats && (
          <div className="rounded-lg border bg-white shadow-sm p-3">
            <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Context Stats</h4>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(data.stats).map(([k, v]) => (
                <StatusBadge key={k} variant="neutral" size="sm">
                  {k.replace(/_/g, ' ')}: {String(v)}
                </StatusBadge>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  // For email analysis, show the classified results
  if (testType === 'email_analysis' && data.results) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-slate-400">{data.results.length} emails classified</p>
        {data.results.map((r: any, i: number) => (
          <div key={i} className="rounded-lg border bg-white shadow-sm p-3">
            <div className="flex flex-wrap gap-1.5 mb-1">
              <StatusBadge variant="info" size="sm">{r.intent}</StatusBadge>
              <StatusBadge
                variant={r.urgency === 'critical' ? 'danger' : r.urgency === 'high' ? 'warning' : 'neutral'}
                size="sm"
              >
                {r.urgency}
              </StatusBadge>
              <StatusBadge variant="neutral" size="sm">{r.sentiment}</StatusBadge>
              {r.business_signal && <StatusBadge variant="purple" size="sm">{r.business_signal}</StatusBadge>}
              {r.confidence && <StatusBadge variant="neutral" size="sm">conf: {Math.round(r.confidence * 100)}%</StatusBadge>}
            </div>
            <p className="text-sm text-slate-700">{r.summary || r.email_subject}</p>
            {r.suggested_action && <p className="text-xs text-slate-400 mt-0.5">{r.suggested_action}</p>}
          </div>
        ))}
      </div>
    );
  }

  // For insights, show structured output
  if (testType.startsWith('insight_')) {
    const insight = data.insight || data;
    return (
      <div className="space-y-3">
        {insight.headline && <h3 className="text-base font-semibold text-slate-800">{insight.headline}</h3>}
        {insight.health_summary && <p className="text-sm text-slate-600">{insight.health_summary}</p>}
        {insight.key_insight && <p className="text-sm text-slate-600">{insight.key_insight}</p>}
        {insight.engagement_summary && <p className="text-sm text-slate-600">{insight.engagement_summary}</p>}
        {insight.thread_summary && <p className="text-sm text-slate-600">{insight.thread_summary}</p>}
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(insight)
                .filter(([k]) => !['headline', 'health_summary', 'key_insight', 'engagement_summary', 'thread_summary'].includes(k))
                .map(([k, v], i) => (
                  <tr key={k} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}>
                    <td className="px-3 py-2 text-slate-500 font-medium whitespace-nowrap border-r border-slate-100 w-48">
                      {k.replace(/_/g, ' ')}
                    </td>
                    <td className="px-3 py-2 text-slate-700">
                      {Array.isArray(v) ? v.join(', ') : String(v ?? '-')}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // Default: show as key-value
  return (
    <div className="rounded-lg border overflow-hidden">
      <table className="w-full text-sm">
        <tbody>
          {Object.entries(data).map(([k, v], i) => (
            <tr key={k} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}>
              <td className="px-3 py-2 text-slate-500 font-medium whitespace-nowrap border-r border-slate-100 w-48">
                {k}
              </td>
              <td className="px-3 py-2 text-slate-700">
                {typeof v === 'object' ? (
                  <pre className="text-[11px] font-mono whitespace-pre-wrap">{JSON.stringify(v, null, 2)}</pre>
                ) : (
                  String(v ?? '-')
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default PlaygroundPage;
