"""Multi-turn support: turn a follow-up message into a standalone question."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.output_parsers import StrOutputParser

from src import llm as llm_factory
from src.prompts import CONDENSE_PROMPT

MAX_HISTORY_MESSAGES = 10


def standalone_question(question: str, history: Sequence[tuple[str, str]], documents: str = "") -> str:
    """Rewrite ``question`` so it no longer depends on ``history``.

    Args:
        question: The latest user message.
        history: Earlier ``(role, content)`` pairs, oldest first.
        documents: Names and opening lines of the documents selected for the chat.

    Returns:
        The original question when there is no history, otherwise the rewrite.
    """
    if not history:
        return question
    recent = history[-MAX_HISTORY_MESSAGES:]
    transcript = "\n".join(f"{'User' if role == 'user' else 'Assistant'}: {content[:600]}" for role, content in recent)
    chain = CONDENSE_PROMPT | llm_factory.chat_model() | StrOutputParser()
    inputs = {"history": transcript, "question": question, "documents": documents or "(not listed)"}
    rewritten = chain.invoke(inputs).strip().strip('"').strip()
    return rewritten or question
