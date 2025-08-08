"""Settings endpoints for per-tenant toggles."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import engine
from ..api.dependencies import get_current_tenant
from ..models import Tenant

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/research")
def get_research(current=Depends(get_current_tenant)):
    with Session(engine) as db:
        t = db.exec(select(Tenant).where(Tenant.id == current.id)).first()
        if not t:
            raise HTTPException(404, "Tenant not found")
        return {"allow_web_research": t.allow_web_research}


@router.post("/research")
def set_research(payload: dict, current=Depends(get_current_tenant)):
    allow = bool(payload.get("allow", False))
    with Session(engine) as db:
        t = db.exec(select(Tenant).where(Tenant.id == current.id)).first()
        if not t:
            raise HTTPException(404, "Tenant not found")
        t.allow_web_research = allow
        db.add(t)
        db.commit()
    return {"ok": True, "allow_web_research": allow}
