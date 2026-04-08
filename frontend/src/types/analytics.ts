/**
 * Analytics TypeScript Interfaces — mirrors backend/src/models/analytics.py
 *
 * 5 enums + 30+ interfaces covering extraction jobs, contacts, companies,
 * threads, response times, communication patterns, and dashboard summaries.
 */

// ============================================================================
// ENUMS
// ============================================================================

export type ExtractionStatus = 'pending' | 'processing' | 'completed' | 'failed';
export type ExtractionMode = 'full' | 'incremental';
export type ThreadStatus = 'complete' | 'awaiting_response' | 'awaiting_our_response' | 'overdue' | 'dropped' | 'ongoing';
export type ContactType = 'person' | 'automated' | 'shared' | 'mailing_list' | 'internal' | 'unknown';
export type EngagementStatus = 'active' | 'quiet' | 'at_risk' | 'unknown';

// ============================================================================
// EXTRACTION JOB MODELS
// ============================================================================

export interface ExtractionJobCreate {
  mailbox_id: string;
  mode?: ExtractionMode;
  lookback_days?: number;
  exclude_mailing_lists?: boolean;
  exclude_noreply?: boolean;
  exclude_shared?: boolean;
  exclude_internal?: boolean;
  force_relink?: boolean;
  skip_role_classification?: boolean;
}

export interface ExtractionJobResponse {
  id: string;
  client_id: string;
  mailbox_id: string;
  status: ExtractionStatus;
  extraction_mode?: string | null;
  emails_in_scope?: number | null;
  date_range_start?: string | null;
  date_range_end?: string | null;
  current_step?: string | null;
  current_step_number?: number | null;
  total_steps?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at?: string | null;
  errors?: string[] | null;
}

export interface ExtractionJobDetail extends ExtractionJobResponse {
  results?: Record<string, any> | null;
  duration_seconds?: number | null;
}

export interface ExtractionJobListResponse {
  jobs: ExtractionJobResponse[];
  total: number;
}

export interface ExtractionProgressResponse {
  job_id: string;
  status: string;
  current_step?: string | null;
  current_step_number?: number | null;
  total_steps?: number | null;
  processed?: number | null;
  failed?: number | null;
  mailbox_id?: string | null;
  client_id?: string | null;
  error?: string | null;
}

// ============================================================================
// CONTACT ANALYTICS MODELS
// ============================================================================

export interface ContactAnalytics {
  id: string;
  email_address: string;
  full_name?: string | null;
  job_title?: string | null;
  company_name?: string | null;
  customer_company_id?: string | null;
  customer_company_name?: string | null;
  client_id: string;
  contact_type?: ContactType | null;
  is_decision_maker?: boolean | null;
  seniority_level?: string | null;
  engagement_score?: number | null;
  total_emails_sent?: number | null;
  total_emails_received?: number | null;
  first_contacted_at?: string | null;
  last_contacted_at?: string | null;
  initiation_ratio?: number | null;
  reply_rate?: number | null;
  avg_response_time_seconds?: number | null;
  avg_thread_depth?: number | null;
  // QB business context (Sprint 3)
  qb_contact_id?: string | null;
  qb_customer_type?: string | null;
  qb_tier?: string | null;
  qb_quotes_count?: number | null;
  qb_last_quote_date?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ContactAnalyticsListResponse {
  contacts: ContactAnalytics[];
  total: number;
}

export interface TopEngagedContact {
  id: string;
  email_address: string;
  full_name?: string | null;
  company_name?: string | null;
  engagement_score: number;
  total_emails: number;
  last_contacted_at?: string | null;
  qb_customer_type?: string | null;
  qb_tier?: string | null;
}

export interface AtRiskContact {
  id: string;
  email_address: string;
  full_name?: string | null;
  company_name?: string | null;
  last_contacted_at?: string | null;
  days_since_contact: number;
  engagement_score?: number | null;
  qb_total_revenue?: number | null;
  qb_tier?: string | null;
}

export interface ContactTypeGrouping {
  contact_type: ContactType;
  count: number;
  avg_engagement_score?: number | null;
}

// ============================================================================
// COMPANY ANALYTICS MODELS
// ============================================================================

export interface CompanyAnalytics {
  id: string;
  company_name: string;
  client_id: string;
  client_name?: string | null;
  email_domains?: string[] | null;
  industry?: string | null;
  engagement_score?: number | null;
  engagement_status?: EngagementStatus | null;
  total_emails?: number | null;
  total_inbound?: number | null;
  total_outbound?: number | null;
  first_contact_date?: string | null;
  last_contact_date?: string | null;
  contact_count?: number | null;
  decision_maker_count?: number | null;
  active_threads?: number | null;
  overdue_threads?: number | null;
  // QB matching metadata (Sprint 4)
  qb_customer_id?: string | null;
  qb_customer_code?: string | null;
  qb_match_method?: string | null;
  qb_matched_at?: string | null;
  // QB business context (Sprint 3)
  qb_customer_type?: string | null;
  qb_tier?: string | null;
  qb_total_revenue?: number | null;
  qb_invoiced_ty?: number | null;
  qb_invoiced_ly?: number | null;
  qb_growth_90d?: number | null;
  qb_days_since_last_invoice?: number | null;
  qb_account_manager?: string | null;
  // QB capability tags (from Unique Emails)
  qb_capabilities?: string[] | null;
  qb_processes?: string[] | null;
  qb_embellishments?: string[] | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CompanyAnalyticsListResponse {
  companies: CompanyAnalytics[];
  total: number;
}

export interface TopEngagedCompany {
  id: string;
  company_name: string;
  engagement_score: number;
  total_emails: number;
  contact_count: number;
  last_contact_date?: string | null;
  qb_tier?: string | null;
  qb_total_revenue?: number | null;
}

export interface AtRiskCompany {
  id: string;
  company_name: string;
  last_contact_date?: string | null;
  days_since_contact: number;
  contact_count: number;
  engagement_score?: number | null;
  qb_total_revenue?: number | null;
  qb_days_since_last_invoice?: number | null;
  qb_tier?: string | null;
}

export interface EngagementStatusGrouping {
  engagement_status: EngagementStatus;
  count: number;
  avg_engagement_score?: number | null;
}

// ============================================================================
// THREAD ANALYTICS MODELS
// ============================================================================

export interface ThreadStatusSummary {
  thread_id: string;
  subject?: string | null;
  contact_id?: string | null;
  contact_email?: string | null;
  contact_name?: string | null;
  company_id?: string | null;
  company_name?: string | null;
  status: ThreadStatus;
  total_messages?: number | null;
  last_message_date?: string | null;
  last_sender_type?: string | null;
  days_since_last_message?: number | null;
  // QB context (Sprint 3)
  qb_customer_type?: string | null;
  qb_customer_tier?: string | null;
  // Intent intelligence (Thread Intelligence)
  intent_status?: string | null;
  intent_override_reason?: string | null;
  last_email_intent?: string | null;
  last_email_urgency?: string | null;
  last_email_sentiment?: string | null;
  created_at?: string | null;
}

export interface ThreadStatusListResponse {
  threads: ThreadStatusSummary[];
  total: number;
}

export interface OverdueThread {
  thread_id: string;
  subject?: string | null;
  contact_email?: string | null;
  contact_name?: string | null;
  company_name?: string | null;
  last_message_date?: string | null;
  days_overdue: number;
  qb_customer_type?: string | null;
  qb_customer_tier?: string | null;
}

export interface ThreadStatusCount {
  status: ThreadStatus;
  count: number;
}

export interface ThreadEmail {
  id: string;
  subject?: string | null;
  sender_email?: string | null;
  sender_name?: string | null;
  recipients?: any[] | null;
  sent_date?: string | null;
  is_outbound?: boolean | null;
  body_text?: string | null;
  folder_path?: string | null;
}

export interface ThreadDetail {
  thread_id: string;
  subject?: string | null;
  status: ThreadStatus;
  total_messages: number;
  last_message_date?: string | null;
  days_since_last_message?: number | null;
  contact_id?: string | null;
  contact_email?: string | null;
  contact_name?: string | null;
  company_id?: string | null;
  company_name?: string | null;
  thread_depth?: number | null;
  created_at?: string | null;
  emails: ThreadEmail[];
}

// ============================================================================
// RESPONSE TIME MODELS
// ============================================================================

export interface ResponseTimeMetric {
  id: string;
  email_id: string;
  responding_to_email_id: string;
  responder_contact_id?: string | null;
  responder_company_id?: string | null;
  contact_email?: string | null;
  response_time_seconds: number;
  is_auto_reply?: boolean | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ResponseTimeListResponse {
  metrics: ResponseTimeMetric[];
  total: number;
}

export interface ResponseTimeStats {
  total_responses: number;
  avg_response_time_hours: number;
  median_response_time_hours?: number | null;
  min_response_time_hours: number;
  max_response_time_hours: number;
  avg_business_hours_response_time_hours?: number | null;
  median_business_hours_response_time_hours?: number | null;
  our_avg_response_time?: number | null;
  their_avg_response_time?: number | null;
  auto_reply_count?: number | null;
  auto_reply_percentage?: number | null;
}

export interface SlowestResponder {
  contact_id: string;
  contact_email: string;
  contact_name?: string | null;
  company_name?: string | null;
  avg_response_time_hours: number;
  response_count: number;
}

// ============================================================================
// COMMUNICATION PATTERN MODELS
// ============================================================================

export interface InitiationPattern {
  contact_id: string;
  contact_email: string;
  contact_name?: string | null;
  company_name?: string | null;
  total_threads: number;
  threads_initiated_by_us: number;
  threads_initiated_by_them: number;
  initiation_ratio: number;
}

export interface FrequencyPattern {
  contact_id: string;
  contact_email: string;
  contact_name?: string | null;
  company_name?: string | null;
  total_emails: number;
  emails_per_week?: number | null;
  emails_per_month?: number | null;
  first_contact_date?: string | null;
  last_contact_date?: string | null;
  days_active?: number | null;
}

export interface EngagementTrend {
  contact_id: string;
  contact_email: string;
  contact_name?: string | null;
  company_name?: string | null;
  current_engagement_score: number;
  trend: 'increasing' | 'stable' | 'decreasing';
  last_30_days_emails: number;
  previous_30_days_emails: number;
  change_percentage: number;
}

export interface CommunicationPattern {
  contact_id: string;
  contact_email: string;
  contact_name?: string | null;
  company_name?: string | null;
  thread_initiation_ratio?: number | null;
  total_threads?: number | null;
  reply_rate?: number | null;
  avg_response_time_hours?: number | null;  // Our avg response time
  their_avg_response_time_hours?: number | null;  // Their avg response time
  emails_per_week?: number | null;
  total_emails?: number | null;
  avg_thread_depth?: number | null;
}

// ============================================================================
// DASHBOARD MODELS
// ============================================================================

export interface DashboardSummary {
  client_id: string;
  total_contacts: number;
  total_companies: number;
  total_emails: number;
  active_contacts: number;
  quiet_contacts: number;
  at_risk_contacts: number;
  avg_engagement_score?: number | null;
  total_threads: number;
  active_threads: number;
  overdue_threads: number;
  awaiting_response_threads: number;
  avg_response_time_hours?: number | null;
  top_engaged_contacts: TopEngagedContact[];
  top_engaged_companies: TopEngagedCompany[];
  at_risk_contacts_list: AtRiskContact[];
  at_risk_companies_list: AtRiskCompany[];
  last_extraction_date?: string | null;
  last_contact_date?: string | null;
}

export interface ClientSummary {
  client_id: string;
  client_name?: string | null;
  mailbox_count: number;
  contact_count: number;
  company_count: number;
  total_emails: number;
  avg_engagement_score?: number | null;
  active_contacts: number;
  at_risk_contacts: number;
  last_extraction_date?: string | null;
  last_contact_date?: string | null;
}

// ============================================================================
// HELPER TYPES
// ============================================================================

export interface PaginationParams {
  limit?: number;
  offset?: number;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
}

export interface ContactFilterParams extends PaginationParams {
  client_id?: string;
  company_id?: string;
  contact_type?: ContactType;
  is_decision_maker?: boolean;
  min_engagement_score?: number;
  qb_linked?: boolean;
  search?: string;
}

export interface CompanyFilterParams extends PaginationParams {
  client_id?: string;
  engagement_status?: EngagementStatus;
  min_engagement_score?: number;
  qb_matched?: boolean;
  qb_tier?: string;
  qb_account_manager?: string;
  search?: string;
}

export interface ThreadFilterParams extends PaginationParams {
  client_id?: string;
  mailbox_id?: string;
  status?: ThreadStatus | 'active' | string;
  search?: string;
}

export interface ExtractionJobFilterParams extends PaginationParams {
  client_id?: string;
  mailbox_id?: string;
  status?: ExtractionStatus;
}
