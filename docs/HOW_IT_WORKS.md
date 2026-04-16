# How It Works — Platform Feature Guide

A plain-language guide to every feature in the Email Intelligence Platform. For each feature: what it does, how data flows through it, what it depends on, and what depends on it.

---

## 1. Email Ingestion

**What it does:** Brings emails into the platform from multiple sources.

**Sources supported:**
- **File uploads** — MBOX, PST, OLM archives uploaded directly
- **Gmail** — OAuth connection, automatic sync every 15 minutes using Gmail's incremental history
- **Outlook** — OAuth connection, automatic sync using Microsoft Graph delta links
- **Google Drive** — Stream files directly from Drive without downloading first

**How it works:**
1. User connects a source (uploads a file or authorises an OAuth account)
2. A mailbox record is created to track the source
3. Emails are parsed from the raw format into a standard schema (subject, sender, recipients, body, dates, threading)
4. Parsed emails are inserted into the `emails` table
5. For live sources (Gmail/Outlook), a background sync runs periodically and fetches only new messages since the last sync

**Depends on:** Nothing — this is the entry point for all data.
**Feeds into:** Email Processing Pipeline, AI Analysis, Reference Extraction, Vector Embeddings.

---

## 2. Email Processing Pipeline (13-Step Extraction)

**What it does:** Takes raw emails and extracts business-relevant data: who are the contacts, which companies do they belong to, what are their roles, how engaged are they.

**The 13 steps in plain language:**
1. **Validate** — Confirm the mailbox exists and is accessible
2. **Extract contacts** — Parse sender/recipient/CC/BCC fields to find people
3. **Deduplicate** — Merge duplicate contacts (same email address appearing in multiple emails)
4. **Resolve companies** — Match email domains to company names (e.g., `@acme.com` → Acme Corp)
5. **Save contacts** — Insert or update contact records
6. **Save companies** — Insert or update company records
7. **Classify roles** — Analyse email signatures to determine job titles and seniority
8. **Update roles** — Store classified roles on contact records
9. **Link emails** — Connect each email back to its sender contact and company
10. **Score engagement** — Calculate an engagement score per company (email frequency, response times, seniority of contacts)
11. **Track threads** — Group related emails into conversations and track thread status
12. **Analyse patterns** — Compute communication trends (who initiates, reply rates, frequency)
13. **Complete** — Mark the job finished and report results

**Depends on:** Email Ingestion (needs raw emails in the database).
**Feeds into:** AI Analysis (provides contacts and companies as context), QB Matching (provides companies to match against QB records), Engagement Analytics.

---

## 3. QuickBase Sync

**What it does:** Imports CRM data from QuickBase — customers, contacts, quotes, jobs, operations, and sales line items — then matches them to platform-extracted companies.

**How it works:**
1. Admin configures QB API credentials and field mappings per client
2. Sync fetches 6 tables from QB: Customers, Contacts, Quotes, Jobs, Operations, Sales Line Items
3. Records are stored locally (qb_customers, qb_quotes, etc.) as a cache
4. **3-pass matching** links QB customers to platform companies:
   - **Pass 1 (Exact):** Company name matches exactly (case-insensitive)
   - **Pass 2 (Domain):** Email domain roots match (e.g., `acme.com` in both systems)
   - **Pass 3 (Fuzzy):** Token-sorted fuzzy name matching (>82% similarity) — flagged for manual review
5. Matched companies get enriched with QB data: customer type, revenue tier, days since last invoice, open quote count, growth percentage
6. Contact records also get enriched: QB contact role, quote count, capabilities used

**Depends on:** Email Processing Pipeline (needs companies to match against).
**Feeds into:** AI Analysis (QB context makes AI smarter), Action Signals (lifecycle tiers use QB data), Journey Tracking (quote/job references are validated against QB tables).

---

## 4. AI Email Analysis

**What it does:** Classifies every email with intent, urgency, sentiment, business signals, entities, and a suggested AM action.

**How it works:**
1. Emails are batched (20 per API call for cost efficiency)
2. Each batch is sent to Claude Haiku with:
   - The email content (subject + body, PII-filtered)
   - Business context from QB (customer type, tier, revenue, open quotes)
   - Thread history (prior messages in the conversation)
3. Claude returns structured JSON: intent, urgency, sentiment, business signal, entities (competitors, budgets, people mentioned), and a suggested action
4. Results are validated and stored in `ai_email_intelligence`
5. Results feed into the Action Bucket Engine (next feature)

**Key classifications:**
- **Intent:** action_required, question, complaint, pricing_inquiry, expansion_signal, churn_risk, etc.
- **Urgency:** critical, high, medium, low, none
- **Sentiment:** very_positive to very_negative (with numeric score)
- **Business signals:** buying_intent, renewal, competitive_evaluation, budget_discussion, escalation

**Depends on:** Email Ingestion (emails), QB Sync (business context enriches prompts).
**Feeds into:** Action Signals, Smart Inbox, Strategic Digest.

---

## 5. Action Signals (Bucket Engine)

**What it does:** Derives 6 actionable AM-centric signals from AI classifications + QB data. Pure logic — no additional AI calls.

**The 6 signals:**
1. **Response Urgency** — Inbound email needs a reply (high urgency + action required)
2. **Deal at Risk** — Quote open 30+ days + low engagement → follow up before it dies
3. **Retention Risk** — Customer was active, now gone quiet + declining engagement
4. **Revenue Opportunity** — Active customer with high engagement but no recent quote → propose something
5. **New Relationship** — First-time contact → qualify and introduce
6. **Account Neglect** — Customer emailing but AM hasn't replied in 14+ days

**How it works:**
- Takes each AI classification + engagement metrics + QB data
- Runs a deterministic decision tree (not AI — predictable, debuggable)
- Assigns 0-2 signals per email with confidence scores
- Computes a customer **lifecycle tier**: prospect, new_customer, active_customer, at_risk, dormant, champion

**Depends on:** AI Analysis (intent, urgency, sentiment), QB Sync (customer type, revenue, last invoice date), Engagement scores.
**Feeds into:** Smart Inbox page, Opportunities page, Strategic Digest.

---

## 6. Strategic Digest

**What it does:** Generates executive summaries (weekly/monthly) of AM performance, customer health, pipeline status, and deals at risk.

**How it works:**
1. **Context building** (deterministic):
   - Fetches top 20 companies by email volume for the period
   - Aggregates QB data: revenue, growth, quote pipeline, order history
   - Computes AM efficiency: response times, after-hours work, workload balance
   - Packages into a ~15K token context block

2. **Agent analysis** (AI with tools):
   - LangGraph ReAct agent receives the context
   - Can use tools to drill deeper: look up specific company details, read email threads, check quote status
   - Produces structured output: executive summary, relationship health per company, pipeline intel, AM efficiency insights, recommended actions

**Depends on:** Email Processing Pipeline, QB Sync, AI Analysis, Action Signals.
**Feeds into:** Strategic Digest page (frontend display).

---

## 7. Vector Embeddings & Semantic Search

**What it does:** Embeds emails, companies, and operations into vector space so users can search by meaning ("Who asked about bulk printing?") rather than exact keywords.

**How it works:**
1. Embedding text is constructed:
   - Emails: subject + body + sender name
   - Companies: name + industry + domains + QB tier
   - Operations: operation name + department + machine + capabilities
2. Text is sent to an embedding API (Google text-embedding-004 or OpenAI)
3. The returned 768-dimensional vector is stored alongside the record
4. Searches embed the query, then find the nearest neighbors using pgvector's HNSW index

**Depends on:** Email Ingestion, QB Sync (for company/operation data), an embedding API key.
**Feeds into:** Semantic search page, AI Chat Agent.

---

## 8. Background Job System

**What it does:** Runs long tasks (email uploads, AI analysis, QB sync, reference extraction) in the background so the app stays responsive.

**How it works:**
1. User triggers an action (e.g., "Analyse all emails")
2. API creates a `processing_jobs` record with status "pending"
3. **Single-flight protection:** if the same job type is already running for the same mailbox, it returns "already in progress" (no duplicates)
4. A **worker process** polls for pending jobs, claims one atomically (database lock prevents two workers grabbing the same job)
5. Worker executes the handler with:
   - **Heartbeat:** extends the lease every 30s so the system knows the worker is alive
   - **Progress tracking:** updates processed/failed record counts
   - **Cancellation check:** worker polls for stop requests
6. On completion/failure: status is updated, an event is emitted
7. A **stuck-job reconciler** runs every 10 minutes — if a worker dies mid-job, the expired lease is detected and the job is marked for retry

**Job lifecycle:**
```
pending → running (claimed by worker) → completed OR failed OR stopped
```

**Depends on:** Database (processing_jobs table), Supabase RPCs (claim_next_job, heartbeat_job).
**Feeds into:** Events/Notifications (job state changes emit events).

---

## 9. Events & Notifications

**What it does:** Delivers real-time alerts to users when things happen (jobs complete, action items detected, risks identified).

**How it works:**
1. System events (job started/completed/failed) are inserted into the `events` table
2. A **notification dispatcher** reads undispatched events, determines recipients (admins see everything, users see their assigned client's events), and creates `notification` records
3. Notifications are delivered via WebSocket push to connected browsers
4. Users see a bell icon with unread count in the header
5. Clicking opens a popover with notification titles, timestamps, and mark-read buttons

**Depends on:** Background Job System (emits events), WebSocket infrastructure.
**Feeds into:** Frontend notification bell (real-time display).

---

## 10. Journey Tracking (Thread-QB Linking)

**What it does:** Traces an email thread all the way through to its QuickBase quote, job, operations, and invoices — showing the complete customer journey from first email to final invoice.

**How it works:**
1. **Regex extraction:** Scans email subjects and bodies for QB reference patterns (Q20334, J460037, etc.)
2. **Validation:** Checks extracted references against actual QB records in the database
3. **Link creation:** Creates `thread_qb_links` records connecting a thread to a QB quote or job
4. **Journey API:** When viewing a thread's journey, the system follows the full chain:
   - Thread → linked quotes → linked jobs → operations on those jobs → sales line items (invoices) → job status log (timeline)
5. **Manual linking:** AMs can manually link a thread to a quote/job if the regex didn't catch it

**Depends on:** Email Ingestion (emails with thread IDs), QB Sync (quote and job records to validate against).
**Feeds into:** Journey view on thread/company detail pages.

---

## 11. Authentication & Access Control

**What it does:** Controls who can access what based on roles.

**Three roles:**
- **Admin** — Full access to all mailboxes, users, configuration, all clients
- **Client Manager** — Access to mailboxes of their assigned clients, can invite users
- **Account Manager** — Access to their own mailboxes only

**How it works:**
- Users log in via Supabase Auth (email/password, Google OAuth, or Microsoft OAuth)
- JWT tokens are verified on every API request
- Database has Row-Level Security (RLS) policies that enforce access at the data layer
- Frontend routes check roles and hide/show pages accordingly

---

## 12. Frontend Structure

**Pages grouped by purpose:**

| Section | Pages | Who uses it |
|---------|-------|-------------|
| **Dashboard** | Home with quick stats | Everyone |
| **Emails** | Browse emails by mailbox, search, filter | Everyone |
| **Customers** | Company list, company detail, contact list, contact detail, threads | Everyone |
| **Insights** | Smart Inbox, Daily Digest, Opportunities, Strategic Digest, Semantic Search, AI Agent, Email Rules | AMs + Managers |
| **Manage** | Processing jobs, errors, data health, response times, patterns, logs | Managers + Admins |
| **Admin** | Users, clients, QB config, QB data, AI usage, intelligence config, audit logs | Admins only |

---

## Data Flow Summary

```
Email Sources (Gmail/Outlook/Files)
    ↓
Email Ingestion → emails table
    ↓
13-Step Pipeline → contacts, companies, engagement scores
    ↓                    ↓
    ↓              QB Sync → qb_customers, qb_quotes, qb_jobs
    ↓                    ↓
    ↓              3-pass Matching → companies enriched with QB data
    ↓                    ↓
AI Analysis (Claude) → intent, urgency, sentiment, entities
    ↓
Action Signals (Python) → 6 AM-centric signals + lifecycle tiers
    ↓
Strategic Digest (LangGraph) → executive summaries
    ↓
Vector Embeddings (optional) → semantic search
    ↓
Reference Extraction → thread-QB links → journey tracking
    ↓
Background Jobs manage all long-running work
    ↓
Events → Notifications → WebSocket → real-time UI updates
```

---

## What Breaks If Something Changes

| If you change... | Check these downstream effects |
|-----------------|-------------------------------|
| Email parsing/schema | Pipeline steps 2-9, AI prompt templates, reference extractor patterns |
| Contact/company extraction | Engagement scoring, QB matching, AI context enrichment |
| QB field mappings | Company enrichment, AI context (customer_type, tier, revenue), lifecycle tiers, journey validation |
| AI classification output | Action bucket engine rules, digest context builder, Smart Inbox display |
| Thread ID logic | Reference extraction (needs canonical_thread_id), journey tracking, thread analytics |
| Job system (processing_jobs schema) | All job types, heartbeat/lease RPCs, stuck-job reconciler, progress tracking |
| WebSocket rooms | Notification delivery, job progress updates |
| Auth/roles | All protected endpoints, frontend route guards, RLS policies |

---

*Last updated: 2026-04-15*
