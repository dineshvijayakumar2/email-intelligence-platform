"""
Job handler registry. Maps job_type -> async handler function.

Adding a new job type: write a handler in this package, register it here.
No worker changes needed.
"""
from __future__ import annotations
from typing import Callable, Awaitable

from .reembed import reembed_handler
from .notification_dispatch import notification_dispatch_handler
from .reference_extraction import reference_extraction_handler
from .ai_backfill import ai_backfill_handler
from .ai_analysis import ai_analysis_handler

JOB_HANDLERS: dict[str, Callable[..., Awaitable[None]]] = {
    'reembed': reembed_handler,
    'notification_dispatch': notification_dispatch_handler,
    'reference_extraction': reference_extraction_handler,
    'ai_backfill': ai_backfill_handler,
    'ai_analysis': ai_analysis_handler,
    # Future handlers (uncomment as implemented):
    # 'strategic_digest': digest_handler,
    # 'qb_sync_scheduled': qb_sync_handler,
    # 'gmail_sync': gmail_sync_handler,
    # 'outlook_sync': outlook_sync_handler,
    # 'reprocessing': reprocessing_handler,
    # 'analytics_rollup_daily': analytics_rollup_handler,
    # 'contact_metrics_refresh': contact_metrics_handler,
}
