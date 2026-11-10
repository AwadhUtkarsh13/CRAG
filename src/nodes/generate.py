"""``generate`` node: cited answer synthesis from the working context."""

from __future__ import annotations

from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableConfig

from src import llm as llm_factory
from src.prompts import GENERATE_PROMPT
from src.state import AgentState
from src.utils.formatting import extract_citations, format_context, today
from src.utils.tracing import traced_node


@traced_node("generate")
def generate(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Answer the original question using only numbered, cited context."""
    docs = state.get("documents", [])
    chain = GENERATE_PROMPT | llm_factory.chat_model() | StrOutputParser()
    answer = chain.invoke(
        {"question": state["question"], "context": format_context(docs), "today": today()}, config=config
    ).strip()
    citations = extract_citations(answer, docs)
    return {
        "generation": answer,
        "citations": citations,
        "_trace": {
            "decision": f"drafted answer from {len(docs)} chunk(s), {len(citations)} cited",
            "details": {
                "citations": [{"index": c["index"], "source": c["source"], "spans": c["spans"]} for c in citations]
            },
        },
    }
