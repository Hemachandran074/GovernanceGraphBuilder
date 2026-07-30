"""Shared FastAPI dependencies.

The Neo4j client is created once during application startup (see the lifespan
handler in ``app.main``) and stored on ``app.state``. Routers retrieve it via
this dependency rather than reaching into app state directly.
"""

from __future__ import annotations

from fastapi import Request

from app.graph.client import Neo4jClient


def get_neo4j_client(request: Request) -> Neo4jClient:
    """Return the process-wide Neo4j client from application state."""
    client: Neo4jClient | None = getattr(request.app.state, "neo4j_client", None)
    if client is None:
        raise RuntimeError("Neo4j client is not available on app state.")
    return client


def get_queries(request: Request) -> "GraphQueries":
    """Return a GraphQueries wrapper bound to the process-wide Neo4j client."""
    from app.graph.queries import GraphQueries

    return GraphQueries(get_neo4j_client(request))
