from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    billing,
    history,
    kitchen,
    menu,
    notifications,
    orders,
    pricing,
    reservations,
    tables,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/admin/users", tags=["admin-users"])
api_router.include_router(menu.router, prefix="/menu", tags=["menu"])
api_router.include_router(tables.router, prefix="/tables", tags=["tables"])
api_router.include_router(reservations.router, prefix="/reservations", tags=["reservations"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(kitchen.router, prefix="/kitchen", tags=["kitchen"])
api_router.include_router(pricing.router, prefix="/pricing", tags=["pricing"])
api_router.include_router(billing.router, prefix="/bills", tags=["billing"])
api_router.include_router(history.router, prefix="/history", tags=["history"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
