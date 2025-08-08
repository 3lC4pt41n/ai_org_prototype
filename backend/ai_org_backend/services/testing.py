import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import List, Tuple, Optional

from ai_org_backend.config import (
    TEST_CPU_LIMIT,
    TEST_MEMORY_LIMIT,
    TEST_TIMEOUT_SECONDS,
)

DOCKER_IMAGE = "ai_org_test:latest"


def run_tests(tenant_id: str, test_files: List[str]) -> Tuple[bool, str, Optional[str]]:
    """Run pytest inside a sandboxed Docker container.

    Returns a tuple ``(tests_passed, test_output, note)`` where ``note`` contains
    a human readable failure reason (e.g. timeout) to be surfaced in task notes.
    """
    temp_dir = tempfile.mkdtemp(prefix="qa_test_")
    src_dir = Path("workspace") / tenant_id
    shutil.copytree(src_dir, temp_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
    container_name = f"qa_{uuid.uuid4().hex[:8]}"
    note: Optional[str] = None
    try:
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--memory",
            TEST_MEMORY_LIMIT,
            "--cpus",
            TEST_CPU_LIMIT,
            "-v",
            f"{temp_dir}:/workspace",
            "-w",
            "/workspace",
            DOCKER_IMAGE,
            "pytest",
            "-q",
            *test_files,
        ]
        env_vars = os.environ.copy()
        for key in list(env_vars):
            low = key.lower()
            if any(k in low for k in ["key", "token", "secret", "password"]):
                env_vars.pop(key, None)
        logging.info(f"[TestingService] Starting test container for tenant {tenant_id}…")
        result = subprocess.run(
            docker_cmd,
            env=env_vars,
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS,
        )
        test_output = result.stdout + result.stderr
        tests_passed = result.returncode == 0
        if tests_passed:
            logging.info(f"[TestingService] Tests completed successfully for tenant {tenant_id}.")
        else:
            if result.returncode == 137:
                logging.error("[TestingService] Container terminated (OOM/Signal).")
            else:
                logging.warning(
                    f"[TestingService] Tests failed with exit code {result.returncode}."
                )
    except subprocess.TimeoutExpired:
        tests_passed = False
        note = f"Testlauf nach {TEST_TIMEOUT_SECONDS}s abgebrochen (Timeout)"
        logging.error(f"[TestingService] {note}")
        subprocess.run(["docker", "kill", container_name], stderr=subprocess.DEVNULL)
        test_output = f"ERROR: {note}"
    except Exception as exc:  # pragma: no cover - subprocess failure
        tests_passed = False
        note = f"Testausführung fehlgeschlagen: {exc}"
        logging.error(f"[TestingService] {note}")
        test_output = f"ERROR: {exc}"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return tests_passed, test_output, note
