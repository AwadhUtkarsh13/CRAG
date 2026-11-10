"""Runs the CRAG agent for one question and emits user-friendly stream events.

Event types (one JSON object per line):

* ``status``  - a short plain-language progress message
* ``token``   - a piece of the answer as it is written
* ``reset``   - discard the partial answer (the agent is improving it)
* ``done``    - the final answer, its sources, whether it was verified, and the outcome
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from typing import Any
from urllib.parse import urlparse

from src.conversation import standalone_question
from src.graph import get_app, run_config
from src.ingestion.vector_store import get_index
from src.state import initial_state
from src.utils.tracing import flush_tracing

_SMALL_TALK = [
    (
        re.compile(r"^(hi+|hello+|hey+|hiya|namaste|good (morning|afternoon|evening))\b[\s!.,]*$", re.I),
        "Hi! Ask me anything about the selected documents.",
    ),
    (
        re.compile(r"^(thanks|thank you|thx|ty|thanks a lot|thank you so much)\b[\s!.,]*$", re.I),
        "You're welcome! Ask another question whenever you like.",
    ),
    (re.compile(r"^(ok|okay|cool|great|nice|got it|alright)\b[\s!.,]*$", re.I), "Sure. What would you like to know?"),
    (re.compile(r"^(bye|goodbye|see you|see ya)\b[\s!.,]*$", re.I), "Goodbye! Your chat is saved for later."),
]


def small_talk_reply(question: str) -> str | None:
    """A direct reply for greetings and pleasantries, which need no document search."""
    text = question.strip()
    for pattern, reply in _SMALL_TALK:
        if pattern.match(text):
            return reply
    return None


def _status_after(node: str, update: dict[str, Any], web: bool) -> str | None:
    if node == "retrieve":
        return "Picking the most relevant passages"
    if node == "rerank":
        return "Checking what is useful"
    if node == "grade_documents":
        if not update.get("web_search_needed"):
            return "Writing your answer"
        return "Looking further on the web" if web else None
    if node == "transform_query":
        return "Searching the web"
    if node == "web_search":
        return "Writing your answer"
    if node == "generate":
        return "Double-checking the answer"
    if node == "check_hallucination" and not (update.get("verification") or {}).get("passed"):
        return "Improving the answer"
    return None


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


def answer_events(
    question: str,
    owner: str,
    history: Sequence[tuple[str, str]],
    document_ids: list[str],
    web_search: bool,
) -> Iterator[dict[str, Any]]:
    """Yield stream events while the agent answers ``question`` from the selected documents."""
    reply = small_talk_reply(question)
    if reply:
        yield {"type": "done", "answer": reply, "sources": [], "verified": None, "outcome": "chat", "web_used": False}
        return

    yield {"type": "status", "text": "Reading your documents"}
    index = get_index()
    hints = []
    for doc_id in document_ids[:10]:
        name, heading = index.document_heading(doc_id)
        if name:
            hints.append(f'- {name}: begins "{heading}"')
    standalone = standalone_question(question, history, "\n".join(hints))
    final: dict[str, Any] = {}
    generation_open = False
    has_tokens = False
    web_used = False
    try:
        for mode, payload in get_app().stream(
            initial_state(standalone, owner, document_ids, web_search),
            config=run_config(),
            stream_mode=["updates", "messages"],
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
                if node == "web_search":
                    web_used = True
                if node == "not_found" and has_tokens:
                    yield {"type": "reset"}
                status = _status_after(node, update, web_search)
                if status:
                    yield {"type": "status", "text": status}
    finally:
        flush_tracing()

    sources = _sources(final.get("citations", []))
    verification = final.get("verification") or {}
    yield {
        "type": "done",
        "answer": final.get("generation", ""),
        "sources": sources,
        "verified": bool(verification.get("passed")) and bool(sources),
        "outcome": final.get("outcome", "answered"),
        "web_used": web_used,
    }
