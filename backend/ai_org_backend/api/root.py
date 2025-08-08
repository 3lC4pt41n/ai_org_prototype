from fastapi import APIRouter, Depends

from .dependencies import get_current_tenant
from ..services import budget

router = APIRouter()


@router.get("/")
def root(current=Depends(get_current_tenant)):
    tid = current.id
    return {
        "status": "alive",
        "budget_left": budget.get_left(tid),
        "budget_total": budget.get_total(tid),
    }
