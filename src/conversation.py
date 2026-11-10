"""Multi-turn support: turn a follow-up message into a standalone question."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.output_parsers import StrOutputParser

from src import llm as llm_factory
from src.prompts import CONDENSE_PROMPT

MAX_HISTORY_TURNS = 6


def standalone_question(question: str, history: Sequence[tuple[str, str]]) -> str:
    """Rewrite ``question`` so it no longer depends on ``history``.

    Args:
        question: The latest user message.
        history: Earlier ``(role, content)`` pairs, oldest first.

    Returns:
        The original question when there is no history, otherwise the rewrite.
    """
    if not history:
        return question
    recent = history[-MAX_HISTORY_TURNS:]
    transcript = "\n".join(f"{'User' if role == 'user' else 'Assistant'}: {content[:600]}" for role, content in recent)
    chain = CONDENSE_PROMPT | llm_factory.chat_model() | StrOutputParser()
    rewritten = chain.invoke({"history": transcript, "question": question}).strip().strip('"').strip()
    return rewritten or question
