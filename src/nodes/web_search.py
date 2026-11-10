"""``web_search`` node: Tavily fallback when local retrieval is insufficient."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig

from config.settings import get_settings
from src.cache import get_cache, make_key
from src.state import AgentState
from src.utils.formatting import doc_summary
from src.utils.tracing import traced_node

logger = logging.getLogger(__name__)


def _tavily_results(query: str, max_results: int) -> list[dict[str, Any]]:
    """Raw Tavily results, served from the response cache when fresh."""
    settings = get_settings()
    cache = get_cache()
    key = make_key("tavily", query, str(max_results), settings.web_search_depth)
    if cache is not None:
        hit = cache.get(key, max_age_s=settings.web_cache_ttl_hours * 3600)
        if hit is not None:
            return json.loads(hit)

    from tavily import TavilyClient

    client = TavilyClient(api_key=settings.tavily_api_key.get_secret_value() if settings.tavily_api_key else None)
    response = client.search(query=query, max_results=max_results, search_depth=settings.web_search_depth)
    results = response.get("results", [])
    if cache is not None:
        cache.set(key, json.dumps(results, ensure_ascii=False))
    return results


def tavily_search(query: str, max_results: int) -> list[Document]:
    """Query Tavily and convert results to documents (``origin='web'``)."""
    docs = []
    for item in _tavily_results(query, max_results):
        content = (item.get("content") or "").strip()
        if not content:
            continue
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "origin": "web",
                    "source": item.get("url", "web"),
                    "url": item.get("url"),
                    "title": item.get("title"),
                    "web_score": item.get("score"),
                    "chunk_id": f"web::{item.get('url')}",
                },
            )
        )
    return docs


@traced_node("web_search")
def web_search(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Combine the graded local chunks with fresh web results.

    Web results from an earlier attempt are replaced, not accumulated, so
    retries do not pile up noisy, possibly off-topic pages. Skips gracefully
    when no Tavily key is configured or the API errors, so the generator then
    works with whatever local context survived grading.
    """
    settings = get_settings()
    query = state.get("rewritten_question") or state["question"]
    docs = list(state.get("documents", []))

    if not settings.web_search_enabled:
        return {"_trace": {"decision": "skipped: TAVILY_API_KEY not set", "details": {"query": query}}}

    try:
        results = tavily_search(query, settings.web_search_k)
    except Exception as exc:  # network or quota errors
        logger.exception("Tavily search failed")
        return {"_trace": {"decision": f"failed: {type(exc).__name__}", "details": {"query": query}}}

    local = [d for d in docs if d.metadata.get("origin") != "web"]
    replaced = len(docs) - len(local)
    seen: set[str] = set()
    new = []
    for doc in results:
        if doc.metadata["chunk_id"] not in seen:
            seen.add(doc.metadata["chunk_id"])
            new.append(doc)
    decision = f"added {len(new)} web result(s)"
    if replaced:
        decision += f", replaced {replaced} from last attempt"
    return {
        "documents": local + new,
        "_trace": {
            "decision": decision,
            "details": {"query": query, "results": [doc_summary(d) for d in new]},
        },
    }
