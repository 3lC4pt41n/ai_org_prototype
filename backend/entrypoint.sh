#!/bin/sh
set -e
alembic upgrade head
python /app/ai_org_backend/main.py
