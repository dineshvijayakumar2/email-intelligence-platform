"""
Recommendation Engine — Sales Intelligence (Sprint 4)

Two levels of pure-Python recommendations, $0 AI cost:

Level 1 — Cross-contact gaps (per company):
  Find operations/products the company uses but specific contacts haven't
  been involved with.
  Data chain: qb_operations.job_no → qb_quotes.contact_email → customer_contacts

Level 2 — Related product affinities (portfolio-wide):
  Market basket analysis — "customers who use X also use Y".
  Pre-computed via recompute_affinities() and stored in product_affinities table.

Results cached 24h in customer_recommendations per company.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from .capability_resolution import caps_for_op

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24
MIN_AFFINITY_SUPPORT = 3      # min companies sharing a pair for Level 2
MIN_CONTACTS_FOR_GAPS = 2     # need ≥ 2 contacts to show cross-contact gaps
CONCENTRATION_REVENUE_THRESHOLD = 100_000  # $100K minimum for concentration risk
CONCENTRATION_MAX_REVENUE_CONTACTS = 2     # ≤ 2 contacts producing revenue
CONCENTRATION_MIN_TOTAL_CONTACTS = 3       # > 2 total contacts for the filter (HAVING > 2)


def _caps_for_op(op: dict) -> list:
    """Capabilities for an operation. Thin wrapper over the shared resolver so the precedence
    lives in exactly one place (capability_resolution.caps_for_op): the corrected op-name
    CLASSIFIER (capability_tags) wins; qb_capability_tag fills gaps only when the classifier is
    silent. Inverts the old QB-first order, which mis-routed cello->Embellishment / fuse->Hard
    Cover via QB's Department keying. MUST match get_capability_rhythm — the shared helper guarantees it."""
    return caps_for_op(op)


class RecommendationEngine:
    """Compute and cache sales recommendations for a client."""

    def __init__(self, supabase_client, client_id: str):
        self._supabase = supabase_client
        self._client_id = client_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_recommendations(self, company_id: str, force: bool = False) -> dict:
        """Return recommendations for a company (cached 24h)."""
        # Revenue insight is always fresh (fast view query, not worth caching)
        revenue_insight = self._compute_revenue_concentration(company_id)

        if not force:
            cached = self._get_cached(company_id)
            if cached:
                cached['revenue_insight'] = revenue_insight
                return cached

        cross_contact = self._compute_cross_contact(company_id)
        related_product = self._compute_related_product(company_id)
        product_profile = self._compute_product_profile(company_id)

        result = {
            'cross_contact_recs': cross_contact,
            'related_product_recs': related_product,
            'product_profile': product_profile,
            'revenue_insight': revenue_insight,
            'computed_at': datetime.now(timezone.utc).isoformat(),
        }
        self._save_cache(company_id, result)
        return result

    def get_product_profile(self, company_id: str) -> dict:
        """Product categories + operations for a company (no caching)."""
        return self._compute_product_profile(company_id)

    def recompute_affinities(self) -> int:
        """
        Market basket analysis across all qb_operations for this client.
        Stores results in product_affinities (client-wide, not per-company).
        Returns number of affinity pairs stored.
        """
        try:
            # Fetch all operations with a matched company
            all_ops = []
            offset = 0
            while True:
                batch = (
                    self._supabase.table('qb_operations')
                    .select('matched_company_id, operation_name')
                    .eq('client_id', self._client_id)
                    .not_.is_('matched_company_id', 'null')
                    .not_.is_('operation_name', 'null')
                    .range(offset, offset + 999)
                    .execute()
                )
                rows = batch.data or []
                all_ops.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            if not all_ops:
                return 0

            # Build {company_id: set(operation_names)}
            company_ops: dict = {}
            for row in all_ops:
                cid = row['matched_company_id']
                op = row['operation_name']
                if cid not in company_ops:
                    company_ops[cid] = set()
                company_ops[cid].add(op)

            # Count co-occurrences and per-operation totals
            cooccur: dict = {}   # (op_a, op_b) → count
            op_totals: dict = {} # op → num companies using it

            for ops_set in company_ops.values():
                ops_list = sorted(ops_set)
                for op_a in ops_list:
                    op_totals[op_a] = op_totals.get(op_a, 0) + 1
                    for op_b in ops_list:
                        if op_a != op_b:
                            key = (op_a, op_b)
                            cooccur[key] = cooccur.get(key, 0) + 1

            now = datetime.now(timezone.utc).isoformat()
            rows_to_upsert = []
            for (op_a, op_b), count in cooccur.items():
                if count < MIN_AFFINITY_SUPPORT:
                    continue
                confidence = round(count / max(op_totals.get(op_a, 1), 1), 4)
                rows_to_upsert.append({
                    'client_id': self._client_id,
                    'product_a': op_a,
                    'product_b': op_b,
                    'cooccurrence_count': count,
                    'confidence': confidence,
                    'computed_at': now,
                })

            stored = 0
            for i in range(0, len(rows_to_upsert), 100):
                self._supabase.table('product_affinities').upsert(
                    rows_to_upsert[i:i + 100],
                    on_conflict='client_id,product_a,product_b'
                ).execute()
                stored += len(rows_to_upsert[i:i + 100])

            logger.info(f"Stored {stored} affinity pairs for client {self._client_id}")
            return stored

        except Exception as e:
            logger.error(f"Affinity recomputation failed for client {self._client_id}: {e}")
            return 0

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _get_cached(self, company_id: str) -> Optional[dict]:
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
            result = (
                self._supabase.table('customer_recommendations')
                .select('cross_contact_recs, related_product_recs, product_profile, computed_at')
                .eq('client_id', self._client_id)
                .eq('company_id', company_id)
                .gte('computed_at', cutoff)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception as e:
            logger.debug(f"Cache read skipped for {company_id}: {e}")
        return None

    def _save_cache(self, company_id: str, data: dict) -> None:
        try:
            self._supabase.table('customer_recommendations').upsert({
                'client_id': self._client_id,
                'company_id': company_id,
                'cross_contact_recs': data['cross_contact_recs'],
                'related_product_recs': data['related_product_recs'],
                'product_profile': data['product_profile'],
                'computed_at': data['computed_at'],
            }, on_conflict='client_id,company_id').execute()
        except Exception as e:
            logger.warning(f"Cache write failed for {company_id}: {e}")

    # ------------------------------------------------------------------
    # Level 1: Cross-contact gap analysis
    # ------------------------------------------------------------------

    def _compute_cross_contact(self, company_id: str) -> list:
        """
        Capability-level gap analysis per contact. For each contact, shows
        which capabilities the company uses that this contact hasn't been
        on a quote for. Aggregated from raw operations → qb_capability_tag.
        """
        try:
            contacts_result = (
                self._supabase.table('customer_contacts')
                .select('id, email_address, full_name, contact_type')
                .eq('customer_company_id', company_id)
                .eq('client_id', self._client_id)
                .execute()
            )
            all_contacts = contacts_result.data or []

            contacts = [
                c for c in all_contacts
                if c.get('contact_type') in ('person', 'unknown', None)
            ]
            if len(contacts) < MIN_CONTACTS_FOR_GAPS:
                return []

            seen_emails: set = set()
            contact_by_email: dict = {}
            for c in contacts:
                email = (c.get('email_address') or '').strip().lower()
                if not email or email in seen_emails:
                    continue
                seen_emails.add(email)
                contact_by_email[email] = c

            company_result = (
                self._supabase.table('customer_companies')
                .select('email_domains')
                .eq('id', company_id)
                .limit(1)
                .execute()
            )
            company_domains: set = set()
            if company_result.data:
                domains_raw = company_result.data[0].get('email_domains') or []
                company_domains = {d.lower() for d in domains_raw if d}

            ops_result = (
                self._supabase.table('qb_operations')
                .select('job_no, operation_name, qb_capability_tag, capability_tags')
                .eq('matched_company_id', company_id)
                .eq('client_id', self._client_id)
                .execute()
            )
            operations = ops_result.data or []
            if not operations:
                return []

            job_nos = list({op['job_no'] for op in operations if op.get('job_no')})
            if not job_nos:
                return []

            job_to_email: dict = {}
            for batch_start in range(0, len(job_nos), 500):
                batch = job_nos[batch_start:batch_start + 500]
                quotes = (
                    self._supabase.table('qb_quotes')
                    .select('job_no, contact_email')
                    .in_('job_no', batch)
                    .eq('client_id', self._client_id)
                    .execute()
                )
                for q in (quotes.data or []):
                    if q.get('job_no') and q.get('contact_email'):
                        job_to_email[q['job_no']] = q['contact_email'].strip().lower()

            # Map each contact to their set of capabilities (via operations → capability_tag)
            contact_cap_map: dict = {}
            all_capabilities: set = set()

            for op in operations:
                caps = _caps_for_op(op)   # classifier-first, QB fills gaps (shared resolver, matches rhythm)
                if not caps:
                    continue
                all_capabilities.update(caps)
                email = job_to_email.get(op.get('job_no', ''))
                if not email:
                    continue
                contact = contact_by_email.get(email)
                if not contact:
                    continue
                cid = contact['id']
                if cid not in contact_cap_map:
                    contact_cap_map[cid] = {'contact': contact, 'capabilities': set()}
                contact_cap_map[cid]['capabilities'].update(caps)

            if not contact_cap_map or len(all_capabilities) < 2:
                return []

            recs = []
            for cid, v in contact_cap_map.items():
                gaps = all_capabilities - v['capabilities']
                if not gaps:
                    continue
                contact = v['contact']
                contact_name = contact.get('full_name') or contact.get('email_address', '')

                contact_email = (contact.get('email_address') or '').lower()
                domain_mismatch = False
                if company_domains and '@' in contact_email:
                    contact_domain = contact_email.split('@')[1]
                    domain_mismatch = contact_domain not in company_domains

                rec = {
                    'type': 'cross_contact',
                    'contact_id': cid,
                    'contact_name': contact_name,
                    'contact_email': contact_email,
                    'already_buys': sorted(v['capabilities']),
                    'untapped_capabilities': sorted(gaps),
                    'reason': (
                        f"{contact_name} buys {len(v['capabilities'])} capability(ies) but "
                        f"hasn't been introduced to {len(gaps)} other(s) this company uses"
                    ),
                }
                if domain_mismatch:
                    rec['domain_mismatch'] = True
                    rec['contact_domain'] = contact_email.split('@')[1]

                recs.append(rec)

            recs.sort(key=lambda r: -len(r['untapped_capabilities']))
            return recs

        except Exception as e:
            logger.warning(f"cross_contact computation failed for {company_id}: {e}")
            return []

    # ------------------------------------------------------------------
    # Revenue Concentration / Buyer Decay Analysis
    # ------------------------------------------------------------------

    def _compute_revenue_concentration(self, company_id: str) -> Optional[dict]:
        """
        Classify a company's revenue concentration risk using contact_persona view.
        Returns insight dict or None if company doesn't meet thresholds.
        """
        try:
            all_rows = []
            offset = 0
            while True:
                batch = (
                    self._supabase.table('contact_persona')
                    .select(
                        'contact_id, name, email, persona_classification, '
                        'engagement_score, total_job_value, email_days_since_last, contact_type'
                    )
                    .eq('company_id', company_id)
                    .eq('client_id', self._client_id)
                    .neq('persona_classification', 'shared_mailbox')
                    .eq('contact_type', 'person')
                    .range(offset, offset + 999)
                    .execute()
                )
                rows = batch.data or []
                all_rows.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            if len(all_rows) < CONCENTRATION_MIN_TOTAL_CONTACTS:
                return None

            total_contacts = len(all_rows)
            company_total_revenue = sum(float(r.get('total_job_value') or 0) for r in all_rows)

            if company_total_revenue < CONCENTRATION_REVENUE_THRESHOLD:
                return None

            revenue_contacts = [
                r for r in all_rows if float(r.get('total_job_value') or 0) > 0
            ]
            revenue_producing_contacts = len(revenue_contacts)

            if revenue_producing_contacts > CONCENTRATION_MAX_REVENUE_CONTACTS:
                return None

            ranked = sorted(all_rows, key=lambda r: -float(r.get('total_job_value') or 0))
            top_buyer = ranked[0]
            top_buyer_persona = top_buyer.get('persona_classification', 'unknown')
            top_buyer_name = top_buyer.get('name') or top_buyer.get('email', 'unknown')

            # Classify insight type
            if top_buyer_persona == 'inactive_buyer':
                insight_type = 'buyer_decay_risk'
            elif (revenue_producing_contacts <= 2
                  and total_contacts > 4
                  and company_total_revenue > CONCENTRATION_REVENUE_THRESHOLD):
                insight_type = 'concentration_risk'
            else:
                return None

            # Build top 2 contact summaries
            top_2 = []
            for r in ranked[:2]:
                val = float(r.get('total_job_value') or 0)
                if val <= 0:
                    break
                pct = round(100.0 * val / company_total_revenue, 1)
                name = r.get('name') or r.get('email', '?')
                top_2.append({
                    'name': name,
                    'pct_of_revenue': pct,
                    'persona': r.get('persona_classification'),
                    'total_job_value': val,
                })

            # Build unengaged contact list
            unengaged = []
            for r in all_rows:
                if float(r.get('total_job_value') or 0) == 0:
                    unengaged.append({
                        'name': r.get('name') or r.get('email', '?'),
                        'persona': r.get('persona_classification'),
                        'engagement_score': r.get('engagement_score', 0),
                    })

            return {
                'insight_type': insight_type,
                'company_total_revenue': round(company_total_revenue, 2),
                'total_contacts': total_contacts,
                'revenue_producing_contacts': revenue_producing_contacts,
                'top_buyer_name': top_buyer_name,
                'top_buyer_persona': top_buyer_persona,
                'top_revenue_contacts': top_2,
                'unengaged_contacts': unengaged,
            }

        except Exception as e:
            logger.warning(f"revenue_concentration failed for {company_id}: {e}")
            return None

    def get_portfolio_insights(self) -> list:
        """
        Portfolio-wide scan: all companies with concentration_risk or buyer_decay_risk.
        Queries contact_persona view, aggregates in Python. No caching (on-demand).
        """
        try:
            all_rows = []
            offset = 0
            while True:
                batch = (
                    self._supabase.table('contact_persona')
                    .select(
                        'company_id, company_name, contact_id, name, email, '
                        'persona_classification, engagement_score, total_job_value, '
                        'email_days_since_last, contact_type'
                    )
                    .eq('client_id', self._client_id)
                    .neq('persona_classification', 'shared_mailbox')
                    .eq('contact_type', 'person')
                    .range(offset, offset + 999)
                    .execute()
                )
                rows = batch.data or []
                all_rows.extend(rows)
                if len(rows) == 0:
                    break
                offset += len(rows)

            if not all_rows:
                return []

            # Group by company
            companies: dict = {}
            for r in all_rows:
                cid = r.get('company_id')
                if not cid:
                    continue
                if cid not in companies:
                    companies[cid] = {
                        'company_id': cid,
                        'company_name': r.get('company_name', ''),
                        'contacts': [],
                    }
                companies[cid]['contacts'].append(r)

            insights = []
            for cid, company in companies.items():
                contacts = company['contacts']
                total_contacts = len(contacts)
                company_total_revenue = sum(float(c.get('total_job_value') or 0) for c in contacts)

                if company_total_revenue < CONCENTRATION_REVENUE_THRESHOLD:
                    continue
                if total_contacts <= 2:
                    continue

                revenue_producing = [
                    c for c in contacts if float(c.get('total_job_value') or 0) > 0
                ]
                revenue_producing_contacts = len(revenue_producing)

                if revenue_producing_contacts > CONCENTRATION_MAX_REVENUE_CONTACTS:
                    continue

                ranked = sorted(contacts, key=lambda c: -float(c.get('total_job_value') or 0))
                top_buyer = ranked[0]
                top_buyer_persona = top_buyer.get('persona_classification', 'unknown')
                top_buyer_name = top_buyer.get('name') or top_buyer.get('email', 'unknown')

                if top_buyer_persona == 'inactive_buyer':
                    insight_type = 'buyer_decay_risk'
                elif (revenue_producing_contacts <= 2
                      and total_contacts > 4
                      and company_total_revenue > CONCENTRATION_REVENUE_THRESHOLD):
                    insight_type = 'concentration_risk'
                else:
                    continue

                # Top 2 revenue contacts
                top_2_parts = []
                for c in ranked[:2]:
                    val = float(c.get('total_job_value') or 0)
                    if val <= 0:
                        break
                    pct = round(100.0 * val / company_total_revenue, 1)
                    name = c.get('name') or c.get('email', '?')
                    top_2_parts.append(f"{name} ({pct}%, {c.get('persona_classification')})")

                # Unengaged contacts
                unengaged_parts = []
                for c in contacts:
                    if float(c.get('total_job_value') or 0) == 0:
                        name = c.get('name') or c.get('email', '?')
                        unengaged_parts.append(
                            f"{name} ({c.get('persona_classification')}, "
                            f"score {c.get('engagement_score', 0)})"
                        )

                insights.append({
                    'company_id': cid,
                    'company_name': company['company_name'],
                    'insight_type': insight_type,
                    'company_total_revenue': round(company_total_revenue, 2),
                    'total_contacts': total_contacts,
                    'revenue_producing_contacts': revenue_producing_contacts,
                    'top_buyer_name': top_buyer_name,
                    'top_buyer_persona': top_buyer_persona,
                    'top_2_contacts': ', '.join(top_2_parts),
                    'unengaged_contacts': ', '.join(unengaged_parts[:10]),
                })

            insights.sort(key=lambda x: -x['company_total_revenue'])
            logger.info(
                f"Portfolio insights: {len(insights)} companies with "
                f"concentration/decay risk out of {len(companies)} total"
            )
            return insights

        except Exception as e:
            logger.error(f"Portfolio insights failed for {self._client_id}: {e}")
            return []

    # ------------------------------------------------------------------
    # Level 2: Related product affinities
    # ------------------------------------------------------------------

    def _compute_related_product(self, company_id: str) -> list:
        """
        Suggest operations the company hasn't tried, based on pre-computed
        co-occurrence with operations they already use.
        """
        try:
            ops_result = (
                self._supabase.table('qb_operations')
                .select('operation_name')
                .eq('matched_company_id', company_id)
                .eq('client_id', self._client_id)
                .execute()
            )
            company_ops = {
                r['operation_name']
                for r in (ops_result.data or [])
                if r.get('operation_name')
            }
            if not company_ops:
                return []

            affinities = (
                self._supabase.table('product_affinities')
                .select('product_a, product_b, confidence, cooccurrence_count')
                .eq('client_id', self._client_id)
                .in_('product_a', list(company_ops))
                .order('confidence', desc=True)
                .limit(20)
                .execute()
            )

            recs = []
            seen_b: set = set()
            for aff in (affinities.data or []):
                product_b = aff.get('product_b')
                if not product_b or product_b in company_ops or product_b in seen_b:
                    continue
                seen_b.add(product_b)
                confidence = float(aff.get('confidence') or 0)
                count = int(aff.get('cooccurrence_count') or 0)
                recs.append({
                    'type': 'related_product',
                    'current_operation': aff['product_a'],
                    'recommended_operation': product_b,
                    'confidence': confidence,
                    'supporting_count': count,
                    'message': (
                        f"{int(confidence * 100)}% of customers using {aff['product_a']} "
                        f"also use {product_b} ({count} companies)"
                    ),
                })
                if len(recs) >= 5:
                    break

            return recs

        except Exception as e:
            logger.warning(f"related_product computation failed for {company_id}: {e}")
            return []

    # ------------------------------------------------------------------
    # Product profile (also used independently by /product-profile endpoint)
    # ------------------------------------------------------------------

    def _compute_product_profile(self, company_id: str) -> dict:
        """
        Aggregate product categories (from qb_sales_line_items) and operation
        names (from qb_operations) for the company.
        """
        try:
            # Resolve QB customer key ID (field 92) for this company
            # Note: qb_sales_line_items.qb_customer_id uses Customer ID (key), NOT Record ID#
            cust_result = (
                self._supabase.table('qb_customers')
                .select('customer_key_id')
                .eq('matched_company_id', company_id)
                .eq('client_id', self._client_id)
                .limit(1)
                .execute()
            )
            if not cust_result.data or not cust_result.data[0].get('customer_key_id'):
                return {'categories': [], 'operations': []}

            qb_key_id = cust_result.data[0]['customer_key_id']

            # Sales line items → revenue by product_group (fallback to industry)
            # FRAGILE (mixed-space ID): safe only because qb_key_id comes from
            # qb_customers.customer_key_id and qb_sales_line_items.qb_customer_id is key-id
            # space. Never feed a customer_companies.qb_customer_id (mixed key_id/record_id)
            # here — resolve it first via resolve_qb in scripts/db/merge_duplicate_companies.py.
            sli_result = (
                self._supabase.table('qb_sales_line_items')
                .select('product_group, industry, total')
                .eq('qb_customer_id', qb_key_id)
                .eq('client_id', self._client_id)
                .execute()
            )
            group_totals: dict = {}
            for row in (sli_result.data or []):
                # Use product_group first, fallback to industry, then 'Other'
                pg = (row.get('product_group') or '').strip()
                if not pg or pg.lower() == 'other':
                    pg = (row.get('industry') or '').strip()
                if not pg:
                    pg = 'Other'
                group_totals[pg] = group_totals.get(pg, 0) + float(row.get('total') or 0)

            categories = [
                {'category': k, 'revenue': round(v, 2)}
                for k, v in sorted(group_totals.items(), key=lambda x: -x[1])
            ]

            # If categories are just "Other", use capability tags as categories instead
            if len(categories) <= 1 and categories and categories[0]['category'] == 'Other':
                # Will be populated from operations below — defer to capability_breakdown
                categories = []

            # Operation names + capability/process tags from qb_operations
            ops_result = (
                self._supabase.table('qb_operations')
                .select('operation_name, department, capability_tags, qb_capability_tag, qb_process_tag, qb_embellishment_tag')
                .eq('matched_company_id', company_id)
                .eq('client_id', self._client_id)
                .execute()
            )
            operations = [
                {'operation': r['operation_name'], 'department': r.get('department')}
                for r in (ops_result.data or [])
                if r.get('operation_name')
            ]
            # Deduplicate by operation name
            seen: set = set()
            unique_ops = []
            for op in operations:
                if op['operation'] not in seen:
                    seen.add(op['operation'])
                    unique_ops.append(op)

            # Aggregate capability breakdowns (classifier-first via shared resolver; QB fills gaps)
            cap_counts: dict = {}
            process_set: set = set()
            embellishment_set: set = set()
            for r in (ops_result.data or []):
                for cap in caps_for_op(r):
                    cap_counts[cap] = cap_counts.get(cap, 0) + 1
                proc = (r.get('qb_process_tag') or '').strip()
                if proc:
                    process_set.add(proc)
                emb = (r.get('qb_embellishment_tag') or '').strip()
                if emb:
                    embellishment_set.add(emb)

            capability_breakdown = sorted(
                [{'capability': k, 'operation_count': v} for k, v in cap_counts.items()],
                key=lambda x: -x['operation_count']
            )

            return {
                'categories': categories,
                'operations': unique_ops,
                'capability_breakdown': capability_breakdown,
                'process_tags': sorted(process_set),
                'embellishment_tags': sorted(embellishment_set),
            }

        except Exception as e:
            logger.warning(f"product_profile computation failed for {company_id}: {e}")
            return {'categories': [], 'operations': []}
