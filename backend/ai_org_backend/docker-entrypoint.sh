#!/bin/sh
set -e

# Require explicit Alembic config file (no defaults)
if [ ! -f /app/alembic.ini ]; then
    echo "ERROR: Alembic config file /app/alembic.ini is missing. Exiting."
    exit 1
fi

# Initialize Alembic if the migration scripts directory is missing
if [ ! -d /app/alembic ]; then
    echo "Alembic directory not found; initializing Alembic environment..."
    alembic init alembic
fi

# Always attempt to upgrade to the latest migration head
echo "Running Alembic migrations..."
alembic upgrade head
echo "Migrations complete."

# Execute the original container command
exec "$@"
