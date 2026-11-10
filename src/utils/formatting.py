"""Formatting helpers shared by nodes, the CLI and the UI."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from langchain_core.documents import Document

_CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def source_label(doc: Document) -> str:
    """Human-readable source label for a chunk."""
    meta = doc.metadata
    if meta.get("origin") == "web":
        return meta.get("title") or meta.get("source", "web")
    label = meta.get("source", "unknown")
    if meta.get("page") is not None:
        label += f" (p. {int(meta['page']) + 1})"
    return label


def format_context(docs: list[Document]) -> str:
    """Render documents as a numbered context block for prompting."""
    if not docs:
        return "(no context available)"
    blocks = []
    for i, doc in enumerate(docs, start=1):
        kind = "web" if doc.metadata.get("origin") == "web" else "document"
        url = f" - {doc.metadata['url']}" if kind == "web" and doc.metadata.get("url") else ""
        heading = doc.metadata.get("doc_heading")
        opening = f'\nThis document begins: "{heading}"' if kind == "document" and heading else ""
        blocks.append(f"[{i}] Source ({kind}): {source_label(doc)}{url}{opening}\n{doc.page_content.strip()}")
    return "\n\n".join(blocks)


def chunk_for_grading(doc: Document) -> str:
    """A chunk with its document name and opening line, so graders know whose document it is."""
    heading = doc.metadata.get("doc_heading")
    header = f"From: {source_label(doc)}"
    if heading:
        header += f'\nThis document begins: "{heading}"'
    return f"{header}\n\n{doc.page_content.strip()}"


def extract_citations(answer: str, docs: list[Document]) -> list[dict[str, Any]]:
    """Map ``[n]`` markers in ``answer`` to the documents they reference.

    Out-of-range markers are ignored. Each citation records the character spans
    of the markers so the UI can highlight them.
    """
    found: dict[int, dict[str, Any]] = {}
    for match in _CITATION_RE.finditer(answer):
        for raw in match.group(1).split(","):
            idx = int(raw.strip())
            if not 1 <= idx <= len(docs):
                continue
            doc = docs[idx - 1]
            entry = found.setdefault(
                idx,
                {
                    "index": idx,
                    "source": source_label(doc),
                    "origin": doc.metadata.get("origin", "local"),
                    "url": doc.metadata.get("url"),
                    "snippet": doc.page_content.strip()[:300],
                    "spans": [],
                },
            )
            entry["spans"].append([match.start(), match.end()])
    return [found[k] for k in sorted(found)]


def today() -> str:
    """Today's date (ISO format) for time-aware prompts."""
    return date.today().isoformat()


def fallback_citations(docs: list[Document]) -> list[dict[str, Any]]:
    """Sources for an answer that forgot its [n] markers: the passages it was written from."""
    return [
        {
            "index": i,
            "source": source_label(doc),
            "origin": doc.metadata.get("origin", "local"),
            "url": doc.metadata.get("url"),
            "snippet": doc.page_content.strip()[:300],
            "spans": [],
        }
        for i, doc in enumerate(docs, start=1)
    ]


def preview(text: str, limit: int = 160) -> str:
    """Single-line truncated preview of ``text``."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def doc_summary(doc: Document) -> dict[str, Any]:
    """Compact, JSON-serialisable view of a chunk for traces and inspectors."""
    meta = doc.metadata
    return {
        "source": source_label(doc),
        "origin": meta.get("origin", "local"),
        "chunk_id": meta.get("chunk_id"),
        "rrf_score": meta.get("rrf_score"),
        "rerank_score": meta.get("rerank_score"),
        "final_score": meta.get("final_score"),
        "relevant": meta.get("relevant"),
        "grade_reasoning": meta.get("grade_reasoning"),
        "preview": preview(doc.page_content),
    }
