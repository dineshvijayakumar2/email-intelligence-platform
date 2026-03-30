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

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24
MIN_AFFINITY_SUPPORT = 3      # min companies sharing a pair for Level 2
MIN_CONTACTS_FOR_GAPS = 2     # need ≥ 2 contacts to show cross-contact gaps


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
        if not force:
            cached = self._get_cached(company_id)
            if cached:
                return cached

        cross_contact = self._compute_cross_contact(company_id)
        related_product = self._compute_related_product(company_id)
        product_profile = self._compute_product_profile(company_id)

        result = {
            'cross_contact_recs': cross_contact,
            'related_product_recs': related_product,
            'product_profile': product_profile,
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
        Find operations that the company uses but specific contacts haven't
        been involved with. Requires ≥ 2 contacts to be meaningful.
        """
        try:
            # All contacts for this company
            contacts_result = (
                self._supabase.table('customer_contacts')
                .select('id, email_address, full_name')
                .eq('customer_company_id', company_id)
                .eq('client_id', self._client_id)
                .execute()
            )
            contacts = contacts_result.data or []
            if len(contacts) < MIN_CONTACTS_FOR_GAPS:
                return []

            contact_by_email = {
                c['email_address'].strip().lower(): c
                for c in contacts
                if c.get('email_address')
            }

            # All operations for this company
            ops_result = (
                self._supabase.table('qb_operations')
                .select('job_no, operation_name, department')
                .eq('matched_company_id', company_id)
                .eq('client_id', self._client_id)
                .execute()
            )
            operations = ops_result.data or []
            if not operations:
                return []

            # Resolve contact per operation via job_no → qb_quotes.contact_email
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

            # Build {contact_id: set(operation_names)}
            contact_op_map: dict = {}
            op_dept_map: dict = {}

            for op in operations:
                op_name = op.get('operation_name')
                if not op_name:
                    continue
                op_dept_map[op_name] = op.get('department')
                email = job_to_email.get(op.get('job_no', ''))
                if not email:
                    continue
                contact = contact_by_email.get(email)
                if not contact:
                    continue
                cid = contact['id']
                if cid not in contact_op_map:
                    contact_op_map[cid] = {'contact': contact, 'ops': set()}
                contact_op_map[cid]['ops'].add(op_name)

            if not contact_op_map:
                return []

            # Company-wide operations set
            all_ops = set()
            for v in contact_op_map.values():
                all_ops |= v['ops']

            # Gap per contact
            recs = []
            for cid, v in contact_op_map.items():
                gaps = all_ops - v['ops']
                if not gaps:
                    continue
                contact_name = v['contact'].get('full_name') or v['contact'].get('email_address', '')
                missing = sorted(gaps)
                depts = sorted({op_dept_map.get(g) for g in missing if op_dept_map.get(g)})
                recs.append({
                    'type': 'cross_contact',
                    'contact_id': cid,
                    'contact_name': contact_name,
                    'missing_operations': missing,
                    'departments': depts,
                    'reason': (
                        f"{len(missing)} operation(s) used by other contacts at this company "
                        f"that {contact_name} hasn't been involved with"
                    ),
                })

            return recs

        except Exception as e:
            logger.warning(f"cross_contact computation failed for {company_id}: {e}")
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
            # Resolve QB customer record ID for this company
            cust_result = (
                self._supabase.table('qb_customers')
                .select('qb_record_id')
                .eq('matched_company_id', company_id)
                .eq('client_id', self._client_id)
                .limit(1)
                .execute()
            )
            if not cust_result.data:
                return {'categories': [], 'operations': []}

            qb_record_id = cust_result.data[0]['qb_record_id']

            # Sales line items → revenue by product_group
            sli_result = (
                self._supabase.table('qb_sales_line_items')
                .select('product_group, total')
                .eq('qb_customer_id', qb_record_id)
                .eq('client_id', self._client_id)
                .execute()
            )
            group_totals: dict = {}
            for row in (sli_result.data or []):
                pg = row.get('product_group') or 'Other'
                group_totals[pg] = group_totals.get(pg, 0) + float(row.get('total') or 0)

            categories = [
                {'category': k, 'revenue': round(v, 2)}
                for k, v in sorted(group_totals.items(), key=lambda x: -x[1])
            ]

            # Operation names + QB tags from qb_operations
            ops_result = (
                self._supabase.table('qb_operations')
                .select('operation_name, department, qb_capability_tag, qb_process_tag, qb_embellishment_tag')
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

            # Aggregate QB tag breakdowns
            cap_counts: dict = {}
            process_set: set = set()
            embellishment_set: set = set()
            for r in (ops_result.data or []):
                cap = (r.get('qb_capability_tag') or '').strip()
                if cap:
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
