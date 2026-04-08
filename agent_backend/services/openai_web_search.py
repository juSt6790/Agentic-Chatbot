"""
Public web search via OpenAI Responses API (web_search_preview).

Standalone tool: one Responses call per invocation. Uses the cheapest model that
supports hosted web search (default: gpt-4o-mini).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

WEB_SEARCH_MODEL = os.getenv("OPENAI_WEB_SEARCH_MODEL", "gpt-4o-mini")

_INSTRUCTIONS = """You have web search. Use it to answer the user's query with current, factual public information.
Be concise. Prefer short paragraphs or bullet points. Cite sources implicitly in your answer when the API provides citations."""


def _collect_url_sources(response) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in response.output or []:
        if getattr(item, "type", None) != "message":
            continue
        for part in getattr(item, "content", []) or []:
            if getattr(part, "type", None) != "output_text":
                continue
            for ann in getattr(part, "annotations", []) or []:
                if getattr(ann, "type", None) == "url_citation":
                    url = getattr(ann, "url", None) or ""
                    if url and url not in seen:
                        seen.add(url)
                        sources.append(
                            {
                                "title": getattr(ann, "title", "") or "",
                                "url": url,
                            }
                        )
    return sources


def web_search(query: str, token: str | None = None) -> dict[str, Any]:
    """
    Run a web-backed search/answer for public information. Not for workspace data.

    `token` is accepted for parity with other tools but is unused (OpenAI uses OPENAI_API_KEY).
    """
    del token  # unused; workspace auth does not apply to OpenAI web search
    q = (query or "").strip()
    if not q:
        return {"status": "error", "message": "query is required"}

    if not os.getenv("OPENAI_API_KEY"):
        return {
            "status": "error",
            "message": "OPENAI_API_KEY is not configured; web search is unavailable.",
        }

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    params = {
        "model": WEB_SEARCH_MODEL,
        "tools": [{"type": "web_search_preview"}],
        "tool_choice": {"type": "web_search_preview"},
        "instructions": _INSTRUCTIONS,
        "input": q,
    }
    try:
        response = client.responses.create(**params)
    except Exception as e:
        logger.warning("OpenAI web_search failed (forced tool): %s", e)
        try:
            params_retry = {**params, "tool_choice": "auto"}
            response = client.responses.create(**params_retry)
        except Exception as e2:
            logger.warning("OpenAI web_search retry failed: %s", e2)
            return {"status": "error", "message": str(e2)}

    text = (response.output_text or "").strip()
    sources = _collect_url_sources(response)
    if not text:
        return {
            "status": "error",
            "message": "Empty response from web search.",
            "sources": sources,
        }

    out: dict[str, Any] = {
        "status": "success",
        "answer": text,
        "sources": sources,
        "model": getattr(response, "model", None) or WEB_SEARCH_MODEL,
    }
    return out
