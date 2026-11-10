"""StateGraph assembly, conditional routing and compilation.

Topology::

    retrieve -> rerank -> grade_documents --(>=1 relevant chunk)--> generate
                               |
                               +--(nothing relevant, web on)---> transform_query -> web_search -> generate
                               +--(nothing relevant, web off)--> not_found -> END

    generate -> check_hallucination --(pass | retries exhausted)--> finalize -> END
                       |
                       +--(ungrounded, retries left)--> generate again with the verifier's feedback,
                       |                               or transform_query -> web_search when web is on
                       +--(grounded but not answered)--> transform_query -> web_search (web on, retry left)
                                                        or not_found
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from config.settings import get_settings
from src.nodes import (
    check_hallucination,
    finalize,
    generate,
    grade_documents,
    not_found,
    rerank,
    retrieve,
    transform_query,
    web_search,
)
from src.state import AgentState
from src.utils.tracing import get_callbacks


def decide_to_generate(state: AgentState) -> Literal["transform_query", "generate", "not_found"]:
    """Generate from the documents, search the web (only if allowed), or report nothing found."""
    if not state.get("web_search_needed"):
        return "generate"
    return "transform_query" if state.get("web_search_enabled") else "not_found"


def grade_generation(state: AgentState) -> Literal["useful", "retry_web", "retry_local", "not_found", "exhausted"]:
    """Route after verification.

    ``retry_count`` is incremented by ``check_hallucination`` on each failure.
    Ungrounded drafts get up to ``max_retries`` new attempts (via the web when it
    is enabled, otherwise from the same documents with the verifier's feedback).
    Grounded drafts that don't answer the question mean the sources lack the
    answer: search the web once if allowed, otherwise say it wasn't found.
    """
    verification = state.get("verification") or {}
    if verification.get("passed"):
        return "useful"
    settings = get_settings()
    retries = state.get("retry_count", 0)
    web = bool(state.get("web_search_enabled"))
    if verification.get("grounded"):
        return "retry_web" if web and retries <= settings.max_unhelpful_retries else "not_found"
    if retries <= settings.max_retries:
        return "retry_web" if web else "retry_local"
    return "exhausted"


def build_graph() -> StateGraph:
    """Construct the (uncompiled) CRAG state graph."""
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("rerank", rerank)
    graph.add_node("grade_documents", grade_documents)
    graph.add_node("transform_query", transform_query)
    graph.add_node("web_search", web_search)
    graph.add_node("generate", generate)
    graph.add_node("check_hallucination", check_hallucination)
    graph.add_node("not_found", not_found)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "grade_documents")
    graph.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {"transform_query": "transform_query", "generate": "generate", "not_found": "not_found"},
    )
    graph.add_edge("transform_query", "web_search")
    graph.add_edge("web_search", "generate")
    graph.add_edge("generate", "check_hallucination")
    graph.add_conditional_edges(
        "check_hallucination",
        grade_generation,
        {
            "useful": "finalize",
            "retry_web": "transform_query",
            "retry_local": "generate",
            "not_found": "not_found",
            "exhausted": "finalize",
        },
    )
    graph.add_edge("not_found", END)
    graph.add_edge("finalize", END)
    return graph


@lru_cache(maxsize=1)
def get_app() -> CompiledStateGraph:
    """Return the compiled graph (cached per process)."""
    return build_graph().compile()


def run_config() -> dict[str, Any]:
    """Runnable config with tracing callbacks and a recursion limit."""
    return {"callbacks": get_callbacks(), "recursion_limit": 40, "run_name": "crag"}
