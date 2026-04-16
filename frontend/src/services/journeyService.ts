import api from './apiClient';

export interface ThreadQBLink {
  id: string;
  client_id: string;
  canonical_thread_id: string;
  link_type: string;
  qb_record_id: string;
  qb_reference: string | null;
  confidence: number;
  source: string;
  verified: boolean;
  created_at: string;
}

export interface ThreadJourney {
  thread_id: string;
  emails: Array<{
    id: string;
    subject: string;
    sender_email: string;
    sender_name: string;
    date_sent: string;
    canonical_thread_id: string;
  }>;
  links: ThreadQBLink[];
  quotes: Array<Record<string, unknown>>;
  jobs: Array<Record<string, unknown>>;
  operations: Array<Record<string, unknown>>;
  sales_line_items: Array<Record<string, unknown>>;
  status_log: Array<Record<string, unknown>>;
}

export interface JobJourney {
  job: Record<string, unknown>;
  links: ThreadQBLink[];
  emails: Array<Record<string, unknown>>;
  quotes: Array<Record<string, unknown>>;
  operations: Array<Record<string, unknown>>;
  sales_line_items: Array<Record<string, unknown>>;
  status_log: Array<Record<string, unknown>>;
}

export interface CompanyTimeline {
  company_id: string;
  total_threads: number;
  linked_threads: number;
  journeys: Array<{
    thread_id: string;
    links: ThreadQBLink[];
    qb_references: string[];
  }>;
}

export async function getThreadJourney(threadId: string, clientId: string): Promise<ThreadJourney> {
  return api.get<ThreadJourney>(`/v1/journey/threads/${threadId}?client_id=${clientId}`);
}

export async function getJobJourney(jobNo: string, clientId: string): Promise<JobJourney> {
  return api.get<JobJourney>(`/v1/journey/jobs/${jobNo}?client_id=${clientId}`);
}

export async function getCompanyTimeline(companyId: string, clientId: string, limit = 20): Promise<CompanyTimeline> {
  return api.get<CompanyTimeline>(`/v1/journey/companies/${companyId}/timeline?client_id=${clientId}&limit=${limit}`);
}

export async function createManualLink(
  clientId: string,
  threadId: string,
  linkType: string,
  qbReference: string,
): Promise<{ status: string; link: ThreadQBLink }> {
  return api.post('/v1/journey/links', {
    client_id: clientId,
    canonical_thread_id: threadId,
    link_type: linkType,
    qb_reference: qbReference,
  });
}

export async function deleteLink(linkId: string): Promise<void> {
  await api.delete(`/v1/journey/links/${linkId}`);
}
