"""
Customer Contacts API Router

CRUD endpoints for managing customer contacts.

Stage 2 Phase 2 - Business Hierarchy Implementation
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging

from ..models.contact import (
    ContactCreate,
    ContactUpdate,
    ContactResponse,
    ContactWithCompany,
    CompanyInfo,
    ContactSummary,
    ContactListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contacts", tags=["contacts"])

# Supabase client will be injected from main.py
_supabase = None


def init_contacts_router(supabase_client):
    """Initialize the router with Supabase client"""
    global _supabase
    _supabase = supabase_client


@router.post("/", response_model=ContactResponse)
async def create_contact(data: ContactCreate):
    """
    Create a new customer contact.

    Args:
        data: Contact creation data

    Returns:
        Created contact record
    """
    try:
        # Validate customer_company_id
        company_check = _supabase.table('customer_companies').select('id, client_id').eq(
            'id', data.customer_company_id
        ).execute()
        if not company_check.data:
            raise HTTPException(status_code=400, detail="Customer company not found")

        # Check for duplicate email within company
        existing = _supabase.table('customer_contacts').select('id').eq(
            'customer_company_id', data.customer_company_id
        ).eq('email_address', data.email_address.lower()).execute()

        if existing.data:
            raise HTTPException(
                status_code=400,
                detail=f"Contact with email '{data.email_address}' already exists for this company"
            )

        # Create contact
        insert_data = {
            'customer_company_id': data.customer_company_id,
            'client_id': data.client_id,
            'email_address': data.email_address.lower(),
            'full_name': data.full_name,
            'first_name': data.first_name,
            'last_name': data.last_name,
            'job_title': data.job_title,
            'company_name': data.company_name,
            'phone_number': data.phone_number,
            'mobile_number': data.mobile_number,
            'linkedin_url': data.linkedin_url,
            'notes': data.notes,
        }

        result = _supabase.table('customer_contacts').insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create contact")

        return ContactResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=ContactListResponse)
async def list_contacts(
    client_id: Optional[str] = Query(default=None),
    customer_company_id: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List customer contacts with optional filters.

    Args:
        client_id: Filter by client
        customer_company_id: Filter by customer company
        search: Search by name or email
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of contact summaries
    """
    try:
        # Build query
        query = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, job_title, company_name,
            customer_company_id, client_id, last_contacted_at,
            total_emails_sent, total_emails_received,
            customer_companies(company_name)
            '''
        )

        if client_id:
            query = query.eq('client_id', client_id)
        if customer_company_id:
            query = query.eq('customer_company_id', customer_company_id)

        result = query.order('full_name').range(offset, offset + limit - 1).execute()

        # Filter by search if provided (post-query filtering for flexibility)
        contacts = []
        for c in result.data:
            if search:
                search_lower = search.lower()
                full_name = (c.get('full_name') or '').lower()
                email = (c.get('email_address') or '').lower()
                if search_lower not in full_name and search_lower not in email:
                    continue

            company_name = None
            if c.get('customer_companies'):
                company_name = c['customer_companies'].get('company_name')

            total_emails = (c.get('total_emails_sent', 0) or 0) + (c.get('total_emails_received', 0) or 0)

            contacts.append(ContactSummary(
                id=c['id'],
                email_address=c['email_address'],
                full_name=c.get('full_name'),
                job_title=c.get('job_title'),
                company_name=c.get('company_name') or company_name,
                customer_company_id=c.get('customer_company_id'),
                customer_company_name=company_name,
                client_id=c.get('client_id'),
                last_contacted_at=c.get('last_contacted_at'),
                total_emails=total_emails
            ))

        # Get total count
        count_query = _supabase.table('customer_contacts').select('id', count='exact')
        if client_id:
            count_query = count_query.eq('client_id', client_id)
        if customer_company_id:
            count_query = count_query.eq('customer_company_id', customer_company_id)
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ContactListResponse(contacts=contacts, total=total)

    except Exception as e:
        logger.error(f"Failed to list contacts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-email")
async def find_contact_by_email(email: str = Query(...)):
    """
    Find a contact by email address.

    Args:
        email: Email address to search for

    Returns:
        Contact with company info if found
    """
    try:
        result = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, first_name, last_name,
            job_title, company_name, phone_number, mobile_number, linkedin_url,
            customer_company_id, client_id,
            first_contacted_at, last_contacted_at,
            total_emails_sent, total_emails_received,
            signature_data, signature_last_updated,
            created_at, updated_at,
            customer_companies(id, company_name, client_id, clients(client_name))
            '''
        ).eq('email_address', email.lower()).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        c = result.data
        company_info = None
        if c.get('customer_companies'):
            cc = c['customer_companies']
            client_name = cc.get('clients', {}).get('client_name') if cc.get('clients') else None
            company_info = CompanyInfo(
                id=cc['id'],
                company_name=cc['company_name'],
                client_id=cc['client_id'],
                client_name=client_name
            )

        return ContactWithCompany(
            id=c['id'],
            email_address=c['email_address'],
            full_name=c.get('full_name'),
            first_name=c.get('first_name'),
            last_name=c.get('last_name'),
            job_title=c.get('job_title'),
            company_name=c.get('company_name'),
            phone_number=c.get('phone_number'),
            mobile_number=c.get('mobile_number'),
            linkedin_url=c.get('linkedin_url'),
            notes=c.get('notes'),
            customer_company_id=c.get('customer_company_id'),
            client_id=c.get('client_id'),
            first_contacted_at=c.get('first_contacted_at'),
            last_contacted_at=c.get('last_contacted_at'),
            total_emails_sent=c.get('total_emails_sent', 0),
            total_emails_received=c.get('total_emails_received', 0),
            signature_data=c.get('signature_data'),
            signature_last_updated=c.get('signature_last_updated'),
            created_at=c['created_at'],
            updated_at=c['updated_at'],
            company_info=company_info
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to find contact by email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{contact_id}", response_model=ContactWithCompany)
async def get_contact(contact_id: str):
    """
    Get contact details with company information.

    Args:
        contact_id: UUID of the contact

    Returns:
        Contact with company info
    """
    try:
        result = _supabase.table('customer_contacts').select(
            '''
            id, email_address, full_name, first_name, last_name,
            job_title, company_name, phone_number, mobile_number, linkedin_url,
            customer_company_id, client_id, notes,
            first_contacted_at, last_contacted_at,
            total_emails_sent, total_emails_received,
            signature_data, signature_last_updated,
            created_at, updated_at,
            customer_companies(id, company_name, client_id, clients(client_name))
            '''
        ).eq('id', contact_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        c = result.data
        company_info = None
        if c.get('customer_companies'):
            cc = c['customer_companies']
            client_name = cc.get('clients', {}).get('client_name') if cc.get('clients') else None
            company_info = CompanyInfo(
                id=cc['id'],
                company_name=cc['company_name'],
                client_id=cc['client_id'],
                client_name=client_name
            )

        return ContactWithCompany(
            id=c['id'],
            email_address=c['email_address'],
            full_name=c.get('full_name'),
            first_name=c.get('first_name'),
            last_name=c.get('last_name'),
            job_title=c.get('job_title'),
            company_name=c.get('company_name'),
            phone_number=c.get('phone_number'),
            mobile_number=c.get('mobile_number'),
            linkedin_url=c.get('linkedin_url'),
            notes=c.get('notes'),
            customer_company_id=c.get('customer_company_id'),
            client_id=c.get('client_id'),
            first_contacted_at=c.get('first_contacted_at'),
            last_contacted_at=c.get('last_contacted_at'),
            total_emails_sent=c.get('total_emails_sent', 0),
            total_emails_received=c.get('total_emails_received', 0),
            signature_data=c.get('signature_data'),
            signature_last_updated=c.get('signature_last_updated'),
            created_at=c['created_at'],
            updated_at=c['updated_at'],
            company_info=company_info
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(contact_id: str, data: ContactUpdate):
    """
    Update a customer contact.

    Args:
        contact_id: UUID of the contact
        data: Fields to update

    Returns:
        Updated contact record
    """
    try:
        # Check if exists
        existing = _supabase.table('customer_contacts').select('id').eq(
            'id', contact_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        # Validate new customer_company_id if provided
        if data.customer_company_id:
            company_check = _supabase.table('customer_companies').select('id').eq(
                'id', data.customer_company_id
            ).execute()
            if not company_check.data:
                raise HTTPException(status_code=400, detail="Customer company not found")

        # Build update data
        update_data = {}
        if data.full_name is not None:
            update_data['full_name'] = data.full_name
        if data.first_name is not None:
            update_data['first_name'] = data.first_name
        if data.last_name is not None:
            update_data['last_name'] = data.last_name
        if data.job_title is not None:
            update_data['job_title'] = data.job_title
        if data.company_name is not None:
            update_data['company_name'] = data.company_name
        if data.phone_number is not None:
            update_data['phone_number'] = data.phone_number
        if data.mobile_number is not None:
            update_data['mobile_number'] = data.mobile_number
        if data.linkedin_url is not None:
            update_data['linkedin_url'] = data.linkedin_url
        if data.notes is not None:
            update_data['notes'] = data.notes
        if data.customer_company_id is not None:
            update_data['customer_company_id'] = data.customer_company_id

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = _supabase.table('customer_contacts').update(
            update_data
        ).eq('id', contact_id).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update contact")

        return ContactResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{contact_id}")
async def delete_contact(contact_id: str):
    """
    Delete a customer contact.

    Args:
        contact_id: UUID of the contact

    Returns:
        Success message
    """
    try:
        # Check if exists
        existing = _supabase.table('customer_contacts').select('id, email_address').eq(
            'id', contact_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        # Delete
        _supabase.table('customer_contacts').delete().eq('id', contact_id).execute()

        return {
            "message": f"Contact '{existing.data['email_address']}' deleted successfully",
            "id": contact_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete contact: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{contact_id}/update-signature")
async def update_contact_signature(contact_id: str, signature_data: dict):
    """
    Update contact signature data.

    Used by the signature parser to update parsed signature information.

    Args:
        contact_id: UUID of the contact
        signature_data: Parsed signature data

    Returns:
        Updated contact
    """
    try:
        from datetime import datetime

        # Check if exists
        existing = _supabase.table('customer_contacts').select('id').eq(
            'id', contact_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Contact not found")

        # Update signature and related fields
        update_data = {
            'signature_data': signature_data,
            'signature_last_updated': datetime.utcnow().isoformat(),
        }

        # Also update individual fields if present in signature
        if signature_data.get('full_name'):
            update_data['full_name'] = signature_data['full_name']
        if signature_data.get('job_title'):
            update_data['job_title'] = signature_data['job_title']
        if signature_data.get('phone'):
            update_data['phone_number'] = signature_data['phone']
        if signature_data.get('mobile'):
            update_data['mobile_number'] = signature_data['mobile']
        if signature_data.get('linkedin_url'):
            update_data['linkedin_url'] = signature_data['linkedin_url']
        if signature_data.get('company_name'):
            update_data['company_name'] = signature_data['company_name']

        result = _supabase.table('customer_contacts').update(
            update_data
        ).eq('id', contact_id).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update signature")

        return ContactResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update contact signature: {e}")
        raise HTTPException(status_code=500, detail=str(e))
