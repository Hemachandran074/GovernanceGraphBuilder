"""Graph endpoints: snapshot, reset, stats, entity listing, neighbors, drift."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.schemas import (
    EntityListResponse,
    GraphStats,
    MessageResponse,
    QueryResponse,
)
from app.dependencies import get_neo4j_client, get_queries
from app.graph.client import Neo4jClient
from app.graph.loader import reset_graph
from app.graph.queries import GraphQueries
from app.llm import get_llm_provider
from app.models.graph import GraphSnapshot
from app.models.nodes import NodeLabel

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
