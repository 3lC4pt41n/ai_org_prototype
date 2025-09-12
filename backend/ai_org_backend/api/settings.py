"""Settings endpoints for per-tenant toggles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..api.dependencies import get_current_tenant
from ..db import engine
from ..models import Tenant

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/research")
def get_research_setting(current: Tenant = Depends(get_current_tenant)):
    """Return whether the current tenant allows web research."""
    with Session(engine) as session:
        t = session.exec(select(Tenant).where(Tenant.id == current.id)).first()
        if not t:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return {"allow_web_research": bool(getattr(t, "allow_web_research", True))}


@router.post("/research")
def set_research_setting(payload: dict, current: Tenant = Depends(get_current_tenant)):
    """Update the tenant's web research setting."""
    val = bool(payload.get("allow_web_research", True))
    with Session(engine) as session:
        t = session.exec(select(Tenant).where(Tenant.id == current.id)).first()
        if not t:
            raise HTTPException(status_code=404, detail="Tenant not found")
        t.allow_web_research = val
        session.add(t)
        session.commit()
        return {"allow_web_research": val}


@router.get("/theme")
def get_theme_setting(current: Tenant = Depends(get_current_tenant)):
    """Return the current tenant's theme preference."""
    with Session(engine) as session:
        t = session.exec(select(Tenant).where(Tenant.id == current.id)).first()
        if not t:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return {"theme": getattr(t, "theme", "light")}


@router.post("/theme")
def set_theme_setting(payload: dict, current: Tenant = Depends(get_current_tenant)):
    """Update the tenant's theme preference (light or dark)."""
    theme_value = payload.get("theme")
    if theme_value not in ("light", "dark"):
        raise HTTPException(status_code=400, detail="Invalid theme value")
    with Session(engine) as session:
        t = session.exec(select(Tenant).where(Tenant.id == current.id)).first()
        if not t:
            raise HTTPException(status_code=404, detail="Tenant not found")
        t.theme = theme_value
        session.add(t)
        session.commit()
        return {"theme": theme_value}
