# Database Design — Email Intelligence Platform

A comprehensive reference for every database object in the Email Intelligence Platform. Describes current-state production schema as of 2026-05-14. Validated against live Supabase PostgreSQL 17.6.

**Total database size: 9.4 GB** across 55 tables, 1 materialized view, 10 regular views, ~60 application-level RPC functions, and 7 PostgreSQL extensions.

---

## 1. Database Overview

### Infrastructure
- **Engine:** PostgreSQL 17.6 (aarch64 Linux) on Supabase
- **Extensions:** pgvector 0.8.0, pg_stat_statements 1.11, pgcrypto 1.3, uuid-ossp 1.1, pg_graphql 1.5.11, supabase_vault 0.3.1, plpgsql 1.0
- **Access:** PostgREST auto-generates REST API; RPC functions exposed as `POST /rest/v1/rpc/<fn_name>`
- **Auth:** Supabase Auth (JWT) with Row-Level Security on select tables
- **Migrations:** incremental SQL scripts in `scripts/migrations/` (001–122), applied via `exec_sql` RPC + PostgREST schema reload

### Schema Domains

| Domain | Tables | Purpose |
|--------|--------|---------|
| **Auth & Users** | 5 | User profiles, RBAC, client assignments |
| **Email Core** | 8 | Emails, mailboxes, folders, categories, contact links |
| **Customer Data** | 6 | Companies, contacts, recognition rules, intelligence cache |
| **AI Intelligence** | 7 | Classifications, digests, entities, prompts, usage |
| **QuickBase Cache** | 10 | Customers, contacts, quotes, jobs, operations, sync |
| **Analytics** | 5 | Metrics, recommendations, performance snapshots |
| **Infrastructure** | 8 | Processing jobs, events, notifications, errors, config |
| **Views** | 11 | Computed aggregates, persona, benchmarks, stats |

---

## 2. Tables — Full Schema Reference

Tables are organized by domain. For each table: columns, types, constraints, and current scale.

---

### 2.1 Auth & User Management

#### `user_profiles`
Links Supabase Auth users to platform roles and preferences. Auto-created on signup via `handle_new_user()` trigger on `auth.users`.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | — | PK, matches auth.users.id |
| email | text | NOT NULL | | |
| name | text | NOT NULL | | |
| is_active | bool | NULL | true | |
| avatar_url | text | NULL | | |
| roles | text[] | NULL | `{account_manager}` | Array: admin, client_manager, account_manager |
| timezone | text | NOT NULL | `UTC` | IANA timezone |
| business_hours_start | int4 | NOT NULL | 9 | Hour (0-23) |
| business_hours_end | int4 | NOT NULL | 18 | |
| business_days | int4[] | NOT NULL | `{1,2,3,4,5}` | 1=Mon, 7=Sun |
| created_at | timestamptz | NULL | now() | |
| updated_at | timestamptz | NULL | now() | Auto-updated by trigger |

**Scale:** 10 rows | **RLS:** Yes (self-select, self-update, admin-all)

#### `clients`
Tenant entities — each client is a separate business using the platform.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| client_name | text | NOT NULL | | |
| client_label | text | NULL | | Short code for UI |
| industry | text | NULL | | |
| status | text | NULL | `active` | |
| uses_quickbase | bool | NULL | false | |
| quickbase_realm | text | NULL | | e.g., `dc.quickbase.com` |
| quickbase_api_token | text | NULL | | **Security concern:** plaintext token |
| uses_printiq | bool | NULL | false | |
| printiq_api_url | text | NULL | | |
| printiq_api_key | text | NULL | | |
| notes | text | NULL | | |
| timezone | text | NOT NULL | `Australia/Sydney` | |
| currency_code | text | NOT NULL | `AUD` | |
| created_at | timestamptz | NULL | now() | |
| updated_at | timestamptz | NULL | now() | |

**Scale:** 3 rows | **RLS:** No (backend uses service key)

#### `user_client_assignments`
Many-to-many: which users can access which clients.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| user_id | uuid | NOT NULL | | FK → user_profiles.id (CASCADE) |
| client_id | uuid | NOT NULL | | FK → clients.id (CASCADE) |
| created_at | timestamptz | NULL | now() |

**Unique:** (user_id, client_id) | **Scale:** 8 rows | **RLS:** Yes (admin-all, manager-select, self-select)

#### `client_manager_assignments`
Which client_manager users manage which clients (subset of user_client_assignments).

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| user_id | uuid | NOT NULL | | FK → user_profiles.id (CASCADE) |
| client_id | uuid | NOT NULL | | FK → clients.id (CASCADE) |
| created_at | timestamptz | NULL | now() |

**Unique:** (user_id, client_id) | **Scale:** 4 rows | **RLS:** Yes

#### `account_managers`
Legacy table — pre-RBAC account manager list. **Unused in production** (0 rows). Retained for backward compatibility.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| name | text | NOT NULL | | |
| email | text | NOT NULL | | UNIQUE |
| role | text | NOT NULL | `account_manager` | |
| password_hash | text | NULL | | |
| is_active | bool | NULL | true | |
| created_at/updated_at | timestamptz | | now() | |

**Scale:** 0 rows (legacy)

---

### 2.2 Email Core

#### `mailboxes`
Connected email accounts (Outlook, Gmail, file uploads). Each stores its own OAuth tokens.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| name | text | NOT NULL | | Display name |
| email_address | text | NULL | | UNIQUE; read-only after OAuth |
| mailbox_type | text | NOT NULL | | `outlook`, `gmail`, `mbox`, `pst`, `olm` |
| connection_config | jsonb | NULL | | OAuth tokens, delta links, sync state |
| is_active | bool | NULL | true | |
| sync_enabled | bool | NULL | false | |
| last_sync_at | timestamptz | NULL | | |
| last_synced_at | timestamptz | NULL | | Duplicate of above (legacy) |
| total_emails | int4 | NULL | 0 | |
| client_id | uuid | NULL | | FK → clients.id |
| user_id | uuid | NULL | | FK → user_profiles.id |
| last_extraction_at | timestamptz | NULL | | |
| extraction_mode | varchar(20) | NULL | `full` | `full` or `lightweight` |
| auto_extract_enabled | bool | NULL | false | |
| incremental_lookback_days | int4 | NULL | 7 | |
| created_at/updated_at | timestamptz | | now() | |

**Scale:** 7 rows | **RLS:** Yes (mailbox_access policy)

#### `emails`
Core email storage — every synced/imported email.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| message_id | text | NOT NULL | | Provider message ID |
| mailbox_id | uuid | NULL | | FK → mailboxes.id (CASCADE) |
| thread_id | text | NULL | | Provider thread ID |
| folder_path | text | NULL | | |
| sender_email | text | NOT NULL | | |
| sender_name | text | NULL | | |
| recipients | jsonb | NULL | | Array of {email, name} |
| cc_list | jsonb | NULL | | |
| bcc_list | jsonb | NULL | | |
| subject | text | NULL | | |
| body_text | text | NULL | | Plain text body |
| body_html | text | NULL | | HTML body |
| sent_date | timestamptz | NULL | | |
| received_date | timestamptz | NULL | | |
| is_outbound | bool | NULL | false | |
| is_reply | bool | NULL | false | |
| message_size | int4 | NULL | | Bytes |
| raw_headers | jsonb | NULL | | |
| client_id | uuid | NULL | | FK → clients.id |
| customer_company_id | uuid | NULL | | FK → customer_companies.id |
| customer_contact_id | uuid | NULL | | FK → customer_contacts.id |
| direction | text | NULL | | `inbound`/`outbound` |
| processing_status | text | NULL | `pending` | `pending`, `success`, `failed` |
| processing_error | text | NULL | | |
| processing_attempts | int4 | NULL | 0 | |
| last_processing_attempt | timestamptz | NULL | | |
| internet_message_id | text | NULL | | Standards-based Message-ID |
| in_reply_to | text | NULL | | Threading header |
| references_header | text | NULL | | Threading header |
| provider_thread_id | text | NULL | | Gmail/Outlook thread grouping |
| subject_normalized | text | NULL | | Stripped Re:/Fwd: prefixes |
| thread_confidence | float4 | NULL | 1.0 | |
| attachments | jsonb | NOT NULL | `[]` | Array of attachment metadata |
| provider_web_link | text | NULL | | Deep link to email in provider |
| embedding | vector(768) | NULL | | See §5.5 Vector Embedding Architecture |
| embedding_model | text | NULL | | Provider/model tag, e.g. `openai/text-embedding-3-small-768` |
| embedded_at | timestamptz | NULL | | When the embedding was last written |
| extracted_at | timestamptz | NULL | | When extraction pipeline last processed this email |
| canonical_thread_id | uuid | NULL | | 4-tier resolved thread ID |
| thread_match_method | text | NULL | | `in_reply_to`, `references`, `subject_participants`, `new` |
| thread_match_confidence | float4 | NULL | | |
| search_text | tsvector | NULL | | Auto-populated by trigger for BM25 search |
| created_at/updated_at | timestamptz | | now() | |

**Scale:** 262,051 rows | **Total size:** 7.7 GB (473 MB data + 7.2 GB indexes including IVFFlat vector index) | **Unique:** (message_id, mailbox_id) | **RLS:** Yes

#### `email_categories`
Tags/categories assigned to emails by the rule-based tagger (20+ tags).

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| email_id | uuid | NULL | | FK → emails.id (CASCADE) |
| category | text | NOT NULL | | Tag name |
| confidence | numeric | NULL | 1.0 | |
| detection_method | text | NULL | | `rule`, `ai`, etc. |
| tag_type | text | NULL | | |
| created_at | timestamptz | NULL | now() | |

**Unique:** (email_id, category) | **Scale:** 607,485 rows (291 MB)

#### `email_contact_links`
Many-to-many junction between emails and contacts/companies with role tracking. **Scope: contact-level / participant analysis ONLY.** `company_id` is resolved per-participant (contact-FK → domain lookup) and diverges from `emails.customer_company_id`; do NOT use it to count a company's emails (it inflates end-customers with broker/shared-domain spillover — see `customer_companies` aggregate-semantics note). Company email volume comes from `emails.customer_company_id`.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| email_id | uuid | NOT NULL | | FK → emails.id (CASCADE) |
| contact_id | uuid | NULL | | FK → customer_contacts.id |
| company_id | uuid | NULL | | FK → customer_companies.id |
| email_address | text | NOT NULL | | |
| role | text | NOT NULL | | `sender`, `to`, `cc`, `bcc` |
| client_id | uuid | NOT NULL | | FK → clients.id (CASCADE) |
| created_at | timestamptz | NULL | now() | |

**Unique:** (email_id, email_address, role) | **Scale:** 458,211 rows (173 MB)

#### `email_response_metrics`
Calculated response times between email pairs.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| email_id | uuid | NOT NULL | | FK → emails.id (CASCADE) |
| responding_to_email_id | uuid | NOT NULL | | FK → emails.id (CASCADE) |
| responder_contact_id | uuid | NULL | | FK → customer_contacts.id |
| responder_company_id | uuid | NULL | | FK → customer_companies.id |
| response_time_seconds | int4 | NOT NULL | | |
| is_auto_reply | bool | NOT NULL | false | |
| business_hours_response_time_seconds | int4 | NULL | | |
| created_at/updated_at | timestamptz | | now() | |

**Unique:** email_id (one response metric per email) | **Scale:** 54,607 rows (24 MB)

#### `folders`
Email folder hierarchy within mailboxes.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| folder_path | text | NOT NULL | | |
| mailbox_id | uuid | NULL | | FK → mailboxes.id (CASCADE) |
| parent_folder_id | uuid | NULL | | FK → folders.id (self-reference) |
| folder_type | text | NULL | | |
| message_count | int4 | NULL | 0 | |
| created_at | timestamptz | NULL | now() | |

**Unique:** (folder_path, mailbox_id) | **Scale:** 157 rows

#### `thread_status`
Computed thread-level aggregates — status, participants, SLA tracking, AI intent overrides.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| thread_id | text | NOT NULL | | UNIQUE |
| mailbox_id | uuid | NULL | | FK → mailboxes.id (CASCADE) |
| customer_company_id | uuid | NULL | | FK (legacy, pre-canonical) |
| customer_contact_id | uuid | NULL | | FK (legacy) |
| subject | text | NULL | | |
| status | text | NOT NULL | `complete` | `awaiting_reply`, `complete`, `overdue`, `dropped`, `new`, `one_way` |
| last_message_direction | text | NULL | | |
| last_message_at | timestamptz | NULL | | |
| last_inbound_at | timestamptz | NULL | | |
| last_outbound_at | timestamptz | NULL | | |
| message_count | int4 | NULL | 0 | |
| participant_count | int4 | NULL | 0 | |
| open_duration_seconds | int4 | NULL | | |
| sla_deadline | timestamptz | NULL | | |
| sla_threshold_hours | int4 | NULL | 4 | |
| is_flagged | bool | NULL | false | |
| last_email_id | uuid | NULL | | FK → emails.id |
| last_email_date | timestamptz | NULL | | |
| last_sender_is_outbound | bool | NULL | | |
| thread_depth | int4 | NULL | 0 | |
| days_since_last_email | int4 | NULL | | |
| is_overdue | bool | NULL | false | |
| primary_contact_id | uuid | NULL | | FK → customer_contacts.id |
| primary_company_id | uuid | NULL | | FK → customer_companies.id |
| qb_customer_type | text | NULL | | Denormalized from QB |
| qb_customer_tier | text | NULL | | |
| canonical_thread_id | uuid | NULL | | Links to canonical resolution |
| intent_status | text | NULL | | AI-derived: `urgent`, `revenue`, `closing`, `escalation`, `informational` |
| intent_override_reason | text | NULL | | |
| last_email_intent | text | NULL | | |
| last_email_urgency | text | NULL | | |
| last_email_sentiment | text | NULL | | |
| timing_status | text | NULL | | `awaiting_reply`, `needs_follow_up`, etc. |
| override_rule_id | uuid | NULL | | FK → thread_status_override_rules.id |
| created_at/updated_at | timestamptz | | now() | |

**Scale:** 57,428 rows (85 MB) | **Unique:** thread_id (enforced twice — legacy + explicit)

#### `thread_status_override_rules`
Rules engine for AI-driven thread status overrides (e.g., "if urgent intent + awaiting reply → escalation").

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| name | text | NOT NULL | | UNIQUE |
| description | text | NULL | | |
| priority | int4 | NOT NULL | | Lower = higher priority |
| when_timing_in | text[] | NULL | | Match if timing_status IN these |
| when_timing_not_in | text[] | NULL | | |
| when_intent_in | text[] | NULL | | |
| when_urgency_in | text[] | NULL | | |
| effective_status_becomes | text | NOT NULL | | |
| reason_template | text | NULL | | |
| enabled | bool | NOT NULL | true | |
| created_at/updated_at | timestamptz | | now() | |

**Scale:** ~10 rows

---

### 2.3 Customer Data

#### `customer_companies`
Extracted companies from email domains. Enriched with QB data post-matching.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| client_id | uuid | NOT NULL | | FK → clients.id (CASCADE) |
| company_name | text | NOT NULL | | |
| email_domains | jsonb | NULL | `[]` | Array of domain strings |
| industry | text | NULL | | |
| website | text | NULL | | |
| first_contact_date | timestamptz | NULL | | |
| last_contact_date | timestamptz | NULL | | |
| total_emails | int4 | NULL | 0 | |
| total_inbound | int4 | NULL | 0 | |
| total_outbound | int4 | NULL | 0 | |
| contact_count | int4 | NULL | 0 | |
| decision_maker_count | int4 | NULL | 0 | |
| primary_contact_id | uuid | NULL | | FK → customer_contacts.id |
| highest_seniority | text | NULL | | |
| engagement_score | int4 | NULL | 0 | 0-100 composite |
| relationship_status | text | NULL | `new` | |
| avg_response_time_seconds | int4 | NULL | | |
| sla_compliance_rate | numeric | NULL | | |
| open_thread_count | int4 | NULL | 0 | |
| dropped_thread_count | int4 | NULL | 0 | |
| avg_emails_per_month | numeric | NULL | | |
| frequency_trend | text | NULL | | `increasing`, `stable`, `declining` |
| communication_health | text | NULL | `good` | `good`, `warning`, `critical` |
| scoring_version | int4 | NOT NULL | 1 | |
| qb_customer_type | text | NULL | | From QB: `Active`, `Inactive`, etc. |
| qb_tier | text | NULL | | `Gold`, `Silver`, etc. |
| qb_total_revenue | numeric | NULL | | |
| qb_invoiced_ty | numeric | NULL | | This year |
| qb_invoiced_ly | numeric | NULL | | Last year |
| qb_growth_90d | numeric | NULL | | 90-day growth rate |
| qb_days_since_last_invoice | int4 | NULL | | |
| qb_account_manager | text | NULL | | |
| embedding | vector(768) | NULL | | See §5.5 Vector Embedding Architecture |
| embedding_model | text | NULL | | Provider/model tag |
| embedded_at | timestamptz | NULL | | When embedding was last written |
| qb_customer_id | text | NULL | | **MIXED ID-SPACE (record-id in practice).** Holds a QB numeric id that collides with the `customer_key_id` space (QB field 3 vs field 92) — root cause of cross-customer contamination. Being superseded by `qb_customer_key_id` (Option A). Do NOT compare/join raw against `qb_customers` without name-aware resolution. |
| qb_customer_key_id | text | NULL | | **Canonical key-id-space resolution** of `qb_customer_id` (name-aware). Added mig 118 (Option A Phase 1), backfilled 13,570 rows. NOT yet read by code (Phase 2 repoints to it; Phase 3 drops `qb_customer_id`). NULL = ambiguous/unresolved. |
| qb_customer_code | text | NULL | | |
| qb_match_method | text | NULL | | `exact_domain`, `email_first`, `fuzzy` |
| qb_matched_at | timestamptz | NULL | | |
| notes | text | NULL | | |
| created_at/updated_at | timestamptz | | now() | |

**Unique:** (client_id, company_name) | **Scale:** 14,939 rows (40 MB)

**Email/contact aggregate semantics (mig 117, 9 June):** `total_emails`/`total_inbound`/`total_outbound`/`first_contact_date`/`last_contact_date` are computed from the CANONICAL assignment `emails.customer_company_id`, and `contact_count`/`decision_maker_count` from `customer_contacts.customer_company_id` — **NOT** from `email_contact_links.company_id`. The junction's `company_id` is a per-participant resolution that diverges from the email's primary assignment and inflates end-customers with broker/shared-domain spillover. The recompute function `update_company_email_counts_from_junction` (name retained for caller compat) was rewritten accordingly; it must be invoked via a direct connection (`statement_timeout=0`), not the PostgREST RPC. The `get_company_emails` endpoint lists by `customer_company_id` to match these counts.

#### `customer_contacts`
Extracted contacts from email addresses with role classification and engagement metrics.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| customer_company_id | uuid | NULL | | FK → customer_companies.id (CASCADE) |
| client_id | uuid | NULL | | FK → clients.id (CASCADE) |
| email_address | text | NOT NULL | | |
| full_name | text | NULL | | |
| first_name | text | NULL | | |
| last_name | text | NULL | | |
| job_title | text | NULL | | |
| company_name | text | NULL | | Denormalized |
| phone_number | text | NULL | | |
| mobile_number | text | NULL | | |
| linkedin_url | text | NULL | | |
| seniority_level | text | NULL | | `c_suite`, `director`, `manager`, `individual` |
| functional_role | text | NULL | | `sales`, `operations`, `design`, etc. |
| is_decision_maker | bool | NULL | false | |
| is_primary_contact | bool | NULL | false | |
| role_source | text | NULL | `unknown` | `title_parser`, `ai`, `manual` |
| role_confidence | numeric | NULL | 0.00 | |
| department | text | NULL | | |
| engagement_score | int4 | NULL | 0 | 0-100 composite |
| avg_response_time_seconds | int4 | NULL | | Our response time to them |
| their_avg_response_time | int4 | NULL | | Their response time to us |
| initiation_ratio | numeric | NULL | | 0.0 = they always initiate, 1.0 = we always initiate |
| reply_rate | numeric | NULL | | |
| emails_per_month_avg | numeric | NULL | | |
| frequency_trend | text | NULL | | |
| avg_thread_depth | numeric | NULL | | |
| last_inbound_at | timestamptz | NULL | | |
| last_outbound_at | timestamptz | NULL | | |
| open_thread_count | int4 | NULL | 0 | |
| dropped_thread_count | int4 | NULL | 0 | |
| is_shared_address | bool | NULL | false | e.g., info@, sales@ |
| contact_type | text | NULL | `person` | `person`, `internal`, `shared`, `automated`, `mailing_list`, `unknown` |
| scoring_version | int4 | NOT NULL | 1 | |
| total_emails_sent | int4 | NULL | 0 | |
| total_emails_received | int4 | NULL | 0 | |
| signature_data | jsonb | NULL | | |
| signature_last_updated | timestamptz | NULL | | |
| qb_quotes_count | int4 | NULL | 0 | |
| qb_last_quote_date | date | NULL | | |
| qb_contact_recency_days | int4 | NULL | | |
| qb_customer_type | text | NULL | | |
| qb_tier | text | NULL | | |
| qb_total_revenue | numeric | NULL | | |
| qb_capabilities_used | text | NULL | | |
| qb_processes_used | text | NULL | | |
| qb_linked_at | timestamptz | NULL | | |
| notes | text | NULL | | |
| first_contacted_at/last_contacted_at | timestamptz | | | |
| created_at/updated_at | timestamptz | | now() | |

**Unique:** (client_id, email_address) and (customer_company_id, email_address) | **Scale:** 21,237 rows (46 MB)

#### `customer_intelligence_cache`
Cached computed intelligence per company/contact (seasonality, product profiles, etc.).

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| client_id | uuid | NOT NULL | | FK → clients.id (CASCADE) |
| company_id | uuid | NOT NULL | | FK → customer_companies.id (CASCADE) |
| contact_id | uuid | NULL | | FK → customer_contacts.id (CASCADE) |
| cache_type | text | NOT NULL | | `seasonality`, `product_profile`, etc. |
| data | jsonb | NOT NULL | `{}` | |
| computed_at | timestamptz | NOT NULL | now() | |

**Unique:** (client_id, company_id, cache_type) WHERE contact_id IS NULL; (client_id, company_id, contact_id, cache_type) WHERE contact_id IS NOT NULL | **Scale:** 8 rows

#### `customer_recommendations`
Computed cross-contact and related-product recommendations per company.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| client_id | uuid | NOT NULL | | FK → clients.id (CASCADE) |
| company_id | uuid | NOT NULL | | FK → customer_companies.id (CASCADE) |
| cross_contact_recs | jsonb | NOT NULL | `[]` | |
| related_product_recs | jsonb | NOT NULL | `[]` | |
| product_profile | jsonb | NOT NULL | `{}` | |
| computed_at | timestamptz | NOT NULL | now() | |

**Unique:** (client_id, company_id) | **Scale:** 37 rows

#### `customer_recognition_rules`
Pattern-based rules for recognizing companies from email domains/addresses.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| client_id | uuid | NULL | | FK → clients.id (CASCADE) |
| customer_company_id | uuid | NULL | | FK → customer_companies.id (CASCADE) |
| rule_name | text | NOT NULL | | |
| rule_type | text | NOT NULL | | |
| pattern | text | NOT NULL | | |
| priority | int4 | NULL | 0 | |
| is_active | bool | NULL | true | |
| match_count | int4 | NULL | 0 | |
| last_matched_at | timestamptz | NULL | | |
| created_at/updated_at | timestamptz | | now() | |

**Scale:** 0 rows (available but unused)

#### `internal_domains`
Domains belonging to the client's own organization (used to determine email direction).

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| client_id | uuid | NOT NULL | | FK → clients.id (CASCADE) |
| domain | text | NOT NULL | | |
| created_at | timestamptz | NULL | now() | |

**Unique:** (client_id, domain) | **Scale:** 1 row

#### `free_email_providers`
Lookup table of domains that are free email providers (gmail.com, yahoo.com, etc.) — contacts from these don't get company associations.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| domain | text | NOT NULL | | PK |
| provider_name | text | NULL | | |
| notes | text | NULL | | |
| created_at | timestamptz | NULL | now() | |

**Scale:** 29 rows

---

### 2.4 AI Intelligence

#### `ai_email_intelligence`
Per-email AI classification output (intent, urgency, sentiment, signals, action buckets).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| email_id | uuid | NULL | | FK → emails.id (CASCADE), UNIQUE |
| mailbox_id | uuid | NULL | | FK → mailboxes.id (CASCADE) |
| client_id | uuid | NULL | | FK → clients.id |
| intent | text | NULL | | `inquiry`, `quote_request`, `order_confirm`, etc. |
| urgency | text | NULL | | `critical`, `high`, `medium`, `low` |
| sentiment | text | NULL | | `positive`, `neutral`, `negative`, `mixed` |
| sentiment_score | numeric | NULL | | -1.0 to 1.0 |
| summary | text | NULL | | AI-generated one-line summary |
| suggested_action | text | NULL | | |
| key_topics | text[] | NULL | | |
| confidence | numeric | NULL | | |
| justification | text | NULL | | AI's reasoning |
| action_type | text | NULL | | |
| business_signal | text | NULL | | `strong_positive`, `positive`, `neutral`, `negative` |
| thread_role | text | NULL | | `auto_reply`, `bounce`, etc. |
| competitors_mentioned | text[] | NULL | | |
| products_mentioned | text[] | NULL | | |
| budget_signals | jsonb | NULL | | |
| buying_signals | text[] | NULL | | |
| people_mentioned | jsonb | NULL | | |
| dates_mentioned | jsonb | NULL | | |
| action_items_extracted | text[] | NULL | | |
| has_budget_signal | bool | NULL | false | |
| has_buying_signal | bool | NULL | false | |
| has_competitor_mention | bool | NULL | false | |
| has_deadline | bool | NULL | false | |
| has_response_urgency | bool | NULL | false | AM-centric signal |
| business_signal_score | int4 | NULL | 0 | |
| action_buckets | jsonb | NULL | `[]` | Array of bucket assignments |
| primary_bucket | text | NULL | | `response_urgency`, `deal_at_risk`, etc. |
| human_feedback | text | NULL | | |
| feedback_field | text | NULL | | |
| human_override_intent | text | NULL | | |
| human_override_bucket | text | NULL | | |
| human_override_sentiment | text | NULL | | |
| feedback_note | text | NULL | | |
| feedback_at | timestamptz | NULL | | |
| feedback_by | uuid | NULL | | |
| customer_lifecycle_tier | text | NULL | | `prospect`, `new_customer`, `active_customer`, `at_risk`, `dormant`, `champion` |
| embedding | vector | NULL | | 768-dim HNSW index |
| extracted_references | jsonb | NULL | | QB ref extraction output |
| model_used | text | NULL | | `claude-3-haiku-20240307`, etc. |
| input_tokens | int4 | NULL | | |
| output_tokens | int4 | NULL | | |
| processing_time_ms | int4 | NULL | | |
| processing_status | text | NULL | `pending` | `pending`, `completed`, `failed` |
| processed_at | timestamptz | NULL | | |
| error_message | text | NULL | | |
| prompt_version | text | NULL | | |
| scoring_version | text | NULL | | |
| bucket_engine_version | text | NULL | | |
| raw_ai_response | jsonb | NULL | | |
| created_at | timestamptz | NULL | now() | |

**Scale:** 45,071 rows (99 MB) | **Notable indexes:** 21 indexes including HNSW on embedding

#### `ai_daily_digests`
Generated daily/weekly digest summaries.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| mailbox_id | uuid | NULL | | FK → mailboxes.id (CASCADE) |
| client_id | uuid | NULL | | FK → clients.id |
| digest_date | date | NOT NULL | | |
| digest_type | text | NOT NULL | `daily` | `daily`, `weekly` |
| summary | text | NOT NULL | | |
| action_items | jsonb | NULL | `[]` | |
| highlights | jsonb | NULL | `[]` | |
| stats | jsonb | NULL | `{}` | |
| bucket_summary | jsonb | NULL | `{}` | |
| emails_analyzed | int4 | NULL | | |
| model_used | text | NULL | | |
| input_tokens/output_tokens | int4 | | | |
| prompt_version | text | NULL | | |
| raw_ai_response | jsonb | NULL | | |
| created_at | timestamptz | NULL | now() | |

**Unique:** (mailbox_id, digest_date, digest_type) | **Scale:** 27 rows

#### `ai_strategic_digests`
Executive-level strategic digests generated by LangGraph ReAct agent.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| client_id | uuid | NULL | | FK → clients.id |
| digest_date | date | NOT NULL | | |
| period_type | text | NOT NULL | | `weekly`, `monthly` |
| period_start/period_end | date | | | |
| comparison_period_start/end | date | | | |
| executive_summary | text | NULL | | |
| relationship_health | jsonb | NULL | `[]` | |
| pipeline_intelligence | jsonb | NULL | `{}` | |
| risk_alerts | jsonb | NULL | `[]` | |
| opportunities | jsonb | NULL | `[]` | |
| competitive_landscape | jsonb | NULL | `{}` | |
| am_performance | jsonb | NULL | `{}` | |
| action_items | jsonb | NULL | `[]` | |
| companies_analyzed/contacts_analyzed/emails_analyzed/qb_orders_included/qb_quotes_included | int4 | | 0 | |
| model_used | text | NULL | | |
| total_input_tokens/total_output_tokens | int4 | | 0 | |
| total_cost_usd | numeric | NULL | 0 | |
| chain_steps_completed | int4 | NULL | 0 | |
| prompt_version | text | NULL | `v1.0` | |
| raw_ai_responses | jsonb | NULL | | |
| generation_time_ms | int4 | NULL | 0 | |
| created_at | timestamptz | NULL | now() | |

**Unique:** (client_id, digest_date, period_type) | **Scale:** 4 rows

#### `ai_prompt_config`
Configurable AI prompt templates — global + per-client overrides.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| client_id | uuid | NULL | | FK → clients.id (CASCADE); NULL = global |
| prompt_key | text | NOT NULL | | e.g., `email_classification`, `digest_generation` |
| prompt_text | text | NOT NULL | | Full prompt template |
| description | text | NULL | | |
| is_active | bool | NOT NULL | true | |
| version | text | NOT NULL | `v1.0` | |
| created_at/updated_at | timestamptz | | now() | |

**Unique:** (client_id, prompt_key); global: prompt_key WHERE client_id IS NULL | **Scale:** 23 rows

#### `ai_usage_log`
Token usage and cost tracking for all AI API calls.

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| operation | text | NOT NULL | | `email_classification`, `digest`, etc. |
| model | text | NOT NULL | | |
| mailbox_id | uuid | NULL | | FK → mailboxes.id |
| client_id | uuid | NULL | | FK → clients.id |
| input_tokens | int4 | NOT NULL | | |
| output_tokens | int4 | NOT NULL | | |
| estimated_cost_usd | numeric | NULL | | |
| processing_time_ms | int4 | NULL | | |
| batch_size | int4 | NULL | 1 | |
| error_type | text | NULL | | |
| error_detail | text | NULL | | |
| retry_count | int4 | NULL | 0 | |
| success | bool | NULL | true | |
| prompt_version | text | NULL | | |
| created_at | timestamptz | NULL | now() | |

**Scale:** 4,400 rows

#### `ai_business_entities`
Named entities extracted by AI from emails (companies, products, competitors).

| Column | Type | Nullable | Default |
|--------|------|----------|---------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| client_id | uuid | NULL | | FK → clients.id (CASCADE) |
| mailbox_id | uuid | NULL | | FK → mailboxes.id (CASCADE) |
| entity_type | text | NOT NULL | | `company`, `product`, `competitor` |
| entity_name | text | NOT NULL | | |
| normalized_name | text | NOT NULL | | |
| mention_count | int4 | NULL | 1 | |
| first_seen_at/last_seen_at | timestamptz | | | |
| associated_company_ids | uuid[] | NULL | | |
| context_snippets | jsonb | NULL | `[]` | |
| created_at/updated_at | timestamptz | | now() | |

**Unique:** (client_id, entity_type, normalized_name) | **Scale:** 1,027 rows

#### `ai_relationship_summaries`
AI-generated relationship summaries per company. **Scale:** 0 rows (available but unused).

---

### 2.5 QuickBase Cache

All QB tables follow a common pattern: `client_id` (FK → clients), `qb_record_id` (QB primary key), `matched_company_id` or `matched_contact_id` (FK to platform entity), `synced_at`, `created_at`.

#### `qb_customers` — 15,140 rows (11 MB)
QB customer master data with financial metrics and matching.

Key columns: `customer_name`, `customer_code`, `customer_key_id`, `customer_tier`, `customer_status`, `account_manager`, `industry`, `active`, `total_invoiced`, `invoiced_ty`, `invoiced_ly`, `invoiced_l90d`, `invoiced_l12m`, `recency_days`, `cadence_score`, `growth_90d`, `days_since_last_invoice`, `matched_company_id`.

**Unique:** (client_id, qb_record_id), (client_id, matched_company_id) WHERE matched_company_id IS NOT NULL — enforces 1:1 QB-to-SB company matching

#### `qb_contacts` — 29,726 rows (15 MB)
QB contact records with quote metrics.

Key columns: `qb_customer_id`, `first_name`, `surname`, `email`, `phone`, `active`, `contact_recency_days`, `quotes_accepted_count`, `most_recent_quote_date`, `matched_contact_id`.

**Unique:** (client_id, qb_record_id)

#### `qb_quotes` — 148,071 rows (61 MB)
Quote records from QB.

Key columns: `qb_customer_id`, `quote_no`, `quote_am_name`, `sell_ex_tax`, `date_created`, `date_accepted`, `category`, `contact_email`, `contact_name`, `job_no`, `has_job`, `quantity`, `kinds`, `total_quantity`, `matched_company_id`, `embedding` (vector(768)), `embedding_model`, `embedded_at`.

**Unique:** (client_id, qb_record_id)

#### `qb_jobs` — 70,262 rows (26 MB)
Job records from QB.

Key columns: `qb_customer_id`, `job_no`, `quote_no`, `job_status`, `retail_sale`, `invoiced_margin`, `margin_pct`, `accepted_date`, `due_date`, `factory_rush_level`, `pieces_ordered`, `kinds_ordered`, `total_qty_ordered`, `has_hot_foil`/`has_spot_uv`/`has_special_substrate`/`has_digital_foil`/`has_de_emboss`/`has_raised_ink`/`has_laser_cut`/`has_white_ink` (8 embellishment flags), `matched_company_id`.

**Unique:** (client_id, qb_record_id)

#### `qb_operations` — 630,707 rows (~855 MB total incl. indexes)
Largest QB table — individual production operations per job.

Key columns: `operation_id`, `qb_customer_id`, `job_no`, `quote_no`, `operation_name`, `machine`, `department`, `finishing_type`, `job_title`, `date_accepted`, `date_due`, `customer_name`, `customer_code`, `am_job`, `am_customer`, `quantity`, `production_status`, `cost_price`, `cost_plus_price`, `profit_amount`, `profit_pct`, `capability_tags` (jsonb), `has_coating`, `has_sewing`, `has_outsource_component`, `am_rush`, `factory_rush`, `row_type`, `embedding` (vector(768)), `embedding_model`, `embedded_at`, `qb_process_tag`, `qb_capability_tag`, `qb_machine_tier_tag`, `qb_row_type_tag`, `qb_blank_reason_tag`, `qb_embellishment_tag`, `contact_email`, `matched_company_id`.

**Unique:** (client_id, qb_record_id)

**Sync notes:**
- **`T-Cancelled` prefilter:** `sync_operations` drops every QB record whose `production_status = 'T-Cancelled'` (client-side page filter). QB holds 683,366 operations; 53,043 are `T-Cancelled`, leaving 630,323 cached. A cache count below the raw QB total is therefore expected by design, not a sync gap.
- **`profit_pct` is unbounded `NUMERIC`** (migration 119). QB computes Profit % as an astronomically large value when cost approaches zero (e.g. ~5,000,000% for a $500 sale at $0.01 cost), which overflowed the prior `DECIMAL(8,2)` and silently dropped upsert batches. The column is display-only (never aggregated), so it carries no precision cap. Earlier history: `DECIMAL(5,2)` → `DECIMAL(8,2)` (migration 036) → `NUMERIC` (migration 119).
- **Reliable pagination:** the streamed QB sync sorts by Record ID# (field 3) ascending so skip/top paging over ~680 pages can't skip or double-fetch records as the table changes mid-sync; transient QB 5xx are retried with capped backoff (~61s/page tolerance).

#### `qb_sales_line_items` — 79,900 rows (38 MB)
Invoice line items from QB.

Key columns: `qb_customer_id`, `invoice_id`, `invoice_no`, `job_no`, `job_am_name`, `customer_name`, `inv_date`, `subtotal`, `total`, `product_group`, `industry`, `job_title`, `matched_company_id`.

**Unique:** (client_id, qb_record_id)

#### `qb_unique_emails` — 22,600 rows (12 MB)
QB's "Unique Emails" table — email-first matching source for contact linking.

Key columns: `email`, `qb_customer_id`, `customer_name`, `first_name`, `last_name`, `hide`, `quality`, `result`, `free`, `email_invalid`, `customer_type`, `customer_id_text`, `embellishments_used`, `processes_used`, `capabilities_used`.

**Unique:** (client_id, qb_record_id) and (client_id, lower(email))

#### `qb_sync_config` — 1 row
Per-client QuickBase connection configuration.

Key columns: `realm_hostname`, `app_id`, `user_token_encrypted`, table IDs for customers/contacts/quotes/jobs/sales_line_items/operations/unique_emails/audit_logs, `field_mappings`, `sync_interval_hours`, `last_sync_at`, `is_active`.

**Unique:** client_id

#### `qb_sync_log` — 249 rows
Audit log of QB sync operations.

#### `qb_field_definitions` — 532 rows
Cached QB field metadata per table.

#### `qb_match_candidates` — 467 rows
Fuzzy match candidates for human review.

#### `qb_job_status_log` — 162 rows
Tracks QB job status changes over time.

---

### 2.6 Analytics & Metrics

#### `metric_history` — 792,033 rows (204 MB)
Time-series engagement score snapshots for contacts and companies.

Key columns: `entity_id`, `entity_type` (`contact`/`company`), `client_id`, `engagement_score`, `scoring_version`, component scores (`response_time_score`, `thread_completeness_score`, `initiation_balance_score`, `reply_rate_score`, `frequency_score`, `recency_score`, `decision_maker_bonus`, `seniority_bonus`), `emails_per_month_avg`, `avg_response_time_seconds`, `reply_rate`, `calculated_at`.

#### `relationship_context_cache` — 11,044 rows (19 MB)
Pre-computed relationship context per company for digest generation and profile pages.

Key columns: `client_id`, `company_id`, `customer_type`, `customer_tier`, `account_manager`, `engagement_trajectory`, `engagement_scores_history` (jsonb), `communication_health` (jsonb), `key_contacts` (jsonb), `active_threads_summary` (jsonb), `ai_signals_summary` (jsonb), `qb_financial_summary` (jsonb), `lifecycle_tier`, `primary_mailbox_id`, `am_user_id`, `am_name`, `computed_at`.

**Unique:** (client_id, company_id)

#### `am_performance_snapshots` — 0 rows
Account manager performance metrics over time periods. Schema ready, not yet populated.

#### `product_affinities` — 0 rows
Market basket analysis: which products are frequently ordered together. Schema ready, not yet populated.

#### `client_taxonomy_config` — 6 rows
Client-specific capability/process taxonomy configuration.

---

### 2.7 Infrastructure

#### `processing_jobs` — 20,432 rows (10 MB)
Central job queue for all background work (sync, extraction, AI analysis, reembedding, QB sync).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | uuid_generate_v4() | PK |
| job_type | text | NOT NULL | | `email_pipeline`, `ai_analysis`, `qb_sync_scheduled`, `reembed`, etc. |
| mailbox_id | uuid | NULL | | FK → mailboxes.id |
| client_id | uuid | NULL | | FK → clients.id |
| status | text | NOT NULL | | `pending`, `running`, `completed`, `failed`, `interrupted` |
| total_records | int4 | NULL | | |
| processed_records | int4 | NULL | 0 | |
| failed_records | int4 | NULL | 0 | |
| filtered_records | int4 | NULL | 0 | |
| error_log | jsonb | NULL | | |
| error_summary | jsonb | NULL | | |
| parameters | jsonb | NOT NULL | `{}` | Job-specific config |
| current_stage | text | NULL | | |
| started_at | timestamptz | NULL | | |
| completed_at | timestamptz | NULL | | |
| filter_start_date/filter_end_date | timestamptz | | | |
| last_heartbeat_at | timestamptz | NULL | | Worker heartbeat |
| worker_id | text | NULL | | |
| lease_expires_at | timestamptz | NULL | | `claim_next_job` sets this |
| attempts | int4 | NOT NULL | 0 | |
| max_attempts | int4 | NOT NULL | 1 | |
| scheduled_for | timestamptz | NULL | now() | |
| triggered_by | text | NULL | | |
| created_at | timestamptz | NULL | now() | |

**Dedup constraints:** One active email_pipeline per mailbox, one active ai_analysis per mailbox, one active qb_sync globally, one active reembed per client (enforced via partial unique indexes).

#### `extraction_jobs` — 3,188 rows
Detailed extraction pipeline progress tracking (13-step progress).

Key columns: `mailbox_id`, `client_id`, `job_id` (FK → processing_jobs), `status`, `total_emails`, `processed_emails`, `contacts_created`, `contacts_updated`, `companies_created`, `companies_updated`, `rules_created`, `emails_linked`, `threads_analyzed`, `current_step`, `current_step_number`, `total_steps` (13), `errors`, `extraction_mode` (`full`/`lightweight`), `emails_in_scope`, `date_range_start`, `date_range_end`.

#### `events` — 209 rows
Platform events for the notification system.

Key columns: `event_type`, `client_id`, `source_type`, `source_id`, `payload` (jsonb), `dispatched_at`, `created_at`.

#### `notifications` — ~10 rows
User-facing notifications dispatched from events.

Key columns: `event_id` (FK → events.id), `recipient_user_id`, `channel` (`in_app`), `status` (`pending`, `delivered`, `read`), `title`, `body`, `payload`, `delivered_at`, `read_at`.

#### `job_errors` — 8 rows
Structured error tracking for processing jobs.

#### `audit_log` — 440 rows
User action audit trail.

#### `system_settings` — 14 rows
Key-value configuration store with optional client scoping.

**Unique:** (key, client_id); (key) WHERE client_id IS NULL for globals.

#### `app_config` — 2 rows
Application-level configuration. **Unique:** config_key.

#### `user_integrations` — 2 rows
User-level OAuth tokens for Gmail/Outlook (separate from mailbox-level tokens).

---

### 2.8 Supplementary / Legacy Tables

| Table | Rows | Notes |
|-------|------|-------|
| `email_enrichment` | 0 | Schema for future email-level enrichment (tone, sentiment) — unused |
| `gmail_filters` | 0 | Imported Gmail filter rules |
| `outlook_rules` | 72 | Imported Outlook rules |
| `unified_email_rules` | 0 | Unified cross-provider rule representation |
| `downloaded_files` | 2 | Google Drive download cache |
| `thread_merges` | 0 | Track merged thread IDs |
| `sprint2_cleanup_log` | 4 | Historical cleanup log |

---

### 2.9 Thread-to-QuickBase Links

#### `thread_qb_links` — 117 rows
Links email threads to QB records (quotes, jobs, operations) via two extraction sources.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | uuid | NOT NULL | gen_random_uuid() | PK |
| client_id | uuid | NOT NULL | | FK → clients.id |
| canonical_thread_id | text | NOT NULL | | |
| link_type | text | NOT NULL | | `quote`, `job`, `operation` |
| qb_record_id | text | NOT NULL | | |
| qb_reference | text | NULL | | Human-readable ref (e.g., "Q12345") |
| confidence | float8 | NULL | 1.0 | 1.0 = regex, 0.9 = AI |
| source | text | NOT NULL | | `regex`, `ai_extraction`, `manual` |
| verified | bool | NULL | false | |
| created_at | timestamptz | NULL | now() | |

**Unique:** (client_id, canonical_thread_id, link_type, qb_record_id)

---

## 3. Views

### Regular Views (11)

All regular views have `security_invoker = on` (migration 104) so they run as the calling user and respect RLS on base tables.

| View | Purpose |
|------|---------|
| `contact_persona` | Composite contact profile joining contacts + quote metrics + email metrics + company data. Includes `contact_type` column; 8 persona classifications (champion, active_buyer, active_relationship, warm_lead, prospect, inactive_buyer, dormant, shared_mailbox). Used by contact profile pages and contacts list. |
| `contact_quote_metrics` | Per-contact QB quote/job aggregates: quote count, strike rate, total value, avg margin |
| `company_contact_summary` | Per-company contact rollup: person contacts, champions, warm leads, avg engagement (person-only), avg strike rate |
| `contact_deal_activity` | Per-contact thread-to-QB link activity: linked threads, quotes, jobs, pipeline value |
| `industry_benchmarks` | Industry-level benchmarks: avg strike rate, avg quote value, engagement (person contacts only, ≥3 per industry) |
| `customer_engagement_summary` | Company engagement overview joining companies and clients |
| `customer_industry_segments` | Industry segment rollup with revenue and activity counts |
| `daily_email_volume` | Daily email volume by mailbox |
| `folder_stats` | Per-folder email counts and date ranges |
| `thread_stats` | Thread-level stats: message count, participants, date range |
| `top_correspondents` | Most active email senders by volume |

### Materialized View (1)

| View | Rows | Size | Purpose |
|------|------|------|---------|
| `contact_email_metrics` | 17,072 | 3 MB | Pre-computed email engagement metrics per contact (total/inbound/outbound, threads, response times, velocity 30d/90d). Refreshed via `refresh_contact_email_metrics()` RPC. |

---

## 4. RPC Functions

Application-level RPC functions exposed via PostgREST. Excludes pgvector internal functions.

### 4.1 Search & Retrieval

| Function | Arguments | Returns | Notes |
|----------|-----------|---------|-------|
| `search_emails` | query_embedding vector, threshold, count, client_id, date_from, date_to | TABLE(id, subject, sender, sent_date, similarity) | Vector cosine similarity search |
| `search_emails` | search_query text, limit_count | TABLE(id, subject, ..., rank) | Full-text tsvector search (overloaded) |
| `keyword_search_emails` | p_query text, client_id, date_from, date_to, limit | TABLE(id, subject, ..., rank_score) | BM25 keyword search |
| `search_companies` | query_embedding, threshold, count, client_id, date_from, date_to | TABLE(id, name, industry, similarity) | Vector search on companies |
| `search_operations` | query_embedding, threshold, count, client_id | TABLE(id, operation_name, department, similarity) | Vector search on operations |
| `find_customer_by_domain` | p_email text, p_client_id | TABLE(company_id, company_name, client_id) | STABLE; domain-based company lookup |
| `emails_body_left` | email_ids uuid[], n int | TABLE(id uuid, body text) | SECURITY DEFINER, search_path=public. Returns `LEFT(body_text, n)`; clamps n (reject negative, cap 50000). Egress: SQL-side truncation for previews/context (migration 116) |
| `emails_body_right` | email_ids uuid[], n int | TABLE(id uuid, body text) | SECURITY DEFINER, search_path=public. Returns `RIGHT(body_text, n)`; clamps n (reject negative, cap 50000). Egress: SQL-side signature-tail fetch (migration 116) |

### 4.2 Batch Update RPCs (Performance-Critical)

These replace row-by-row updates with single-statement bulk operations, reducing Supabase connection pressure.

| Function | Arguments | Notes |
|----------|-----------|-------|
| `batch_update_embeddings_emails` | p_ids uuid[], p_embeddings vector[], p_embedding_model text, p_embedded_at timestamptz | SECURITY DEFINER, 30s timeout |
| `batch_update_embeddings_companies` | p_ids uuid[], p_embeddings vector[], p_embedding_model text, p_embedded_at timestamptz | SECURITY DEFINER, 30s timeout |
| `batch_update_embeddings_operations` | p_ids uuid[], p_embeddings vector[], p_embedding_model text, p_embedded_at timestamptz | SECURITY DEFINER, 30s timeout |
| `batch_update_embeddings_quotes` | p_ids uuid[], p_embeddings vector[], p_embedding_model text, p_embedded_at timestamptz | SECURITY DEFINER, 30s timeout |
| `batch_update_classifications` | p_ids, p_capability_tags, p_has_coating, p_has_sewing, ... | QB operation classification tags |
| `batch_update_canonical_threads` | p_updates jsonb | Thread ID resolution results |
| `batch_update_company_analytics` | updates jsonb | Engagement scores, thread counts |
| `batch_update_contact_analytics` | updates jsonb | Contact engagement metrics |
| `batch_update_contact_companies` | updates jsonb | Contact-company linking |
| `batch_update_contact_roles` | updates jsonb | Role classification results |
| `batch_update_qb_capabilities` | p_updates jsonb | QB capability tag updates |
| `batch_update_qb_contact_emails` | p_updates jsonb | QB contact email updates |
| `batch_write_qb_matches` | p_client_id, p_matches jsonb, p_now | Write company matches with DISTINCT ON dedup + NOT EXISTS 1:1 guard |
| `batch_propagate_qb_data` | p_client_id, p_data jsonb | Push QB financial data to companies |
| `batch_propagate_qb_data_to_contacts` | p_client_id | 3-pass: (1) qb_unique_emails by email, (2) qb_contacts by FK, (3) inherit company qb_type/tier |

### 4.3 Analytics & Engagement RPCs

| Function | Purpose |
|----------|---------|
| `calculate_all_contact_response_times(p_client_id)` | Returns TABLE(contact_id, avg_response_time, their_avg_response_time) |
| `calculate_all_contact_reply_rates(p_client_id)` | Returns TABLE(contact_id, reply_rate) |
| `calculate_all_contact_initiation_ratios(p_client_id)` | Returns TABLE(contact_id, ratios) |
| `calculate_all_contact_comm_patterns(p_client_id)` | Returns TABLE(contact_id, email counts, frequency, dates) |
| `calculate_all_contact_thread_counts(p_client_id)` | Returns TABLE(contact_id, open/dropped counts) |
| `calculate_all_company_thread_counts(p_client_id)` | Returns TABLE(company_id, open/dropped counts) |
| `update_company_engagement_metrics(p_company_id)` | Recalculate single company engagement |
| `update_contact_engagement_metrics(p_contact_id)` | Recalculate single contact engagement |
| `update_customer_engagement(p_customer_company_id)` | Legacy engagement update |
| `update_company_email_counts_from_junction(p_client_id)` | Recount from email_contact_links; SECURITY DEFINER, 30s timeout |
| `update_contact_email_counts_from_junction(p_client_id)` | Recount from email_contact_links + set first/last_contacted_at from email dates; SECURITY DEFINER, 30s timeout |
| `refresh_contact_email_metrics()` | Refresh materialized view; SECURITY DEFINER |

### 4.4 Seasonality & Outreach

| Function | Purpose |
|----------|---------|
| `get_company_seasonality(p_company_id, p_client_id)` | Multi-year monthly analysis from QB operations |
| `get_industry_seasonality(p_industry, p_client_id)` | Industry-wide seasonal patterns |
| `get_outreach_windows(p_client_id, p_weeks_ahead)` | Recommended outreach timing based on seasonal data |

### 4.5 Data Health & Monitoring

| Function | Purpose | Auth |
|----------|---------|------|
| `get_db_table_stats()` | Table sizes, row counts | SECURITY DEFINER |
| `get_db_index_stats()` | Index sizes, scan counts | SECURITY DEFINER |
| `get_db_cache_stats()` | Buffer cache hit rates | SECURITY DEFINER |
| `get_db_slow_queries(p_limit)` | Slow query log from pg_stat_statements | SECURITY DEFINER |
| `get_vector_stats(p_client_id)` | Embedding coverage percentages | |
| `get_classification_health(p_client_id)` | AI classification completion rates; 60s timeout | |
| `get_thread_health(p_client_id)` | Thread deduplication health metrics | |
| `get_monitoring_stats(p_client_id)` | Overall system health dashboard | |
| `reset_db_stats()` | Reset pg_stat_statements; SECURITY DEFINER | |

### 4.6 Worker Infrastructure

| Function | Purpose |
|----------|---------|
| `claim_next_job(p_worker_id)` | SELECT FOR UPDATE SKIP LOCKED — claims oldest pending job |
| `heartbeat_job(p_job_id, p_worker_id)` | Extend lease by 5 minutes |
| `reconcile_stuck_jobs()` | Mark expired-lease running jobs as `interrupted` |
| `increment_job_progress(p_job_id, p_delta_processed, p_delta_failed, p_stage)` | Atomic progress update |

### 4.7 Auth & Access

| Function | Purpose | Auth |
|----------|---------|------|
| `user_has_role(p_user_id, p_role)` | Check if user has specific role | SECURITY DEFINER |
| `get_user_accessible_mailboxes(p_user_id)` | Get mailbox IDs user can access (admin=all, manager=client's, AM=own) | SECURITY DEFINER |
| `handle_new_user()` | TRIGGER: auto-create user_profiles row on auth.users insert | SECURITY DEFINER, search_path=public |

### 4.8 QB Matching

| Function | Purpose |
|----------|---------|
| `promote_accepted_matches(p_client_id)` | Move reviewed+accepted fuzzy matches to confirmed company links |
| `link_emails_by_domain(p_client_id, p_domain, p_company_id)` | Bulk-link emails to a company by sender domain |
| `backfill_contacts_to_matched_companies(p_client_id)` | 3-pass: link contacts via QB email chain, backfill emails.customer_company_id, backfill email_contact_links.company_id; SECURITY DEFINER, 120s timeout |
| `_enforce_1to1_matches(p_client_id)` | Cleanup: keep highest-revenue QB customer per company, unmatch the rest |

### 4.9 Utility & Admin

| Function | Purpose | Risk |
|----------|---------|------|
| `exec_sql(query text)` | Execute arbitrary SQL | **HIGH** — granted to authenticated role |
| `exec_sql_extended(p_query, p_timeout_s)` | Execute SQL with custom timeout | **HIGH** |
| `backfill_search_text(p_batch_size)` | Rebuild search_text tsvector in batches | |
| `backfill_search_text_by_ids(p_ids)` | Rebuild search_text for specific emails | |
| `clear_canonical_threads(p_mailbox_id, p_batch)` | Reset canonical thread resolution; SECURITY DEFINER, 300s timeout | |
| `get_dashboard_stats()` | Quick dashboard metrics | |
| `get_distinct_folders() / get_distinct_folders_for_mailbox()` | Folder listings | |
| `get_email_counts_by_mailbox()` | Per-mailbox email totals | |
| `get_failed_emails(p_mailbox_id, limit, offset)` | List failed email classifications | |
| `reset_failed_emails_for_retry(p_mailbox_id, p_max_attempts)` | Reset failed emails for reprocessing | |
| `get_spend_total(p_client_id, p_period)` | AI spend totals | |
| `get_usage_summary(p_client_id, p_days)` | AI usage breakdown | |
| `get_client_summary(p_client_id)` | Client data overview | |
| `get_job_error_summary / get_job_errors_summary(p_job_id)` | Error aggregates | |
| `get_job_errors_paginated(...)` | Paginated error list | |
| `get_domain_summary(p_mailbox_id, p_client_id)` | Domain-level email summary | |
| `get_unlinked_emails_count(p_mailbox_id)` | Count unlinked emails | |
| `update_folder_counts()` | Refresh folder message counts | |
| `upsert_customer_contact(...)` | Atomic contact insert/update | |

### 4.10 Trigger Functions

| Function | Used By |
|----------|---------|
| `update_updated_at_column()` | 10+ tables — auto-set updated_at on UPDATE |
| `emails_search_text_trigger()` | emails — auto-populate search_text tsvector on INSERT/UPDATE |
| `update_extraction_jobs_updated_at()` | extraction_jobs, thread_status, unified_email_rules |
| `trg_system_settings_updated_at()` | system_settings |
| `trg_system_settings_changelog()` | system_settings — audit log on INSERT/UPDATE/DELETE |
| `tsor_touch_updated_at()` | thread_status_override_rules |

---

## 5. Indexes — Key Patterns

### 5.1 Size Distribution

| Table | Index Count | Total Index Size | Notes |
|-------|------------|-----------------|-------|
| emails | 37+ | ~7.2 GB | Includes IVFFlat vector index, 304 MB body FTS, 170 MB search_text GIN |
| email_categories | 7 | 217 MB | 66 MB covering index |
| qb_operations | 14+ | 220 MB | 47 MB unique; no vector index (seq scan on small embedded subset) |
| email_contact_links | 6 | 95 MB | 42 MB unique |
| thread_status | 18 | 58 MB | 15 MB thread_id unique |
| customer_contacts | 17 | 22 MB | |
| customer_companies | 17+ | 16 MB | Includes HNSW vector index |
| ai_email_intelligence | 21 | 57 MB | |
| metric_history | 3 | 93 MB | |

### 5.2 Vector Indexes

| Index | Table | Type | Config | Notes |
|-------|-------|------|--------|-------|
| idx_emails_embedding | emails | IVFFlat | lists=500 | Large table; HNSW build fails on Supabase Pro |
| idx_companies_embedding | customer_companies | HNSW | m=16, ef_construction=64 | Small table; HNSW builds reliably |
| idx_email_intelligence_embedding | ai_email_intelligence | HNSW | m=16, ef_construction=64 | Small embedded subset |
| idx_emails_embedding_model | emails | btree | partial: WHERE embedding IS NOT NULL | Audit column lookup |
| idx_emails_extracted_at_null | emails | btree | partial: WHERE extracted_at IS NULL | Fast lookup of unextracted emails for incremental extraction |
| idx_qb_operations_embedding_model | qb_operations | btree | partial: WHERE embedding IS NOT NULL | Audit column lookup |
| idx_customer_companies_embedding_model | customer_companies | btree | partial: WHERE embedding IS NOT NULL | Audit column lookup |
| idx_qb_quotes_embedding_model | qb_quotes | btree | partial: WHERE embedding IS NOT NULL | Audit column lookup |

**No vector index on `qb_operations` or `qb_quotes`:** The embedded subset is small enough that sequential scan is acceptable. Build an IVFFlat index when the embedded row count exceeds ~10K.

### 5.3 Full-Text Search Indexes (GIN)

| Index | Table | Size | Expression |
|-------|-------|------|------------|
| idx_emails_search_text | emails | 170 MB | `search_text` WHERE NOT NULL |
| idx_emails_body_fts | emails | 304 MB | `to_tsvector('english', body_text)` |
| idx_emails_subject_fts | emails | 19 MB | `to_tsvector('english', subject)` |

### 5.4 Index Policy

Per `docs/database/INDEX_POLICY.md`:
- **Two-Signal Drop Rule:** Remove only if code audit confirms no usage AND pg_stat zero scans for 30+ days
- **Naming:** `idx_{table}_{purpose}` for single-column, `idx_{table}_{col1}_{col2}` for composite
- **Partial indexes** preferred for boolean flags and status filters
- **Monthly review** of index scan counts via `get_db_index_stats()`

### 5.5 Vector Embedding Architecture

Every table with a `vector(768)` column also carries two audit columns: `embedding_model TEXT` and `embedded_at TIMESTAMPTZ`. These are set at write time by `vector_service.py` and distinguish embeddings written by different providers or models. Future provider or dimension changes can target stale rows via the partial index on `embedding_model WHERE embedding IS NOT NULL`, instead of bulk null-and-re-embed.

**Tables with embeddings:**

| Table | Coverage | Index | Search behavior |
|-------|----------|-------|-----------------|
| emails | Full (rows passing quality gate) | IVFFlat (lists=500) | Indexed search; requires `ivfflat.probes` ≥ 10 for usable recall (see §5.6) |
| customer_companies | Full (rows passing quality gate) | HNSW (m=16, ef=64) | Indexed search; no runtime tuning needed |
| qb_operations | Partial; auto-trigger via QB sync, capped per run | None | Sequential scan over the embedded subset; acceptable at current scale |
| qb_quotes | Filtered; `matched_company_id IS NOT NULL` only | None | No vectors yet; column exists but is unpopulated |

**Source of truth for embedding provider:** `EMBEDDING_PROVIDER` env var. The AI config page displays the current provider read-only; no UI dropdown writes to `system_settings`. Changing the provider invalidates all existing vectors and requires a full re-embed.

**Composition functions** (all in `vector_service.py`):

| Function | Fields Composed |
|----------|----------------|
| `_build_email_embed_text` | subject + sender + outbound direction + body[:1000] |
| `_build_company_embed_text` | company_name + industry + domains + tier + customer_type + revenue + AM |
| `_build_operation_embed_text` | operation_name + dept + machine + customer + capability/process/technology/type/embellishment/finishing tags |
| `_build_quote_embed_text` | category (when present) + customer_name + AM + contact + qty + value + industry + tier (via join to matched company) |

**Quality gate:**
- `MIN_EMBED_TEXT_LEN = 20` across all embed methods. Rows below the gate are skipped, not failed — visible as `embedded < total` in verification queries.
- `qb_quotes` additionally requires `matched_company_id IS NOT NULL` pre-filter. Unmatched quotes compose to thin customer-identity-only vectors with no semantic value.

### 5.6 Index Choice Rationale

**IVFFlat for tables above ~50K vectors.** HNSW build on Supabase Pro fails at the disk-spill phase with `hnsw graph no longer fits into maintenance_work_mem`. The managed environment's I/O bandwidth cannot sustain the HNSW disk phase to completion above this threshold. IVFFlat builds in a single pass with no disk-spill phase, completes in minutes, and is the operationally viable choice.

**IVFFlat parameters:** `lists ≈ sqrt(row_count)` rounded to nearest 100.

**HNSW parameters:** `m=16, ef_construction=64`. Used only on small tables (e.g. `customer_companies`) where the build completes reliably.

**Runtime tuning:**
- `ivfflat.probes = 10` set at database level: `ALTER DATABASE postgres SET ivfflat.probes = 10;`
- Default probes=1 yields ~10–15% recall; probes=10 yields ~90–95% recall on lists=500.
- Trade-off: higher probes = more lists scanned per query = higher latency for higher recall.

### 5.7 Index Build Operations

Index builds on vector columns require a direct connection (DBeaver, port 5432) with autocommit enabled:

```sql
SET statement_timeout = 0;
SET maintenance_work_mem = '512MB';

-- Only one CREATE INDEX at a time. Concurrent builds cause contention.
CREATE INDEX idx_emails_embedding
  ON emails
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 500);
```

For HNSW on small tables:

```sql
SET statement_timeout = 0;
SET maintenance_work_mem = '256MB';

CREATE INDEX idx_companies_embedding
  ON customer_companies
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

### 5.8 Forbidden Vector Operations

- **Do not bulk UPDATE vector columns.** `UPDATE...SET embedding = NULL` on a large vector column hits `statement_timeout` due to MVCC dead-tuple cost (~6KB per row × N rows). Null-then-embed per small batch within the runner instead.
- **Do not run multiple CREATE INDEX statements concurrently** on the same database. Causes contention, inconsistent state, apparent freezes.
- **Do not change `EMBEDDING_PROVIDER` without a re-embed plan.** Existing vectors are model-specific; mixing providers in one column produces noise similarity scores even at matching dimensions.

---

## 6. Foreign Key Relationships

### Entity Relationship Summary

```
clients (tenant root)
  ├── mailboxes ──────── emails ──────── email_categories
  │                        │              email_contact_links
  │                        │              email_response_metrics
  │                        │              ai_email_intelligence
  │                        ├── folders
  │                        └── thread_status
  ├── customer_companies ── customer_contacts
  │     │                     └── email_contact_links
  │     ├── customer_intelligence_cache
  │     ├── customer_recommendations
  │     ├── relationship_context_cache
  │     └── qb_customers (matched_company_id)
  │          qb_quotes (matched_company_id)
  │          qb_jobs (matched_company_id)
  │          qb_operations (matched_company_id)
  │          qb_sales_line_items (matched_company_id)
  ├── qb_sync_config
  ├── ai_prompt_config
  ├── system_settings
  └── internal_domains

user_profiles
  ├── user_client_assignments
  ├── client_manager_assignments
  ├── mailboxes (user_id)
  └── am_performance_snapshots

processing_jobs
  ├── extraction_jobs (job_id)
  ├── job_errors
  └── downloaded_files (last_job_id)

events → notifications
thread_qb_links (references canonical_thread_id + qb_record_id)
```

### Cascade Rules

- **CASCADE on DELETE:** Most child tables cascade from `clients`, `mailboxes`, `emails`, `customer_companies`, `customer_contacts`
- **SET NULL on DELETE:** Cross-reference FKs (e.g., `emails.customer_company_id`, QB `matched_company_id`) set to NULL rather than cascade
- **NO ACTION:** `events.client_id`, `processing_jobs.client_id`, `thread_qb_links.client_id`

---

## 7. Triggers

| Timing | Event | Table | Function | Purpose |
|--------|-------|-------|----------|---------|
| BEFORE UPDATE | UPDATE | 10 tables | `update_updated_at_column()` | Auto-set updated_at timestamp |
| BEFORE INSERT | INSERT | emails | `emails_search_text_trigger()` | Auto-populate search_text tsvector |
| BEFORE UPDATE | UPDATE | emails | `emails_search_text_trigger()` | Keep search_text in sync |
| AFTER INSERT/UPDATE/DELETE | ALL | system_settings | `trg_system_settings_changelog()` | Audit log for settings changes |
| BEFORE UPDATE | UPDATE | system_settings | `trg_system_settings_updated_at()` | updated_at timestamp |
| BEFORE UPDATE | UPDATE | thread_status_override_rules | `tsor_touch_updated_at()` | updated_at timestamp |

**Note:** `handle_new_user()` is a trigger on `auth.users` (not in public schema triggers list) — auto-creates `user_profiles` row on signup.

---

## 8. Row-Level Security (RLS)

**RLS is enabled on ALL tables** (migration 102, applied May 2026). No table in the public schema is accessible via the anon key.

### Architecture

- **Backend** uses the `service_role` key → bypasses RLS entirely. All data queries go through the backend API.
- **Frontend** uses Supabase **exclusively for auth** (`supabase.auth.*`). Zero direct table access. The anon key is never used to read/write data.
- **Views and materialized views** cannot have RLS (Postgres limitation) but inherit protection from their RLS-enabled base tables. All regular views have `security_invoker = on` so they run as the calling user.

### Explicit RLS Policies

Most tables have RLS enabled with **no policies** — this means only the service role can access them. The following tables have explicit policies for authenticated users:

| Table | Policy | Command | Description |
|-------|--------|---------|-------------|
| user_profiles | user_profile_select_self | SELECT | Users can read their own profile |
| user_profiles | user_profile_update_self | UPDATE | Users can update their own profile |
| user_profiles | user_profile_admin_all | ALL | Admins have full access |
| user_client_assignments | user_client_select_self | SELECT | Users see own assignments |
| user_client_assignments | user_client_manager | SELECT | Client managers see their clients' assignments |
| user_client_assignments | user_client_admin | ALL | Admins have full access |
| client_manager_assignments | client_manager_assignments_admin | ALL | Admin full access |
| client_manager_assignments | client_manager_assignments_self | SELECT | Self-select |
| emails | email_access | ALL | Multi-tenant isolation |
| mailboxes | mailbox_access | ALL | Multi-tenant isolation |
| email_response_metrics | email_response_metrics_client_isolation | ALL | Client isolation |
| audit_log | Admins can read audit_log | SELECT | Admin read-only |
| audit_log | Service role full access on audit_log | ALL | Service role bypass |

### Views (UNRESTRICTED in Supabase dashboard — expected)

These show an "UNRESTRICTED" badge because Postgres cannot apply RLS to views/matviews. Data is protected because their base tables all have RLS enabled and all regular views have `security_invoker = on` (migration 104).

| View | Type | Base Tables |
|------|------|-------------|
| thread_stats | VIEW | thread_status |
| top_correspondents | VIEW | customer_contacts, emails |
| contact_persona | VIEW | customer_contacts, contact_quote_metrics, contact_email_metrics |
| contact_quote_metrics | VIEW | qb_quotes, qb_jobs, customer_contacts |
| contact_deal_activity | VIEW | qb_quotes, qb_jobs, customer_contacts |
| company_contact_summary | VIEW | customer_contacts, contact_persona |
| customer_engagement_summary | VIEW | customer_companies, emails |
| customer_industry_segments | VIEW | customer_companies, qb_customers |
| contact_email_metrics | MATVIEW | emails, email_contact_links, customer_contacts |

---

## 9. Extensions

| Extension | Version | Purpose |
|-----------|---------|---------|
| **vector** | 0.8.0 | pgvector — HNSW/IVFFlat indexes, vector similarity search |
| **pg_stat_statements** | 1.11 | Query performance monitoring (used by `get_db_slow_queries`) |
| **pgcrypto** | 1.3 | Cryptographic functions |
| **uuid-ossp** | 1.1 | UUID generation (`uuid_generate_v4()`) |
| **pg_graphql** | 1.5.11 | Supabase GraphQL layer |
| **supabase_vault** | 0.3.1 | Secrets management |
| **plpgsql** | 1.0 | PL/pgSQL procedural language |

---

## 10. Migration History

102 migrations in `scripts/migrations/` track the schema evolution:

| Range | Era | Key Changes |
|-------|-----|-------------|
| 001–016 | Sprint 1–2 Foundation | Error handling, business hierarchy, RBAC, user profiles, Gmail-to-mailbox migration |
| 021–034 | Sprint 2–3 Analytics & AI | QB enrichment, field definitions, sync logging, system settings, AI prompts, product intelligence |
| 035–057 | Sales Intelligence & Vector | pgvector + HNSW, batch RPCs, QB matching revamp, email contact links, canonical threads, hybrid search |
| 060–072 | Data Quality & IO Budget | Thread constraints, IO budget RPCs, data health RPCs, seasonality engine, bulk ops helpers |
| 073–093 | Worker Infrastructure & Polish | Processing job reembed, thread override rules, QB contact linking, worker infrastructure, events/notifications, contact persona views, deal activity |
| 094 | QB Propagation Guards | Pass 3 company→contact QB propagation with contact-type exclusions (`internal`, `shared`, `automated`, `mailing_list`) |
| 095–097 | Embedding & Contact Hardening | Internal/shared contact cleanup + QB tier nulling, embedding audit columns (`embedding_model`, `embedded_at`) on all vector tables, qb_quotes embedding support, batch RPC audit params |
| 098 | Extraction Scoping | `extracted_at` column on emails + partial index; incremental extraction skips already-processed emails |
| 100 | Contact Date Backfill | Updated `update_contact_email_counts_from_junction` RPC to also compute and set `first_contacted_at`/`last_contacted_at` from email dates |
| 101 | Persona Classification v2 | DROP+CREATE `contact_persona`, `company_contact_summary`, `industry_benchmarks` views. Champion rule: `accepted_quote_count >= 10 OR total_job_value >= 50000`. Added `contact_type` column. Non-person contacts → `shared_mailbox`. Split `active_relationship` → `active_buyer` + `warm_lead`. Person-only filtering on rollup views |
| 102 | RLS on All Tables | `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` on all 49 public tables. Resolves Supabase critical security alert. Views/matviews excluded (Postgres limitation — inherit protection from base tables) |
| 103 | AI Insights Prompt Update | Updated `insight_company` prompt in `ai_prompt_config` (all 3 rows: global + Newbound + Carbon8) to request `strategic_summary` field and clarify revenue framing as invoiced-to-customer |
| 104 | Security Definer Fixes | `security_invoker = on` on all 11 regular views; `SET search_path = public` on 10 SECURITY DEFINER functions missing it. Resolves all Supabase Advisor security warnings |
| 116 | Egress: body_text truncation RPCs | Added `emails_body_left(email_ids uuid[], n int)` and `emails_body_right(...)` — SECURITY DEFINER, search_path=public, clamped n. Pushes fetch-then-truncate to SQL at 4 callsites (role_classifier, analytics thread detail, ai_insights, ai_digest). Measured 91.2% egress reduction on role_classifier pass |

**Migration application method:** `scripts/db/_run_NNN_via_rest.py` → `exec_sql` RPC + `NOTIFY pgrst, 'reload schema'`; scripts are throwaway and deleted after verification.

**IMPORTANT — Table grants:** Supabase has announced that `ALTER DEFAULT PRIVILEGES` auto-granting `anon`/`authenticated`/`service_role` access on new `public` tables will be removed in a future update. All 55 existing tables already have full grants (verified May 2026 via `has_table_privilege()` audit). Every new `CREATE TABLE` migration must include explicit grants:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON <table_name> TO anon, authenticated, service_role;
```

Without this, the table will be invisible to the Data API (PostgREST). See also `BEST_PRACTICES.md` §1 "Migration patterns".

---

## 11. Known Issues & Technical Debt

### Security
- `exec_sql` and `exec_sql_extended` RPCs are granted to the `authenticated` role — any user with a valid JWT can execute arbitrary SQL. **Needs restriction to service role only.**
- QB API token stored in `qb_sync_config.user_token_encrypted` (column name suggests encryption but value handling should be verified)
- Some analytics endpoints accept `client_id` from frontend without verifying the user's client assignment (cross-tenant risk for non-admin roles)

### Schema
- `thread_status.thread_id` has two UNIQUE constraints (`thread_status_thread_id_key` + `uq_thread_status_thread_id`) — one is redundant
- `emails` table has 37 indexes totaling 7.2 GB (13.5× the 473 MB data size) — see `docs/database/ROOT_CAUSE.md` for analysis
- `email_categories` has redundant indexes: `email_id_category` unique constraint + separate `email_id_category` btree + `email_id` btree + `coverage` covering index — consolidation possible
- `mailboxes.last_sync_at` and `mailboxes.last_synced_at` are duplicate columns
- `account_managers` table is unused (0 rows) — legacy pre-RBAC

### Performance
- `metric_history` at 792K rows and growing — no retention policy
- `email_categories` at 607K rows with heavy indexing (291 MB) — consider partitioning
- Vector index rebuild on `emails` requires direct connection with `statement_timeout=0` and `maintenance_work_mem=512MB`; see §5.7

---

## 12. Quick Reference

### Table Sizes (Top 10)

| Table | Rows | Total Size | Data Size |
|-------|------|-----------|-----------|
| emails | 262,051 | 7.7 GB | 473 MB |
| qb_operations | 614,257 | 525 MB | 305 MB |
| email_categories | 607,485 | 291 MB | 74 MB |
| metric_history | 792,033 | 204 MB | 111 MB |
| email_contact_links | 458,211 | 173 MB | 78 MB |
| ai_email_intelligence | 45,071 | 99 MB | 42 MB |
| thread_status | 57,428 | 85 MB | 27 MB |
| qb_quotes | 148,071 | 61 MB | 36 MB |
| customer_contacts | 21,237 | 46 MB | 24 MB |
| customer_companies | 14,939 | 40 MB | 18 MB |

### Connection Patterns (from BEST_PRACTICES.md)
- Always paginate on tables >1,000 rows
- Batch updates: 25–100 rows via RPC, never individual rows
- Use `.in_()` with max 500 IDs per call
- ThreadPoolExecutor limited to 3 workers for Supabase connection safety
- Python-side filtering for NULL handling (not Supabase `.neq()`)

---

## 13. Recent Schema Changes

- **Migration 122 (2026-06-12) — contact response-time direction split.** Rewrote the contact-average rollup: `calculate_all_contact_response_times` (which returned rows and was silently PostgREST `db-max-rows`-capped at 1,000 of 21,655 contacts) replaced by `update_all_contact_response_times`, which performs the UPDATE server-side and returns only a count (no cap; 4,123 contacts updated). **Column-semantics change:** `avg_response_time_seconds` (our reply latency) and `their_avg_response_time` are now computed separately by `is_outbound`; previously both held the same undirected `AVG(response_time_seconds)`. Any consumer that read the two as interchangeable must be updated. `update_contact_averages()` in `response_time_tracker.py` now calls the single new RPC. Verified against the known-good Python `_calculate_contact_response_times` (717/946 sampled contacts show distinct our/their values). Note: extreme `their_*` magnitudes may warrant an outlier/staleness guard before use in comparisons.

---

*This is a living document. Update it when migrations are applied, RPC functions are added/changed, or schema-level decisions are made.*
