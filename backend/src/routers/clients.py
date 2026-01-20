"""
Clients API Router

CRUD endpoints for managing clients.

Stage 2 Phase 2 - Business Hierarchy Implementation
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import logging

from ..models.client import (
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientWithStats,
    ClientSummary,
    ClientListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["clients"])

# Supabase client will be injected from main.py
_supabase = None


def init_clients_router(supabase_client):
    """Initialize the router with Supabase client"""
    global _supabase
    _supabase = supabase_client


@router.post("/", response_model=ClientResponse)
async def create_client(data: ClientCreate):
    """
    Create a new client.

    Args:
        data: Client creation data

    Returns:
        Created client record
    """
    try:
        # Validate account_manager_id if provided
        if data.account_manager_id:
            am_check = _supabase.table('account_managers').select('id').eq(
                'id', data.account_manager_id
            ).execute()
            if not am_check.data:
                raise HTTPException(
                    status_code=400,
                    detail="Account manager not found"
                )

        # Create client
        insert_data = {
            'client_name': data.client_name,
            'client_label': data.client_label,
            'industry': data.industry,
            'status': data.status.value,
            'account_manager_id': data.account_manager_id,
            'notes': data.notes,
            'uses_quickbase': data.uses_quickbase,
            'quickbase_realm': data.quickbase_realm,
            'quickbase_api_token': data.quickbase_api_token,
            'uses_printiq': data.uses_printiq,
            'printiq_api_url': data.printiq_api_url,
            'printiq_api_key': data.printiq_api_key,
        }

        result = _supabase.table('clients').insert(insert_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create client")

        return ClientResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create client: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=ClientListResponse)
async def list_clients(
    account_manager_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List all clients with optional filters.

    Args:
        account_manager_id: Filter by account manager
        status: Filter by status (active, inactive, prospect)
        limit: Maximum number of results
        offset: Offset for pagination

    Returns:
        List of client summaries
    """
    try:
        # Build query for client data with account manager name
        query = _supabase.table('clients').select(
            '''
            id, client_name, client_label, status, industry,
            account_manager_id, created_at, updated_at,
            account_managers(name)
            '''
        )

        if account_manager_id:
            query = query.eq('account_manager_id', account_manager_id)
        if status:
            query = query.eq('status', status)

        result = query.order('client_name').range(offset, offset + limit - 1).execute()

        # Get counts for each client
        clients = []
        for c in result.data:
            # Get customer company count
            cc_result = _supabase.table('customer_companies').select(
                'id', count='exact'
            ).eq('client_id', c['id']).execute()
            cc_count = cc_result.count if cc_result.count else len(cc_result.data)

            # Get contact count
            ct_result = _supabase.table('customer_contacts').select(
                'id', count='exact'
            ).eq('client_id', c['id']).execute()
            ct_count = ct_result.count if ct_result.count else len(ct_result.data)

            # Get mailbox count
            mb_result = _supabase.table('mailboxes').select(
                'id', count='exact'
            ).eq('client_id', c['id']).execute()
            mb_count = mb_result.count if mb_result.count else len(mb_result.data)

            # Get email count
            email_result = _supabase.table('emails').select(
                'id', count='exact'
            ).eq('client_id', c['id']).execute()
            email_count = email_result.count if email_result.count else 0

            am_name = None
            if c.get('account_managers'):
                am_name = c['account_managers'].get('name')

            clients.append(ClientSummary(
                id=c['id'],
                client_name=c['client_name'],
                client_label=c.get('client_label'),
                status=c['status'],
                account_manager_name=am_name,
                customer_company_count=cc_count,
                contact_count=ct_count,
                mailbox_count=mb_count,
                total_emails=email_count
            ))

        # Get total count
        count_query = _supabase.table('clients').select('id', count='exact')
        if account_manager_id:
            count_query = count_query.eq('account_manager_id', account_manager_id)
        if status:
            count_query = count_query.eq('status', status)
        count_result = count_query.execute()
        total = count_result.count if count_result.count else len(count_result.data)

        return ClientListResponse(clients=clients, total=total)

    except Exception as e:
        logger.error(f"Failed to list clients: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{client_id}", response_model=ClientWithStats)
async def get_client(client_id: str):
    """
    Get client details with statistics.

    Args:
        client_id: UUID of the client

    Returns:
        Client with detailed statistics
    """
    try:
        # Get client with account manager
        result = _supabase.table('clients').select(
            '''
            id, client_name, client_label, status, industry, notes,
            account_manager_id, uses_quickbase, uses_printiq,
            created_at, updated_at,
            account_managers(name)
            '''
        ).eq('id', client_id).single().execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        c = result.data

        # Get statistics
        cc_result = _supabase.table('customer_companies').select(
            'id', count='exact'
        ).eq('client_id', client_id).execute()
        cc_count = cc_result.count if cc_result.count else len(cc_result.data)

        ct_result = _supabase.table('customer_contacts').select(
            'id', count='exact'
        ).eq('client_id', client_id).execute()
        ct_count = ct_result.count if ct_result.count else len(ct_result.data)

        mb_result = _supabase.table('mailboxes').select(
            'id', count='exact'
        ).eq('client_id', client_id).execute()
        mb_count = mb_result.count if mb_result.count else len(mb_result.data)

        email_result = _supabase.table('emails').select(
            'id', count='exact'
        ).eq('client_id', client_id).execute()
        email_count = email_result.count if email_result.count else 0

        rules_result = _supabase.table('customer_recognition_rules').select(
            'id', count='exact'
        ).eq('client_id', client_id).execute()
        rules_count = rules_result.count if rules_result.count else len(rules_result.data)

        am_name = None
        if c.get('account_managers'):
            am_name = c['account_managers'].get('name')

        return ClientWithStats(
            id=c['id'],
            client_name=c['client_name'],
            client_label=c.get('client_label'),
            status=c['status'],
            industry=c.get('industry'),
            notes=c.get('notes'),
            account_manager_id=c.get('account_manager_id'),
            uses_quickbase=c.get('uses_quickbase', False),
            uses_printiq=c.get('uses_printiq', False),
            created_at=c['created_at'],
            updated_at=c['updated_at'],
            account_manager_name=am_name,
            total_customer_companies=cc_count,
            total_customer_contacts=ct_count,
            total_mailboxes=mb_count,
            total_emails=email_count,
            total_rules=rules_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get client: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(client_id: str, data: ClientUpdate):
    """
    Update a client.

    Args:
        client_id: UUID of the client
        data: Fields to update

    Returns:
        Updated client record
    """
    try:
        # Check if exists
        existing = _supabase.table('clients').select('id').eq(
            'id', client_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Client not found")

        # Validate account_manager_id if provided
        if data.account_manager_id:
            am_check = _supabase.table('account_managers').select('id').eq(
                'id', data.account_manager_id
            ).execute()
            if not am_check.data:
                raise HTTPException(status_code=400, detail="Account manager not found")

        # Build update data
        update_data = {}
        if data.client_name is not None:
            update_data['client_name'] = data.client_name
        if data.client_label is not None:
            update_data['client_label'] = data.client_label
        if data.industry is not None:
            update_data['industry'] = data.industry
        if data.status is not None:
            update_data['status'] = data.status.value
        if data.account_manager_id is not None:
            update_data['account_manager_id'] = data.account_manager_id
        if data.notes is not None:
            update_data['notes'] = data.notes
        if data.uses_quickbase is not None:
            update_data['uses_quickbase'] = data.uses_quickbase
        if data.quickbase_realm is not None:
            update_data['quickbase_realm'] = data.quickbase_realm
        if data.quickbase_api_token is not None:
            update_data['quickbase_api_token'] = data.quickbase_api_token
        if data.uses_printiq is not None:
            update_data['uses_printiq'] = data.uses_printiq
        if data.printiq_api_url is not None:
            update_data['printiq_api_url'] = data.printiq_api_url
        if data.printiq_api_key is not None:
            update_data['printiq_api_key'] = data.printiq_api_key

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        result = _supabase.table('clients').update(
            update_data
        ).eq('id', client_id).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update client")

        return ClientResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update client: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{client_id}")
async def delete_client(client_id: str):
    """
    Delete a client.

    Warning: This will cascade delete all customer companies, contacts, and rules.

    Args:
        client_id: UUID of the client

    Returns:
        Success message
    """
    try:
        # Check if exists
        existing = _supabase.table('clients').select('id, client_name').eq(
            'id', client_id
        ).single().execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Client not found")

        # Delete (cascade will handle customer_companies, contacts, rules)
        _supabase.table('clients').delete().eq('id', client_id).execute()

        return {
            "message": f"Client '{existing.data['client_name']}' deleted successfully",
            "id": client_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete client: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{client_id}/summary")
async def get_client_summary(client_id: str):
    """
    Get comprehensive client summary using database function.

    Args:
        client_id: UUID of the client

    Returns:
        Client summary with all statistics
    """
    try:
        # Use the database function for comprehensive summary
        result = _supabase.rpc(
            'get_client_summary',
            {'p_client_id': client_id}
        ).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Client not found")

        return result.data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get client summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
