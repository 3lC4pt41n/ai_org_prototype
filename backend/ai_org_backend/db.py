from __future__ import annotations

import os
from sqlmodel import Session, create_engine

DB_URL = os.getenv("DATABASE_URL", "sqlite:///ai_org.db")
engine = create_engine(DB_URL, echo=False)


def SessionLocal() -> Session:
    """Return new ORM session bound to engine."""
    return Session(engine)
