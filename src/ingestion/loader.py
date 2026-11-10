"""Document loading and chunking for PDF, Markdown and plain-text files."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from config.settings import get_settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".md", ".markdown", ".txt"})


class UnsupportedFileTypeError(ValueError):
    """Raised for files whose extension has no registered loader."""


def _load_pdf(path: Path) -> list[Document]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    docs = []
    for page_no, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            docs.append(Document(page_content=text, metadata={"page": page_no}))
    return docs


def _load_text(path: Path) -> list[Document]:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return [Document(page_content=text, metadata={})] if text else []


def load_file(path: str | Path, display_name: str | None = None) -> list[Document]:
    """Load a single file into page-level documents.

    Args:
        path: Path to a ``.pdf``, ``.md``/``.markdown`` or ``.txt`` file.
        display_name: Name shown to users as the source; defaults to the file name.

    Returns:
        One document per PDF page, or a single document for text formats.
        Every document carries ``source`` and ``file_type`` metadata.

    Raises:
        UnsupportedFileTypeError: If the extension is not supported.
    """
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileTypeError(f"Unsupported file type: {path.name}")
    docs = _load_pdf(path) if ext == ".pdf" else _load_text(path)
    file_type = "markdown" if ext in {".md", ".markdown"} else ext.lstrip(".")
    for doc in docs:
        doc.metadata.update({"source": display_name or path.name, "file_type": file_type})
    logger.info("Loaded %s (%d page(s))", display_name or path.name, len(docs))
    return docs


def _splitter_for(file_type: str) -> RecursiveCharacterTextSplitter:
    settings = get_settings()
    if file_type == "markdown":
        return RecursiveCharacterTextSplitter.from_language(
            Language.MARKDOWN,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def split_documents(docs: Iterable[Document]) -> list[Document]:
    """Split documents into overlapping chunks with stable ``chunk_id`` metadata.

    Markdown is split on structural boundaries (headers, lists, code fences)
    first; other formats on paragraphs, then sentences.
    """
    chunks: list[Document] = []
    counters: dict[str, int] = {}
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        for chunk in _splitter_for(doc.metadata.get("file_type", "txt")).split_documents([doc]):
            idx = counters.get(source, 0)
            counters[source] = idx + 1
            digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:10]
            chunk.metadata.update({"chunk_index": idx, "chunk_id": f"{digest}-{idx:04d}", "origin": "local"})
            chunks.append(chunk)
    return chunks
