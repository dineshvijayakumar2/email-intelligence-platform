# Email Intelligence Platform - Stage 2 User Stories

## Sprint Overview

| Sprint | Theme | Duration | Value Delivered |
|--------|-------|----------|-----------------|
| Sprint 1 | Foundation | Weeks 1-3 | Secure multi-tenant system with real-time email sync |
| Sprint 2 | Intelligence | Weeks 4-6 | Automatic customer recognition and contact database |
| Sprint 3 | AI Layer | Weeks 7-9 | AI classification with trust mechanisms |

---

## 🏗️ Sprint 1: Foundation (Weeks 1-3)

**Sprint Goal:** Establish secure multi-tenant infrastructure with OAuth-based email synchronization

### Epic 1.1: Account Manager & Client Hierarchy

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S1-01 | As an **Admin**, I want to create Account Managers so that each AM can manage their assigned clients | - Admin can create/edit/deactivate Account Managers<br>- AM has email, name, status fields<br>- AM list view with search/filter | 3 |
| S1-02 | As an **Admin**, I want to assign Clients to Account Managers so that client data is properly segmented | - Admin can create Clients (Carbon8, EBNT, Wisk, etc.)<br>- Each Client linked to one Account Manager<br>- Client has name, industry, status fields | 3 |
| S1-03 | As an **Account Manager**, I want to see only my assigned clients so that I don't access other AMs' data | - AM dashboard shows only their clients<br>- API enforces tenant isolation<br>- Cannot query other AMs' client data | 5 |

### Epic 1.2: Role-Based Access Control

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S1-04 | As an **Admin**, I want to manage user roles so that access is properly controlled | - Three roles: Admin, Account Manager, Viewer<br>- Role assignment UI<br>- Role persists across sessions | 3 |
| S1-05 | As a **System**, I want to enforce row-level security so that users only see authorized data | - Database RLS policies on all tenant tables<br>- API validates user permissions<br>- Audit log for access attempts | 5 |
| S1-06 | As a **Viewer**, I want read-only access to my AM's clients so that I can view reports without editing | - Viewer can view emails, contacts, analytics<br>- Cannot create/edit/delete records<br>- Cannot connect mailboxes | 2 |

### Epic 1.3: Gmail OAuth Integration

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S1-07 | As an **Account Manager**, I want to connect my Gmail account so that emails sync automatically | - "Connect Gmail" button triggers OAuth flow<br>- User sees Google consent screen<br>- Successful auth stores refresh token | 5 |
| S1-08 | As the **System**, I want to import existing Gmail filters so that I understand how emails are organized | - Fetch filters via Gmail API<br>- Store filter rules in database<br>- Display imported filters in UI | 3 |
| S1-09 | As the **System**, I want to sync emails every 15 minutes so that new emails are captured automatically | - Background job polls Gmail API<br>- Processes only new emails (since last sync)<br>- Handles rate limits gracefully | 5 |
| S1-10 | As an **Account Manager**, I want to see sync status so that I know my mailbox is connected | - Dashboard shows last sync time<br>- Shows email count synced<br>- Shows error status if sync failed | 2 |

### Epic 1.4: Outlook OAuth Integration

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S1-11 | As an **Account Manager**, I want to connect my Outlook account so that emails sync automatically | - "Connect Outlook" button triggers OAuth flow<br>- User sees Microsoft consent screen<br>- Successful auth stores refresh token | 5 |
| S1-12 | As the **System**, I want to import existing Outlook rules so that I understand how emails are organized | - Fetch rules via Microsoft Graph API<br>- Store rules in database<br>- Display imported rules in UI | 3 |
| S1-13 | As the **System**, I want to handle token expiry gracefully so that sync doesn't break | - Detect expired tokens<br>- Attempt refresh automatically<br>- Notify user if re-auth needed<br>- "Disconnected" state handling | 3 |

### Epic 1.5: Date Range Processing

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S1-14 | As an **Account Manager**, I want to select a date range for initial sync so that I control what gets processed | - Date picker with presets (30/90/180 days, custom)<br>- Shows estimated email count<br>- Confirms before processing | 3 |
| S1-15 | As an **Account Manager**, I want to re-process historical emails so that I can apply new rules to old data | - "Re-process" button for date range<br>- Idempotent (same input = same output)<br>- Shows progress during reprocessing | 3 |
| S1-16 | As the **System**, I want deterministic processing so that reprocessing doesn't create duplicates | - Upsert logic based on email Message-ID<br>- Clear rules for overwrite vs preserve<br>- Audit trail for reprocessed emails | 3 |

### Sprint 1 Summary
- **Total Stories:** 16
- **Total Points:** 56
- **Key Deliverable:** Working multi-tenant system with Gmail/Outlook sync

---

## 🔍 Sprint 2: Intelligence (Weeks 4-6)

**Sprint Goal:** Automatic customer recognition and comprehensive contact database

### Epic 2.1: Customer Recognition System

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S2-01 | As an **Account Manager**, I want to define customer companies by domain pattern so that emails are auto-tagged | - Rule: "If sender domain contains 'carbon8' → tag as Carbon8"<br>- Support wildcards (*.carbon8.com.au)<br>- Multiple patterns per company | 5 |
| S2-02 | As an **Account Manager**, I want to define keyword-based rules so that emails with specific terms are tagged | - Rule: "If subject contains 'Project Alpha' → tag as ProjectAlpha"<br>- Support AND/OR logic<br>- Case-insensitive matching | 3 |
| S2-03 | As the **System**, I want to apply rules to historical emails so that past emails are organized | - Bulk apply rules to existing emails<br>- Progress indicator during processing<br>- Shows count of emails tagged | 3 |
| S2-04 | As an **Account Manager**, I want to see why an email was tagged so that I can verify accuracy | - "Why tagged?" shows matching rule<br>- Shows which pattern/keyword matched<br>- Helps debug incorrect tagging | 3 |

### Epic 2.2: Rules Management Interface

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S2-05 | As an **Account Manager**, I want to create rules via a simple UI so that I don't need technical knowledge | - Form-based rule creation<br>- Dropdown for rule type (domain/keyword)<br>- Preview of pattern syntax | 3 |
| S2-06 | As an **Account Manager**, I want to set rule priority so that conflicts are resolved predictably | - Drag-and-drop priority ordering<br>- Higher priority rules win conflicts<br>- Clear indication of priority order | 3 |
| S2-07 | As an **Account Manager**, I want to test rules before applying so that I can verify they work correctly | - "Test Rule" shows sample matching emails<br>- Shows count of emails that would match<br>- No actual changes until confirmed | 3 |
| S2-08 | As an **Admin**, I want rule versioning so that changes can be audited | - Rules have version history<br>- Can view previous versions<br>- Audit log of who changed what | 2 |

### Epic 2.3: Contact Database

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S2-09 | As the **System**, I want to auto-extract contacts from email headers so that a contact database is built | - Extract From, To, CC email addresses<br>- Create contact record per unique email<br>- Link contact to customer company if known | 3 |
| S2-10 | As the **System**, I want to parse email signatures so that contact details are enriched | - Extract name, title, company, phone from signatures<br>- Confidence score per extracted field<br>- Handle multiple signature formats | 5 |
| S2-11 | As the **System**, I want to deduplicate contacts so that each person appears once | - Match by email address (primary)<br>- Fuzzy match by name + company<br>- Merge duplicate records intelligently | 3 |
| S2-12 | As an **Account Manager**, I want to manually edit contact details so that I can correct parsing errors | - Edit form for contact fields<br>- "Override" flag for manual edits<br>- Manual edits preserved on re-parse | 2 |
| S2-13 | As an **Account Manager**, I want to search/filter contacts so that I can find specific people | - Search by name, email, company<br>- Filter by customer company<br>- Sort by last contact date | 2 |

### Epic 2.4: Communication History

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S2-14 | As an **Account Manager**, I want to see communication history per contact so that I understand the relationship | - Contact detail page shows email timeline<br>- Sent vs received indicators<br>- Click to view email content | 3 |
| S2-15 | As an **Account Manager**, I want to see customer company overview so that I understand account health | - Company page shows all contacts<br>- Total email volume<br>- Last communication date | 3 |

### Epic 2.5: Shared Inbox Handling

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S2-16 | As the **System**, I want to identify shared inbox aliases so that they're not treated as individuals | - Detect common patterns (info@, support@, sales@)<br>- Flag as "shared inbox" type<br>- Don't create individual contact records | 2 |

### Sprint 2 Summary
- **Total Stories:** 16
- **Total Points:** 48
- **Key Deliverable:** Customer recognition with contact database

---

## 🤖 Sprint 3: AI Layer (Weeks 7-9)

**Sprint Goal:** AI-powered email classification with trust mechanisms and accuracy metrics

### Epic 3.1: AI Email Classification

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S3-01 | As the **System**, I want to classify emails by type so that they're categorized automatically | - Types: Quote, Order, Inquiry, Complaint, General<br>- Confidence score per classification<br>- Multi-label support (email can be multiple types) | 5 |
| S3-02 | As the **System**, I want to detect email priority so that urgent items are highlighted | - Priority: Urgent, High, Normal, Low<br>- Based on language analysis + patterns<br>- Confidence score included | 3 |
| S3-03 | As the **System**, I want to analyze sentiment so that tone is understood | - Sentiment: Positive, Neutral, Negative<br>- Confidence score included<br>- Based on overall email tone | 3 |
| S3-04 | As the **System**, I want to flag urgency indicators so that time-sensitive items are visible | - Detect deadline language ("by Friday", "ASAP")<br>- Extract specific dates mentioned<br>- Visual urgency flag in UI | 3 |
| S3-05 | As the **System**, I want an "Unable to classify" state so that low-confidence items are flagged | - If confidence < threshold → "Needs Review"<br>- Separate queue for review items<br>- Explicit abstain rather than guess | 2 |

### Epic 3.2: Business Entity Extraction

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S3-06 | As the **System**, I want to extract quote numbers so that they're searchable | - Regex-first approach (patterns like Q-12345)<br>- AI fallback for unusual formats<br>- Confidence score per extraction | 3 |
| S3-07 | As the **System**, I want to extract PO numbers so that orders are trackable | - Regex patterns for common PO formats<br>- Handle variations (PO#, P.O., Purchase Order)<br>- Link to relevant emails | 3 |
| S3-08 | As the **System**, I want to extract dollar amounts so that deal values are visible | - Detect currency + amount<br>- Handle multiple currencies (USD, AUD)<br>- Multiple amounts per email possible | 2 |
| S3-09 | As the **System**, I want to extract deadlines so that time-sensitive items are tracked | - Parse explicit dates<br>- Interpret relative dates ("next Tuesday")<br>- Confidence score included | 3 |
| S3-10 | As the **System**, I want to handle extraction collisions so that multiple matches are managed | - If multiple quote numbers found → list all<br>- Don't arbitrarily pick one<br>- UI shows all detected values | 2 |

### Epic 3.3: Manual Correction UI (Trust Building)

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S3-11 | As an **Account Manager**, I want to correct AI classifications so that accuracy improves | - Override buttons for type/priority/sentiment<br>- Correction saved with "human verified" flag<br>- Easy one-click correction flow | 3 |
| S3-12 | As an **Account Manager**, I want to see a "Needs Review" queue so that I can verify low-confidence items | - Filter for confidence < threshold<br>- Batch correction interface<br>- Shows AI's guess + confidence | 3 |
| S3-13 | As the **System**, I want to track human corrections so that accuracy is measurable | - Log all corrections (before/after)<br>- Calculate accuracy rate<br>- Report: "X% required human correction" | 3 |

### Epic 3.4: AI Cost & Performance Tracking

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S3-14 | As an **Admin**, I want to see AI cost per 1,000 emails so that costs are predictable | - Track API calls and token usage<br>- Calculate cost per email batch<br>- Dashboard shows cost trends | 3 |
| S3-15 | As the **System**, I want batch processing so that API costs are optimized | - Batch emails before sending to AI<br>- Configurable batch size<br>- Retry logic for failed batches | 3 |
| S3-16 | As an **Admin**, I want prompt versioning so that changes can be rolled back | - Version history for prompts<br>- A/B test different prompts<br>- Rollback to previous version | 2 |

### Epic 3.5: Accuracy Testing & Metrics

| ID | User Story | Acceptance Criteria | Points |
|----|------------|---------------------|--------|
| S3-17 | As the **System**, I want a gold-standard test dataset so that accuracy is measurable | - 1,000 manually labeled test emails<br>- Diverse across all classification types<br>- Used for regression testing | 5 |
| S3-18 | As an **Admin**, I want precision/recall metrics per class so that I understand AI performance | - Precision: How many tagged items were correct?<br>- Recall: How many correct items were found?<br>- Report per classification type | 3 |
| S3-19 | As an **Admin**, I want an accuracy dashboard so that I can monitor AI quality | - Overall accuracy percentage<br>- Accuracy by classification type<br>- Trend over time | 3 |
| S3-20 | As the **System**, I want to detect accuracy drift so that degradation is caught early | - Compare weekly accuracy to baseline<br>- Alert if accuracy drops > 5%<br>- Trigger review if drift detected | 2 |

### Sprint 3 Summary
- **Total Stories:** 20
- **Total Points:** 60
- **Key Deliverable:** AI classification with ≥85% accuracy + trust mechanisms

---

## 📊 Go/No-Go Criteria for Phase 3

At the end of Sprint 3, evaluate:

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Accuracy** | ≥85% overall | Test against 1,000 labeled emails |
| **Confidence** | Scores on all outputs | 100% of classifications have confidence |
| **Cost** | < $X per 1,000 emails | Dashboard tracking |
| **Human Trust** | Correction UI working | Can fix AI mistakes |
| **Actionability** | Users act on signals | Track action rate |
| **Volume** | 10k emails no degradation | Performance test |

**Phase 3 proceeds only if targets are met.**

---

## 🔄 Story Status Legend

| Status | Meaning |
|--------|---------|
| 📋 Backlog | Not started |
| 🔄 In Progress | Currently being worked on |
| 👀 In Review | Code complete, needs testing |
| ✅ Done | Completed and verified |
| 🚫 Blocked | Waiting on dependency |

---

## 📈 Velocity Tracking

| Sprint | Planned Points | Completed | Velocity |
|--------|---------------|-----------|----------|
| Sprint 1 | 56 | - | - |
| Sprint 2 | 48 | - | - |
| Sprint 3 | 60 | - | - |

**Total Stage 2 Points: 164**

---

## 🎯 Definition of Done

A story is "Done" when:
- [ ] Code implemented and working
- [ ] Unit tests passing
- [ ] Integration tested
- [ ] Deployed to staging
- [ ] Acceptance criteria verified
- [ ] No critical bugs
