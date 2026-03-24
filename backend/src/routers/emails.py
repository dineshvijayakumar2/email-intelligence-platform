"""
Emails API Router

Endpoints for querying, filtering, and retrieving emails.
Extracted from main.py to follow the modular router pattern.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Callable, Optional
import asyncio
import logging

from ..dependencies.auth import get_current_user, get_accessible_mailbox_ids
from ..models.api_models import EmailFilters, EmailRequest, EmailResponse, EmailListResponse
from ..utils.search import sanitize_search_term

logger = logging.getLogger(__name__)

router = APIRouter(tags=["emails"])

# Supabase getter will be injected from main.py
_get_supabase: Callable = None


def init_emails_router(supabase_getter: Callable):
    """Initialize the router with a Supabase client getter callable."""
    global _get_supabase
    _get_supabase = supabase_getter


# =========================================================================
# Helper Functions
# =========================================================================

def _normalize_folder_name(raw: str) -> str:
    """Normalize folder_path values so 'INBOX'/'inbox' both become 'Inbox', etc."""
    FOLDER_MAP = {
        'inbox': 'Inbox', 'sent': 'Sent', 'sent items': 'Sent', 'sent mail': 'Sent',
        'sentitems': 'Sent', 'drafts': 'Drafts', 'draft': 'Drafts',
        'spam': 'Spam', 'junk': 'Spam', 'junk email': 'Spam', 'junk e-mail': 'Spam',
        'trash': 'Trash', 'deleted items': 'Trash', 'deleted': 'Trash',
        'starred': 'Starred', 'flagged': 'Starred', 'important': 'Important',
    }
    return FOLDER_MAP.get(raw.strip().lower(), raw.strip())


# Reverse map: canonical name -> all raw aliases that should match
_FOLDER_ALIASES = {
    'sent': ['Sent', 'Sent Items', 'Sent Mail'],
    'trash': ['Trash', 'Deleted Items'],
    'spam': ['Spam', 'Junk Email', 'Junk E-Mail'],
    'drafts': ['Drafts', 'Draft'],
    'starred': ['Starred', 'Flagged'],
}


def _apply_folder_filter(query, folder_name: str):
    """Apply folder filter with alias expansion for backward compatibility.

    For well-known folders (Sent, Trash, Spam, etc.), expands the filter to
    match all aliases (e.g. 'Sent' also matches 'Sent Items' in DB).
    For user-created folders, does a simple case-insensitive match.
    """
    aliases = _FOLDER_ALIASES.get(folder_name.strip().lower())
    if aliases and len(aliases) > 1:
        # Match any alias (case-insensitive)
        conditions = ','.join(f'folder_path.ilike.{a}' for a in aliases)
        return query.or_(conditions)
    else:
        return query.ilike('folder_path', folder_name)


def transform_email_data(item: dict) -> EmailResponse:
    """Transform database row to EmailResponse format"""
    # Extract tags and metadata from email_categories
    categories = item.get('email_categories', []) or []
    tags = [cat['category'] for cat in categories if not cat['category'].startswith('_meta_')]

    # Extract metadata
    is_spam = any(cat['category'] == '_meta_spam' for cat in categories)
    is_marketing = any(cat['category'] == '_meta_marketing' for cat in categories)

    # Extract priority score
    priority_tag = next((cat for cat in categories if cat['category'].startswith('_meta_priority_')), None)
    priority_score = int(priority_tag['category'].replace('_meta_priority_', '')) if priority_tag else 5

    # Extract sender type
    sender_tag = next((cat for cat in categories if cat['category'].startswith('_meta_sender_')), None)
    sender_type = sender_tag['category'].replace('_meta_sender_', '') if sender_tag else 'unknown'

    # Extract mailbox name + type from nested structure
    mailbox_name = 'Unknown'
    mailbox_type = None
    mailboxes_data = item.get('mailboxes')
    if mailboxes_data:
        # Handle both dict and list formats
        if isinstance(mailboxes_data, dict):
            mailbox_name = mailboxes_data.get('name', 'Unknown')
            mailbox_type = mailboxes_data.get('mailbox_type')
        elif isinstance(mailboxes_data, list) and len(mailboxes_data) > 0:
            mailbox_name = mailboxes_data[0].get('name', 'Unknown')
            mailbox_type = mailboxes_data[0].get('mailbox_type')

    return EmailResponse(
        id=item['id'],
        subject=item['subject'],
        sender_email=item['sender_email'],
        sender_name=item.get('sender_name'),
        recipients=item.get('recipients'),
        cc_list=item.get('cc_list'),
        bcc_list=item.get('bcc_list'),
        sent_date=item['sent_date'],
        received_date=item.get('received_date'),
        category=categories[0]['category'] if categories else 'unassigned',
        is_outbound=item['is_outbound'],
        is_reply=item['is_reply'],
        folder_path=item['folder_path'],
        message_size=item['message_size'],
        body_text=item.get('body_text'),
        body_html=item.get('body_html'),
        mailbox_id=item['mailbox_id'],
        mailbox_name=mailbox_name,
        mailbox_type=mailbox_type,
        tags=tags,
        is_spam=is_spam,
        is_marketing=is_marketing,
        priority_score=priority_score,
        sender_type=sender_type,
        attachments=item.get('attachments') or [],
        provider_web_link=item.get('provider_web_link') or None,
    )


# =========================================================================
# Email API Endpoints
# =========================================================================

@router.post("/emails")
async def get_emails_with_filters(
    request: EmailRequest,
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """
    SCALABLE EMAIL QUERY ENDPOINT - Fixed category filter with same approach

    Industry best practices for handling millions of emails:
    1. Cursor-based pagination for better performance
    2. Efficient single query with proper joins
    3. Database indexing strategy
    4. Query optimization with selective fields
    5. Caching for metadata (categories, mailboxes)
    6. Row-level security - only accessible mailboxes
    """
    try:
        sb = _get_supabase()
        filters = request.filters
        page = request.page
        pageSize = min(request.pageSize, 100)  # Limit max page size for performance

        logger.debug(f"Scalable email query - Filters: {filters.dict()}, Page: {page}, Size: {pageSize}")

        # Build optimized query without joins (PostgREST limitation with complex selects)
        # We'll get categories separately for better performance
        base_query = sb.table('emails').select(f"""
            id,
            subject,
            sender_email,
            sender_name,
            sent_date,
            is_outbound,
            is_reply,
            folder_path,
            message_size,
            mailbox_id
        """)

        # Apply filters efficiently
        filters_applied = []

        # Mailbox filter (most selective - apply first)
        if filters.mailbox and filters.mailbox.strip():
            # First get mailbox ID from accessible mailboxes only
            try:
                # Filter by name AND accessible mailbox IDs
                mailbox_result = sb.table('mailboxes').select('id').eq('name', filters.mailbox).in_('id', accessible_mailbox_ids).execute()
                if mailbox_result.data:
                    mailbox_id = mailbox_result.data[0]['id']
                    base_query = base_query.eq('mailbox_id', mailbox_id)
                    filters_applied.append(f"mailbox={filters.mailbox}")
                else:
                    # No matching accessible mailbox found, return empty results
                    logger.warning(f"No accessible mailbox found with name: {filters.mailbox}")
                    return EmailListResponse(emails=[], totalCount=0)
            except Exception as e:
                logger.error(f"Error filtering by mailbox: {e}")
                # Continue without mailbox filter
        else:
            # No specific mailbox filter - restrict to accessible mailboxes only
            if accessible_mailbox_ids:
                base_query = base_query.in_('mailbox_id', accessible_mailbox_ids)
                filters_applied.append(f"accessible_mailboxes={len(accessible_mailbox_ids)}")
            else:
                # User has no accessible mailboxes, return empty
                logger.warning("User has no accessible mailboxes")
                return EmailListResponse(emails=[], totalCount=0)

        # Folder filter with alias expansion (e.g. "Sent" also matches "Sent Items")
        if filters.folder and filters.folder.strip():
            base_query = _apply_folder_filter(base_query, filters.folder)
            filters_applied.append(f"folder={filters.folder}")

        # Date range filter (use indexes)
        if filters.dateRange and len(filters.dateRange) == 2:
            base_query = base_query.gte('sent_date', filters.dateRange[0]).lte('sent_date', filters.dateRange[1])
            filters_applied.append(f"date_range={filters.dateRange}")

        # Outbound/Inbound filter
        if filters.isOutbound == 'outbound':
            base_query = base_query.eq('is_outbound', True)
            filters_applied.append("direction=outbound")
        elif filters.isOutbound == 'inbound':
            base_query = base_query.eq('is_outbound', False)
            filters_applied.append("direction=inbound")

        # Text search (expensive - apply last)
        if filters.search and filters.search.strip():
            search_term = sanitize_search_term(filters.search.strip())
            # Simple subject search for now (will expand to multi-field later)
            base_query = base_query.ilike('subject', f'%{search_term}%')
            filters_applied.append(f"search={search_term}")

        # Category filter (requires separate optimization)
        if filters.category and filters.category.strip():
            return await handle_category_filter(base_query, filters, page, pageSize)

        # Apply ordering and pagination
        # Use sent_date index for efficient sorting
        base_query = base_query.order('sent_date', desc=True)

        # Cursor-based pagination for better performance at scale
        from_idx = (page - 1) * pageSize
        to_idx = from_idx + pageSize - 1
        base_query = base_query.range(from_idx, to_idx)

        logger.debug(f"Optimized query - Applied filters: {filters_applied}")

        # Execute count query separately (PostgREST limitation with joins + count)
        count_query = sb.table('emails').select('id', count='exact')
        # Apply same filters to count query (exclude joins for count)
        if filters.mailbox and filters.mailbox.strip():
            try:
                # Filter by name AND accessible mailbox IDs
                mailbox_result = sb.table('mailboxes').select('id').eq('name', filters.mailbox).in_('id', accessible_mailbox_ids).execute()
                if mailbox_result.data:
                    mailbox_id = mailbox_result.data[0]['id']
                    count_query = count_query.eq('mailbox_id', mailbox_id)
            except Exception:
                pass  # Skip mailbox filter for count if it fails
        else:
            # No specific mailbox filter - restrict to accessible mailboxes
            if accessible_mailbox_ids:
                count_query = count_query.in_('mailbox_id', accessible_mailbox_ids)
        if filters.folder and filters.folder.strip():
            count_query = _apply_folder_filter(count_query, filters.folder)
        if filters.dateRange and len(filters.dateRange) == 2:
            count_query = count_query.gte('sent_date', filters.dateRange[0]).lte('sent_date', filters.dateRange[1])
        if filters.isOutbound == 'outbound':
            count_query = count_query.eq('is_outbound', True)
        elif filters.isOutbound == 'inbound':
            count_query = count_query.eq('is_outbound', False)
        if filters.search and filters.search.strip():
            search_term = sanitize_search_term(filters.search.strip())
            count_query = count_query.ilike('subject', f'%{search_term}%')

        # Execute queries
        result = base_query.execute()
        count_result = count_query.execute()

        logger.debug(f"Query executed successfully, got {len(result.data or [])} results")

        # Get mailbox names separately for better performance (PostgREST multiple join limitation)
        mailbox_names = {}
        email_categories_map = {}

        if result.data:
            # Get unique mailbox IDs
            unique_mailbox_ids = list(set(item['mailbox_id'] for item in result.data if item.get('mailbox_id')))
            if unique_mailbox_ids:
                mailbox_result = sb.table('mailboxes').select('id, name').in_('id', unique_mailbox_ids).execute()
                for mailbox in mailbox_result.data or []:
                    mailbox_names[mailbox['id']] = mailbox['name']

            # Get email categories separately (PostgREST complex join limitation)
            email_ids = [item['id'] for item in result.data]
            if email_ids:
                # Process in batches to avoid URL length limits
                batch_size = 10  # Safe batch size for UUIDs
                total_categories = 0
                for i in range(0, len(email_ids), batch_size):
                    batch_ids = email_ids[i:i + batch_size]
                    try:
                        categories_result = sb.table('email_categories').select('email_id, category').in_('email_id', batch_ids).execute()
                        total_categories += len(categories_result.data or [])
                        # Group categories by email_id
                        for cat in categories_result.data or []:
                            email_id = cat['email_id']
                            if email_id not in email_categories_map:
                                email_categories_map[email_id] = []
                            email_categories_map[email_id].append({
                                'category': cat['category']
                            })
                    except Exception as e:
                        logger.error(f"Error fetching categories for batch {i//batch_size}: {e}")
                        # Continue with other batches
                        continue

                logger.debug(f"Categories query returned {total_categories} categories for {len(email_ids)} emails")

        # Transform results efficiently
        emails = []
        for item in result.data or []:
            # Extract mailbox name from separate query
            mailbox_name = mailbox_names.get(item.get('mailbox_id'), 'Unknown')

            # Extract tags and categories from join
            tags = []
            category = 'unassigned'
            is_spam = False
            is_marketing = False
            priority_score = 5
            sender_type = 'unknown'

            # Get categories from separate query
            categories_data = email_categories_map.get(item['id'], [])

            if categories_data:
                if isinstance(categories_data, list):
                    # Multiple categories
                    for cat in categories_data:
                        if isinstance(cat, dict):
                            cat_name = cat.get('category', '')
                            if cat_name and not cat_name.startswith('_meta_'):
                                tags.append(cat_name)
                                if category == 'unassigned':  # Use first non-meta category
                                    category = cat_name
                            elif cat_name == '_meta_spam':
                                is_spam = True
                            elif cat_name == '_meta_marketing':
                                is_marketing = True
                elif isinstance(categories_data, dict):
                    # Single category
                    cat_name = categories_data.get('category', '')
                    if cat_name and not cat_name.startswith('_meta_'):
                        tags.append(cat_name)
                        category = cat_name
                    elif cat_name == '_meta_spam':
                        is_spam = True
                    elif cat_name == '_meta_marketing':
                        is_marketing = True

            emails.append(EmailResponse(
                id=item['id'],
                subject=item['subject'],
                sender_email=item['sender_email'],
                sender_name=item.get('sender_name'),
                sent_date=item['sent_date'],
                category=category,
                is_outbound=item['is_outbound'],
                is_reply=item['is_reply'],
                folder_path=item['folder_path'],
                message_size=item['message_size'],
                body_text=None,  # Don't return body for list view (performance)
                body_html=None,  # Don't return body for list view (performance)
                mailbox_id=item['mailbox_id'],
                mailbox_name=mailbox_name,
                tags=tags,
                is_spam=is_spam,
                is_marketing=is_marketing,
                priority_score=priority_score,
                sender_type=sender_type
            ))

        total_count = count_result.count or 0
        logger.debug(f"Scalable query result: {len(emails)} emails out of {total_count} total")

        return EmailListResponse(emails=emails, totalCount=total_count)

    except Exception as e:
        logger.error(f"Error in scalable email query: {e}", exc_info=True)
        return EmailListResponse(emails=[], totalCount=0)


async def handle_category_filter(base_query, filters: EmailFilters, page: int, pageSize: int):
    """
    OPTIMIZED CATEGORY FILTERING

    For millions of emails, category filtering needs special handling:
    1. Use database-level joins instead of IN clauses
    2. Leverage indexes on email_categories table
    """
    try:
        sb = _get_supabase()

        # First get emails that have the specified category using a subquery approach
        # Step 1: Get email IDs that have the specified category
        category_emails_result = sb.table('email_categories').select('email_id').eq('category', filters.category).execute()

        if not category_emails_result.data:
            # No emails with this category
            return EmailListResponse(emails=[], totalCount=0)

        # Get the email IDs
        email_ids_with_category = [item['email_id'] for item in category_emails_result.data]

        # Step 2: Query emails table with these IDs (in batches to avoid URL limits)
        all_emails = []
        batch_size = 50  # Process email IDs in batches

        for i in range(0, len(email_ids_with_category), batch_size):
            batch_ids = email_ids_with_category[i:i + batch_size]

            category_query = sb.table('emails').select(f"""
                id,
                subject,
                sender_email,
                sender_name,
                sent_date,
                is_outbound,
                is_reply,
                folder_path,
                message_size,
                mailbox_id
            """).in_('id', batch_ids)

            # Apply other filters to this batch
            if filters.mailbox and filters.mailbox.strip():
                try:
                    mailbox_result = sb.table('mailboxes').select('id').eq('name', filters.mailbox).execute()
                    if mailbox_result.data:
                        mailbox_id = mailbox_result.data[0]['id']
                        category_query = category_query.eq('mailbox_id', mailbox_id)
                    else:
                        continue  # Skip this batch if no matching mailbox
                except Exception as e:
                    logger.error(f"Error filtering by mailbox in category filter: {e}")
                    continue

            if filters.folder and filters.folder.strip():
                category_query = _apply_folder_filter(category_query, filters.folder)
            if filters.isOutbound == 'outbound':
                category_query = category_query.eq('is_outbound', True)
            elif filters.isOutbound == 'inbound':
                category_query = category_query.eq('is_outbound', False)
            if filters.dateRange and len(filters.dateRange) == 2:
                category_query = category_query.gte('sent_date', filters.dateRange[0]).lte('sent_date', filters.dateRange[1])
            if filters.search and filters.search.strip():
                search_term = sanitize_search_term(filters.search.strip())
                category_query = category_query.ilike('subject', f'%{search_term}%')

            # Execute this batch
            batch_result = category_query.execute()
            if batch_result.data:
                all_emails.extend(batch_result.data)

        # Sort all emails by sent_date desc
        all_emails.sort(key=lambda x: x['sent_date'], reverse=True)

        # Apply pagination to the combined results
        from_idx = (page - 1) * pageSize
        to_idx = from_idx + pageSize
        paginated_emails = all_emails[from_idx:to_idx]

        # Create a mock result object
        class MockResult:
            def __init__(self, data):
                self.data = data

        result = MockResult(paginated_emails)

        # Get mailbox names and categories separately (same as main query)
        mailbox_names = {}
        email_categories_map = {}

        if result.data:
            # Get unique mailbox IDs
            unique_mailbox_ids = list(set(item['mailbox_id'] for item in result.data if item.get('mailbox_id')))
            if unique_mailbox_ids:
                mailbox_result = sb.table('mailboxes').select('id, name').in_('id', unique_mailbox_ids).execute()
                for mailbox in mailbox_result.data or []:
                    mailbox_names[mailbox['id']] = mailbox['name']

            # Get email categories separately (same batching logic)
            email_ids = [item['id'] for item in result.data]
            if email_ids:
                batch_size = 10
                total_categories = 0
                for i in range(0, len(email_ids), batch_size):
                    batch_ids = email_ids[i:i + batch_size]
                    try:
                        categories_result = sb.table('email_categories').select('email_id, category').in_('email_id', batch_ids).execute()
                        total_categories += len(categories_result.data or [])
                        for cat in categories_result.data or []:
                            email_id = cat['email_id']
                            if email_id not in email_categories_map:
                                email_categories_map[email_id] = []
                            email_categories_map[email_id].append({
                                'category': cat['category']
                            })
                    except Exception as e:
                        logger.error(f"Error fetching categories for category filter batch: {e}")
                        continue

        # Transform results (same logic as main query)
        emails = []
        for item in result.data or []:
            mailbox_name = mailbox_names.get(item.get('mailbox_id'), 'Unknown')

            # Get categories from separate query
            categories_data = email_categories_map.get(item['id'], [])

            tags = []
            category = filters.category  # We know this email has this category
            is_spam = False
            is_marketing = False
            priority_score = 5
            sender_type = 'unknown'

            if categories_data:
                for cat in categories_data:
                    cat_name = cat.get('category', '')
                    if cat_name and not cat_name.startswith('_meta_'):
                        tags.append(cat_name)
                    elif cat_name == '_meta_spam':
                        is_spam = True
                    elif cat_name == '_meta_marketing':
                        is_marketing = True

            emails.append(EmailResponse(
                id=item['id'],
                subject=item['subject'],
                sender_email=item['sender_email'],
                sender_name=item.get('sender_name'),
                sent_date=item['sent_date'],
                category=category,
                is_outbound=item['is_outbound'],
                is_reply=item['is_reply'],
                folder_path=item['folder_path'],
                message_size=item['message_size'],
                body_text=None,
                body_html=None,
                mailbox_id=item['mailbox_id'],
                mailbox_name=mailbox_name,
                tags=tags,
                is_spam=is_spam,
                is_marketing=is_marketing,
                priority_score=priority_score,
                sender_type=sender_type
            ))

        logger.info(f"Category filter result: {len(emails)} emails for category '{filters.category}'")
        return EmailListResponse(emails=emails, totalCount=len(all_emails))

    except Exception as e:
        logger.error(f"Error in category filter: {e}", exc_info=True)
        return EmailListResponse(emails=[], totalCount=0)


@router.get("/emails/folders")
async def get_folder_names(mailbox_id: Optional[str] = None):
    """Get distinct folder names from emails for filter dropdown - Optimized with direct SQL"""
    try:
        sb = _get_supabase()

        if mailbox_id:
            logger.info(f"Fetching distinct folder names for mailbox {mailbox_id}...")
            # Paginate through ALL emails (selecting only folder_path) to find every folder
            # Without this, .limit(10000) could miss custom folders with few emails
            all_folders = set()
            offset = 0
            batch_size = 5000
            while True:
                result = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda off=offset: sb.table('emails')
                        .select('folder_path')
                        .eq('mailbox_id', mailbox_id)
                        .range(off, off + batch_size - 1)
                        .execute()
                )
                if not result.data:
                    break
                for row in result.data:
                    folder = row.get('folder_path')
                    if folder:
                        all_folders.add(_normalize_folder_name(folder))
                if len(result.data) < batch_size:
                    break
                offset += len(result.data)

            folders_list = sorted(list(all_folders))
            logger.info(f"Found {len(folders_list)} unique folders for mailbox {mailbox_id}: {folders_list}")
            return folders_list

        logger.info("Fetching distinct folder names (optimized)...")

        # Use PostgreSQL DISTINCT query for efficient folder retrieval
        # This is much faster than fetching all rows
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sb.rpc('get_distinct_folders', {}).execute()
        )

        if result.data:
            folders_list = sorted(set(
                _normalize_folder_name(f['folder_path'])
                for f in result.data if f.get('folder_path')
            ))
            logger.info(f"Found {len(folders_list)} unique folders: {folders_list}")
            return folders_list

        # Fallback: If RPC function doesn't exist, use regular query with limit
        # This will only work if there aren't too many unique folders
        logger.warning("RPC function not found, using fallback method")
        all_folders = set()
        offset = 0
        batch_size = 5000
        while True:
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda off=offset: sb.table('emails')
                    .select('folder_path')
                    .range(off, off + batch_size - 1)
                    .execute()
            )
            if not result.data:
                break
            for row in result.data:
                folder = row.get('folder_path')
                if folder:
                    all_folders.add(_normalize_folder_name(folder))
            if len(result.data) < batch_size:
                break
            offset += len(result.data)

        folders_list = sorted(list(all_folders))
        logger.info(f"Found {len(folders_list)} unique folders (fallback): {folders_list}")
        return folders_list

    except Exception as e:
        logger.error(f"Error fetching folder names: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch folders: {str(e)}")


@router.get("/emails/categories")
async def get_email_categories():
    """Get email categories for filter dropdown - replaces frontend emailService.getEmailCategories()"""
    logger.info('[Categories API] Request received')
    try:
        sb = _get_supabase()

        # Use filter to exclude _meta_ prefixed categories at database level
        # and fetch more rows to ensure we get actual categories
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sb.table('email_categories')
                .select('category')
                .not_.like('category', '_meta_%')
                .limit(10000)
                .execute()
        )

        row_count = len(result.data or [])
        logger.info(f'[Categories API] Fetched {row_count} non-meta category rows')

        # Get unique categories
        category_set = set()
        for item in result.data or []:
            category = item.get('category')
            if category:
                category_set.add(category)

        categories = sorted(list(category_set))
        logger.info(f'[Categories API] Returning {len(categories)} categories: {categories}')

        return categories

    except Exception as e:
        logger.error(f"[Categories API] Error fetching email categories: {e}", exc_info=True)
        return []


@router.get("/emails/{email_id}")
async def get_email_by_id(email_id: str):
    """Get a single email by ID - replaces frontend emailService.getEmail()"""
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            sb = _get_supabase()

            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: sb.table('emails').select("""
                    id,
                    subject,
                    sender_email,
                    sender_name,
                    recipients,
                    cc_list,
                    bcc_list,
                    attachments,
                    provider_web_link,
                    sent_date,
                    received_date,
                    is_outbound,
                    is_reply,
                    folder_path,
                    message_size,
                    body_text,
                    body_html,
                    mailbox_id,
                    mailboxes!inner(name,mailbox_type),
                    email_categories(category)
                """).eq('id', email_id).single().execute()
            )

            if not result.data:
                raise HTTPException(status_code=404, detail="Email not found")

            email = transform_email_data(result.data)
            return email
        except HTTPException:
            raise
        except Exception as e:
            if attempt < max_retries - 1 and "WinError 10035" in str(e):
                logger.warning(f"Retry {attempt + 1}/{max_retries} for email {email_id} due to socket error")
                await asyncio.sleep(retry_delay)
                continue
            logger.error(f"Error fetching email {email_id}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to fetch email")


@router.get("/mailbox-names")
async def get_mailbox_names():
    """Get mailbox names for filter dropdown - replaces frontend emailService.getMailboxNames()"""
    try:
        sb = _get_supabase()

        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sb.table('mailboxes').select('name').eq('is_active', True).execute()
        )

        return [item['name'] for item in result.data or []]

    except Exception as e:
        logger.error(f"Error fetching mailbox names: {e}", exc_info=True)
        return []
