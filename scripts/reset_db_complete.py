#!/usr/bin/env python3
"""
Complete database reset script
"""

import os
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from sqlmodel import SQLModel, create_engine
from ai_org_backend.models import Tenant, Task, TaskDependency, Purpose, Artifact

def reset_database():
    """Drop and recreate all tables."""
    
    db_path = "ai_org.db"
    
    # Remove existing database
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"✓ Removed existing database: {db_path}")
    
    # Create new database with all tables
    engine = create_engine(f"sqlite:///{db_path}", echo=True)
    SQLModel.metadata.create_all(engine)
    print("✓ Created all tables with current schema")

if __name__ == "__main__":
    reset_database()
