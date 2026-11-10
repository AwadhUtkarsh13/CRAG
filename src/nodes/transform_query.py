"""``transform_query`` node: rewrite the question into a better search query."""

from __future__ import annotations

from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableConfig

from src import llm as llm_factory
from src.prompts import REWRITE_PROMPT
from src.state import AgentState
from src.utils.formatting import today
from src.utils.tracing import traced_node


@traced_node("transform_query")
def transform_query(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Produce ``rewritten_question``, using verifier feedback on retries."""
    verification = state.get("verification") or {}
    feedback = ""
    if verification and not verification.get("passed", True):
        feedback = (
            verification.get("grounding_reasoning", "")
            if not verification.get("grounded", True)
            else verification.get("answer_reasoning", "")
        )
    notes = ""
    if state.get("rewritten_question"):
        notes += f"\nPrevious search query (find something different): {state['rewritten_question']}"
    if feedback:
        notes += f"\nWhy the previous answer was rejected: {feedback}"
    chain = REWRITE_PROMPT | llm_factory.chat_model() | StrOutputParser()
    rewritten = (
        chain.invoke({"question": state["question"], "notes": notes, "today": today()}, config=config)
        .strip()
        .strip('"')
        .strip()
    )
    rewritten = rewritten or state["question"]
    return {
        "rewritten_question": rewritten,
        "_trace": {
            "decision": f"rewrote query (attempt {state.get('retry_count', 0) + 1})",
            "details": {"original": state["question"], "rewritten": rewritten, "feedback": feedback},
        },
    }
