import os

from fastapi import APIRouter

from ..services import budget

router = APIRouter()


@router.get("/")
def root():
    """Public health endpoint with budget info for default tenant."""
    tid = os.getenv("DEFAULT_TENANT", "demo")
    return {
        "status": "alive",
        "budget_left": budget.get_left(tid),
        "budget_total": budget.get_total(tid),
    }


@router.get("/api/")
def api_index():
    """Health/Index endpoint for the API prefix.

    Prevents 404s when the frontend accidentally requests ``/api/``
    without specifying a resource.
    """
    return {"ok": True, "message": "API index"}
