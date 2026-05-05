"""Intent compiler package for multi-axis request semantics."""

from .compiler import CompiledIntent, IntentCompiler, compile_intent, legacy_role_for_intent
from .schema import UserIntent

__all__ = [
    "CompiledIntent",
    "IntentCompiler",
    "UserIntent",
    "compile_intent",
    "legacy_role_for_intent",
]
