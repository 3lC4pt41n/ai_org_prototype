# DEPRECATED: Legacy Migration Files

These migration files are **DEPRECATED** and no longer in use.

## Why?

The new Alembic configuration with the canonical migration directory is located at:
```
backend/ai_org_backend/alembic/versions/
```

The initial schema migration (`20251207_init_schema.py`) creates the full database schema from scratch, superseding all the legacy migrations previously stored here.

## What to do?

- **For new development**: All new migrations should be created in `backend/ai_org_backend/alembic/versions/`
- **For reference**: These files are kept for historical reference only and may be needed for auditing or understanding past changes
- **Do NOT use**: Do not apply or reference these migrations in production or development workflows

## Migration Information

The legacy files in this directory include:
- Tenant setup and configuration
- Pipeline templates and phases
- Chat messaging and artifacts
- Feedback collection
- Various schema refinements and data normalization migrations

All of these are now consolidated into the single init schema that creates a complete database schema ready for use.
