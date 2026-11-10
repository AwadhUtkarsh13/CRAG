"""StateGraph assembly, conditional routing and compilation.

Topology::

    retrieve -> rerank -> grade_documents --(>=1 relevant chunk)--> generate
                               |                                     ^
                               +--(no relevant chunk)--> transform_query -> web_search
                                                              ^
    generate -> check_hallucination --(pass | retries exhausted)--> finalize -> END
                       |
                       +--(fail, retries left)--> transform_query
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
    rerank,
    retrieve,
    transform_query,
    web_search,
)
from src.state import AgentState
from src.utils.tracing import get_callbacks


def decide_to_generate(state: AgentState) -> Literal["transform_query", "generate"]:
    """Route to the corrective web path when local context is insufficient."""
    return "transform_query" if state.get("web_search_needed") else "generate"


def grade_generation(state: AgentState) -> Literal["useful", "retry", "exhausted"]:
    """Route after verification.

    ``retry_count`` is incremented by ``check_hallucination`` on each failure.
    Ungrounded answers get up to ``max_retries`` extra attempts. Grounded
    answers that merely fail to resolve the question (typically an honest "the
    documents don't specify") get ``max_unhelpful_retries``, since repeating
    the search rarely changes the outcome.
    """
    verification = state.get("verification") or {}
    if verification.get("passed"):
        return "useful"
    settings = get_settings()
    limit = settings.max_unhelpful_retries if verification.get("grounded") else settings.max_retries
    if state.get("retry_count", 0) <= limit:
        return "retry"
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
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "grade_documents")
    graph.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {"transform_query": "transform_query", "generate": "generate"},
    )
    graph.add_edge("transform_query", "web_search")
    graph.add_edge("web_search", "generate")
    graph.add_edge("generate", "check_hallucination")
    graph.add_conditional_edges(
        "check_hallucination",
        grade_generation,
        {"useful": "finalize", "retry": "transform_query", "exhausted": "finalize"},
    )
    graph.add_edge("finalize", END)
    return graph


@lru_cache(maxsize=1)
def get_app() -> CompiledStateGraph:
    """Return the compiled graph (cached per process)."""
    return build_graph().compile()


def run_config() -> dict[str, Any]:
    """Runnable config with tracing callbacks and a recursion limit."""
    return {"callbacks": get_callbacks(), "recursion_limit": 40, "run_name": "crag"}
