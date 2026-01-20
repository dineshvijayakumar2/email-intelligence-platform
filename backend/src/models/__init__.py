# Stage 2 Models Package
# Pydantic models for request/response validation

from .account_manager import (
    AccountManagerRole,
    AccountManagerBase,
    AccountManagerCreate,
    AccountManagerUpdate,
    AccountManagerResponse,
    AccountManagerWithStats,
    AccountManagerListResponse,
)

from .client import (
    ClientStatus,
    ClientBase,
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientWithStats,
    ClientSummary,
    ClientListResponse,
)

from .customer import (
    CustomerCompanyBase,
    CustomerCompanyCreate,
    CustomerCompanyUpdate,
    CustomerCompanyResponse,
    CustomerCompanyWithContacts,
    CustomerCompanySummary,
    CustomerCompanyListResponse,
    ContactSummary as CustomerContactSummary,
)

from .contact import (
    ContactBase,
    ContactCreate,
    ContactUpdate,
    ContactResponse,
    ContactWithCompany,
    CompanyInfo,
    ContactSummary,
    ContactListResponse,
    SignatureData,
)

from .rule import (
    RuleType,
    RuleBase,
    RuleCreate,
    RuleUpdate,
    RuleResponse,
    RuleWithContext,
    RuleSummary,
    RuleListResponse,
    RuleTestRequest,
    RuleTestResponse,
    RuleApplyRequest,
    RuleApplyResponse,
)

__all__ = [
    # Account Manager
    'AccountManagerRole',
    'AccountManagerBase',
    'AccountManagerCreate',
    'AccountManagerUpdate',
    'AccountManagerResponse',
    'AccountManagerWithStats',
    'AccountManagerListResponse',
    # Client
    'ClientStatus',
    'ClientBase',
    'ClientCreate',
    'ClientUpdate',
    'ClientResponse',
    'ClientWithStats',
    'ClientSummary',
    'ClientListResponse',
    # Customer Company
    'CustomerCompanyBase',
    'CustomerCompanyCreate',
    'CustomerCompanyUpdate',
    'CustomerCompanyResponse',
    'CustomerCompanyWithContacts',
    'CustomerCompanySummary',
    'CustomerCompanyListResponse',
    'CustomerContactSummary',
    # Contact
    'ContactBase',
    'ContactCreate',
    'ContactUpdate',
    'ContactResponse',
    'ContactWithCompany',
    'CompanyInfo',
    'ContactSummary',
    'ContactListResponse',
    'SignatureData',
    # Rule
    'RuleType',
    'RuleBase',
    'RuleCreate',
    'RuleUpdate',
    'RuleResponse',
    'RuleWithContext',
    'RuleSummary',
    'RuleListResponse',
    'RuleTestRequest',
    'RuleTestResponse',
    'RuleApplyRequest',
    'RuleApplyResponse',
]
