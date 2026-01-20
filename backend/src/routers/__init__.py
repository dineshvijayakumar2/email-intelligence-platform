# Stage 2 Routers Package
# FastAPI routers for Stage 2 features

from .errors import router as errors_router, init_error_router
from .account_managers import router as account_managers_router, init_account_managers_router
from .clients import router as clients_router, init_clients_router
from .customers import router as customers_router, init_customers_router
from .contacts import router as contacts_router, init_contacts_router

__all__ = [
    # Routers
    'errors_router',
    'account_managers_router',
    'clients_router',
    'customers_router',
    'contacts_router',
    # Init functions
    'init_error_router',
    'init_account_managers_router',
    'init_clients_router',
    'init_customers_router',
    'init_contacts_router',
]
