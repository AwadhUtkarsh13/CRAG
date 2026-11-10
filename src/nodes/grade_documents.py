"""``grade_documents`` node: LLM relevance grading of each retrieved chunk."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from config.settings import get_settings
from src import llm as llm_factory
from src.prompts import GRADE_DOCUMENT_PROMPT
from src.state import AgentState
from src.utils.formatting import doc_summary
from src.utils.tracing import traced_node


class BinaryDocumentGrade(BaseModel):
    """Relevance verdict for a single retrieved chunk.

    ``reasoning`` is declared first so the model justifies before deciding.
    """

    reasoning: str = Field(description="One or two sentences justifying the score.")
    binary_score: Literal["yes", "no"] = Field(
        description="'yes' if the chunk is relevant to the question, otherwise 'no'."
    )


@traced_node("grade_documents")
def grade_documents(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Grade every chunk, keep the relevant ones, and decide on web fallback.

    ``web_search_needed`` is set when fewer than ``min_relevant_chunks``
    (default 1) chunks are relevant, i.e. local knowledge cannot answer at all.
    """
    settings = get_settings()
    question = state["question"]
    docs = state.get("documents", [])

    grades: list[BinaryDocumentGrade] = []
    if docs:
        chain = GRADE_DOCUMENT_PROMPT | llm_factory.structured_model(BinaryDocumentGrade)
        grades = chain.batch([{"question": question, "document": d.page_content} for d in docs], config=config)

    graded: list[Document] = []
    for doc, grade in zip(docs, grades, strict=True):
        meta = {
            **doc.metadata,
            "relevant": grade.binary_score == "yes",
            "grade_reasoning": grade.reasoning,
        }
        graded.append(Document(page_content=doc.page_content, metadata=meta))

    relevant = [d for d in graded if d.metadata["relevant"]]
    ratio = len(relevant) / len(graded) if graded else 0.0
    web_needed = len(relevant) < settings.min_relevant_chunks

    return {
        "documents": relevant,
        "web_search_needed": web_needed,
        "_trace": {
            "decision": (
                f"{len(relevant)}/{len(graded)} relevant ({ratio:.0%}) -> "
                + ("web fallback" if web_needed else "generate")
            ),
            "details": {
                "relevance_ratio": round(ratio, 3),
                "min_relevant_chunks": settings.min_relevant_chunks,
                "graded_chunks": [doc_summary(d) for d in graded],
            },
        },
    }
