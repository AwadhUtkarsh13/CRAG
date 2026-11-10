"""Self-RAG verification (``check_hallucination``), ``not_found`` and ``finalize`` nodes."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig, RunnableParallel
from pydantic import BaseModel, Field

from src import llm as llm_factory
from src.prompts import ANSWER_RELEVANCE_PROMPT, GROUNDEDNESS_PROMPT
from src.state import AgentState, Verification
from src.utils.formatting import format_context
from src.utils.tracing import traced_node

ABSTAIN_MESSAGE = (
    "I couldn't produce an answer that is clearly supported by the sources, so I'd rather not "
    "guess. Try rephrasing the question, or select the document that covers this topic."
)
NOT_FOUND_MESSAGE = "I couldn't find the answer to this in the selected document(s)."
NOT_FOUND_WITH_WEB_MESSAGE = "I couldn't find the answer to this in the selected document(s) or on the web."


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
    """Check groundedness and answer relevance in parallel.

    On failure, increments ``retry_count``; the router decides whether to retry
    locally, search the web (if allowed) or report that nothing was found.
    """
    checks = RunnableParallel(
        grounded=GROUNDEDNESS_PROMPT | llm_factory.structured_model(GroundednessGrade),
        answers=ANSWER_RELEVANCE_PROMPT | llm_factory.structured_model(AnswerRelevanceGrade),
    )
    result = checks.invoke(
        {
            "context": format_context(state.get("documents", [])),
            "generation": state.get("generation", ""),
            "question": state["question"],
        },
        config=config,
    )
    grounded = result["grounded"].binary_score == "yes"
    answers = result["answers"].binary_score == "yes"
    verification = Verification(
        grounded=grounded,
        answers_question=answers,
        passed=grounded and answers,
        grounding_reasoning=result["grounded"].reasoning,
        answer_reasoning=result["answers"].reasoning,
    )
    update: dict[str, Any] = {"verification": verification}
    if verification["passed"]:
        decision = "PASS: grounded and answers the question"
    else:
        update["retry_count"] = state.get("retry_count", 0) + 1
        update["web_search_needed"] = bool(state.get("web_search_enabled"))
        decision = "FAIL: " + ("not grounded" if not grounded else "does not answer question")
    update["_trace"] = {"decision": decision, "details": dict(verification)}
    return update


@traced_node("not_found")
def not_found(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Tell the user plainly that the selected sources don't answer the question."""
    web = bool(state.get("web_search_enabled"))
    return {
        "generation": NOT_FOUND_WITH_WEB_MESSAGE if web else NOT_FOUND_MESSAGE,
        "citations": [],
        "outcome": "not_found",
        "_trace": {"decision": "no answer in the selected sources" + (" or the web" if web else "")},
    }


@traced_node("finalize")
def finalize(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Return the verified answer, or abstain if the last draft was ungrounded."""
    verification = state.get("verification") or {}
    if verification.get("passed"):
        return {"outcome": "answered", "_trace": {"decision": "verified answer returned"}}
    if not verification.get("grounded", False):
        return {
            "generation": ABSTAIN_MESSAGE,
            "citations": [],
            "outcome": "unverified",
            "_trace": {
                "decision": "abstained: retries exhausted with ungrounded draft",
                "details": {"discarded_draft": state.get("generation", "")},
            },
        }
    return {"outcome": "unverified", "_trace": {"decision": "returned grounded but partial answer"}}
