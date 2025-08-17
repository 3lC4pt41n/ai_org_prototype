FROM python:3.11-slim as base

# System deps (git für Repo-Init; libxml2/xslt als Fallback für lxml-Wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libpq-dev \
    curl \
    libxml2 \
    libxslt1.1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Anforderungen installieren (direkt aus dem App-Ordner)
COPY ai_org_backend/requirements.txt /app/requirements.txt
# Laufzeit-Umgebung / Alembic
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ALEMBIC_CONFIG=/app/alembic.ini \
    PYTHONPATH=/app
RUN pip install --no-cache-dir -r /app/requirements.txt

# Application source
COPY . /app/ai_org_backend
# Top-level scripts-Package für `from scripts.seed_graph import ingest`
COPY scripts /app/scripts
# Alembic: zentrale, service-übergreifende Location
COPY ai_org_backend/alembic.ini /app/alembic.ini
COPY ai_org_backend/alembic /app/alembic
COPY ai_org_backend/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh
ENTRYPOINT ["/app/docker-entrypoint.sh"]
