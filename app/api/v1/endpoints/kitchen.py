from fastapi import APIRouter, Depends, HTTPException, status

from app.core.exceptions import BitePlateError
from app.dependencies import require_role
from app.dto.kitchen import KitchenCommandDTO, KitchenStateDTO
from app.services.kitchen import (
    CancelOrderCommand,
    ExpediteOrderCommand,
    PrepareOrderCommand,
    kitchen_queue,
)

router = APIRouter()


@router.get(
    "/state",
    response_model=KitchenStateDTO,
    dependencies=[Depends(require_role("head_chef", "manager"))],
)
async def kitchen_state():
    return KitchenStateDTO(**kitchen_queue.snapshot())


@router.post("/commands", dependencies=[Depends(require_role("head_chef", "manager"))])
async def submit_command(dto: KitchenCommandDTO):
    if dto.kind == "prepare":
        command = PrepareOrderCommand(order_id=dto.order_id)
    elif dto.kind == "expedite":
        command = ExpediteOrderCommand(order_id=dto.order_id)
    elif dto.kind == "cancel":
        command = CancelOrderCommand(order_id=dto.order_id)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown command kind")
    try:
        kitchen_queue.submit(command)
    except BitePlateError:
        raise
    return {"submitted": command.describe()}


@router.post("/commands/undo", dependencies=[Depends(require_role("head_chef", "manager"))])
async def undo_last_command():
    command = kitchen_queue.undo_last()
    if command is None:
        return {"undone": None}
    return {"undone": command.describe()}


@router.post("/start-next", dependencies=[Depends(require_role("head_chef", "manager"))])
async def start_next():
    ticket = kitchen_queue.start_next()
    return {"started": ticket.__dict__ if ticket else None}
