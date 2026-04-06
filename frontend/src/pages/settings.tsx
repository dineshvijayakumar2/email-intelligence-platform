import { useEffect, useState } from 'react';
import api from '../services/apiClient';
import { useClient } from '../contexts/ClientContext';
import { CURRENCY_OPTIONS } from '../utils/numberFormat';
import { PageShell, PageHeader } from '@/components/ui/page-shell';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { toast } from '@/lib/toast';
import { Clock, Globe, DollarSign } from 'lucide-react';
import { Spinner } from '@/lib/icons';

interface BusinessHoursSettings {
  timezone: string; business_hours_start: number; business_hours_end: number; business_days: number[];
}

const WEEKDAYS = [
  { label: 'Mon', value: 1 }, { label: 'Tue', value: 2 }, { label: 'Wed', value: 3 },
  { label: 'Thu', value: 4 }, { label: 'Fri', value: 5 }, { label: 'Sat', value: 6 }, { label: 'Sun', value: 7 },
];

const TIMEZONE_OPTIONS = [
  'UTC', 'Asia/Kolkata', 'Asia/Dubai', 'Asia/Singapore', 'Asia/Tokyo', 'Asia/Shanghai',
  'Europe/London', 'Europe/Paris', 'Europe/Berlin',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'Australia/Sydney', 'Pacific/Auckland',
];

export default function SettingsPage() {
  const { clientId } = useClient();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clientSaving, setClientSaving] = useState(false);

  // Business hours state
  const [timezone, setTimezone] = useState('UTC');
  const [startHour, setStartHour] = useState(9);
  const [endHour, setEndHour] = useState(18);
  const [businessDays, setBusinessDays] = useState<number[]>([1, 2, 3, 4, 5]);

  // Client locale state
  const [clientTz, setClientTz] = useState('Australia/Sydney');
  const [currency, setCurrency] = useState('AUD');

  const detectedTz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const data = await api.get<BusinessHoursSettings>('/auth/me/settings');
        setTimezone(data.timezone || 'UTC');
        setStartHour(data.business_hours_start ?? 9);
        setEndHour(data.business_hours_end ?? 18);
        setBusinessDays(data.business_days || [1, 2, 3, 4, 5]);
      } catch { toast.error('Failed to load settings'); }
      finally { setLoading(false); }
    })();
  }, []);

  useEffect(() => {
    if (!clientId) return;
    api.get<any>(`/v1/clients/${clientId}`).then(data => {
      setClientTz(data.timezone || 'Australia/Sydney');
      setCurrency(data.currency_code || 'AUD');
    }).catch(() => {});
  }, [clientId]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.patch('/auth/me/settings', { timezone, business_hours_start: startHour, business_hours_end: endHour, business_days: businessDays });
      toast.success('Business hours saved');
    } catch { toast.error('Failed to save'); }
    finally { setSaving(false); }
  };

  const handleClientSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!clientId) { toast.warning('Select a client first'); return; }
    setClientSaving(true);
    try {
      await api.patch(`/v1/clients/${clientId}`, { timezone: clientTz, currency_code: currency });
      toast.success('Client locale saved');
    } catch { toast.error('Failed to save'); }
    finally { setClientSaving(false); }
  };

  const toggleDay = (day: number) => {
    setBusinessDays(prev => prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day].sort());
  };

  if (loading) return <PageShell><ContentSkeleton rows={6} /></PageShell>;

  return (
    <PageShell maxWidth="640px">
      <PageHeader title="Settings" />

      {/* Business Hours */}
      <div className="rounded-lg border bg-white shadow-sm p-5 mb-5">
        <div className="flex items-center gap-2 mb-1">
          <Globe className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-bold text-slate-900">Timezone & Business Hours</h2>
        </div>
        <p className="text-xs text-slate-500 mb-4">Response time metrics calculated within configured business hours.</p>

        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="text-xs font-medium text-slate-600 block mb-1">Timezone</label>
            <select value={timezone} onChange={e => setTimezone(e.target.value)}
              className="w-full h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
              {TIMEZONE_OPTIONS.map(tz => <option key={tz} value={tz}>{tz}</option>)}
            </select>
            <p className="text-[11px] text-slate-400 mt-1">Detected: {detectedTz}</p>
          </div>

          <div className="flex gap-4">
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">Start</label>
              <select value={startHour} onChange={e => setStartHour(Number(e.target.value))}
                className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
                {Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{String(i).padStart(2, '0')}:00</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 block mb-1">End</label>
              <select value={endHour} onChange={e => setEndHour(Number(e.target.value))}
                className="h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
                {Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{String(i).padStart(2, '0')}:00</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 block mb-2">Business Days</label>
            <div className="flex gap-2">
              {WEEKDAYS.map(d => (
                <button key={d.value} type="button" onClick={() => toggleDay(d.value)}
                  className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${businessDays.includes(d.value) ? 'bg-primary text-white border-primary' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}>
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <button type="submit" disabled={saving}
            className="h-9 px-4 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark disabled:opacity-50 inline-flex items-center gap-2">
            {saving && <Spinner className="h-3.5 w-3.5 animate-spin" />}
            <Clock className="h-3.5 w-3.5" />Save Business Hours
          </button>
        </form>
      </div>

      {/* Client Locale */}
      <div className="rounded-lg border bg-white shadow-sm p-5">
        <div className="flex items-center gap-2 mb-1">
          <DollarSign className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-bold text-slate-900">Client Locale (Admin)</h2>
        </div>
        <p className="text-xs text-slate-500 mb-4">Timezone and currency for AI analysis, digests, and financial figures.</p>

        <form onSubmit={handleClientSave} className="space-y-4">
          <div>
            <label className="text-xs font-medium text-slate-600 block mb-1">Client Timezone</label>
            <select value={clientTz} onChange={e => setClientTz(e.target.value)} disabled={!clientId}
              className="w-full h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50">
              {TIMEZONE_OPTIONS.map(tz => <option key={tz} value={tz}>{tz}</option>)}
            </select>
          </div>

          <div>
            <label className="text-xs font-medium text-slate-600 block mb-1">Currency</label>
            <select value={currency} onChange={e => setCurrency(e.target.value)} disabled={!clientId}
              className="w-full h-9 px-3 text-sm rounded-md border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50">
              {CURRENCY_OPTIONS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
            <p className="text-[11px] text-slate-400 mt-1">Used for all financial figures in AI prompts and insights.</p>
          </div>

          <button type="submit" disabled={clientSaving || !clientId}
            className="h-9 px-4 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary-dark disabled:opacity-50 inline-flex items-center gap-2">
            {clientSaving && <Spinner className="h-3.5 w-3.5 animate-spin" />}
            <DollarSign className="h-3.5 w-3.5" />Save Client Locale
          </button>
        </form>
      </div>
    </PageShell>
  );
}
