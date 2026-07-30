"""Governance query endpoints (the four required queries + blast radius)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.schemas import QueryResponse
from app.dependencies import get_queries
from app.graph.queries import GraphQueries
from app.models.graph import BlastRadiusResult

router = APIRouter(tags=["queries"])


@router.get("/agents/orphans", response_model=QueryResponse, summary="Agents with no policy attached")
async def orphan_agents(q: GraphQueries = Depends(get_queries)) -> QueryResponse:
    results = await q.orphan_agents()
    return QueryResponse(query="orphan_agents", count=len(results), results=results)


@router.get("/agents/{name}/tools", response_model=QueryResponse, summary="Tools an agent can access")
async def agent_tools(name: str, q: GraphQueries = Depends(get_queries)) -> QueryResponse:
    results = await q.tools_for_agent(name)
    return QueryResponse(query="tools_for_agent", parameters={"agent": name}, count=len(results), results=results)


@router.get("/models/{name}/agents", response_model=QueryResponse, summary="Agents using a model")
async def model_agents(name: str, q: GraphQueries = Depends(get_queries)) -> QueryResponse:
    results = await q.agents_using_model(name)
    return QueryResponse(query="agents_using_model", parameters={"model": name}, count=len(results), results=results)


@router.get("/datasources/{name}/agents", response_model=QueryResponse, summary="Agents that can access a data source")
async def datasource_agents(name: str, q: GraphQueries = Depends(get_queries)) -> QueryResponse:
    results = await q.agents_accessing_datasource(name)
    return QueryResponse(
        query="agents_accessing_datasource",
        parameters={"data_source": name},
        count=len(results),
        results=results,
    )


@router.get("/tools/{name}/blast-radius", response_model=BlastRadiusResult, summary="Blast radius of a compromised tool")
async def tool_blast_radius(name: str, q: GraphQueries = Depends(get_queries)) -> BlastRadiusResult:
    return await q.blast_radius(name)
