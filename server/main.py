"""FastAPI application: JSON API under ``/api`` plus the built React app."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config.settings import get_settings
from server.db import init_db
from server.routes import auth, chat, conversations, documents, profile

logger = logging.getLogger(__name__)

_FIELD_MESSAGES = {"email": "Enter a valid email address."}


class Readiness:
    """Tracks background loading of the search models."""

    def __init__(self) -> None:
        self.ready = False
        self.error: str | None = None

    def warm_up(self) -> None:
        try:
            from src.ingestion.vector_store import get_embeddings, get_index, get_reranker

            get_index()
            get_embeddings().embed_query("warm up")
            get_reranker()
            self.ready = True
            logger.info("Search models loaded; ready to answer")
        except Exception as exc:  # surfaced through /api/health
            logger.exception("Warm-up failed")
            self.error = type(exc).__name__


readiness = Readiness()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    threading.Thread(target=readiness.warm_up, name="warm-up", daemon=True).start()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="CRAG", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # noqa: ANN001, ANN202
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
            field = loc[0] if loc else "request"
            message = _FIELD_MESSAGES.get(field) or str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
            fields.setdefault(field, message)
        first = next(iter(fields.values()), "Please check the form.")
        return JSONResponse(
            status_code=422, content={"detail": {"code": "invalid", "message": first, "fields": fields}}
        )

    for router in (auth.router, profile.router, documents.router, conversations.router, chat.router):
        app.include_router(router)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        from server.mailer import delivery_mode

        return {
            "ready": readiness.ready,
            "error": readiness.error,
            "email": delivery_mode(),
            "web_search": get_settings().web_search_enabled,
        }

    @app.api_route("/api/{_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_not_found(_path: str) -> None:
        raise HTTPException(404, {"code": "not_found", "message": "Not found."})

    dist = get_settings().frontend_dist
    if (dist / "index.html").exists():
        if (dist / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
