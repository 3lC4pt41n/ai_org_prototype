"""S5-A1: Shared Contracts loader.

Loads the canonical ``shared_contracts.txt`` that all agents must reference.
The file is loaded once and cached for the lifetime of the process.
Agents receive the full text injected into their prompt context.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


def _find_contracts_file() -> Path:
    """Walk up from this file to find prompts/shared_contracts.txt."""
    base = Path(__file__).resolve()
    for parent in [base, *base.parents]:
        candidate = parent / "prompts" / "shared_contracts.txt"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("shared_contracts.txt not found in any parent prompts/ dir")


@lru_cache(maxsize=1)
def load_shared_contracts() -> str:
    """Return the full shared contracts text (cached after first read).

    If the file cannot be found, returns an empty string (agents can still
    function without it, but code-review will flag violations).
    """
    try:
        path = _find_contracts_file()
        text = path.read_text(encoding="utf-8").strip()
        logger.info("[S5-A1] Loaded shared contracts (%d chars) from %s", len(text), path)
        return text
    except FileNotFoundError:
        logger.warning("[S5-A1] shared_contracts.txt not found – agents run without constraints")
        return ""
    except Exception as exc:
        logger.error("[S5-A1] Failed to load shared contracts: %s", exc)
        return ""
