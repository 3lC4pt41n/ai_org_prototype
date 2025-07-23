# -------- base image ----------
FROM python:3.11-slim

# -------- system deps ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# -------- workdir --------------
WORKDIR /app

# -------- python deps ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -------- project source -------
COPY . /app/ai_org_backend
COPY alembic.ini /app
COPY alembic /app/alembic

# -------- default cmd ----------
CMD ["python", "-m", "ai_org_backend.main"]
