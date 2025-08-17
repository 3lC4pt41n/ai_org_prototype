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

# Execute the original container command
exec "$@"
