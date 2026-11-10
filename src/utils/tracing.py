"""Observability helpers: Langfuse callbacks and per-node latency tracing."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig

from config.settings import get_settings
from src.state import AgentState, TraceEvent

logger = logging.getLogger(__name__)

NodeFn = Callable[[AgentState, RunnableConfig], dict[str, Any]]


@functools.lru_cache(maxsize=1)
def _langfuse_handler() -> BaseCallbackHandler | None:
    settings = get_settings()
    if not settings.tracing_enabled:
        return None
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        # Initialise the singleton client with explicit credentials, because
        # values read from .env by pydantic-settings are not in os.environ.
        public_key = settings.langfuse_public_key.get_secret_value()  # type: ignore[union-attr]
        Langfuse(
            public_key=public_key,
            secret_key=settings.langfuse_secret_key.get_secret_value(),  # type: ignore[union-attr]
            host=settings.langfuse_host,
        )
        return CallbackHandler(public_key=public_key)
    except Exception:
        logger.exception("Langfuse tracing could not be initialised; continuing without it.")
        return None


def get_callbacks() -> list[BaseCallbackHandler]:
    """Return callback handlers to attach to a graph run (empty if tracing is off)."""
    handler = _langfuse_handler()
    return [handler] if handler else []


def flush_tracing() -> None:
    """Flush buffered Langfuse events (call before short-lived processes exit)."""
    if _langfuse_handler() is None:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:
        logger.debug("Langfuse flush failed", exc_info=True)


def traced_node(name: str) -> Callable[[NodeFn], NodeFn]:
    """Decorate a node so it records latency and appends a :class:`TraceEvent`.

    The wrapped node may return an ``_trace`` key (``decision`` and ``details``)
    which is converted into an ``evaluation_trace`` entry.
    """

    def decorator(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        def wrapper(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
            start = time.perf_counter()
            update = dict(fn(state, config))
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            meta = update.pop("_trace", {})
            event = TraceEvent(
                node=name,
                latency_ms=latency_ms,
                decision=meta.get("decision", ""),
                details=meta.get("details", {}),
            )
            logger.info("node=%s latency_ms=%.1f decision=%s", name, latency_ms, event["decision"])
            update["evaluation_trace"] = [event]
            return update

        return wrapper

    return decorator
