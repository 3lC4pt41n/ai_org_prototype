from __future__ import annotations

import os
from sqlmodel import create_engine

DB_URL = os.getenv("DATABASE_URL", "sqlite:///ai_org.db")
engine = create_engine(DB_URL, echo=False)
