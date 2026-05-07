import React, { useState } from 'react';
import { insightsApi } from '../services/strategicDigestService';
import type { AIInsight } from '../types/strategic-digest';
import { cn } from '@/lib/utils';
import { StatusBadge } from '@/components/ui/status-badge';
import { ContentSkeleton } from '@/components/ui/empty-state';
import { Bot, RefreshCw, Sparkles } from 'lucide-react';

interface AIInsightsCardProps {
  entityType: 'company' | 'contact' | 'thread';
  entityId: string;
  clientId?: string;
}

const SKIP_KEYS = new Set(['_entity_type', '_entity_id', '_generated_at', '_model', '_ai_insight', 'error']);

const riskVariant = (level?: string) => {
  if (!level) return 'neutral';
  const l = level.toLowerCase();
  if (l === 'low') return 'success';
  if (l === 'medium') return 'warning';
  if (l === 'high' || l === 'critical') return 'danger';
  return 'neutral';
};

const BulletList: React.FC<{ items?: string[]; header: string }> = ({ items, header }) => {
  if (!items || items.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">{header}</p>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="text-sm text-slate-700 flex gap-2">
            <span className="text-slate-300 shrink-0">•</span>{item}
          </li>
        ))}
      </ul>
    </div>
  );
};

const CompanyInsight: React.FC<{ insight: AIInsight }> = ({ insight }) => (
  <div className="space-y-2">
    {insight.strategic_summary && (
      <div className="rounded-md border border-primary/20 bg-primary/5 px-3 py-2.5 mb-1">
        <p className="text-sm text-slate-800 leading-relaxed font-medium">{insight.strategic_summary}</p>
      </div>
    )}
    {insight.health_summary && <p className="text-sm text-slate-700 leading-relaxed">{insight.health_summary}</p>}
    <div className="flex gap-2 flex-wrap">
      {insight.revenue_risk && <span className="text-xs text-slate-500">Revenue Risk: <StatusBadge variant={riskVariant(insight.revenue_risk) as any} size="sm">{insight.revenue_risk}</StatusBadge></span>}
      {insight.engagement_trend && <span className="text-xs text-slate-500">Trend: <StatusBadge variant={insight.engagement_trend === 'improving' ? 'success' : insight.engagement_trend === 'declining' ? 'danger' : 'neutral'} size="sm">{insight.engagement_trend}</StatusBadge></span>}
    </div>
    <BulletList items={insight.key_observations} header="Key Observations" />
    <BulletList items={insight.recommended_actions} header="Recommended Actions" />
  </div>
);

const ContactInsight: React.FC<{ insight: AIInsight }> = ({ insight }) => (
  <div className="space-y-2">
    {insight.engagement_summary && <p className="text-sm text-slate-700 leading-relaxed">{insight.engagement_summary}</p>}
    {insight.importance_level && <div className="text-xs text-slate-500">Importance: <StatusBadge variant={riskVariant(insight.importance_level) as any} size="sm">{insight.importance_level}</StatusBadge></div>}
    {insight.follow_up_suggestion && (
      <div className="mt-2"><p className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">Follow-up</p><p className="text-sm text-slate-700">{insight.follow_up_suggestion}</p></div>
    )}
    <BulletList items={insight.key_observations} header="Key Observations" />
  </div>
);

const ThreadInsight: React.FC<{ insight: AIInsight }> = ({ insight }) => (
  <div className="space-y-2">
    {insight.thread_summary && <p className="text-sm text-slate-700 leading-relaxed">{insight.thread_summary}</p>}
    <div className="flex gap-2 flex-wrap">
      {insight.deal_probability != null && <span className="text-xs text-slate-500">Deal Probability: <StatusBadge variant={insight.deal_probability >= 70 ? 'success' : insight.deal_probability >= 40 ? 'warning' : 'danger'} size="sm">{insight.deal_probability}/100</StatusBadge></span>}
      {insight.risk_level && <span className="text-xs text-slate-500">Risk: <StatusBadge variant={riskVariant(insight.risk_level) as any} size="sm">{insight.risk_level}</StatusBadge></span>}
    </div>
    <BulletList items={insight.key_signals} header="Key Signals" />
    {insight.recommended_action && (
      <div className="mt-2"><p className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">Recommended Action</p><p className="text-sm text-slate-700">{insight.recommended_action}</p></div>
    )}
  </div>
);

const GenericInsight: React.FC<{ insight: Record<string, any> }> = ({ insight }) => (
  <div className="space-y-2">
    {Object.entries(insight).filter(([k]) => !SKIP_KEYS.has(k)).map(([key, value]) => {
      const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      if (Array.isArray(value)) return <BulletList key={key} items={value.map(String)} header={label} />;
      if (typeof value === 'string' && value.length > 80) return <div key={key}><p className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-1">{label}</p><p className="text-sm text-slate-700">{value}</p></div>;
      if (typeof value === 'string') return <div key={key} className="text-xs text-slate-500">{label}: <StatusBadge variant="neutral" size="sm">{value}</StatusBadge></div>;
      if (typeof value === 'number') return <div key={key} className="text-xs text-slate-500">{label}: <StatusBadge variant="info" size="sm">{value}</StatusBadge></div>;
      return null;
    })}
  </div>
);

const hasTypedFields = (data: any): boolean => !!(data?.health_summary || data?.engagement_summary || data?.thread_summary);

const AIInsightsCard: React.FC<AIInsightsCardProps> = ({ entityType, entityId, clientId }) => {
  const [insight, setInsight] = useState<AIInsight | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await insightsApi[entityType](entityId, false, clientId) as any;
      if (!result) { setError('Request timed out — try again.'); return; }
      const data: AIInsight = result?.insight ?? result?.data?.insight ?? result;
      if (data?.error) setError(data.error);
      else setInsight(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to generate AI insight');
    } finally {
      setLoading(false);
    }
  };

  // No auto-trigger — on-demand only to avoid unnecessary cost
  return (
    <div className="rounded-lg border bg-white shadow-sm mt-4 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-bold text-slate-900">AI Insights</h3>
        </div>
        {insight ? (
          <button onClick={handleAnalyze} disabled={loading}
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline disabled:opacity-50">
            <RefreshCw className={cn('h-3 w-3', loading && 'animate-spin')} /> Refresh
          </button>
        ) : (
          <button onClick={handleAnalyze} disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary rounded-md hover:bg-primary-dark disabled:opacity-50 transition-colors">
            {loading ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            {loading ? 'Analyzing...' : 'Summarize this page'}
          </button>
        )}
      </div>
      <div className="p-4">
        {loading && !insight && <ContentSkeleton rows={4} className="p-0" />}
        {error && !loading && <p className="text-sm text-destructive">{error}</p>}
        {insight && !loading && (
          hasTypedFields(insight) ? (
            <>
              {entityType === 'company' && <CompanyInsight insight={insight} />}
              {entityType === 'contact' && <ContactInsight insight={insight} />}
              {entityType === 'thread' && <ThreadInsight insight={insight} />}
            </>
          ) : (
            <GenericInsight insight={insight as any} />
          )
        )}
        {!insight && !loading && !error && (
          <p className="text-xs text-slate-400">Click "Summarize this page" to generate AI-powered insights based on threads, business data, and communication patterns.</p>
        )}
      </div>
    </div>
  );
};

export default AIInsightsCard;
