"""Health and readiness probes.

- ``/health`` (liveness): the process is up and serving. No dependencies are
  touched, so a slow/unavailable database will not flap the liveness signal.
- ``/ready`` (readiness): the service can do useful work, which requires the
  graph database to be reachable. Returns 503 when Neo4j is unreachable so a
  load balancer / orchestrator can stop routing traffic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app import __version__
from app.config import Settings, get_settings
from app.graph.client import Neo4jClient
from app.dependencies import get_neo4j_client

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready(
    response: Response,
    client: Neo4jClient = Depends(get_neo4j_client),
) -> ReadinessResponse:
    neo4j_ok = await client.verify_connectivity()
    checks = {"neo4j": "ok" if neo4j_ok else "unavailable"}

    if not neo4j_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", checks=checks)

    return ReadinessResponse(status="ready", checks=checks)
