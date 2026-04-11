"""
Customer Analytics Service — Phase 2 Intelligence (Sprint 4)

Pure SQL/Python analytics, $0 AI cost. Cached in customer_intelligence_cache.

Features:
  1. Strike rate — quotes sent vs jobs created, per company + per contact
  2. Contact capabilities — which contacts order which capability tags
  3. Seasonality trends — monthly/quarterly ordering patterns
  4. Capability ordering rhythm — avg interval, overdue detection
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta, date
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_TTL_HOURS = 24
MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]


class CustomerAnalyticsService:
    """Compute and cache customer analytics for a client."""

    def __init__(self, supabase_client, client_id: str):
        self._sb = supabase_client
        self._client_id = client_id

    # ------------------------------------------------------------------
    # Cache helpers (follow recommendation_engine.py pattern)
    # ------------------------------------------------------------------

    def _get_cached(self, company_id: str, cache_type: str) -> Optional[dict]:
        """Return cached data if fresh (< 24h)."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
            result = self._sb.table('customer_intelligence_cache').select(
                'data, computed_at'
            ).eq('client_id', self._client_id).eq(
                'company_id', company_id
            ).eq('cache_type', cache_type).is_(
                'contact_id', 'null'
            ).gte('computed_at', cutoff).limit(1).execute()

            if result.data:
                data = result.data[0]['data']
                data['computed_at'] = result.data[0]['computed_at']
                return data
        except Exception as e:
            logger.debug(f"Cache miss for {cache_type}/{company_id}: {e}")
        return None

    def _save_cache(self, company_id: str, cache_type: str, data: dict) -> None:
        """Upsert cache entry."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            # Delete existing then insert (partial unique index doesn't support upsert well)
            self._sb.table('customer_intelligence_cache').delete().eq(
                'client_id', self._client_id
            ).eq('company_id', company_id).eq(
                'cache_type', cache_type
            ).is_('contact_id', 'null').execute()

            self._sb.table('customer_intelligence_cache').insert({
                'client_id': self._client_id,
                'company_id': company_id,
                'cache_type': cache_type,
                'data': data,
                'computed_at': now,
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to save cache {cache_type}/{company_id}: {e}")

    # ------------------------------------------------------------------
    # Feature 3: Strike Rate
    # ------------------------------------------------------------------

    def get_strike_rate(self, company_id: str, force: bool = False) -> dict:
        """Quotes sent vs jobs created — per company and per contact."""
        if not force:
            cached = self._get_cached(company_id, 'strike_rate')
            if cached:
                return cached

        # Resolve ALL QB customer key IDs (a company can have multiple QB records)
        qb_key_ids: list[str] = []
        try:
            cust_result = self._sb.table('qb_customers').select(
                'customer_key_id'
            ).eq('matched_company_id', company_id).eq(
                'client_id', self._client_id
            ).execute()
            qb_key_ids = [
                r['customer_key_id'] for r in (cust_result.data or [])
                if r.get('customer_key_id')
            ]
        except Exception:
            pass

        # Fetch all quotes for this company via ALL QB customer keys
        quotes: list[dict] = []
        if qb_key_ids:
            for key_id in qb_key_ids:
                batch = self._fetch_all_paginated(
                    'qb_quotes',
                    'quote_no, has_job, contact_email, contact_name, date_created',
                    {'qb_customer_id': key_id},
                )
                quotes.extend(batch)
        else:
            # Fallback: try matched_company_id (if propagated)
            quotes = self._fetch_all_paginated(
                'qb_quotes',
                'quote_no, has_job, contact_email, contact_name, date_created',
                {'matched_company_id': company_id},
            )

        if not quotes:
            result = {
                'company_total': {'total_quotes': 0, 'converted': 0, 'strike_rate_pct': 0},
                'by_contact': [],
                'by_year': [],
            }
            self._save_cache(company_id, 'strike_rate', result)
            return result

        # Company-level
        total = len(quotes)
        converted = sum(1 for q in quotes if q.get('has_job'))
        rate = round(converted / total * 100, 1) if total else 0

        # Per-contact breakdown
        contact_map = defaultdict(lambda: {'total': 0, 'converted': 0, 'name': ''})
        for q in quotes:
            email = q.get('contact_email')
            if not email:
                continue
            contact_map[email]['total'] += 1
            if q.get('has_job'):
                contact_map[email]['converted'] += 1
            if q.get('contact_name'):
                contact_map[email]['name'] = q['contact_name']

        by_contact = sorted([
            {
                'contact_email': email,
                'contact_name': data['name'],
                'total_quotes': data['total'],
                'converted': data['converted'],
                'strike_rate_pct': round(data['converted'] / data['total'] * 100, 1) if data['total'] else 0,
            }
            for email, data in contact_map.items()
        ], key=lambda x: x['total_quotes'], reverse=True)

        # Per-year breakdown
        year_map = defaultdict(lambda: {'total': 0, 'converted': 0})
        for q in quotes:
            dc = q.get('date_created')
            if dc:
                try:
                    year = int(str(dc)[:4])
                    year_map[year]['total'] += 1
                    if q.get('has_job'):
                        year_map[year]['converted'] += 1
                except (ValueError, TypeError):
                    pass

        by_year = sorted([
            {
                'year': year,
                'total_quotes': data['total'],
                'converted': data['converted'],
                'strike_rate_pct': round(data['converted'] / data['total'] * 100, 1) if data['total'] else 0,
            }
            for year, data in year_map.items()
        ], key=lambda x: x['year'], reverse=True)

        result = {
            'company_total': {'total_quotes': total, 'converted': converted, 'strike_rate_pct': rate},
            'by_contact': by_contact,
            'by_year': by_year,
        }
        self._save_cache(company_id, 'strike_rate', result)
        return result

    # ------------------------------------------------------------------
    # Feature 5: Contact Capabilities
    # ------------------------------------------------------------------

    def get_contact_capabilities(self, company_id: str, force: bool = False) -> dict:
        """Which contacts order which capabilities. Groups by contact + capability_tag."""
        if not force:
            cached = self._get_cached(company_id, 'contact_capability_profile')
            if cached:
                return cached

        # Fetch operations with capability tags and contact_email
        # Include QB tags — they may exist even when classifier capability_tags is []
        ops = self._fetch_all_paginated(
            'qb_operations',
            'contact_email, customer_name, capability_tags, qb_capability_tag, qb_process_tag, cost_plus_price, date_accepted',
            {'matched_company_id': company_id},
        )

        # If most operations lack contact_email, fall back to customer_name as grouping key
        ops_with_email = [o for o in ops if o.get('contact_email')]
        if len(ops_with_email) < len(ops) * 0.3 and ops:
            # Use customer_name as a proxy group — at least shows capability data
            for op in ops:
                if not op.get('contact_email'):
                    op['contact_email'] = op.get('customer_name') or 'Unknown'

        # Fetch contacts for this company (for name resolution)
        contacts_result = self._sb.table('customer_contacts').select(
            'id, email_address, first_name, last_name, full_name'
        ).eq('customer_company_id', company_id).execute()
        contacts_by_email = {}
        for c in (contacts_result.data or []):
            email = (c.get('email_address') or '').lower()
            if email:
                name = c.get('full_name') or f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
                contacts_by_email[email] = {'id': c['id'], 'name': name}

        # Build: {contact_email -> {capability_tag -> {count, revenue, last_date}}}
        contact_caps = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'revenue': 0, 'last_date': None}))

        # Also track process-level granular tags from QB
        contact_process_caps = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'revenue': 0, 'last_date': None}))

        for op in ops:
            email = (op.get('contact_email') or '').lower()
            if not email:
                continue

            # Prefer QB capability tag, fall back to classifier tags
            qb_cap = (op.get('qb_capability_tag') or '').strip()
            raw_tags = op.get('capability_tags') or []
            if isinstance(raw_tags, str):
                import json as _json
                try:
                    raw_tags = _json.loads(raw_tags)
                except (ValueError, TypeError):
                    raw_tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
            classifier_tags = raw_tags if isinstance(raw_tags, list) else []
            tags = [qb_cap] if qb_cap else [t for t in classifier_tags if t and len(t) > 1]
            if not tags:
                continue

            price = float(op.get('cost_plus_price') or 0)
            date_str = op.get('date_accepted')

            for tag in tags:
                entry = contact_caps[email][tag]
                entry['count'] += 1
                entry['revenue'] += price
                if date_str:
                    if not entry['last_date'] or str(date_str) > str(entry['last_date']):
                        entry['last_date'] = str(date_str)

            # Track granular process tag from QB
            process_tag = (op.get('qb_process_tag') or '').strip()
            if process_tag:
                entry = contact_process_caps[email][process_tag]
                entry['count'] += 1
                entry['revenue'] += price
                if date_str:
                    if not entry['last_date'] or str(date_str) > str(entry['last_date']):
                        entry['last_date'] = str(date_str)

        # Build output
        contacts_list = []
        for email, caps in contact_caps.items():
            contact_info = contacts_by_email.get(email, {})
            capabilities = sorted([
                {
                    'tag': tag,
                    'order_count': data['count'],
                    'total_revenue': round(data['revenue'], 2),
                    'last_order': data['last_date'],
                }
                for tag, data in caps.items()
            ], key=lambda x: x['order_count'], reverse=True)

            primary = capabilities[0]['tag'] if capabilities else None

            # Granular process capabilities from QB
            process_data = contact_process_caps.get(email, {})
            process_capabilities = sorted([
                {'tag': tag, 'order_count': d['count'], 'total_revenue': round(d['revenue'], 2), 'last_order': d['last_date']}
                for tag, d in process_data.items()
            ], key=lambda x: x['order_count'], reverse=True)

            contacts_list.append({
                'contact_id': contact_info.get('id'),
                'contact_name': contact_info.get('name', email),
                'contact_email': email,
                'capabilities': capabilities,
                'process_capabilities': process_capabilities,
                'primary_capability': primary,
            })

        contacts_list.sort(key=lambda x: sum(c['order_count'] for c in x['capabilities']), reverse=True)

        result = {'contacts': contacts_list}
        self._save_cache(company_id, 'contact_capability_profile', result)
        return result

    # ------------------------------------------------------------------
    # Feature 2: Seasonality Trends
    # ------------------------------------------------------------------

    def get_seasonality(self, company_id: str, force: bool = False) -> dict:
        """Multi-year seasonality with year-over-year breakdown, outreach windows,
        and YTD comparison. Uses DB-side aggregation via get_company_seasonality RPC.
        """
        if not force:
            cached = self._get_cached(company_id, 'seasonality_profile')
            if cached:
                return cached

        # Single RPC call replaces the old _fetch_all_paginated loop
        try:
            resp = self._sb.rpc('get_company_seasonality', {
                'p_company_id': company_id,
                'p_client_id': self._client_id,
            }).execute()
            raw = resp.data
            if isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
                rows = raw[0]  # Unwrap [[...]] from JSONB
            elif isinstance(raw, list):
                rows = raw
            else:
                rows = []
        except Exception as e:
            logger.warning(f"Seasonality RPC failed for {company_id}: {e}")
            rows = []

        if not rows:
            result = {
                'monthly': [], 'quarterly': [], 'yearly': {},
                'peak_months': [], 'trough_months': [],
                'outreach_windows': [], 'ytd_comparison': None,
                'total_orders': 0, 'date_range': None,
            }
            self._save_cache(company_id, 'seasonality_profile', result)
            return result

        # Build year-over-year breakdown
        yearly: dict[int, list] = {}
        monthly_agg = defaultdict(lambda: {'order_count': 0, 'revenue': 0.0})
        quarterly_agg = defaultdict(lambda: {'order_count': 0, 'revenue': 0.0})
        total_orders = 0
        all_years = set()

        for r in rows:
            yr = int(r.get('year', 0))
            mo = int(r.get('month', 0))
            cnt = int(r.get('order_count', 0))
            rev = float(r.get('revenue', 0))
            if not yr or not mo:
                continue

            all_years.add(yr)
            total_orders += cnt

            # Per-year monthly data
            if yr not in yearly:
                yearly[yr] = []
            yearly[yr].append({
                'month': mo,
                'month_name': MONTH_NAMES[mo],
                'order_count': cnt,
                'revenue': rev,
            })

            # Aggregate across all years
            monthly_agg[mo]['order_count'] += cnt
            monthly_agg[mo]['revenue'] += rev

            quarter = (mo - 1) // 3 + 1
            quarterly_agg[quarter]['order_count'] += cnt
            quarterly_agg[quarter]['revenue'] += rev

        # Sort each year's months
        for yr in yearly:
            yearly[yr].sort(key=lambda x: x['month'])

        # Build monthly output (all-years aggregate)
        monthly_list = []
        for m in range(1, 13):
            data = monthly_agg.get(m)
            if data and data['order_count'] > 0:
                monthly_list.append({
                    'month': m,
                    'month_name': MONTH_NAMES[m],
                    'order_count': data['order_count'],
                    'revenue': round(data['revenue'], 2),
                })

        # Peak/trough detection
        import statistics
        counts = [m['order_count'] for m in monthly_list if m['order_count'] > 0]
        if len(counts) >= 3:
            mean = statistics.mean(counts)
            stdev = statistics.stdev(counts) if len(counts) > 1 else 0
            threshold = max(stdev * 0.5, mean * 0.15)
            peak_months = [m['month'] for m in monthly_list if m['order_count'] > mean + threshold]
            trough_months = [m['month'] for m in monthly_list if 0 < m['order_count'] < mean - threshold]
        else:
            peak_months = []
            trough_months = []

        # Quarterly
        quarterly_list = sorted([
            {'quarter': q, 'order_count': d['order_count'], 'revenue': round(d['revenue'], 2)}
            for q, d in quarterly_agg.items()
        ], key=lambda x: x['quarter'])

        # Outreach windows — 4-6 weeks before each peak month
        now = datetime.now(timezone.utc)
        current_month = now.month
        current_year = now.year
        num_years = len(all_years) if all_years else 1
        outreach_windows = []
        for pm in peak_months:
            # Approach window = 1-2 months before the peak
            approach_month = pm - 1 if pm > 1 else 12
            approach_year = current_year if approach_month >= current_month else current_year + 1
            approach_start = date(approach_year, approach_month, 1)
            approach_end = date(approach_year, approach_month, 28)  # Safe end-of-month

            avg_peak_revenue = round(monthly_agg[pm]['revenue'] / num_years, 2)
            outreach_windows.append({
                'peak_month': pm,
                'peak_month_name': MONTH_NAMES[pm],
                'approach_month': approach_month,
                'approach_month_name': MONTH_NAMES[approach_month],
                'approach_start': approach_start.isoformat(),
                'approach_end': approach_end.isoformat(),
                'avg_peak_revenue': avg_peak_revenue,
                'avg_peak_orders': round(monthly_agg[pm]['order_count'] / num_years, 1),
                'is_approaching': approach_month == current_month or (
                    approach_month == current_month + 1 and now.day >= 15
                ),
            })

        # YTD comparison — current year vs prior year
        sorted_years = sorted(all_years, reverse=True)
        ytd_comparison = None
        if len(sorted_years) >= 2:
            cy = sorted_years[0]
            py = sorted_years[1]
            cy_months = {r['month']: r for r in (yearly.get(cy) or [])}
            py_months = {r['month']: r for r in (yearly.get(py) or [])}
            # Only compare up to current month
            max_month = current_month if cy == current_year else 12
            cy_rev = sum(cy_months.get(m, {}).get('revenue', 0) for m in range(1, max_month + 1))
            py_rev = sum(py_months.get(m, {}).get('revenue', 0) for m in range(1, max_month + 1))
            growth_pct = round((cy_rev - py_rev) / py_rev * 100, 1) if py_rev > 0 else 0
            ytd_comparison = {
                'current_year': cy,
                'prior_year': py,
                'current_ytd_revenue': round(cy_rev, 2),
                'prior_ytd_revenue': round(py_rev, 2),
                'growth_pct': growth_pct,
                'months_compared': max_month,
            }

        # Date range
        min_yr = min(all_years) if all_years else None
        max_yr = max(all_years) if all_years else None
        date_range = {'earliest_year': min_yr, 'latest_year': max_yr} if min_yr else None

        result = {
            'monthly': monthly_list,
            'quarterly': quarterly_list,
            'yearly': {str(yr): data for yr, data in sorted(yearly.items())},
            'peak_months': peak_months,
            'trough_months': trough_months,
            'outreach_windows': outreach_windows,
            'ytd_comparison': ytd_comparison,
            'total_orders': total_orders,
            'date_range': date_range,
        }
        self._save_cache(company_id, 'seasonality_profile', result)
        return result

    # ------------------------------------------------------------------
    # Feature 4: Capability Ordering Rhythm
    # ------------------------------------------------------------------

    def get_capability_rhythm(self, company_id: str, force: bool = False) -> dict:
        """Per-capability avg order interval + overdue detection."""
        if not force:
            cached = self._get_cached(company_id, 'capability_rhythm')
            if cached:
                return cached

        ops = self._fetch_all_paginated(
            'qb_operations',
            'capability_tags, qb_capability_tag, date_accepted',
            {'matched_company_id': company_id},
            extra_filters=[
                ('not_.is_', 'date_accepted', 'null'),
            ],
        )

        if not ops:
            result = {'rhythms': [], 'alerts': []}
            self._save_cache(company_id, 'capability_rhythm', result)
            return result

        # Collect dates per capability tag — prefer QB tag, fall back to classifier
        tag_dates = defaultdict(list)
        for op in ops:
            da = op.get('date_accepted')
            if not da:
                continue

            qb_cap = (op.get('qb_capability_tag') or '').strip()
            raw_tags = op.get('capability_tags') or []
            if isinstance(raw_tags, str):
                import json as _json
                try:
                    raw_tags = _json.loads(raw_tags)
                except (ValueError, TypeError):
                    raw_tags = [t.strip() for t in raw_tags.split(',') if t.strip()]
            classifier_tags = raw_tags if isinstance(raw_tags, list) else []
            tags = [qb_cap] if qb_cap else [t for t in classifier_tags if t and len(t) > 1]
            if not tags:
                continue

            try:
                d = datetime.strptime(str(da)[:10], '%Y-%m-%d').date()
                for tag in tags:
                    if len(tag.strip()) > 1:  # Skip stray characters like '[', ']'
                        tag_dates[tag.strip()].append(d)
            except (ValueError, TypeError):
                continue

        today = date.today()
        rhythms = []
        alerts = []

        for tag, dates_list in tag_dates.items():
            dates_sorted = sorted(set(dates_list))  # dedupe same-day ops
            order_count = len(dates_sorted)

            if order_count < 2:
                # Not enough data to compute interval
                last_date = dates_sorted[-1] if dates_sorted else None
                days_since = (today - last_date).days if last_date else None
                rhythms.append({
                    'capability': tag,
                    'order_count': order_count,
                    'avg_interval_days': None,
                    'last_order_date': str(last_date) if last_date else None,
                    'days_since_last': days_since,
                    'overdue': False,
                    'overdue_days': 0,
                    'status': 'insufficient_data',
                    'message': f'Only {order_count} order(s) — need ≥2 to detect rhythm.',
                })
                continue

            # Compute intervals between consecutive orders
            intervals = [(dates_sorted[i+1] - dates_sorted[i]).days for i in range(len(dates_sorted) - 1)]
            # Filter out same-day (0) and very short intervals (< 7 days) that are likely same-job ops
            meaningful = [iv for iv in intervals if iv >= 7]
            if not meaningful:
                meaningful = intervals  # fall back to all

            avg_interval = sum(meaningful) / len(meaningful)
            last_date = dates_sorted[-1]
            days_since = (today - last_date).days
            overdue_threshold = avg_interval * 1.3
            overdue = days_since > overdue_threshold
            overdue_days = max(0, round(days_since - avg_interval))

            status = 'overdue' if overdue else ('due_soon' if days_since > avg_interval * 0.9 else 'on_track')

            interval_weeks = round(avg_interval / 7)
            interval_desc = f"{interval_weeks} weeks" if interval_weeks > 0 else f"{round(avg_interval)} days"
            message = f"Usually orders every {interval_desc}. Last order was {days_since} days ago"
            if overdue:
                message += f" ({overdue_days} days overdue)."
            else:
                message += "."

            rhythms.append({
                'capability': tag,
                'order_count': order_count,
                'avg_interval_days': round(avg_interval),
                'last_order_date': str(last_date),
                'days_since_last': days_since,
                'overdue': overdue,
                'overdue_days': overdue_days,
                'status': status,
                'message': message,
            })

            if overdue:
                alerts.append({
                    'capability': tag,
                    'overdue_days': overdue_days,
                    'severity': 'danger' if overdue_days > avg_interval * 0.5 else 'warning',
                })

        # Sort: overdue first, then by order count
        rhythms.sort(key=lambda x: (-x['overdue_days'], -x['order_count']))
        alerts.sort(key=lambda x: -x['overdue_days'])

        result = {'rhythms': rhythms, 'alerts': alerts}
        self._save_cache(company_id, 'capability_rhythm', result)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_all_paginated(
        self, table: str, select: str, eq_filters: dict,
        extra_filters: list = None, page_size: int = 1000,
        max_rows: int = 50000,
    ) -> list:
        """Fetch rows from a table with pagination (capped at max_rows)."""
        all_rows = []
        offset = 0
        while len(all_rows) < max_rows:
            remaining = min(page_size, max_rows - len(all_rows))
            query = self._sb.table(table).select(select)
            query = query.eq('client_id', self._client_id)
            for col, val in eq_filters.items():
                query = query.eq(col, val)
            if extra_filters:
                for method, col, val in extra_filters:
                    if method == 'neq':
                        query = query.neq(col, val)
                    elif method == 'not_.is_':
                        query = query.not_.is_(col, val)
            query = query.range(offset, offset + remaining - 1)
            result = query.execute()
            rows = result.data or []
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < remaining:
                break
            offset += len(rows)
        return all_rows
