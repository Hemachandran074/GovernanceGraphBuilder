"""Graph endpoints: snapshot, reset, stats, entity listing, neighbors, drift, NL query."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.schemas import (
    EntityListResponse,
    GraphStats,
    MessageResponse,
    NlQueryRequest,
    NlQueryResponse,
    QueryResponse,
)
from app.dependencies import get_neo4j_client, get_queries
from app.graph.client import Neo4jClient
from app.graph.loader import reset_graph
from app.graph.queries import GraphQueries
from app.llm import get_llm_provider
from app.llm.cypher import GRAPH_SCHEMA, UnsafeCypherError, ensure_read_only
from app.models.graph import GraphSnapshot
from app.models.nodes import NodeLabel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/graph", tags=["graph"])

# Friendly aliases (case-insensitive, singular/plural) -> NodeLabel.
_LABEL_ALIASES = {
    "user": NodeLabel.USER,
    "agent": NodeLabel.AGENT,
    "model": NodeLabel.MODEL,
    "tool": NodeLabel.TOOL,
    "datasource": NodeLabel.DATA_SOURCE,
    "data_source": NodeLabel.DATA_SOURCE,
    "policy": NodeLabel.POLICY,
}


def _resolve_label(label: str) -> NodeLabel:
    key = label.strip().lower().rstrip("s").replace("-", "_")
    # normalize "datasources" -> "datasource", "policie" (from policies) -> "policy"
    if key == "policie":
        key = "policy"
    resolved = _LABEL_ALIASES.get(key)
    if resolved is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Unknown entity label '{label}'. Valid: {[a.value for a in NodeLabel]}",
        )
    return resolved


@router.get("", response_model=GraphSnapshot, summary="Full graph snapshot")
async def get_graph(q: GraphQueries = Depends(get_queries)) -> GraphSnapshot:
    return await q.full_graph()


@router.delete("", response_model=MessageResponse, summary="Reset the graph (delete all nodes/edges)")
async def delete_graph(client: Neo4jClient = Depends(get_neo4j_client)) -> MessageResponse:
    await reset_graph(client)
    return MessageResponse(message="Graph reset: all nodes and relationships deleted.")


@router.get("/stats", response_model=GraphStats, summary="Graph statistics for dashboards")
async def graph_stats(q: GraphQueries = Depends(get_queries)) -> GraphStats:
    stats = await q.stats()
    return GraphStats(**stats, llm_provider=get_llm_provider().name)


@router.get("/drift", response_model=QueryResponse, summary="Runtime-observed relationships not declared in config")
async def graph_drift(q: GraphQueries = Depends(get_queries)) -> QueryResponse:
    results = await q.drift()
    return QueryResponse(query="drift", count=len(results), results=results)


@router.get("/entities/{label}", response_model=EntityListResponse, summary="List entities of a type")
async def list_entities(
    label: str,
    search: str | None = Query(None, description="Case-insensitive name substring filter."),
    limit: int = Query(100, ge=1, le=1000),
    q: GraphQueries = Depends(get_queries),
) -> EntityListResponse:
    node_label = _resolve_label(label)
    results = await q.list_entities(node_label, search, limit)
    return EntityListResponse(label=node_label.value, count=len(results), results=results)


@router.get("/neighbors/{name}", response_model=GraphSnapshot, summary="Subgraph around a node")
async def neighbors(
    name: str,
    depth: int = Query(1, ge=1, le=4, description="Traversal depth (hops)."),
    q: GraphQueries = Depends(get_queries),
) -> GraphSnapshot:
    return await q.neighbors(name, depth)


@router.post(
    "/nl-query",
    response_model=NlQueryResponse,
    summary="Natural-language query: LLM generates read-only Cypher, returns the matching subgraph",
)
async def nl_query(
    req: NlQueryRequest,
    client: Neo4jClient = Depends(get_neo4j_client),
) -> NlQueryResponse:
    """Translate a question into read-only Cypher (via the LLM) and run it.

    Pipeline: LLM -> Cypher -> read-only safety validation -> READ transaction
    -> subgraph. Failures at any stage map to a 4xx/5xx with a clear message
    instead of a 500, and the executed Cypher is always returned for
    transparency.
    """
    provider = get_llm_provider()

    # 1. Generate Cypher. The heuristic (offline fallback) cannot author Cypher.
    try:
        plan = provider.generate_cypher(req.question, schema=GRAPH_SCHEMA)
    except NotImplementedError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The active LLM provider '{provider.name}' cannot generate Cypher. "
            "Configure a generative provider (set LLM_PROVIDER=llm and LLM_API_KEY).",
        )
    except Exception as exc:  # noqa: BLE001 - surface upstream LLM errors as 502
        logger.warning("NL query generation failed", extra={"provider": provider.name, "error": str(exc)})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"LLM query generation failed: {exc}")

    # 2. Enforce read-only safety before the statement touches the database.
    try:
        safe_cypher = ensure_read_only(plan.cypher)
    except UnsafeCypherError as exc:
        logger.warning("Rejected unsafe generated Cypher", extra={"cypher": plan.cypher, "error": str(exc)})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Generated query rejected: {exc}")

    # 3. Execute in a READ transaction and shape into a subgraph.
    try:
        snapshot = await client.run_read_graph(safe_cypher)
    except Exception as exc:  # noqa: BLE001 - bad Cypher / read-mode violation -> 400, not 500
        logger.warning("NL query execution failed", extra={"cypher": safe_cypher, "error": str(exc)})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Query execution failed: {exc}")

    return NlQueryResponse(
        question=req.question,
        cypher=safe_cypher,
        explanation=plan.explanation,
        provider=provider.name,
        node_count=len(snapshot.nodes),
        edge_count=len(snapshot.edges),
        snapshot=snapshot,
    )
