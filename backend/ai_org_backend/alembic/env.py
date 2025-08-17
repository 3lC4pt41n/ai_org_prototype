# backend/ai_org_backend/alembic/env.py

import logging
from logging.config import fileConfig
import os
import sys
from alembic import context

# --- Make project package importable ---------------------------------------
# Alembic wird im Container typischerweise aus /app gestartet. Unsere
# Paketwurzel liegt bei /app/backend, dort befindet sich ai_org_backend/.
# Wir fügen /app/backend (relativ zu dieser Datei) zum sys.path hinzu,
# damit "from ai_org_backend..." zuverlässig funktioniert.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# ---------------------------------------------------------------------------

# Importiere die SQLModel-MetaData!
from ai_org_backend.db import engine
from sqlmodel import SQLModel
from ai_org_backend.models import *

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Das ist entscheidend!
target_metadata = SQLModel.metadata

def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
