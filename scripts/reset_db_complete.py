#!/usr/bin/env python3
"""
Complete database reset script
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))



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
    print("✓ Dropped and recreated all tables with current schema")


if __name__ == "__main__":
    reset_database()
