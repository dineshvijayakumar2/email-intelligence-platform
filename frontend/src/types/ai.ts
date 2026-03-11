/**
 * AI Intelligence Types — Sprint 3
 *
 * TypeScript interfaces mirroring backend/src/models/ai.py
 */

// ============================================================================
// ENUMS (union types)
// ============================================================================

export type IntentType =
  | 'action_required' | 'fyi_update' | 'meeting_scheduling' | 'question'
  | 'complaint' | 'positive_feedback' | 'pricing_inquiry' | 'feature_request'
  | 'expansion_signal' | 'churn_risk' | 'follow_up' | 'introduction' | 'other';

export type UrgencyLevel = 'critical' | 'high' | 'medium' | 'low' | 'none';

export type SentimentType = 'very_positive' | 'positive' | 'neutral' | 'negative' | 'very_negative';

export type ActionType =
  | 'respond_to_inquiry' | 'provide_quote' | 'schedule_meeting'
  | 'escalate_internally' | 'send_follow_up' | 'resolve_issue'
  | 'acknowledge_receipt' | 'no_action' | 'delegate' | 'prepare_document';

export type BusinessSignalType =
  | 'buying_intent' | 'renewal_intent' | 'expansion_interest'
  | 'churn_signal' | 'competitive_evaluation' | 'budget_discussion'
  | 'escalation' | 'positive_feedback' | 'negative_feedback'
  | 'contract_activity' | 'neutral';

export type BucketType =
  | 'buying_signal' | 'expansion_signal' | 'churn_risk' | 'competitor_threat'
  | 'missed_opportunity' | 'stakeholder_entry' | 'silent_champion' | 'unresolved_block';

export type ProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed';

export type FeedbackType = 'correct' | 'incorrect';

export type EntityType = 'competitor' | 'product' | 'person' | 'company' | 'technology';

// ============================================================================
// INTELLIGENCE RESULTS
// ============================================================================

export interface BucketEntry {
  bucket: string;
  confidence: number;
  justification: string;
}

export interface IntelligenceResult {
  id?: string;
  email_id?: string;

  // Email display fields (joined from emails table)
  email_subject: string;
  email_sender: string;
  email_sender_name: string;
  email_date?: string;
  email_direction: string;
  email_body?: string;
  email_body_html?: string;
  email_recipients?: any[];

  // Classification
  intent?: IntentType;
  urgency?: UrgencyLevel;
  sentiment?: SentimentType;
  sentiment_score?: number;
  summary: string;
  suggested_action: string;
  key_topics: string[];
  confidence?: number;
  justification: string;

  // Multi-axis
  action_type?: ActionType;
  business_signal?: BusinessSignalType;
  thread_role?: string;

  // Entities
  competitors_mentioned: string[];
  products_mentioned: string[];
  budget_signals?: Record<string, any> | null;
  buying_signals: string[];
  people_mentioned: Record<string, any>[];
  dates_mentioned: Record<string, any>[];
  action_items_extracted: string[];

  // Business signal flags
  has_budget_signal: boolean;
  has_buying_signal: boolean;
  has_competitor_mention: boolean;
  has_deadline: boolean;
  business_signal_score: number;

  // Buckets
  action_buckets: BucketEntry[];
  primary_bucket?: BucketType;

  // Feedback
  human_feedback?: FeedbackType;
  feedback_field?: string;
  feedback_note?: string;

  // Processing
  processing_status?: ProcessingStatus;
  processed_at?: string;
  model_used?: string;
  prompt_version?: string;
}

export interface IntelligenceListResponse {
  items: IntelligenceResult[];
  page: number;
  page_size: number;
}

export interface IntelligenceStats {
  total: number;
  by_status: Record<string, number>;
  by_intent: Record<string, number>;
  by_urgency: Record<string, number>;
  by_sentiment: Record<string, number>;
  by_bucket: Record<string, number>;
  by_business_signal: Record<string, number>;
  avg_confidence: number;
}

// ============================================================================
// ACTION BUCKETS
// ============================================================================

export interface BucketConfig {
  label: string;
  color: string;
  severity: string;
  action: string;
}

export interface ActionItem {
  email_id?: string;
  bucket: BucketType;
  bucket_label: string;
  bucket_color: string;
  severity: string;
  recommended_action: string;
  confidence: number;
  justification: string;
  email_summary: string;
  email_suggested_action: string;
  intent?: IntentType;
  urgency?: UrgencyLevel;
  business_signal_score: number;
  email_subject?: string;
  email_sender?: string;
  email_sender_name?: string;
  email_date?: string;
}

export interface ActionItemsResponse {
  items: ActionItem[];
  total: number;
}

export interface BucketSummary {
  buying_signal: number;
  expansion_signal: number;
  churn_risk: number;
  competitor_threat: number;
  missed_opportunity: number;
  stakeholder_entry: number;
  silent_champion: number;
  unresolved_block: number;
  total: number;
}

// ============================================================================
// ENTITIES
// ============================================================================

export interface BusinessEntity {
  id?: string;
  entity_type: EntityType;
  entity_name: string;
  normalized_name: string;
  mention_count: number;
  first_seen_at?: string;
  last_seen_at?: string;
  context_snippets: string[];
}

export interface EntityListResponse {
  items: BusinessEntity[];
  total: number;
}

export interface CompetitorLandscape {
  competitors: BusinessEntity[];
  total_mentions: number;
  accounts_affected: number;
}

export interface OpportunitySignal {
  email_id?: string;
  email_subject: string;
  email_sender: string;
  email_date?: string;
  signal_type: string;
  confidence: number;
  summary: string;
  budget_signal?: Record<string, any> | null;
  buying_signals: string[];
  business_signal_score: number;
}

export interface OpportunitySignalsResponse {
  items: OpportunitySignal[];
  total: number;
}

// ============================================================================
// FEEDBACK
// ============================================================================

export interface FeedbackRequest {
  feedback: FeedbackType;
  feedback_field?: string;
  override_intent?: string;
  override_bucket?: string;
  override_sentiment?: string;
  note?: string;
}

export interface FeedbackResponse {
  status: string;
  email_id: string;
  feedback: string;
  feedback_field?: string;
}

// ============================================================================
// ANALYZE
// ============================================================================

export interface AnalyzeRequest {
  max_emails?: number;
  client_id?: string;
  date_from?: string;
  date_to?: string;
}

export interface AnalyzeResponse {
  status: string;
  message: string;
  mailbox_id: string;
  max_emails: number;
}

// ============================================================================
// DIGEST
// ============================================================================

export interface DigestActionItem {
  email_id?: string;
  priority: number;
  bucket?: string;
  action: string;
  contact_name?: string;
}

export interface DigestHighlight {
  label: string;
  detail: string;
}

export interface DailyDigest {
  id?: string;
  digest_date?: string;
  summary: string;
  action_items: DigestActionItem[];
  highlights: DigestHighlight[];
  stats: Record<string, any>;
  bucket_summary: Record<string, number>;
  emails_analyzed: number;
  model_used?: string;
  created_at?: string;
}

export interface DigestHistoryResponse {
  items: DailyDigest[];
  total: number;
}

// ============================================================================
// USAGE
// ============================================================================

export interface UsageSummary {
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_requests: number;
  by_operation: Record<string, { cost: number; count: number }>;
  by_model: Record<string, { cost: number; count: number }>;
  failure_rate: number;
  avg_latency_ms: number;
}

export interface MonitoringStats {
  parse_failure_rate: number;
  api_failure_rate: number;
  avg_retry_count: number;
  cost_per_1000_emails: number;
  total_failures_24h: number;
  total_requests_24h: number;
}

export interface AIControlSettings {
  ai_enabled: boolean;
  email_analysis_enabled: boolean;
  digest_enabled: boolean;
  relationship_summary_enabled: boolean;
  daily_budget_usd: number;
  monthly_budget_usd: number;
  batch_size: number;
  max_emails_per_run: number;
  max_requests_per_second: number;
  session_spend_usd: number;
  session_requests: number;
}

export interface UsageLogEntry {
  id?: string;
  operation: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  processing_time_ms?: number;
  batch_size: number;
  success: boolean;
  error_type: string;
  error_detail?: string | null;
  retry_count: number;
  prompt_version: string;
  created_at?: string;
}

// ============================================================================
// FILTER PARAMS
// ============================================================================

export interface IntelligenceFilterParams {
  page?: number;
  page_size?: number;
  intent?: IntentType;
  urgency?: UrgencyLevel;
  sentiment?: SentimentType;
  primary_bucket?: BucketType;
  action_type?: ActionType;
  business_signal?: BusinessSignalType;
  has_budget_signal?: boolean;
  has_buying_signal?: boolean;
  has_competitor_mention?: boolean;
  min_confidence?: number;
  processing_status?: ProcessingStatus;
}
