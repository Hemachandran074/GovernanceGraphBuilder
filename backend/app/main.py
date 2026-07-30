"""FastAPI application entrypoint.

Wires together configuration, structured logging, the Neo4j client lifecycle,
request correlation ids, CORS, global error handling, and the health routes.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api import graph, health, ingest, query
from app.config import get_settings
from app.graph.client import Neo4jClient
from app.graph.schema import apply_schema
from app.ingestion.agent_config import IngestionError
from app.logging_config import request_id_ctx, setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage process-wide resources (the Neo4j driver) across the app lifetime."""
    settings = get_settings()
    setup_logging(level=settings.log_level, json_output=settings.log_json)
    logger.info(
        "Starting application",
        extra={"service": settings.app_name, "version": __version__, "environment": settings.environment},
    )

    client = Neo4jClient(settings)
    client.connect()
    app.state.neo4j_client = client

    # Best-effort connectivity check at startup; never blocks boot so /health
    # stays available and /ready can report the real dependency state.
    if await client.verify_connectivity():
        logger.info("Neo4j connectivity verified")
        # Apply constraints/indexes once at startup so the graph is query-ready
        # and ingestion is idempotent without re-applying schema per request.
        try:
            await apply_schema(client)
        except Exception:  # noqa: BLE001 - schema is best-effort at startup
            logger.exception("Failed to apply graph schema at startup")
    else:
        logger.warning("Neo4j not reachable at startup; readiness will report not_ready until it is")

    try:
        yield
    finally:
        await client.close()
        logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Governance Graph Builder",
        description=(
            "Models agents, models, tools, users, data sources, and policies as a "
            "connected graph, making the full composition of any AI agent queryable."
        ),
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """Attach a correlation id and emit structured access logs."""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            # Log completion while the correlation id is still set in context.
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.exception(
                "Unhandled error during request",
                extra={"method": request.method, "path": request.url.path, "duration_ms": duration_ms},
            )
            raise
        finally:
            request_id_ctx.reset(token)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"type": "http_error", "message": exc.detail}},
            headers={"X-Request-ID": request_id_ctx.get()},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"type": "validation_error", "message": "Invalid request", "details": exc.errors()}},
            headers={"X-Request-ID": request_id_ctx.get()},
        )

    @app.exception_handler(IngestionError)
    async def ingestion_error_handler(request: Request, exc: IngestionError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": {"type": "ingestion_error", "message": str(exc)}},
            headers={"X-Request-ID": request_id_ctx.get()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Do not leak internal details to clients; the correlation id ties the
        # response to the structured server-side log for debugging.
        return JSONResponse(
            status_code=500,
            content={"error": {"type": "internal_error", "message": "Internal server error"}},
            headers={"X-Request-ID": request_id_ctx.get()},
        )

    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(query.router)
    app.include_router(graph.router)

    @app.get("/", tags=["meta"], summary="Service metadata")
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "health": "/health",
            "ready": "/ready",
        }

    return app


app = create_app()
