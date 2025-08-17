from __future__ import annotations
import os
import sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, create_engine
from alembic import context

# ------------------------------------------------------------------
# Pfade robust setzen, damit `import ai_org_backend` immer klappt
# ------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))                    # .../backend/ai_org_backend/alembic
PKG_ROOT = os.path.abspath(os.path.join(HERE, ".."))                 # .../backend/ai_org_backend
BACKEND_ROOT = os.path.abspath(os.path.join(PKG_ROOT, ".."))         # .../backend
APP_ROOT = os.path.abspath(os.path.join(BACKEND_ROOT, ".."))         # .../ (Repo)
for p in (APP_ROOT, BACKEND_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# ------------------------------------------------------------------
# Alembic Konfiguration / Logging
# ------------------------------------------------------------------
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ------------------------------------------------------------------
# Ziel-Metadaten und Engine-Ermittlung
# ------------------------------------------------------------------
target_metadata = None

def _load_metadata():
    global target_metadata
    try:
        # Erwartetes Pattern: Base.metadata im Projekt
        from ai_org_backend.db import Base  # type: ignore
        target_metadata = getattr(Base, "metadata", None)
    except Exception as e:
        # Kein harter Abbruch: Migrations mit expliziten Versionsskripten funktionieren
        print(f"[alembic/env.py] Could not import Base.metadata ({e}); proceeding without target_metadata.")

_load_metadata()

def _get_sqlalchemy_url() -> str:
    # Bevorzugt Env-Var; fallback auf INI, falls gesetzt
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url and ini_url.strip():
        return ini_url
    raise RuntimeError(
        "DATABASE_URL not set and sqlalchemy.url not configured in alembic.ini"
    )

# ------------------------------------------------------------------
# Offline / Online Migrations
# ------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = _get_sqlalchemy_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    url = _get_sqlalchemy_url()
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
