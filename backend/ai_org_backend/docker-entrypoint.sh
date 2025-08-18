#!/bin/sh
set -e

if [ ! -f /app/alembic.ini ]; then
  echo "ERROR: Alembic config file /app/alembic.ini is missing. Exiting."
  exit 1
fi

if [ ! -d /app/alembic ]; then
  echo "Alembic directory not found; initializing Alembic environment..."
  alembic init alembic
fi

echo "Running Alembic migrations..."
alembic upgrade head
echo "Migrations complete."

exec "$@"
