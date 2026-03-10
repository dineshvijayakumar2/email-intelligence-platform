"""
Audit Logging Utility

Fire-and-forget audit log writer for tracking key user and system actions.
Logs to the `audit_log` table in Supabase.

Actions tracked:
- login, settings_change, role_change, user_activate, user_deactivate
- mailbox_create, mailbox_delete, mailbox_sync
- analyze, extract, digest_generate
- user_invite, client_assign, client_unassign
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Supabase client — injected from main.py
_supabase = None


def init_audit(supabase_client):
    """Initialize audit utility with Supabase client."""
    global _supabase
    _supabase = supabase_client


def log_audit(
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """
    Write an audit log entry. Fire-and-forget — failures are logged but never raised.

    Args:
        action: Action type (e.g. login, sync, analyze, settings_change)
        resource_type: Resource type (e.g. mailbox, user, settings, ai_analysis)
        resource_id: Optional resource identifier
        user_id: UUID of the acting user
        user_email: Email of the acting user
        details: Optional dict with extra context (changed fields, counts, errors)
        ip_address: Optional client IP
    """
    if not _supabase:
        logger.warning("Audit: Supabase not initialized, skipping audit log")
        return

    try:
        entry = {
            "action": action,
            "resource_type": resource_type,
        }
        if resource_id:
            entry["resource_id"] = str(resource_id)
        if user_id:
            entry["user_id"] = user_id
        if user_email:
            entry["user_email"] = user_email
        if details:
            entry["details"] = details
        if ip_address:
            entry["ip_address"] = ip_address

        _supabase.table("audit_log").insert(entry).execute()
        logger.debug(f"Audit: {action} on {resource_type}/{resource_id} by {user_email or user_id}")
    except Exception as e:
        # Never let audit logging break the main flow
        logger.error(f"Audit log write failed: {e}")


def audit_from_user(current_user: dict, action: str, resource_type: str, resource_id: Optional[str] = None, details: Optional[dict] = None):
    """
    Convenience wrapper that extracts user_id and email from the current_user dict
    returned by get_current_user dependency.
    """
    log_audit(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=current_user.get("user_id"),
        user_email=current_user.get("email"),
        details=details,
    )
