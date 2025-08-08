"""LLM-guided web research utilities.

This module implements a small loop where an OpenAI model can call
tools to search the web and fetch web pages. It returns a markdown
summary and sources list. Fetching uses DuckDuckGo for search and
Readability for extraction; URLs are checked via `url_safety`.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from readability import Document

from .llm_client import MODEL_THINKING, chat_with_tools
from .url_safety import is_url_safe

MAX_STEPS = int(os.getenv("DEEPRESEARCH_MAX_STEPS", "8"))
MAX_BYTES = int(os.getenv("DEEPRESEARCH_MAX_FETCH_BYTES", "3000000"))
TIMEOUT_S = int(os.getenv("DEEPRESEARCH_TIMEOUT_S", "20"))
USER_AGENT = os.getenv("DEEPRESEARCH_USER_AGENT", "ai-org-research-bot/1.0")
SEARCH_TOPK = int(os.getenv("DEEPRESEARCH_SEARCH_TOPK", "6"))

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the public web for relevant documents and links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Download and extract main textual content from a web page.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "format": "uri"}},
                "required": ["url"],
            },
        },
    },
]


def _search_ddg(query: str, top_k: int = SEARCH_TOPK) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=top_k):
            results.append(
                {
                    "title": r.get("title") or "",
                    "url": r.get("href") or "",
                    "snippet": r.get("body") or "",
                }
            )
    return results


def _fetch_and_extract(url: str) -> Dict[str, str]:
    if not is_url_safe(url):
        return {"url": url, "title": "", "text": "", "lang": "", "note": "blocked_by_safety"}
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=TIMEOUT_S, headers=headers, follow_redirects=True) as client:
        resp = client.get(url)
        content = resp.content[:MAX_BYTES]
        html = content.decode(resp.encoding or "utf-8", errors="ignore")
    doc = Document(html)
    title = (doc.short_title() or "").strip()
    summary_html = doc.summary()
    soup = BeautifulSoup(summary_html, "lxml")
    text = re.sub(r"\s+\n", "\n", soup.get_text("\n")).strip()
    lang = "de" if re.search(r"[äöüßÄÖÜ]", text) else "en"
    return {"url": url, "title": title, "text": text, "lang": lang, "note": ""}


def run_deep_research(
    tenant_id: str,
    question: str,
    model: str | None = None,
    max_steps: int = MAX_STEPS,
) -> Dict[str, Any]:
    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a meticulous research assistant. Use web_search to find sources, "
                "web_fetch to read them, then write a concise, well-cited summary. "
                "Always include a final 'Sources' list with the top URLs you used."
            ),
        },
        {"role": "user", "content": question},
    ]
    used_sources: Dict[str, Dict[str, str]] = {}

    for step in range(max_steps):
        resp = chat_with_tools(
            messages=messages, tools=TOOLS, model=model or MODEL_THINKING, tenant=tenant_id
        )
        if resp is None:
            return {
                "summary": "Budget exhausted",
                "sources": [],
                "raw": {"steps": step, "note": "budget_exhausted"},
            }
        choice = resp["choices"][0]
        msg = choice["message"]
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            messages.append(
                {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
            )
            for call in tool_calls:
                fn = call["function"]["name"]
                args = json.loads(call["function"].get("arguments") or "{}")
                if fn == "web_search":
                    query = args.get("query", "")
                    top_k = int(args.get("top_k") or SEARCH_TOPK)
                    results = _search_ddg(query, top_k=top_k)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "name": "web_search",
                            "content": json.dumps({"results": results}, ensure_ascii=False),
                        }
                    )
                elif fn == "web_fetch":
                    url = str(args.get("url") or "")
                    data = _fetch_and_extract(url)
                    if data.get("text"):
                        used_sources[url] = {"title": data.get("title") or url, "url": url}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "name": "web_fetch",
                            "content": json.dumps({"page": data}, ensure_ascii=False),
                        }
                    )
            continue
        final = msg.get("content") or ""
        sources = list(used_sources.values())
        return {"summary": final, "sources": sources, "raw": {"steps": step + 1}}
    return {
        "summary": "Research aborted after max steps without a final answer.",
        "sources": list(used_sources.values()),
        "raw": {"steps": max_steps, "note": "max_steps_reached"},
    }
