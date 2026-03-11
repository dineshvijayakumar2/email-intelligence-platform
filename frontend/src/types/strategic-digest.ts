/**
 * Strategic Digest TypeScript Interfaces — Sprint 3
 */

export type PeriodType = 'weekly' | 'monthly' | 'quarterly' | 'ytd' | 'custom';

export interface RelationshipHealthCard {
  company_name: string;
  company_id?: string;
  customer_type?: string;
  tier?: string;
  engagement_score?: number;
  engagement_trend?: string;
  revenue?: number;
  revenue_trend?: string;
  days_since_order?: number;
  active_threads?: number;
  key_signal?: string;
}

export interface PipelineIntelligence {
  total_pipeline_value?: number;
  open_quotes?: number;
  active_jobs?: number;
  quote_conversion_rate?: number;
  quotes?: Array<{
    quote_no: string;
    company: string;
    amount: number;
    date_created: string;
    status: string;
  }>;
}

export interface RiskAlert {
  company_name: string;
  company_id?: string;
  risk_type: string;
  severity: 'critical' | 'high' | 'medium';
  description: string;
  revenue_at_risk?: number;
}

export interface Opportunity {
  company_name: string;
  company_id?: string;
  opportunity_type: string;
  description: string;
  estimated_value?: number;
  confidence?: number;
}

export interface CompetitiveLandscape {
  competitors?: Array<{
    name: string;
    mention_count: number;
    trend: string;
    companies_mentioning: string[];
  }>;
  threat_level?: string;
  active_battles?: number;
}

export interface AMPerformance {
  account_manager: string;
  total_revenue?: number;
  revenue_change_pct?: number;
  customer_count?: number;
  quote_conversion_rate?: number;
  avg_response_time_hours?: number;
  retention_rate?: number;
}

export interface StrategicActionItem {
  priority: number;
  action: string;
  company?: string;
  contact?: string;
  context?: string;
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
  am_performance?: AMPerformance[] | Record<string, any>;
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
