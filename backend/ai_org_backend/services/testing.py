import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple


def run_tests(tenant_id: str, test_files: List[str]) -> Tuple[bool, str]:
    """Run pytest on the given test files inside an isolated workspace."""
    temp_dir = tempfile.mkdtemp(prefix="qa_test_")
    src_dir = Path("workspace") / tenant_id
    shutil.copytree(src_dir, temp_dir, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.git'))
    try:
        result = subprocess.run([
            "pytest",
            "-q",
            *test_files,
        ], cwd=temp_dir, capture_output=True, text=True)
        test_output = result.stdout + result.stderr
        tests_passed = result.returncode == 0
    except Exception as exc:  # pragma: no cover - subprocess failure
        tests_passed = False
        test_output = f"ERROR: {exc}"
        logging.error(f"[TestingService] Test execution failed: {exc}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return tests_passed, test_output
