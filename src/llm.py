"""LLM factories.

Nodes obtain models exclusively through :func:`chat_model` and
:func:`structured_model`, so the provider can be changed in one place.
Both are wrapped with the persistent response cache
(:mod:`src.cache`), so an identical prompt is only paid for once.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from pydantic import BaseModel

from config.settings import get_settings
from src.cache import ResponseCache, get_cache, make_key

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class MissingAPIKeyError(RuntimeError):
    """Raised when an LLM is requested but no credentials are configured."""


def build_chat_model(model: str, *, streaming: bool = False) -> BaseChatModel:
    """Instantiate an OpenAI(-compatible) chat model from settings."""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    if settings.openai_api_key is None and settings.openai_base_url is None:
        raise MissingAPIKeyError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key, "
            "or point OPENAI_BASE_URL at an OpenAI-compatible server."
        )
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else "not-needed"
    return ChatOpenAI(
        model=model,
        temperature=settings.llm_temperature,
        api_key=api_key,
        base_url=settings.openai_base_url,
        streaming=streaming,
        max_retries=3,
        timeout=60,
    )


def _prompt_text(prompt: Any) -> str:
    if isinstance(prompt, PromptValue):
        return "\n".join(f"{m.type}: {m.content}" for m in prompt.to_messages())
    if isinstance(prompt, list) and all(isinstance(m, BaseMessage) for m in prompt):
        return "\n".join(f"{m.type}: {m.content}" for m in prompt)
    return str(prompt)


def cached_chat(model: Runnable, model_name: str, cache: ResponseCache | None) -> Runnable:
    """Wrap a chat model so identical prompts return the stored text.

    On a miss the inner model is invoked with the caller's config, so token
    streaming and tracing callbacks behave exactly as without the cache. On a
    hit the full message is returned at once (no token stream).
    """
    if cache is None:
        return model

    def call(prompt: Any, config: RunnableConfig) -> AIMessage:
        key = make_key("chat", model_name, _prompt_text(prompt))
        hit = cache.get(key)
        if hit is not None:
            return AIMessage(content=hit)
        message = model.invoke(prompt, config=config)
        content = message.content if isinstance(message.content, str) else str(message.content)
        cache.set(key, content)
        return AIMessage(content=content)

    return RunnableLambda(call, name=f"cached_{model_name}")


def cached_structured(
    runnable: Runnable, schema: type[SchemaT], model_name: str, cache: ResponseCache | None
) -> Runnable:
    """Wrap a structured-output runnable; results are stored as validated JSON."""
    if cache is None:
        return runnable

    def call(prompt: Any, config: RunnableConfig) -> SchemaT:
        key = make_key("structured", model_name, schema.__name__, _prompt_text(prompt))
        hit = cache.get(key)
        if hit is not None:
            return schema.model_validate_json(hit)
        result = runnable.invoke(prompt, config=config)
        cache.set(key, result.model_dump_json())
        return result

    return RunnableLambda(call, name=f"cached_{schema.__name__}")


@lru_cache(maxsize=4)
def chat_model() -> Runnable:
    """Return the (streaming, cached) chat model used for generation and rewriting."""
    name = get_settings().llm_model
    return cached_chat(build_chat_model(name, streaming=True), name, get_cache())


@lru_cache(maxsize=4)
def _grader_base(model: str) -> BaseChatModel:
    return build_chat_model(model, streaming=False)


def structured_model(schema: type[SchemaT], model: str | None = None) -> Runnable:
    """Return a cached runnable that emits validated ``schema`` instances.

    Args:
        schema: Pydantic model describing the output.
        model: Model name; defaults to the configured grader model.
    """
    name = model or get_settings().effective_grader_model
    return cached_structured(_grader_base(name).with_structured_output(schema), schema, name, get_cache())
