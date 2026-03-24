"""
Dashboard API Router

Endpoints for dashboard statistics, email volume, categories, and recent emails.
Extracted from main.py to follow the modular router pattern.
"""

from fastapi import APIRouter, Depends
from datetime import datetime, timedelta, timezone
from typing import Callable
import asyncio
import logging

from ..dependencies.auth import get_current_user, get_accessible_mailbox_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Supabase getter will be injected from main.py
_get_supabase: Callable = None


def init_dashboard_router(supabase_getter: Callable):
    """Initialize the router with a Supabase client getter callable."""
    global _get_supabase
    _get_supabase = supabase_getter


# =========================================================================
# Helper Functions
# =========================================================================

def get_category_label(category: str) -> str:
    """Helper function to format category labels"""
    labels = {
        'promotional': 'Promotional',
        'transactional': 'Transactional',
        'conversation': 'Conversation',
        'internal': 'Internal',
        'system': 'System',
        'social': 'Social',
        'updates': 'Updates'
    }
    return labels.get(category.lower(), category) if category else 'Unknown'


def format_relative_time(date_string: str) -> str:
    """Helper function to format relative time"""
    try:
        date = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        diff_minutes = int((now - date).total_seconds() / 60)

        if diff_minutes < 60:
            return f"{diff_minutes} minutes ago"
        elif diff_minutes < 24 * 60:
            hours = diff_minutes // 60
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = diff_minutes // (24 * 60)
            return f"{days} day{'s' if days != 1 else ''} ago"
    except Exception:
        return "Unknown time"


# =========================================================================
# Dashboard API Endpoints
# =========================================================================

@router.get("/stats")
async def get_dashboard_stats(
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """Get dashboard statistics filtered by user's accessible mailboxes"""

    try:
        sb = _get_supabase()

        logger.info(f"[Dashboard Stats] User {current_user['user_id']} accessing with {len(accessible_mailbox_ids)} mailboxes")

        # If user has no accessible mailboxes, return zeros
        if not accessible_mailbox_ids:
            logger.warning("[Dashboard Stats] User has no accessible mailboxes")
            return {
                "totalEmails": 0,
                "totalMailboxes": 0,
                "todayEmails": 0,
                "processingJobs": 0
            }

        # Count emails in accessible mailboxes
        emails_count = sb.table('emails').select('id', count='exact').in_('mailbox_id', accessible_mailbox_ids).execute()

        # Count accessible mailboxes
        mailboxes_count = len(accessible_mailbox_ids)

        # Count today's emails in accessible mailboxes
        today = datetime.now(timezone.utc).date().isoformat()
        today_emails = sb.table('emails').select('id', count='exact').in_('mailbox_id', accessible_mailbox_ids).gte('sent_date', today).execute()

        # Count active processing jobs for accessible mailboxes
        processing_jobs_count = sb.table('processing_jobs').select('id', count='exact').in_('mailbox_id', accessible_mailbox_ids).in_('status', ['pending', 'running', 'downloading']).execute()

        stats = {
            "totalEmails": emails_count.count or 0,
            "totalMailboxes": mailboxes_count,
            "todayEmails": today_emails.count or 0,
            "processingJobs": processing_jobs_count.count or 0
        }

        logger.info(f"[Dashboard Stats] Returning stats: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        # Return zeros instead of mock data
        return {
            "totalEmails": 0,
            "totalMailboxes": 0,
            "todayEmails": 0,
            "processingJobs": 0
        }


@router.get("/volume")
async def get_volume_data(
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """Get email volume data for the last 7 days filtered by accessible mailboxes"""
    try:
        sb = _get_supabase()

        if not accessible_mailbox_ids:
            return []

        # Get data for last 7 days from emails table (aggregate by date)
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=6)).date().isoformat()
        today = datetime.now(timezone.utc).date().isoformat()

        # Query emails in accessible mailboxes
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sb.table('emails').select('sent_date, direction').in_('mailbox_id', accessible_mailbox_ids).gte('sent_date', seven_days_ago).lte('sent_date', today).execute()
        )

        # Aggregate by date
        volume_by_date = {}
        for item in result.data or []:
            date = item['sent_date'][:10]  # Extract date part
            if date not in volume_by_date:
                volume_by_date[date] = {'inbound': 0, 'outbound': 0}

            direction = item.get('direction', 'inbound')
            if direction == 'outbound':
                volume_by_date[date]['outbound'] += 1
            else:
                volume_by_date[date]['inbound'] += 1

        # Transform to expected format
        volume_data = []
        for i in range(6, -1, -1):
            date = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
            volume_data.append({
                'date': date,
                'inbound': volume_by_date.get(date, {}).get('inbound', 0),
                'outbound': volume_by_date.get(date, {}).get('outbound', 0)
            })

        return volume_data

    except Exception as e:
        logger.error(f"Error fetching volume data: {e}", exc_info=True)
        return []


@router.get("/categories")
async def get_category_data(
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """Get email category distribution filtered by accessible mailboxes"""
    try:
        sb = _get_supabase()

        if not accessible_mailbox_ids:
            return []

        # Get categories for emails in accessible mailboxes
        # Note: email_categories table should have email_id, need to join with emails
        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sb.table('email_categories').select('category, email_id, emails!inner(mailbox_id)').in_('emails.mailbox_id', accessible_mailbox_ids).execute()
        )

        # Count categories (exclude metadata)
        category_counts = {}
        for item in result.data or []:
            category = item.get('category')
            if category and not category.startswith('_meta_'):
                category_counts[category] = category_counts.get(category, 0) + 1

        colors = ['#8884d8', '#82ca9d', '#ffc658', '#ff8042', '#0088fe']

        # Convert to chart format
        category_data = []
        for idx, (name, value) in enumerate(sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]):
            category_data.append({
                'name': get_category_label(name),
                'value': value,
                'color': colors[idx % len(colors)]
            })

        return category_data

    except Exception as e:
        logger.error(f"Error fetching category data: {e}", exc_info=True)
        return []


@router.get("/recent-emails")
async def get_recent_emails(
    current_user: dict = Depends(get_current_user),
    accessible_mailbox_ids: list = Depends(get_accessible_mailbox_ids)
):
    """Get recent emails filtered by accessible mailboxes"""
    try:
        sb = _get_supabase()

        if not accessible_mailbox_ids:
            return []

        result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: sb.table('emails').select("""
                id,
                subject,
                sender_email,
                sender_name,
                sent_date,
                email_categories(category)
            """).in_('mailbox_id', accessible_mailbox_ids).order('sent_date', desc=True).limit(5).execute()
        )

        recent_emails = []
        for email in result.data or []:
            categories = email.get('email_categories', []) or []
            category = categories[0]['category'] if categories else 'Unknown'

            recent_emails.append({
                'id': email['id'],
                'subject': email['subject'],
                'sender': email.get('sender_name') or email['sender_email'],
                'category': get_category_label(category),
                'received': format_relative_time(email['sent_date'])
            })

        return recent_emails

    except Exception as e:
        logger.error(f"Error fetching recent emails: {e}", exc_info=True)
        return []
