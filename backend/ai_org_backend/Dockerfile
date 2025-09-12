# -------- base image ----------
FROM python:3.11-slim AS base

# -------- system deps ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl git \
    && rm -rf /var/lib/apt/lists/*

# -------- workdir --------------
WORKDIR /app

# -------- python deps ----------
COPY backend/ai_org_backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# -------- project source -------
COPY backend/ai_org_backend /app/ai_org_backend
COPY backend/ai_org_backend/alembic.ini /app
COPY backend/ai_org_backend/alembic /app/alembic
COPY prompts /app/prompts

# Ensure pnpm available for frontend builds
RUN corepack enable && corepack prepare pnpm@latest --activate

# Alembic: Migrationsordner verbleibt unter /app (entspricht script_location=alembic)

FROM base AS prod
CMD ["python", "-m", "ai_org_backend.main"]

FROM prod AS test
RUN apt-get update && apt-get install -y --no-install-recommends \
        libnss3 libatk1.0 libdrm2 libxkbcommon0 libxcb1 libx11-6 libxcomposite1 \
        libxdamage1 libxext6 libxfixes3 libxrandr2 libgtk-3-0 libgbm1 \
    && rm -rf /var/lib/apt/lists/*
# ---- Test/QA toolchain (optional; enabled by default) ------------------------
ARG WITH_TEST_EXTRAS=true
ARG PLAYWRIGHT_VERSION=1.37.0
ARG LOCUST_VERSION=2.20.1          # 2.20.2 is yanked; 2.17.5 never existed on PyPI
ARG BANDIT_VERSION=1.7.5
ARG PIP_AUDIT_VERSION=2.4.4

RUN if [ "$WITH_TEST_EXTRAS" = "true" ]; then \
      pip install --no-cache-dir \
        "playwright==${PLAYWRIGHT_VERSION}" \
        "locust==${LOCUST_VERSION}" \
        "bandit==${BANDIT_VERSION}" \
        "pip-audit==${PIP_AUDIT_VERSION}" \
      && playwright install chromium; \
    else \
      echo "Skipping test/QA extras (WITH_TEST_EXTRAS=false)"; \
    fi
