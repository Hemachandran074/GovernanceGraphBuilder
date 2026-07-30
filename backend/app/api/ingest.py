"""Ingestion endpoints.

Each source can be ingested from a JSON body (raw text or a parsed object) for
programmatic use, and a single generic ``/ingest/upload`` endpoint accepts a
file for any source type. Bundles can be discovered dynamically.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.api.schemas import (
    AgentConfigIngestRequest,
    BundleIngestRequest,
    BundleListResponse,
    IngestResponse,
    PolicyIngestRequest,
    RuntimeLogsIngestRequest,
)
from app.dependencies import get_neo4j_client
from app.graph.client import Neo4jClient
from app.graph.loader import reset_graph
from app.graph.schema import apply_schema
from app.ingestion.pipeline import (
    SAMPLES_DIR,
    ingest_agent_config,
    ingest_agent_config_text,
    ingest_bundle,
    ingest_policy_document,
    ingest_runtime_logs,
    ingest_runtime_logs_text,
)

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_UPLOAD_KINDS = {"agent-config", "runtime-logs", "policy"}


@router.get("/bundles", response_model=BundleListResponse, summary="List available sample bundles")
async def list_bundles() -> BundleListResponse:
    bundles = (
        sorted(p.name for p in SAMPLES_DIR.iterdir() if p.is_dir())
        if SAMPLES_DIR.is_dir()
        else []
    )
    return BundleListResponse(bundles=bundles)


@router.post("/agent-config", response_model=IngestResponse, summary="Ingest an agent config")
async def ingest_agent_config_endpoint(
    request: AgentConfigIngestRequest,
    client: Neo4jClient = Depends(get_neo4j_client),
) -> IngestResponse:
    if request.reset:
        await reset_graph(client)
    if request.config is not None:
        result = await ingest_agent_config(client, request.config)
    elif request.content is not None:
        result = await ingest_agent_config_text(client, request.content)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide either 'config' or 'content'.")
    return IngestResponse(result=result)


@router.post("/runtime-logs", response_model=IngestResponse, summary="Ingest runtime logs")
async def ingest_runtime_logs_endpoint(
    request: RuntimeLogsIngestRequest,
    client: Neo4jClient = Depends(get_neo4j_client),
) -> IngestResponse:
    if request.records is not None:
        result = await ingest_runtime_logs(client, request.records)
    elif request.content is not None:
        result = await ingest_runtime_logs_text(client, request.content)
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Provide either 'records' or 'content'.")
    return IngestResponse(result=result)


@router.post("/policy", response_model=IngestResponse, summary="Ingest a policy document (LLM-parsed)")
async def ingest_policy_endpoint(
    request: PolicyIngestRequest,
    client: Neo4jClient = Depends(get_neo4j_client),
) -> IngestResponse:
    result = await ingest_policy_document(client, request.content)
    return IngestResponse(result=result)


@router.post("/bundle", response_model=IngestResponse, summary="Ingest a full sample bundle")
async def ingest_bundle_endpoint(
    request: BundleIngestRequest,
    client: Neo4jClient = Depends(get_neo4j_client),
) -> IngestResponse:
    result = await ingest_bundle(client, request.bundle, reset=request.reset)
    return IngestResponse(result=result)


@router.post("/upload", response_model=IngestResponse, summary="Ingest any source from an uploaded file")
async def ingest_upload_endpoint(
    kind: str = Query(..., description="Source type: agent-config | runtime-logs | policy"),
    reset: bool = Query(False, description="Clear the graph before ingesting."),
    file: UploadFile = File(..., description="The source file to ingest."),
    client: Neo4jClient = Depends(get_neo4j_client),
) -> IngestResponse:
    if kind not in _UPLOAD_KINDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"'kind' must be one of {sorted(_UPLOAD_KINDS)}.",
        )
    text = (await file.read()).decode("utf-8")

    if reset:
        await reset_graph(client)
        await apply_schema(client)

    if kind == "agent-config":
        result = await ingest_agent_config_text(client, text)
    elif kind == "runtime-logs":
        result = await ingest_runtime_logs_text(client, text)
    else:  # policy
        result = await ingest_policy_document(client, text)

    return IngestResponse(result={"filename": file.filename, "kind": kind, **result})
