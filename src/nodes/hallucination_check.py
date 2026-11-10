"""Self-RAG verification (``check_hallucination``) and ``finalize`` nodes."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src import llm as llm_factory
from src.prompts import ANSWER_RELEVANCE_PROMPT, GROUNDEDNESS_PROMPT
from src.state import AgentState, Verification
from src.utils.formatting import format_context
from src.utils.tracing import traced_node

ABSTAIN_MESSAGE = (
    "I couldn't produce an answer that is verifiably supported by the available sources, "
    "so I'd rather not guess. Try rephrasing the question or uploading a document that "
    "covers this topic."
)


class GroundednessGrade(BaseModel):
    """Whether the generation is supported by the context."""

    reasoning: str = Field(description="Which claims are or are not supported.")
    binary_score: Literal["yes", "no"] = Field(description="'yes' if fully grounded.")


class AnswerRelevanceGrade(BaseModel):
    """Whether the generation resolves the question."""

    reasoning: str = Field(description="Why the answer does or does not resolve the question.")
    binary_score: Literal["yes", "no"] = Field(description="'yes' if the question is answered.")


@traced_node("check_hallucination")
def check_hallucination(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Grade groundedness, then (if grounded) answer relevance.

    On failure, increments ``retry_count`` and forces the web fallback for the
    next attempt.
    """
    generation = state.get("generation", "")
    context = format_context(state.get("documents", []))

    grounded_grade = (GROUNDEDNESS_PROMPT | llm_factory.structured_model(GroundednessGrade)).invoke(
        {"context": context, "generation": generation}, config=config
    )
    grounded = grounded_grade.binary_score == "yes"

    verification = Verification(grounded=grounded, grounding_reasoning=grounded_grade.reasoning, answers_question=False)
    if grounded:
        answer_grade = (ANSWER_RELEVANCE_PROMPT | llm_factory.structured_model(AnswerRelevanceGrade)).invoke(
            {"question": state["question"], "generation": generation}, config=config
        )
        verification["answers_question"] = answer_grade.binary_score == "yes"
        verification["answer_reasoning"] = answer_grade.reasoning

    passed = verification["grounded"] and verification["answers_question"]
    verification["passed"] = passed
    update: dict[str, Any] = {"verification": verification}
    if passed:
        decision = "PASS: grounded and answers the question"
    else:
        update["retry_count"] = state.get("retry_count", 0) + 1
        update["web_search_needed"] = True
        decision = "FAIL: " + ("not grounded" if not grounded else "does not answer question")
    update["_trace"] = {"decision": decision, "details": dict(verification)}
    return update


@traced_node("finalize")
def finalize(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Return the verified answer, or abstain if the last draft was ungrounded.

    A grounded answer that merely fails to resolve the question (typically an
    honest "the documents don't say") is kept, since it is still truthful.
    """
    verification = state.get("verification") or {}
    if verification.get("passed"):
        return {"_trace": {"decision": "verified answer returned"}}
    if not verification.get("grounded", False):
        return {
            "generation": ABSTAIN_MESSAGE,
            "citations": [],
            "_trace": {
                "decision": "abstained: retries exhausted with ungrounded draft",
                "details": {"discarded_draft": state.get("generation", "")},
            },
        }
    retries = max(state.get("retry_count", 1) - 1, 0)
    return {"_trace": {"decision": f"returned grounded but partial answer after {retries} retry(ies)"}}
