"""Request and response models for the HTTP API.

Query results keep node properties as open dicts (``dict[str, Any]``) so the API
stays dynamic across evolving node shapes, while envelopes (counts, query name,
parameters) are strongly typed for good OpenAPI docs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# --- Ingestion requests ------------------------------------------------------

class AgentConfigIngestRequest(BaseModel):
    content: str | None = Field(None, description="Raw YAML or JSON agent-config text.")
    config: dict[str, Any] | None = Field(None, description="Already-parsed agent-config object.")
    reset: bool = Field(False, description="Clear the graph before ingesting.")


class RuntimeLogsIngestRequest(BaseModel):
    content: str | None = Field(None, description="Raw JSONL runtime-log text.")
    records: list[dict[str, Any]] | None = Field(None, description="Pre-parsed log records.")


class PolicyIngestRequest(BaseModel):
    content: str = Field(..., description="Natural-language policy document text.")


class BundleIngestRequest(BaseModel):
    bundle: str = Field(..., description="Sample bundle name (e.g. simple|medium|complex) or a path.")
    reset: bool = Field(True, description="Clear the graph before ingesting the bundle.")


# --- Responses ---------------------------------------------------------------

class IngestResponse(BaseModel):
    status: str = "ok"
    result: dict[str, Any]


class QueryResponse(BaseModel):
    query: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    count: int
    results: list[dict[str, Any]]


class EntityListResponse(BaseModel):
    label: str
    count: int
    results: list[dict[str, Any]]


class GraphStats(BaseModel):
    nodes: dict[str, int]
    total_nodes: int
    total_edges: int
    orphan_agents: int
    drift_edges: int
    llm_provider: str


class BundleListResponse(BaseModel):
    bundles: list[str]


class MessageResponse(BaseModel):
    status: str = "ok"
    message: str
