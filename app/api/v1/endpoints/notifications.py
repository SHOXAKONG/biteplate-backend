from fastapi import APIRouter, Depends

from app.dependencies import require_role
from app.services.notifications import order_subject

router = APIRouter()


@router.get("/observers", dependencies=[Depends(require_role("manager"))])
async def list_observers():
    return {"observers": [type(o).__name__ for o in order_subject._observers]}
