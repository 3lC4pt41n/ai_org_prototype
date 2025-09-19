FROM python:3.11-slim as base

# System deps (git for repo init; libxml2/xslt fallback for lxml wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libpq-dev \
    curl \
    libxml2 \
    libxslt1.1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install requirements (directly from the app folder)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
# install project deps (ensure wheels for bcrypt/passlib)
RUN pip install --no-cache-dir -r requirements.txt
# Runtime environment / Alembic
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ALEMBIC_CONFIG=/app/alembic.ini \
    PYTHONPATH=/app

# Application source
COPY . /app/ai_org_backend
# Alembic: central, cross-service location
COPY ai_org_backend/alembic.ini /app/alembic.ini
COPY ai_org_backend/alembic /app/alembic
