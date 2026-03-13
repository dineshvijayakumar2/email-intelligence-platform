/**
 * Strategic Digest TypeScript Interfaces — Sprint 3 v2 (AM-centric rehaul)
 */

export type PeriodType = 'weekly' | 'monthly' | 'quarterly' | 'ytd' | 'custom';

export type LifecycleTier =
  | 'prospect'
  | 'new_customer'
  | 'active_customer'
  | 'at_risk'
  | 'dormant'
  | 'champion';

export type SignalType =
  | 'response_urgency'
  | 'deal_at_risk'
  | 'retention_risk'
  | 'revenue_opportunity'
  | 'new_relationship'
  | 'account_neglect';

export interface RelationshipHealthCard {
  company_name: string;
  company_id?: string;
  lifecycle_tier?: LifecycleTier;
  status?: 'healthy' | 'at_risk' | 'declining' | 'growing' | 'new';
  signal?: string;
  am_owner?: string;
  recommended_action?: string;
  revenue_impact_estimate?: string;
  // Legacy fields kept for backward compat
  customer_type?: string;
  tier?: string;
  engagement_score?: number;
  engagement_trend?: string;
  revenue?: number;
}

export interface LifecycleBreakdown {
  prospect?: number;
  new_customer?: number;
  active_customer?: number;
  at_risk?: number;
  dormant?: number;
  champion?: number;
}

export interface PipelineIntelligence {
  lifecycle_breakdown?: LifecycleBreakdown;
  active_quotes_value?: number;
  stalled_quotes?: string[];
  conversion_trend?: 'improving' | 'stable' | 'declining';
  new_relationships_this_period?: string[];
  // Legacy fields
  total_pipeline_value?: number;
  open_quotes?: number;
}

export interface RiskAlert {
  severity: 'critical' | 'high' | 'medium';
  type: SignalType | string;
  description: string;
  affected_company?: string;
  am_owner?: string;
  days_overdue?: number;
  recommended_action?: string;
  // Legacy fields
  company_name?: string;
  risk_type?: string;
  revenue_at_risk?: number;
}

export interface Opportunity {
  type: 'revenue_opportunity' | 'reactivation' | 'new_relationship' | 'deal_acceleration' | string;
  company_name: string;
  lifecycle_tier?: LifecycleTier;
  description: string;
  estimated_value?: string;
  next_step?: string;
  // Legacy fields
  company_id?: string;
  opportunity_type?: string;
  confidence?: number;
}

export interface CompetitiveLandscape {
  competitor_mentions?: string[];
  price_sensitivity_signals?: string[];
  win_loss_insights?: string[];
}

export interface AMEfficiencyRecord {
  am_name: string;
  avg_bh_response_hours?: number;
  after_hours_pct?: number;
  response_rate_pct?: number;
  revenue_attributed?: number;
  quote_conversion_rate?: number;
  accounts_at_risk?: number;
  performance_note?: string;
}

export interface AMPerformance {
  summary?: AMEfficiencyRecord[];
  top_performers?: string[];
  needs_attention?: string[];
  workload_imbalance?: string | null;
  // Legacy fields
  account_manager?: string;
  total_revenue?: number;
  avg_response_time_hours?: number;
  retention_rate?: number;
}

export interface StrategicActionItem {
  priority: 'urgent' | 'high' | 'medium' | number;
  signal_type?: SignalType;
  action: string;
  owner?: string;
  company?: string;
  deadline_suggestion?: string;
  context?: string;
  // Legacy fields
  contact?: string;
  bucket?: string;
}

export interface StrategicDigest {
  id: string;
  client_id: string;
  digest_date: string;
  period_type: PeriodType;
  period_start: string;
  period_end: string;
  comparison_period_start?: string;
  comparison_period_end?: string;
  executive_summary?: string;
  relationship_health?: RelationshipHealthCard[];
  pipeline_intelligence?: PipelineIntelligence;
  risk_alerts?: RiskAlert[];
  opportunities?: Opportunity[];
  competitive_landscape?: CompetitiveLandscape;
  am_performance?: AMPerformance | AMPerformance[] | Record<string, any>;
  action_items?: StrategicActionItem[];
  companies_analyzed?: number;
  contacts_analyzed?: number;
  emails_analyzed?: number;
  total_cost_usd?: number;
  created_at?: string;
}

export interface StrategicDigestHistory {
  id: string;
  digest_date: string;
  period_type: PeriodType;
  period_start: string;
  period_end: string;
  companies_analyzed?: number;
  emails_analyzed?: number;
  total_cost_usd?: number;
  created_at?: string;
}

export interface AIInsight {
  health_summary?: string;
  engagement_summary?: string;
  thread_summary?: string;
  revenue_risk?: string;
  importance_level?: string;
  risk_level?: string;
  deal_probability?: number;
  key_observations?: string[];
  key_signals?: string[];
  recommended_actions?: string[];
  recommended_action?: string;
  follow_up_suggestion?: string;
  engagement_trend?: string;
  error?: string;
  _entity_type?: string;
  _generated_at?: string;
}

export interface AIModel {
  name: string;
  label: string;
  provider: string;
  cost_input_per_mtok: number;
  cost_output_per_mtok: number;
  available: boolean;
}

// Signal display config (mirrors backend BUCKET_CONFIG)
export const SIGNAL_CONFIG: Record<SignalType, { label: string; color: string; severity: string }> = {
  response_urgency: { label: 'Response Urgency', color: 'red', severity: 'critical' },
  deal_at_risk: { label: 'Deal at Risk', color: 'orange', severity: 'critical' },
  retention_risk: { label: 'Retention Risk', color: 'red', severity: 'critical' },
  revenue_opportunity: { label: 'Revenue Opportunity', color: 'green', severity: 'high' },
  new_relationship: { label: 'New Relationship', color: 'blue', severity: 'high' },
  account_neglect: { label: 'Account Neglect', color: 'gold', severity: 'high' },
};

export const LIFECYCLE_CONFIG: Record<LifecycleTier, { label: string; color: string }> = {
  prospect: { label: 'Prospect', color: 'purple' },
  new_customer: { label: 'New Customer', color: 'blue' },
  active_customer: { label: 'Active Customer', color: 'green' },
  at_risk: { label: 'At Risk', color: 'orange' },
  dormant: { label: 'Dormant', color: 'default' },
  champion: { label: 'Champion', color: 'gold' },
};
