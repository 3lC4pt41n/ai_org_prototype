from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _safe_symlink_or_copy(src: Path, dst: Path) -> None:
    """Create a symlink ``src`` -> ``dst`` if possible, otherwise copy.

    This falls back to copying when the filesystem or OS does not allow
    symlinks (common on Windows or restricted environments).
    """
    if dst.exists():
        return
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.symlink_to(src, target_is_directory=src.is_dir())
        return
    except Exception:  # pragma: no cover - best effort
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def bootstrap() -> None:
    """Ensure alembic artefacts and ``scripts`` are available at runtime.

    Some container images only install the package itself. This function makes
    sure the ``alembic`` directory and ``alembic.ini`` exist at ``/app`` and
    exposes the ``scripts`` directory on ``sys.path`` so they can be imported.
    """
    base = Path("/app")
    app_dir = Path(__file__).resolve().parent

    src_alembic_dir = app_dir / "alembic"
    src_alembic_ini = app_dir / "alembic.ini"
    dst_alembic_dir = base / "alembic"
    dst_alembic_ini = base / "alembic.ini"

    try:
        if src_alembic_dir.exists() and not dst_alembic_dir.exists():
            _safe_symlink_or_copy(src_alembic_dir, dst_alembic_dir)

        if src_alembic_ini.exists() and not dst_alembic_ini.exists():
            _safe_symlink_or_copy(src_alembic_ini, dst_alembic_ini)

        os.environ.setdefault("ALEMBIC_CONFIG", str(dst_alembic_ini))

        for candidate in (base / "scripts", app_dir.parent / "scripts"):
            if candidate.exists():
                p = str(candidate)
                if p not in sys.path:
                    sys.path.append(p)
                break
    except Exception as exc:  # pragma: no cover - bootstrap must not crash
        log.warning("Bootstrap (alembic/scripts) failed: %s", exc)


bootstrap()
