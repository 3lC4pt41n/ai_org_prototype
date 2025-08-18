"""ai_org_backend – Backend package.

Importing this package performs a lightweight bootstrap that ensures Alembic
artefacts are available under ``/app`` and that the ``scripts`` module is
importable. This prevents runtime errors when images only contain the installed
package without copying Alembic files.
"""

from . import boot  # noqa: F401  # ensure bootstrap executes on import
