"""
Dependencies module for FastAPI dependency injection.
"""

from .auth import get_current_user, require_role, init_auth_dependencies

__all__ = ['get_current_user', 'require_role', 'init_auth_dependencies']
