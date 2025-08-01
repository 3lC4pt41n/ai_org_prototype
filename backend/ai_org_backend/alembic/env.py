# backend/ai_org_backend/alembic/env.py

from logging.config import fileConfig
from alembic import context

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
