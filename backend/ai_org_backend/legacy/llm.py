# llm.py – single wrapper for **both** OpenAI SDK < 1 and ≥ 1
# ------------------------------------------------------------
"""
Call `chat_completion()` everywhere in the code-base instead of touching
OpenAI classes directly.  The helper auto-detects the installed SDK
major version at runtime and falls back gracefully.

Usage
-----
from llm import chat_completion

resp = chat_completion("Say hello world")
"""

from __future__ import annotations

import os
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv

load_dotenv()                               # adds OPENAI_API_KEY if in `.env`

import openai  # noqa: E402                               # import *after* dotenv

# ─────────────────── Detect SDK major version ────────────────────
_IS_V2 = hasattr(openai, "OpenAI")          # True for openai-python ≥ 1.0

if _IS_V2:
    _client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
else:
    openai.api_key = os.getenv("OPENAI_API_KEY")  # legacy style


# ─────────────────── High-level helper ───────────────────────────
def chat_completion(
    prompt: str,
    *,
    model: str = "gpt-3.5-turbo",
    max_tokens: int = 256,
    temperature: float = 0.0,
    system_role: str = "system",
    user_role: str = "user",
    extra_messages: Optional[List[Dict[str, str]]] = None,
    **kwargs: Any,
) -> str:
    """
    Minimal, deterministic wrapper around Chat Completions.

    Parameters
    ----------
    prompt : str
        Main user prompt (goes into the first **`user`** message).
    model : str
        OpenAI chat model name, defaults to *gpt-3.5-turbo*.
    max_tokens : int
        Max completion length.
    temperature : float
        Sampling temperature (0 = deterministic).
    system_role : str
        Role name for the *system* message (ignored by most models but
        kept for compatibility).
    user_role : str
        Role name for the *user* message.
    extra_messages : list(dict)
        Optional list of additional messages *before* the user prompt
        (e.g. few-shot examples).  Format identical to OpenAI SDK:
        `{"role": "user" | "assistant" | "system", "content": "..."}`
    kwargs : dict
        Forwarded to the underlying SDK call.

    Returns
    -------
    str
        The model’s `content` string (leading/trailing whitespace stripped).
    """
    messages = (
        extra_messages.copy() if extra_messages else []
    ) + [
        {"role": system_role, "content": prompt if system_role == "system" else ""},
        {"role": user_role, "content": prompt if system_role != "system" else ""},
    ]

    if _IS_V2:
        # openai-python ≥ 1.0.0
        resp = _client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        return resp.choices[0].message.content.strip()

    # ─ legacy (< 1.0) ─
    resp = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs,
    )
    return resp.choices[0].message.content.strip()


# ─────────────────── Convenience util ────────────────────────────
def tokens_approx(text: str) -> int:
    """Rough “1 token ≈ 0.75 words” heuristic."""
    return int(len(text.split()) * 0.75)
