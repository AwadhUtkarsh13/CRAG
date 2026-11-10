"""Centralised, typed configuration for CRAG.

All values can be overridden through environment variables or a ``.env`` file in
the project root (see ``.env.example``). Access settings through
:func:`get_settings`, which caches a single instance per process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration loaded from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = Field(
        default=None,
        description="Optional OpenAI-compatible endpoint (e.g. Ollama: http://localhost:11434/v1).",
    )
    llm_model: str = "gpt-4o-mini"
    grader_model: str | None = Field(default=None, description="Model used by graders; defaults to llm_model.")
    llm_temperature: float = 0.0

    # Embeddings / vector store
    embedding_provider: Literal["fastembed", "openai"] = Field(
        default="fastembed",
        description="'fastembed' runs BAAI/bge-small-en-v1.5 locally via ONNX (no API key).",
    )
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    openai_embedding_model: str = "text-embedding-3-small"
    chroma_dir: Path = PROJECT_ROOT / ".chroma"
    collection_name: str = "crag_chunks"

    # Chunking
    chunk_size: int = 600
    chunk_overlap: int = 100

    # Retrieval
    dense_k: int = Field(default=8, description="Candidates fetched from the vector index.")
    sparse_k: int = Field(default=8, description="Candidates fetched from BM25.")
    fused_k: int = Field(default=10, description="Candidates kept after reciprocal-rank fusion.")
    rrf_k: int = Field(default=60, description="RRF damping constant.")
    rerank_top_n: int = 3
    reranker_model: str = "ms-marco-MiniLM-L-12-v2"
    rerank_weight: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Final score = w * cross-encoder + (1 - w) * max-normalised RRF score.",
    )
    reranker_cache_dir: Path = PROJECT_ROOT / ".cache" / "flashrank"

    # Corrective loop
    min_relevant_chunks: int = Field(
        default=1,
        ge=1,
        description="Web search is triggered when fewer local chunks than this are graded relevant.",
    )
    max_retries: int = Field(default=2, description="Extra attempts after an ungrounded answer.")
    max_unhelpful_retries: int = Field(
        default=1,
        description="Extra attempts after a grounded answer that does not resolve the question.",
    )

    # Web search
    tavily_api_key: SecretStr | None = None
    web_search_k: int = 3
    web_search_depth: Literal["basic", "advanced"] = "advanced"

    # Cost control
    cache_enabled: bool = Field(
        default=True,
        description="Store OpenAI and Tavily responses so repeated identical requests cost nothing.",
    )
    cache_path: Path = PROJECT_ROOT / ".cache" / "responses.sqlite"
    web_cache_ttl_hours: float = Field(
        default=24.0, description="Cached web results older than this are fetched again."
    )

    # Observability
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Web application
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: Path = PROJECT_ROOT / "data" / "app.db"
    user_files_dir: Path = PROJECT_ROOT / "data" / "user_files"
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"
    session_days: int = Field(default=14, description="How long a sign-in stays valid.")
    cookie_secure: bool = Field(
        default=False, description="Set true when serving over HTTPS so cookies are only sent securely."
    )
    max_upload_mb: int = 20
    max_photo_mb: int = 3
    secret_key: SecretStr | None = Field(
        default=None, description="Signs one-time email codes. Generated into data/secret.key if not set."
    )

    # Email (verification codes and password resets)
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = Field(default=None, description='Sender, e.g. "CRAG <you@gmail.com>".')
    email_code_minutes: int = 10
    email_code_attempts: int = 5
    email_resend_seconds: int = 60

    @property
    def email_enabled(self) -> bool:
        """True when SMTP details are configured; otherwise codes are printed to the console."""
        return bool(self.smtp_host and self.smtp_username and self.smtp_password)

    @property
    def effective_grader_model(self) -> str:
        """Model name used by structured graders."""
        return self.grader_model or self.llm_model

    @property
    def web_search_enabled(self) -> bool:
        """True when a Tavily key is configured."""
        return bool(self.tavily_api_key and self.tavily_api_key.get_secret_value())

    @property
    def tracing_enabled(self) -> bool:
        """True when both Langfuse keys are configured."""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance."""
    return Settings()
