# -------- base image ----------
FROM python:3.11-slim AS base

# -------- system deps ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# -------- workdir --------------
WORKDIR /app

# -------- python deps ----------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -------- project source -------
COPY . /app/ai_org_backend
COPY alembic.ini /app
COPY alembic /app/alembic

FROM base AS prod
CMD ["python", "-m", "ai_org_backend.main"]

FROM prod AS test
RUN apt-get update && apt-get install -y --no-install-recommends \
        libnss3 libatk1.0 libdrm2 libxkbcommon0 libxcb1 libx11-6 libxcomposite1 \
        libxdamage1 libxext6 libxfixes3 libxrandr2 libgtk-3-0 libgbm1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir playwright==1.37.0 locust==2.17.5 bandit==1.7.5 pip-audit==2.4.4
RUN playwright install --with-deps chromium
