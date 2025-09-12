#!/usr/bin/env python3
"""
Complete database reset script
"""

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# Import all models so that SQLModel.metadata contains every table
import ai_org_backend.models  # noqa: F401,E402  # Import all models (e.g. Task, Tenant, Artifact)


def reset_database():
    """Drop and recreate all tables."""

    # Load environment and connect to configured Postgres database
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        user = os.getenv("POSTGRES_USER", "postgres")
        password = os.getenv("POSTGRES_PASSWORD", "ai")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db_name = os.getenv("POSTGRES_DB", "ai_org")
        db_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"
    engine = create_engine(db_url, echo=True)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    # Ensure the Alembic version table exists and supports longer version_num
    from sqlalchemy import text

    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='alembic_version'"
            )
        )
        if result.first() is not None:
            conn.execute(
                text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
            )
            conn.commit()
            print("✓ Column 'version_num' in alembic_version extended to VARCHAR(64)")
        else:
            conn.execute(
                text(
                    "CREATE TABLE alembic_version ("
                    "version_num VARCHAR(64) NOT NULL, "
                    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
                    ")"
                )
            )
            conn.commit()
            print("✓ Created alembic_version table (version_num VARCHAR(64))")
    print("✓ Dropped and recreated all tables with current schema")
    alembic_cfg = Config(str(backend_dir / "ai_org_backend" / "alembic.ini"))
    command.stamp(alembic_cfg, "head")
    print("✓ Alembic stamped to head")


if __name__ == "__main__":
    reset_database()
