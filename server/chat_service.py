"""Runs the CRAG agent for one question and emits user-friendly stream events.

Event types (one JSON object per line):

* ``status``  - a short plain-language progress message
* ``token``   - a piece of the answer as it is written
* ``reset``   - discard the partial answer (the agent is improving it)
* ``done``    - the final answer, its sources and whether it was verified
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any
from urllib.parse import urlparse

from src.conversation import standalone_question
from src.graph import get_app, run_config
from src.state import initial_state
from src.utils.tracing import flush_tracing

STATUS_AFTER: dict[str, str] = {
    "retrieve": "Picking the most relevant passages",
    "rerank": "Checking what is useful",
    "transform_query": "Searching the web",
    "web_search": "Writing your answer",
    "generate": "Double-checking the answer",
}


def _status_after(node: str, update: dict[str, Any]) -> str | None:
    if node == "grade_documents":
        return "Looking further on the web" if update.get("web_search_needed") else "Writing your answer"
    if node == "check_hallucination":
        return None if (update.get("verification") or {}).get("passed") else "Improving the answer"
    return STATUS_AFTER.get(node)


def _sources(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in citations:
        is_web = c.get("origin") == "web"
        title = c.get("source") or "Source"
        if is_web and c.get("url"):
            host = urlparse(c["url"]).netloc.removeprefix("www.")
            title = f"{title} ({host})" if host and host not in title else title
        out.append(
            {
                "number": c["index"],
                "title": title,
                "kind": "web" if is_web else "document",
                "url": c.get("url") if is_web else None,
                "excerpt": " ".join((c.get("snippet") or "").split())[:240],
            }
        )
    return out


def answer_events(question: str, owner: str, history: Sequence[tuple[str, str]]) -> Iterator[dict[str, Any]]:
    """Yield stream events while the agent answers ``question`` from ``owner``'s documents."""
    yield {"type": "status", "text": "Reading your documents"}
    standalone = standalone_question(question, history)
    final: dict[str, Any] = {}
    generation_open = False
    has_tokens = False
    try:
        for mode, payload in get_app().stream(
            initial_state(standalone, owner), config=run_config(), stream_mode=["updates", "messages"]
        ):
            if mode == "messages":
                chunk, meta = payload
                if meta.get("langgraph_node") != "generate" or not isinstance(chunk.content, str) or not chunk.content:
                    continue
                if not generation_open:
                    if has_tokens:
                        yield {"type": "reset"}
                    generation_open, has_tokens = True, True
                yield {"type": "token", "text": chunk.content}
                continue
            for node, update in (payload or {}).items():
                update = update or {}
                final.update({k: v for k, v in update.items() if k != "evaluation_trace"})
                if node == "generate":
                    generation_open = False
                status = _status_after(node, update)
                if status:
                    yield {"type": "status", "text": status}
    finally:
        flush_tracing()

    verification = final.get("verification") or {}
    yield {
        "type": "done",
        "answer": final.get("generation", ""),
        "sources": _sources(final.get("citations", [])),
        "verified": bool(verification.get("passed")),
    }
