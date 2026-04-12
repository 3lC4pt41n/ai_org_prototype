"""S6-#8.3: Auto-generate deployment files from generated code.

Infers ``requirements.txt`` from Python imports and generates a
``Dockerfile`` based on the Architecture Blueprint tech-stack field.

Usage::

    from ai_org_backend.services.deployment_generator import (
        infer_requirements,
        generate_dockerfile,
        generate_deployment_files,
    )

    reqs = infer_requirements(workspace_path)
    dockerfile = generate_dockerfile(tech_stack="FastAPI + PostgreSQL")
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Standard library modules that should NOT appear in requirements.txt
_STDLIB_MODULES: set[str] = {
    "abc", "argparse", "ast", "asyncio", "base64", "bisect", "builtins",
    "calendar", "cgi", "cmd", "codecs", "collections", "colorsys",
    "compileall", "concurrent", "configparser", "contextlib", "copy",
    "csv", "ctypes", "dataclasses", "datetime", "decimal", "difflib",
    "dis", "email", "enum", "errno", "faulthandler", "filecmp",
    "fileinput", "fnmatch", "fractions", "ftplib", "functools", "gc",
    "getopt", "getpass", "glob", "gzip", "hashlib", "heapq", "hmac",
    "html", "http", "imaplib", "importlib", "inspect", "io",
    "ipaddress", "itertools", "json", "keyword", "linecache",
    "locale", "logging", "lzma", "mailbox", "math", "mimetypes",
    "multiprocessing", "operator", "os", "pathlib", "pickle",
    "platform", "pprint", "profile", "pstats", "py_compile",
    "queue", "random", "re", "reprlib", "resource", "rlcompleter",
    "sched", "secrets", "select", "shelve", "shlex", "shutil",
    "signal", "site", "smtplib", "socket", "socketserver", "sqlite3",
    "ssl", "stat", "statistics", "string", "struct", "subprocess",
    "sys", "syslog", "tarfile", "tempfile", "textwrap", "threading",
    "time", "timeit", "token", "tokenize", "trace", "traceback",
    "tracemalloc", "types", "typing", "unicodedata", "unittest",
    "urllib", "uuid", "venv", "warnings", "wave", "weakref",
    "webbrowser", "xml", "xmlrpc", "zipfile", "zipimport", "zlib",
    # typing extensions
    "typing_extensions", "__future__",
}

# Common import-name → PyPI-package mappings
_IMPORT_TO_PACKAGE: dict[str, str] = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "skimage": "scikit-image",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "jwt": "PyJWT",
    "attr": "attrs",
    "gi": "PyGObject",
    "wx": "wxPython",
    "serial": "pyserial",
    "usb": "pyusb",
    "psycopg2": "psycopg2-binary",
    "sqlmodel": "sqlmodel",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "celery": "celery",
    "redis": "redis",
    "pydantic": "pydantic",
    "httpx": "httpx",
    "requests": "requests",
    "flask": "Flask",
    "django": "Django",
    "sqlalchemy": "SQLAlchemy",
    "alembic": "alembic",
    "jinja2": "Jinja2",
    "numpy": "numpy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
    "scipy": "scipy",
    "torch": "torch",
    "tensorflow": "tensorflow",
    "pytest": "pytest",
}

# Tech-stack → Docker base image mapping
_TECH_STACK_BASE_IMAGES: dict[str, str] = {
    "python": "python:3.11-slim",
    "fastapi": "python:3.11-slim",
    "flask": "python:3.11-slim",
    "django": "python:3.11-slim",
    "node": "node:20-slim",
    "react": "node:20-slim",
    "next": "node:20-slim",
    "go": "golang:1.22-alpine",
    "rust": "rust:1.77-slim",
}


def infer_requirements(workspace_path: str) -> list[str]:
    """S6-#8.3: Infer Python dependencies from import statements.

    Scans all .py files, extracts top-level import names, filters
    stdlib modules, and maps to PyPI package names.

    Returns sorted list of package names (without version pins).
    """
    workspace = Path(workspace_path)
    if not workspace.is_dir():
        return []

    top_level_imports: set[str] = set()
    local_modules: set[str] = set()

    # First pass: collect local module names (files in the workspace)
    for py_file in workspace.rglob("*.py"):
        parts = py_file.relative_to(workspace).parts
        if any(p in ("venv", ".venv", "__pycache__", "node_modules", ".git") for p in parts):
            continue
        # The top-level module name is the first directory or the stem
        if len(parts) > 1:
            local_modules.add(parts[0])
        else:
            local_modules.add(py_file.stem)

    # Second pass: extract imports
    for py_file in workspace.rglob("*.py"):
        parts = py_file.relative_to(workspace).parts
        if any(p in ("venv", ".venv", "__pycache__", "node_modules", ".git") for p in parts):
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        top_level_imports.add(top)
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.level == 0:
                        top = node.module.split(".")[0]
                        top_level_imports.add(top)
        except (SyntaxError, Exception):
            continue

    # Filter out stdlib + local modules
    external = top_level_imports - _STDLIB_MODULES - local_modules

    # Map to PyPI package names
    packages: set[str] = set()
    for mod in external:
        pkg = _IMPORT_TO_PACKAGE.get(mod, mod)
        packages.add(pkg)

    result = sorted(packages, key=str.lower)
    logger.info(
        "[S6-#8.3] Inferred %d packages from %s: %s",
        len(result), workspace_path, ", ".join(result[:10]),
    )
    return result


def generate_requirements_txt(workspace_path: str) -> str:
    """Generate a requirements.txt content string from workspace imports."""
    packages = infer_requirements(workspace_path)
    header = "# Auto-generated by ai_org deployment_generator (S6-#8.3)\n"
    return header + "\n".join(packages) + "\n" if packages else header


def generate_dockerfile(
    tech_stack: str = "python",
    *,
    has_requirements: bool = True,
    entrypoint: str = "main.py",
) -> str:
    """S6-#8.3: Generate a Dockerfile based on tech stack.

    Parameters
    ----------
    tech_stack : str
        Technology stack description (e.g. "FastAPI + PostgreSQL").
    has_requirements : bool
        Whether to include pip install step.
    entrypoint : str
        The main file to run.
    """
    # Determine base image from tech stack keywords
    stack_lower = tech_stack.lower()
    base_image = "python:3.11-slim"  # default
    for keyword, image in _TECH_STACK_BASE_IMAGES.items():
        if keyword in stack_lower:
            base_image = image
            break

    is_python = "python" in base_image
    is_node = "node" in base_image

    lines = [
        f"# Auto-generated Dockerfile (S6-#8.3)",
        f"FROM {base_image}",
        "",
        "WORKDIR /app",
        "",
        "# Copy dependency manifests first for caching",
    ]

    if is_python and has_requirements:
        lines += [
            "COPY requirements.txt .",
            "RUN pip install --no-cache-dir -r requirements.txt",
        ]
    elif is_node:
        lines += [
            "COPY package*.json ./",
            "RUN npm ci --production",
        ]

    lines += [
        "",
        "# Copy application code",
        "COPY . .",
        "",
    ]

    if is_python:
        if "uvicorn" in stack_lower or "fastapi" in stack_lower:
            lines.append('CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]')
        elif "gunicorn" in stack_lower or "flask" in stack_lower:
            lines.append('CMD ["gunicorn", "-b", "0.0.0.0:8000", "main:app"]')
        else:
            lines.append(f'CMD ["python", "{entrypoint}"]')
    elif is_node:
        lines.append('CMD ["node", "index.js"]')
    else:
        lines.append(f'CMD ["./{entrypoint}"]')

    lines.append("")  # trailing newline
    return "\n".join(lines)


def generate_deployment_files(
    workspace_path: str,
    tech_stack: str = "python",
    *,
    write_to_disk: bool = False,
) -> dict[str, str]:
    """S6-#8.3: Generate all deployment files for a workspace.

    Returns dict mapping filename → content.
    Optionally writes files to disk if ``write_to_disk=True``.
    """
    workspace = Path(workspace_path)
    files: dict[str, str] = {}

    # requirements.txt
    req_content = generate_requirements_txt(workspace_path)
    files["requirements.txt"] = req_content

    # Dockerfile
    has_reqs = bool(infer_requirements(workspace_path))
    dockerfile = generate_dockerfile(
        tech_stack, has_requirements=has_reqs,
    )
    files["Dockerfile"] = dockerfile

    if write_to_disk and workspace.is_dir():
        for fname, content in files.items():
            target = workspace / fname
            if not target.exists():  # don't overwrite existing files
                target.write_text(content, encoding="utf-8")
                logger.info("[S6-#8.3] Written %s to %s", fname, target)

    return files
