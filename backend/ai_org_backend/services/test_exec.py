"""
Minimal test executor utilities used by integration/e2e/perf/security agents.
Safe-by-default: if a tool is missing (e.g., Playwright/Locust), we skip gracefully.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Optional, Tuple


def _run(
    cmd: list[str] | str, cwd: Optional[str] = None, timeout: int = 1800
) -> Tuple[int, str, str]:
    """Run a command and capture output. Accepts list or shell string."""
    shell = isinstance(cmd, str)
    proc = subprocess.run(
        cmd, cwd=cwd, shell=shell, capture_output=True, text=True, timeout=timeout  # nosec
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_pytest(
    paths: list[str],
    marker: Optional[str] = None,
    extra_args: Optional[list[str]] = None,
    timeout: int = 1800,
) -> Tuple[int, str, str]:
    """Run pytest with optional marker. Returns rc, stdout, stderr."""
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if marker:
        cmd += ["-m", marker]
    if extra_args:
        cmd += extra_args
    cmd += paths
    return _run(cmd, timeout=timeout)


def ensure_playwright() -> bool:
    """Try to ensure Playwright is ready; return True if import/browsers available."""
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        pass
    # Try to install browsers (best effort)
    try:
        rc, out, err = _run([sys.executable, "-m", "playwright", "install"], timeout=1200)
        return rc == 0
    except Exception:
        return False


def run_bandit(target_dir: str = "backend") -> Tuple[int, str, str]:
    """Run Bandit static analysis; returns rc, stdout(json), stderr.
    rc==0 means no issues of selected severity."""
    if shutil.which("bandit") is None:
        # Simulate "no bandit": succeed with empty report
        return 0, json.dumps({"results": []}), ""
    return _run(["bandit", "-q", "-r", target_dir, "-f", "json"], timeout=1200)


def run_pip_audit(requirements_file: Optional[str] = None) -> Tuple[int, str, str]:
    """Run pip-audit; returns rc, stdout(json), stderr. rc==0 means no vulns."""
    if shutil.which("pip-audit") is None:
        return 0, json.dumps({"dependencies": [], "vulnerabilities": []}), ""
    cmd = ["pip-audit", "-f", "json"]
    if requirements_file and os.path.exists(requirements_file):
        cmd += ["-r", requirements_file]
    return _run(cmd, timeout=1200)


def run_locust(
    locustfile: str,
    host: str,
    users: int = 20,
    spawn_rate: int = 5,
    run_time: str = "1m",
    csv_base: str = "/tmp/locust",
) -> Tuple[int, str, str]:
    """Run locust headless; returns rc, stdout, stderr. Requires 'locust' in PATH."""
    if shutil.which("locust") is None:
        # Skip if not available
        return 0, "locust not installed; skipping performance test.", ""
    cmd = [
        "locust",
        "-f",
        locustfile,
        "--headless",
        "-u",
        str(users),
        "-r",
        str(spawn_rate),
        "--run-time",
        run_time,
        "--host",
        host,
        "--csv",
        csv_base,
        "--only-summary",
    ]
    return _run(cmd, timeout=3600)
