# ---- base image ----
FROM python:3.11-slim

# system deps (optional): gcc, libpq etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# workdir
WORKDIR /app

# copy & install python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy project source
COPY backend/ai_org_backend /app/ai_org_backend
COPY backend/alembic.ini /app
COPY backend/alembic /app/alembic

# default command (can be overridden in compose)
CMD ["uvicorn", "ai_org_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

