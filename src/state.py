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
        rewritten_question: Query optimised for web / vector retrieval.
        retrieved_documents: Raw hybrid-retrieval candidates (kept for inspection).
        documents: Working context set; reranked, filtered and possibly
            augmented with web results. Scores live in ``Document.metadata``.
        generation: The current draft answer.
        citations: Sources actually cited in ``generation``.
        web_search_needed: Whether the corrective web fallback should run.
        retry_count: Number of failed verification rounds so far.
        verification: Result of the hallucination / answer-relevance checks.
        evaluation_trace: Append-only audit log (one entry per node execution).
    """

    question: str
    owner: str
    rewritten_question: str
    retrieved_documents: list[Document]
    documents: list[Document]
    generation: str
    citations: list[dict[str, Any]]
    web_search_needed: bool
    retry_count: int
    verification: Verification
    evaluation_trace: Annotated[list[TraceEvent], operator.add]


def initial_state(question: str, owner: str) -> AgentState:
    """Build a fresh state for ``question`` scoped to ``owner``'s documents."""
    return AgentState(
        question=question,
        owner=owner,
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
