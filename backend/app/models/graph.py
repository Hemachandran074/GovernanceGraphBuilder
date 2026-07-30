"""Aggregate graph models: the ingestion document and query result shapes."""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, Field

from app.models.edges import Edge
from app.models.nodes import (
    Agent,
    DataSource,
    Model,
    NodeLabel,
    Policy,
    Tool,
    User,
)


class GraphDocument(BaseModel):
    """A normalized set of nodes and edges produced by ingestion / seeding.

    This is the canonical payload the loader writes to Neo4j. Every ingestion
    source (agent config, runtime logs, policy document) is reduced to one of
    these before loading.
    """

    users: list[User] = Field(default_factory=list)
    agents: list[Agent] = Field(default_factory=list)
    models: list[Model] = Field(default_factory=list)
    tools: list[Tool] = Field(default_factory=list)
    data_sources: list[DataSource] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)

    def node_groups(self) -> list[tuple[NodeLabel, list[Any]]]:
        """Return (label, nodes) pairs so the loader can batch per label."""
        return [
            (NodeLabel.USER, self.users),
            (NodeLabel.AGENT, self.agents),
            (NodeLabel.MODEL, self.models),
            (NodeLabel.TOOL, self.tools),
            (NodeLabel.DATA_SOURCE, self.data_sources),
            (NodeLabel.POLICY, self.policies),
        ]

    def merge(self, other: "GraphDocument") -> "GraphDocument":
        """Combine two documents (used when ingesting multiple sources)."""
        return GraphDocument(
            users=[*self.users, *other.users],
            agents=[*self.agents, *other.agents],
            models=[*self.models, *other.models],
            tools=[*self.tools, *other.tools],
            data_sources=[*self.data_sources, *other.data_sources],
            policies=[*self.policies, *other.policies],
            edges=[*self.edges, *other.edges],
        )

    def counts(self) -> dict[str, int]:
        return {
            "users": len(self.users),
            "agents": len(self.agents),
            "models": len(self.models),
            "tools": len(self.tools),
            "data_sources": len(self.data_sources),
            "policies": len(self.policies),
            "edges": len(self.edges),
        }


class GraphNodeView(BaseModel):
    """A node as returned to clients (visualization / query results)."""

    id: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeView(BaseModel):
    """An edge as returned to clients."""

    source: str
    target: str
    type: str


class GraphSnapshot(BaseModel):
    """Full graph payload for visualization."""

    nodes: list[GraphNodeView] = Field(default_factory=list)
    edges: list[GraphEdgeView] = Field(default_factory=list)


class BlastRadiusResult(BaseModel):
    """Bonus query result: who/what is affected by a compromised tool."""

    tool: dict[str, Any] | None = None
    affected_agents: list[dict[str, Any]] = Field(default_factory=list)
    affected_users: list[dict[str, Any]] = Field(default_factory=list)
    exposed_data_sources: list[dict[str, Any]] = Field(default_factory=list)


def flatten_nodes(doc: GraphDocument) -> Iterable[tuple[NodeLabel, Any]]:
    """Yield (label, node) for every node in the document."""
    for label, nodes in doc.node_groups():
        for node in nodes:
            yield label, node
