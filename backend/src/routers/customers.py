"""
Customer Companies API Router

CRUD endpoints for managing customer companies.

Stage 2 Phase 2 - Business Hierarchy Implementation
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from ..models.customer import (
    CustomerCompanyCreate,
    CustomerCompanyUpdate,
    CustomerCompanyResponse,
    CustomerCompanyWithContacts,
    CustomerCompanySummary,
    CustomerCompanyListResponse,
    ContactSummary,
)

logger = logging.getLogger(__name__)


def _sanitize_search(term: str) -> str:
    """Escape SQL ILIKE wildcards in user-supplied search terms."""
    return term.replace('%', r'\%').replace('_', r'\_')

router = APIRouter(prefix="/customers", tags=["customers"])

# Supabase client will be injected from main.py
_supabase = None


def init_customers_router(supabase_client):
    """Initialize the router with Supabase client"""
    global _supabase
    _supabase = supabase_client


def calculate_engagement_status(last_contact_date: Optional[datetime]) -> str:
    """Calculate engagement status based on last contact date"""
    if not last_contact_date:
        return 'unknown'

    if isinstance(last_contact_date, str):
        last_contact_date = datetime.fromisoformat(last_contact_date.replace('Z', '+00:00'))

    now = datetime.now(last_contact_date.tzinfo) if last_contact_date.tzinfo else datetime.now()

    days_since = (now - last_contact_date).days

    if days_since <= 30:
        return 'active'
    elif days_since <= 90:
        return 'quiet'
    else:
        return 'at_risk'


@router.post("/", response_model=CustomerCompanyResponse)
async def create_customer_company(data: CustomerCompanyCreate):
    """
    Create a new customer company.

    Args:
        data: Customer company creation data

    Returns:
        Created customer company record
    """
    try:
        # Validate client_id
        client_check = _supabase.table('clients').select('id').eq(
            'id', data.client_id
        ).execute()
        if not client_check.data:
            raise HTTPException(status_code=400, detail="Client not found")

        # Check for duplicate company name within client
        existing = _supabase.table('customer_companies').select('id').eq(
            'client_id', data.client_id
        ).eq('company_name', data.company_name).execute()

        if existing.data:
            raise HTTPException(
                status_code=400,
                detail=f"Customer company '{data.company_name}' already exists for this client"
            )

        # Create customer company
        insert_data = {
            'client_id': data.client_id,
            'company_name': data.company_name,
            'email_domains': data.email_domains,
            'industry': data.industry,
            'website': data.website,
            'notes': data.notes,
        }

        result = _supabase.table('customer_companies').insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create customer company")

        return CustomerCompanyResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create customer company: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=CustomerCompanyListResponse)
async def list_customer_companies(
    client_id: Optional[str] = Query(default=None),
    engagement_status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List customer companies with optional filters.

    Args:
        client_id: Filter by client
        engagement_status: Filter by engagement status (active, quiet, at_risk)
        search: Search by company name
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of customer company summaries
    """
    try:
        # Build query
        query = _supabase.table('customer_companies').select(
            '''
            id, company_name, client_id, email_domains, industry,
            first_contact_date, last_contact_date, total_emails,
            created_at,
            clients(client_name)
            '''
        )

        if client_id:
            query = query.eq('client_id', client_id)

        if search:
            query = query.ilike('company_name', f'%{_sanitize_search(search)}%')

        result = query.order('company_name').range(offset, offset + limit - 1).execute()

        # Process results and calculate engagement status
        companies = []
        for c in result.data:
            engagement = calculate_engagement_status(c.get('last_contact_date'))

            # Filter by engagement status if specified
            if engagement_status and engagement != engagement_status:
                continue

            # Get contact count
            ct_result = _supabase.table('customer_contacts').select(
                'id', count='exact'
            ).eq('customer_company_id', c['id']).execute()
            ct_count = ct_result.count if ct_result.count else len(ct_result.data)

            client_name = None
            if c.get('clients'):
                client_name = c['clients'].get('client_name')

            companies.append(CustomerCompanySummary(
                id=c['id'],
                company_name=c['company_name'],
                client_id=c['client_id'],
                client_name=client_name,
                email_domains=c.get('email_domains', []),
                industry=c.get('industry'),
                first_contact_date=c.get('first_contact_date'),
                last_contact_date=c.get('last_contact_date'),
                total_emails=c.get('total_emails', 0),
                contact_count=ct_count,
                engagement_status=engagement
            ))

        # Get total count
        count_query = _supabase.table('customer_companies').select('id', count='exact')
        if client_id:
            count_query = count_query.eq('client_id', client_id)
        if search:
            count_query = count_query.ilike('company_name', f'%{_sanitize_search(search)}%')
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return CustomerCompanyListResponse(
            customer_companies=companies,
            total=total
        )

    except Exception as e:
        logger.error(f"Failed to list customer companies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{company_id}", response_model=CustomerCompanyWithContacts)
async def get_customer_company(company_id: str):
    """
    Get customer company details with contacts.

    Args:
        company_id: UUID of the customer company

    Returns:
        Customer company with contact list
    """
    try:
        # Get customer company
        result = _supabase.table('customer_companies').select(
            '''
            id, client_id, company_name, email_domains, industry, website,
            first_contact_date, last_contact_date, total_emails, total_inbound, total_outbound,
            notes, created_at, updated_at
            '''
        ).eq('id', company_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Customer company not found")

        c = result.data

        # Get contacts
        contacts_result = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, job_title,
            total_emails_sent, total_emails_received, last_contacted_at
            '''
        ).eq('customer_company_id', company_id).order('full_name').execute()

        contacts = [
            ContactSummary(
                id=ct['id'],
                email_address=ct['email_address'],
                full_name=ct.get('full_name'),
                job_title=ct.get('job_title'),
                total_emails_sent=ct.get('total_emails_sent', 0),
                total_emails_received=ct.get('total_emails_received', 0),
                last_contacted_at=ct.get('last_contacted_at')
            )
            for ct in contacts_result.data
        ]

        return CustomerCompanyWithContacts(
            id=c['id'],
            client_id=c['client_id'],
            company_name=c['company_name'],
            email_domains=c.get('email_domains', []),
            industry=c.get('industry'),
            website=c.get('website'),
            notes=c.get('notes'),
            first_contact_date=c.get('first_contact_date'),
            last_contact_date=c.get('last_contact_date'),
            total_emails=c.get('total_emails', 0),
            total_inbound=c.get('total_inbound', 0),
            total_outbound=c.get('total_outbound', 0),
            created_at=c['created_at'],
            updated_at=c['updated_at'],
            contacts=contacts,
            contact_count=len(contacts)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get customer company: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{company_id}", response_model=CustomerCompanyResponse)
async def update_customer_company(company_id: str, data: CustomerCompanyUpdate):
    """
    Update a customer company.

    Args:
        company_id: UUID of the customer company
        data: Fields to update

    Returns:
        Updated customer company record
    """
    try:
        # Check if exists
        existing = _supabase.table('customer_companies').select('id, client_id').eq(
            'id', company_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Customer company not found")

        # Build update data
        update_data = {}
        if data.company_name is not None:
            # Check for duplicate name
            dup_check = _supabase.table('customer_companies').select('id').eq(
                'client_id', existing.data['client_id']
            ).eq('company_name', data.company_name).neq('id', company_id).execute()
            if dup_check.data:
                raise HTTPException(
                    status_code=400,
                    detail=f"Company name '{data.company_name}' already exists for this client"
                )
            update_data['company_name'] = data.company_name

        if data.email_domains is not None:
            update_data['email_domains'] = data.email_domains
        if data.industry is not None:
            update_data['industry'] = data.industry
        if data.website is not None:
            update_data['website'] = data.website
        if data.notes is not None:
            update_data['notes'] = data.notes

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = _supabase.table('customer_companies').update(
            update_data
        ).eq('id', company_id).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update customer company")

        return CustomerCompanyResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update customer company: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{company_id}")
async def delete_customer_company(company_id: str):
    """
    Delete a customer company.

    Warning: This will cascade delete all contacts associated with this company.

    Args:
        company_id: UUID of the customer company

    Returns:
        Success message
    """
    try:
        # Check if exists
        existing = _supabase.table('customer_companies').select('id, company_name').eq(
            'id', company_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Customer company not found")

        # Delete (cascade will handle contacts)
        _supabase.table('customer_companies').delete().eq('id', company_id).execute()

        return {
            "message": f"Customer company '{existing.data['company_name']}' deleted successfully",
            "id": company_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete customer company: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{company_id}/add-domain")
async def add_email_domain(company_id: str, domain: str = Query(...)):
    """
    Add an email domain to a customer company.

    Args:
        company_id: UUID of the customer company
        domain: Email domain to add (e.g., "acme.com")

    Returns:
        Updated list of domains
    """
    try:
        # Get current domains
        result = _supabase.table('customer_companies').select(
            'id, email_domains'
        ).eq('id', company_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Customer company not found")

        current_domains = result.data.get('email_domains', [])
        domain = domain.lower().strip()

        if domain in current_domains:
            raise HTTPException(status_code=400, detail="Domain already exists")

        current_domains.append(domain)

        # Update
        update_result = _supabase.table('customer_companies').update({
            'email_domains': current_domains
        }).eq('id', company_id).execute()

        return {
            "company_id": company_id,
            "email_domains": current_domains
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add email domain: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{company_id}/remove-domain")
async def remove_email_domain(company_id: str, domain: str = Query(...)):
    """
    Remove an email domain from a customer company.

    Args:
        company_id: UUID of the customer company
        domain: Email domain to remove

    Returns:
        Updated list of domains
    """
    try:
        # Get current domains
        result = _supabase.table('customer_companies').select(
            'id, email_domains'
        ).eq('id', company_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Customer company not found")

        current_domains = result.data.get('email_domains', [])
        domain = domain.lower().strip()

        if domain not in current_domains:
            raise HTTPException(status_code=400, detail="Domain not found")

        current_domains.remove(domain)

        # Update
        _supabase.table('customer_companies').update({
            'email_domains': current_domains
        }).eq('id', company_id).execute()

        return {
            "company_id": company_id,
            "email_domains": current_domains
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove email domain: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{company_id}/refresh-engagement")
async def refresh_engagement_metrics(company_id: str):
    """
    Refresh engagement metrics for a customer company.

    Recalculates total_emails, first_contact_date, last_contact_date.

    Args:
        company_id: UUID of the customer company

    Returns:
        Updated engagement metrics
    """
    try:
        # Check if exists
        existing = _supabase.table('customer_companies').select('id').eq(
            'id', company_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Customer company not found")

        # Use database function to update engagement
        _supabase.rpc(
            'update_customer_engagement',
            {'p_customer_company_id': company_id}
        ).execute()

        # Get updated data
        result = _supabase.table('customer_companies').select(
            'total_emails, total_inbound, total_outbound, first_contact_date, last_contact_date'
        ).eq('id', company_id).single().execute()

        return {
            "company_id": company_id,
            "metrics": result.data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh engagement metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Sprint 4: Sales Intelligence endpoints
# ---------------------------------------------------------------------------

@router.get("/{company_id}/order-history")
async def get_order_history(
    company_id: str,
    limit: int = Query(50, ge=1, le=200),
):
    """
    Merged timeline of quotes + jobs for a company, sorted by date descending.
    Used by the Order History section of the Customer Profile page.
    """
    try:
        # Resolve QB customer record IDs for this company
        cust_result = _supabase.table('qb_customers').select(
            'qb_record_id, client_id'
        ).eq('matched_company_id', company_id).execute()

        if not cust_result.data:
            return {'items': [], 'company_id': company_id}

        qb_record_ids = [r['qb_record_id'] for r in cust_result.data if r.get('qb_record_id')]
        client_id = cust_result.data[0]['client_id']

        if not qb_record_ids:
            return {'items': [], 'company_id': company_id}

        # Fetch quotes
        quotes_result = _supabase.table('qb_quotes').select(
            'quote_no, date_created, category, sell_ex_tax, contact_name, contact_email, has_job, job_no'
        ).in_('qb_customer_id', qb_record_ids).eq('client_id', client_id).execute()

        # Fetch jobs
        jobs_result = _supabase.table('qb_jobs').select(
            'job_no, accepted_date, due_date, job_status, invoiced_margin, quote_no'
        ).in_('qb_customer_id', qb_record_ids).eq('client_id', client_id).execute()

        items = []

        for q in (quotes_result.data or []):
            items.append({
                'type': 'quote',
                'date': q.get('date_created'),
                'ref_no': q.get('quote_no'),
                'category': q.get('category'),
                'value': q.get('sell_ex_tax'),
                'status': 'Accepted' if q.get('has_job') else 'Quoted',
                'contact_name': q.get('contact_name'),
                'contact_email': q.get('contact_email'),
                'job_no': q.get('job_no'),
            })

        for j in (jobs_result.data or []):
            items.append({
                'type': 'job',
                'date': j.get('accepted_date'),
                'ref_no': j.get('job_no'),
                'category': None,
                'value': j.get('invoiced_margin'),
                'status': j.get('job_status'),
                'contact_name': None,
                'contact_email': None,
                'job_no': j.get('job_no'),
                'due_date': j.get('due_date'),
                'quote_no': j.get('quote_no'),
            })

        # Sort by date descending (None dates go last)
        items.sort(key=lambda x: x.get('date') or '', reverse=True)

        return {'items': items[:limit], 'company_id': company_id, 'total': len(items)}

    except Exception as e:
        logger.error(f"Failed to get order history for {company_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{company_id}/product-profile")
async def get_product_profile(company_id: str):
    """
    Product categories (revenue by group) and operations used by a company.
    Used by the Product Profile section of the Customer Profile page.
    """
    try:
        from ..services.recommendation_engine import RecommendationEngine

        # Resolve client_id
        cust_result = _supabase.table('qb_customers').select(
            'client_id'
        ).eq('matched_company_id', company_id).limit(1).execute()

        client_id = cust_result.data[0]['client_id'] if cust_result.data else None
        if not client_id:
            # Fall back to company's client_id
            co_result = _supabase.table('customer_companies').select(
                'client_id'
            ).eq('id', company_id).limit(1).execute()
            client_id = co_result.data[0]['client_id'] if co_result.data else None

        if not client_id:
            return {'categories': [], 'operations': [], 'company_id': company_id}

        engine = RecommendationEngine(_supabase, client_id)
        profile = engine.get_product_profile(company_id)
        profile['company_id'] = company_id
        return profile

    except Exception as e:
        logger.error(f"Failed to get product profile for {company_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{company_id}/recommendations")
async def get_recommendations(
    company_id: str,
    force: bool = Query(False, description="Bypass 24h cache and recompute"),
):
    """
    Sales recommendations for a company: cross-contact gaps (Level 1) and
    related product opportunities (Level 2). Cached 24h.
    """
    try:
        from ..services.recommendation_engine import RecommendationEngine

        # Resolve client_id
        co_result = _supabase.table('customer_companies').select(
            'client_id'
        ).eq('id', company_id).limit(1).execute()

        if not co_result.data:
            raise HTTPException(status_code=404, detail="Company not found")

        client_id = co_result.data[0]['client_id']
        engine = RecommendationEngine(_supabase, client_id)
        result = engine.get_recommendations(company_id, force=force)
        result['company_id'] = company_id
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recommendations for {company_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Customer Analytics (Phase 2) ────────────────────────────────────────────

def _resolve_company_client(company_id: str) -> str:
    """Resolve client_id from company_id. Raises 404 if not found."""
    co_result = _supabase.table('customer_companies').select(
        'client_id'
    ).eq('id', company_id).limit(1).execute()
    if not co_result.data:
        raise HTTPException(status_code=404, detail="Company not found")
    return co_result.data[0]['client_id']


@router.get("/{company_id}/strike-rate")
async def get_strike_rate(
    company_id: str,
    force: bool = Query(False, description="Bypass 24h cache"),
):
    """Quote conversion rate — company total + per-contact breakdown."""
    try:
        from ..services.customer_analytics_service import CustomerAnalyticsService
        client_id = _resolve_company_client(company_id)
        svc = CustomerAnalyticsService(_supabase, client_id)
        result = svc.get_strike_rate(company_id, force=force)
        result['company_id'] = company_id
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get strike rate for {company_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{company_id}/contact-capabilities")
async def get_contact_capabilities(
    company_id: str,
    force: bool = Query(False, description="Bypass 24h cache"),
):
    """Which contacts order which capabilities — per-contact capability tags."""
    try:
        from ..services.customer_analytics_service import CustomerAnalyticsService
        client_id = _resolve_company_client(company_id)
        svc = CustomerAnalyticsService(_supabase, client_id)
        result = svc.get_contact_capabilities(company_id, force=force)
        result['company_id'] = company_id
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get contact capabilities for {company_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{company_id}/seasonality")
async def get_seasonality(
    company_id: str,
    force: bool = Query(False, description="Bypass 24h cache"),
):
    """Monthly/quarterly ordering patterns from QB operations."""
    try:
        from ..services.customer_analytics_service import CustomerAnalyticsService
        client_id = _resolve_company_client(company_id)
        svc = CustomerAnalyticsService(_supabase, client_id)
        result = svc.get_seasonality(company_id, force=force)
        result['company_id'] = company_id
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get seasonality for {company_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{company_id}/capability-rhythm")
async def get_capability_rhythm(
    company_id: str,
    force: bool = Query(False, description="Bypass 24h cache"),
):
    """Per-capability ordering rhythm — avg interval + overdue detection."""
    try:
        from ..services.customer_analytics_service import CustomerAnalyticsService
        client_id = _resolve_company_client(company_id)
        svc = CustomerAnalyticsService(_supabase, client_id)
        result = svc.get_capability_rhythm(company_id, force=force)
        result['company_id'] = company_id
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get capability rhythm for {company_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
