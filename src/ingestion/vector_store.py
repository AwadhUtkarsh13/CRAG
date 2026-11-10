"""Hybrid (dense + BM25) index backed by a persistent ChromaDB collection,
plus FlashRank cross-encoder re-ranking.

Every chunk carries an ``owner`` (the user it belongs to) and a ``doc_id``.
Searches are always scoped to one owner, so users only ever retrieve from
their own library. Chroma is the single source of truth: each owner's BM25
index is rebuilt lazily from their stored chunks after any change.
"""

from __future__ import annotations

import logging
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from rank_bm25 import BM25Okapi

from config.settings import get_settings
from src.ingestion.loader import load_file, split_documents

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.'-][a-z0-9]+)*")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have how in is it its of on or that the this to "
    "was were what when where which who why will with does do our we you your".split()
)


def tokenize(text: str) -> list[str]:
    """Lower-case word tokenizer used for BM25 (stopwords removed)."""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    """Return the configured embedding model."""
    settings = get_settings()
    if settings.embedding_provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    from langchain_community.embeddings import FastEmbedEmbeddings

    cache_dir = settings.reranker_cache_dir.parent / "fastembed"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return FastEmbedEmbeddings(model_name=settings.embedding_model, cache_dir=str(cache_dir))


def _clean_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Chroma only accepts primitive, non-null metadata values."""
    return {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}


class HybridIndex:
    """Owner-scoped dense + sparse retrieval with reciprocal-rank fusion (RRF)."""

    def __init__(
        self,
        persist_dir: Path | None = None,
        collection_name: str | None = None,
        embeddings: Embeddings | None = None,
    ) -> None:
        from langchain_chroma import Chroma

        settings = get_settings()
        self._settings = settings
        self._lock = threading.RLock()
        self.store = Chroma(
            collection_name=collection_name or settings.collection_name,
            embedding_function=embeddings or get_embeddings(),
            persist_directory=str(persist_dir or settings.chroma_dir),
            collection_metadata={"hnsw:space": "cosine"},
        )
        self._sparse: dict[str, tuple[BM25Okapi | None, list[Document]]] = {}
        self._headings: dict[str, tuple[str, str]] = {}

    def count(self, owner: str | None = None) -> int:
        """Number of chunks stored, optionally for one owner."""
        if owner is None:
            return self.store._collection.count()
        return len(self.store.get(where={"owner": owner}, include=[])["ids"])

    def sources(self, owner: str) -> list[str]:
        """Distinct source names indexed for ``owner``."""
        return sorted({d.metadata.get("source", "?") for d in self._corpus(owner)})

    def _corpus(self, owner: str) -> list[Document]:
        return self._sparse_index(owner)[1]

    def _sparse_index(self, owner: str) -> tuple[BM25Okapi | None, list[Document]]:
        with self._lock:
            cached = self._sparse.get(owner)
            if cached is not None:
                return cached
            data = self.store.get(where={"owner": owner}, include=["documents", "metadatas"])
            corpus = [
                Document(page_content=text, metadata=meta or {})
                for text, meta in zip(data["documents"], data["metadatas"], strict=True)
            ]
            tokenized = [tokenize(d.page_content) for d in corpus]
            entry = (BM25Okapi(tokenized) if tokenized else None, corpus)
            self._sparse[owner] = entry
            logger.info("BM25 index built for owner=%s over %d chunks", owner, len(corpus))
            return entry

    def _invalidate(self, owner: str) -> None:
        with self._lock:
            self._sparse.pop(owner, None)

    def index_file(self, path: str | Path, *, owner: str, doc_id: str, display_name: str | None = None) -> int:
        """Load, chunk and index one file for ``owner``. Returns the chunk count.

        Re-indexing the same ``doc_id`` replaces its previous chunks.
        """
        chunks = split_documents(load_file(path, display_name=display_name))
        for idx, chunk in enumerate(chunks):
            chunk.metadata.update({"owner": owner, "doc_id": doc_id, "chunk_id": f"{doc_id}-{idx:04d}"})
            chunk.metadata = _clean_metadata(chunk.metadata)
        with self._lock:
            self._headings.pop(doc_id, None)
            self.store.delete(where={"doc_id": doc_id})
            if chunks:
                self.store.add_documents(chunks, ids=[c.metadata["chunk_id"] for c in chunks])
            self._invalidate(owner)
        return len(chunks)

    def document_heading(self, doc_id: str) -> tuple[str, str]:
        """``(source name, opening text)`` of a document, used to keep chunks tied to their document."""
        cached = self._headings.get(doc_id)
        if cached is not None:
            return cached
        data = self.store.get(
            where={"$and": [{"doc_id": doc_id}, {"chunk_index": 0}]}, include=["documents", "metadatas"], limit=1
        )
        if not data["ids"]:
            return ("", "")
        text = " ".join((data["documents"][0] or "").split())
        heading = text[:180].rstrip() + ("..." if len(text) > 180 else "")
        entry = ((data["metadatas"][0] or {}).get("source", ""), heading)
        self._headings[doc_id] = entry
        return entry

    def delete_document(self, doc_id: str, owner: str) -> None:
        """Remove every chunk of one document."""
        with self._lock:
            self.store.delete(where={"doc_id": doc_id})
            self._invalidate(owner)

    def delete_owner(self, owner: str) -> None:
        """Remove every chunk belonging to ``owner``."""
        with self._lock:
            self.store.delete(where={"owner": owner})
            self._invalidate(owner)

    def _where(self, owner: str, doc_ids: list[str] | None) -> dict:
        if doc_ids:
            return {"$and": [{"owner": owner}, {"doc_id": {"$in": list(doc_ids)}}]}
        return {"owner": owner}

    def dense_search(
        self, query: str, k: int | None = None, *, owner: str, doc_ids: list[str] | None = None
    ) -> list[Document]:
        """Vector similarity search, optionally limited to ``doc_ids``. Adds ``dense_score``."""
        k = k or self._settings.dense_k
        where = self._where(owner, doc_ids)
        if not self.store.get(where=where, include=[], limit=1)["ids"]:
            return []
        results = self.store.similarity_search_with_relevance_scores(query, k=k, filter=where)
        docs = []
        for doc, score in results:
            doc.metadata["dense_score"] = round(float(score), 4)
            docs.append(doc)
        return docs

    def sparse_search(
        self, query: str, k: int | None = None, *, owner: str, doc_ids: list[str] | None = None
    ) -> list[Document]:
        """BM25 keyword search, optionally limited to ``doc_ids``. Zero-score hits are dropped."""
        k = k or self._settings.sparse_k
        bm25, corpus = self._sparse_index(owner)
        if bm25 is None:
            return []
        allowed = set(doc_ids) if doc_ids else None
        scores = bm25.get_scores(tokenize(query))
        candidates = [i for i in range(len(scores)) if allowed is None or corpus[i].metadata.get("doc_id") in allowed]
        ranked = sorted(candidates, key=lambda i: scores[i], reverse=True)[:k]
        docs = []
        for i in ranked:
            if scores[i] <= 0:
                break
            src = corpus[i]
            docs.append(
                Document(
                    page_content=src.page_content,
                    metadata={**src.metadata, "bm25_score": round(float(scores[i]), 4)},
                )
            )
        return docs

    def hybrid_search(
        self, query: str, k: int | None = None, *, owner: str, doc_ids: list[str] | None = None
    ) -> list[Document]:
        """Fuse dense and sparse rankings with RRF: ``score = sum(1 / (rrf_k + rank))``."""
        k = k or self._settings.fused_k
        rrf_k = self._settings.rrf_k
        fused: dict[str, Document] = {}
        scores: dict[str, float] = {}
        rankings = (
            self.dense_search(query, owner=owner, doc_ids=doc_ids),
            self.sparse_search(query, owner=owner, doc_ids=doc_ids),
        )
        for ranking in rankings:
            for rank, doc in enumerate(ranking, start=1):
                key = doc.metadata.get("chunk_id") or doc.page_content[:200]
                if key in fused:
                    fused[key].metadata.update(doc.metadata)
                else:
                    fused[key] = doc
                scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
        ordered = sorted(scores, key=scores.get, reverse=True)[:k]  # type: ignore[arg-type]
        out = []
        for key in ordered:
            doc = fused[key]
            doc.metadata["rrf_score"] = round(scores[key], 5)
            out.append(doc)
        return out


class Reranker:
    """Cross-encoder re-ranking via FlashRank (ONNX, CPU-friendly)."""

    def __init__(self, model_name: str | None = None, cache_dir: Path | None = None) -> None:
        from flashrank import Ranker

        settings = get_settings()
        cache = cache_dir or settings.reranker_cache_dir
        cache.mkdir(parents=True, exist_ok=True)
        self._ranker = Ranker(model_name=model_name or settings.reranker_model, cache_dir=str(cache))

    def rerank(self, query: str, docs: list[Document], top_n: int) -> list[Document]:
        """Return the ``top_n`` docs by cross-encoder score (adds ``rerank_score``)."""
        if not docs:
            return []
        from flashrank import RerankRequest

        passages = [{"id": i, "text": d.page_content} for i, d in enumerate(docs)]
        results = self._ranker.rerank(RerankRequest(query=query, passages=passages))
        out = []
        for item in results[:top_n]:
            doc = docs[int(item["id"])]
            doc.metadata["rerank_score"] = round(float(item["score"]), 4)
            out.append(doc)
        return out


_index_lock = threading.Lock()
_index: HybridIndex | None = None


def get_index() -> HybridIndex:
    """Return the shared :class:`HybridIndex`."""
    global _index
    with _index_lock:
        if _index is None:
            _index = HybridIndex()
        return _index


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    """Return the shared :class:`Reranker`."""
    return Reranker()
