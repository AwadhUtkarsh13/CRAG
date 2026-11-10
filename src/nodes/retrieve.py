"""``retrieve`` (hybrid BM25 + dense) and ``rerank`` (cross-encoder) nodes."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig

from config.settings import get_settings
from src.ingestion.vector_store import get_index, get_reranker
from src.state import AgentState
from src.utils.formatting import doc_summary
from src.utils.tracing import traced_node

logger = logging.getLogger(__name__)


def _copy(doc: Document) -> Document:
    return Document(page_content=doc.page_content, metadata=dict(doc.metadata))


@traced_node("retrieve")
def retrieve(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Run hybrid retrieval for the question over the owner's documents."""
    question = state["question"]
    index = get_index()
    docs = index.hybrid_search(question, owner=state["owner"], doc_ids=state.get("document_ids") or None)
    for doc in docs:
        if doc.metadata.get("doc_id"):
            doc.metadata["doc_heading"] = index.document_heading(doc.metadata["doc_id"])[1]
    return {
        "retrieved_documents": docs,
        "documents": [_copy(d) for d in docs],
        "_trace": {
            "decision": f"{len(docs)} candidate chunk(s) via BM25 + dense RRF",
            "details": {"query": question, "chunks": [doc_summary(d) for d in docs]},
        },
    }


def blend_scores(docs: list[Document], weight: float) -> list[Document]:
    """Order docs by ``weight * rerank_score + (1 - weight) * normalised rrf_score``.

    Blending keeps a strong lexical + semantic hybrid hit from being discarded
    when the small cross-encoder misjudges it (e.g. "net loss" vs "net income").
    """
    max_rrf = max((d.metadata.get("rrf_score", 0.0) for d in docs), default=0.0) or 1.0
    for doc in docs:
        rrf_norm = doc.metadata.get("rrf_score", 0.0) / max_rrf
        doc.metadata["final_score"] = round(weight * doc.metadata.get("rerank_score", 0.0) + (1 - weight) * rrf_norm, 4)
    return sorted(docs, key=lambda d: d.metadata["final_score"], reverse=True)


@traced_node("rerank")
def rerank(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Cross-encoder rerank, blend with hybrid scores, and prune to the top-N.

    Falls back to the RRF order if the re-ranker cannot be loaded (e.g. the
    model download is blocked), so the pipeline degrades instead of failing.
    """
    settings = get_settings()
    docs = [_copy(d) for d in state.get("documents", [])]
    fallback = False
    try:
        scored = get_reranker().rerank(state["question"], docs, len(docs))
        ranked = blend_scores(scored, settings.rerank_weight)[: settings.rerank_top_n]
    except Exception:
        logger.exception("Re-ranker unavailable; falling back to RRF order")
        ranked, fallback = docs[: settings.rerank_top_n], True
    decision = f"kept top {len(ranked)} of {len(docs)}" + (" (RRF fallback)" if fallback else "")
    return {
        "documents": ranked,
        "_trace": {"decision": decision, "details": {"chunks": [doc_summary(d) for d in ranked]}},
    }
