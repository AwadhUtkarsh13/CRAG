"""Shared graph state for the CRAG agent."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.documents import Document


class TraceEvent(TypedDict, total=False):
    """One audit-log entry emitted by a graph node."""

    node: str
    latency_ms: float
    decision: str
    details: dict[str, Any]


class Verification(TypedDict, total=False):
    """Outcome of the Self-RAG verification step."""

    grounded: bool
    answers_question: bool
    passed: bool
    grounding_reasoning: str
    answer_reasoning: str


class AgentState(TypedDict, total=False):
    """Centralised state passed between LangGraph nodes.

    Attributes:
        question: The user query (never mutated).
        owner: Whose document library to search.
        document_ids: Documents selected for this chat (all of the owner's when empty).
        web_search_enabled: Whether the user allowed the web fallback for this question.
        rewritten_question: Query optimised for web / vector retrieval.
        retrieved_documents: Raw hybrid-retrieval candidates (kept for inspection).
        documents: Working context set; reranked, filtered and possibly
            augmented with web results. Scores live in ``Document.metadata``.
        generation: The current draft answer.
        citations: Sources actually cited in ``generation``.
        web_search_needed: Whether the corrective web fallback should run.
        retry_count: Number of failed verification rounds so far.
        verification: Result of the hallucination / answer-relevance checks.
        outcome: ``answered``, ``not_found`` or ``unverified`` once the run ends.
        evaluation_trace: Append-only audit log (one entry per node execution).
    """

    question: str
    owner: str
    document_ids: list[str]
    web_search_enabled: bool
    rewritten_question: str
    retrieved_documents: list[Document]
    documents: list[Document]
    generation: str
    citations: list[dict[str, Any]]
    web_search_needed: bool
    retry_count: int
    verification: Verification
    outcome: str
    evaluation_trace: Annotated[list[TraceEvent], operator.add]


def initial_state(
    question: str, owner: str, document_ids: list[str] | None = None, web_search: bool = False
) -> AgentState:
    """Build a fresh state for ``question`` scoped to the selected documents of ``owner``."""
    return AgentState(
        question=question,
        owner=owner,
        document_ids=list(document_ids or []),
        web_search_enabled=web_search,
        rewritten_question="",
        retrieved_documents=[],
        documents=[],
        generation="",
        citations=[],
        web_search_needed=False,
        retry_count=0,
        verification={},
        evaluation_trace=[],
    )
