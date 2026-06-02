from routers.merchants import router as merchants_router
from routers.kyc import router as kyc_router
from routers.bank_accounts import router as bank_accounts_router
from routers.api_keys import router as api_keys_router
from routers.webhooks import router as webhooks_router
from routers.dashboard import router as dashboard_router

__all__ = [
    merchants_router,
    kyc_router,
    bank_accounts_router,
    api_keys_router,
    webhooks_router,
    dashboard_router,
]
