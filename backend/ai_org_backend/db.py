from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlmodel import Session, create_engine

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", None)
if not DB_URL:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "ai")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "ai_org")
    DB_URL = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"

engine = create_engine(DB_URL, echo=False)
try:
    with engine.connect() as conn:  # type: ignore[unused-variable]
        pass
except Exception:
    # Fallback to lightweight SQLite if the configured database is unreachable
    engine = create_engine("sqlite:///:memory:", echo=False)


def SessionLocal() -> Session:
    """Return new ORM session bound to engine."""
    return Session(engine)
