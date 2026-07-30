"""Agent config ingestion (Source A).

Parses a declarative agent configuration (YAML or JSON) into a
:class:`GraphDocument`. This is the authoritative *structural* source: it
declares each agent together with its owner/users, model, tools, data sources,
and the policies that govern it.

The file may describe a single agent (top-level keys) or a fleet via a
top-level ``agents:`` list. Edges produced here are tagged ``declared=True`` so
they can later be reconciled against what runtime logs actually *observed*.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError


class _NoDatesSafeLoader(yaml.SafeLoader):
    """SafeLoader that keeps ISO date-like scalars as strings.

    Plain YAML parses ``version: 2024-08-06`` into a ``datetime.date``. Config
    fields like versions are strings, so we drop the implicit timestamp
    resolver to avoid surprising type coercion.
    """


_NoDatesSafeLoader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in mappings if tag != "tag:yaml.org,2002:timestamp"]
    for key, mappings in yaml.SafeLoader.yaml_implicit_resolvers.items()
}

from app.models.edges import Edge, RelType
from app.models.graph import GraphDocument
from app.models.nodes import (
    Agent,
    DataSource,
    Model,
    NodeLabel,
    Policy,
    Tool,
    User,
)


class IngestionError(ValueError):
    """Raised when a source document cannot be parsed into the graph model."""


# --- Input schema (validates the config file structure) ---------------------

class _UserBlock(BaseModel):
    id: str
    name: str
    email: str | None = None
    role: str | None = None
    team: str | None = None
    relation: str = "OWNS"  # OWNS | USES


class _ModelBlock(BaseModel):
    id: str
    name: str
    provider: str | None = None
    version: str | None = None
    modality: str | None = None


class _ToolBlock(BaseModel):
    id: str
    name: str
    type: str | None = None
    endpoint: str | None = None
    scopes: list[str] = Field(default_factory=list)
    reads_from: list[str] = Field(default_factory=list)  # DataSource ids


class _DataSourceBlock(BaseModel):
    id: str
    name: str
    type: str | None = None
    classification: str | None = None


class _PolicyRef(BaseModel):
    id: str
    name: str


class _AgentBlock(BaseModel):
    id: str
    name: str
    description: str | None = None
    version: str | None = None
    environment: str | None = None
    status: str | None = None
    owner: _UserBlock | None = None
    users: list[_UserBlock] = Field(default_factory=list)
    model: _ModelBlock | None = None
    tools: list[_ToolBlock] = Field(default_factory=list)
    data_sources: list[_DataSourceBlock] = Field(default_factory=list)
    policies: list[_PolicyRef] = Field(default_factory=list)


# --- Parsing ----------------------------------------------------------------

def load_config_text(text: str, *, fmt: str | None = None) -> dict[str, Any]:
    """Parse raw config text (YAML or JSON) into a dict.

    YAML is a superset of JSON, so ``yaml.safe_load`` handles both; ``fmt`` is
    accepted for clarity/logging but not required.
    """
    try:
        data = yaml.load(text, Loader=_NoDatesSafeLoader)
    except yaml.YAMLError as exc:  # pragma: no cover - passthrough with context
        raise IngestionError(f"Invalid YAML/JSON agent config: {exc}") from exc
    if not isinstance(data, dict):
        raise IngestionError("Agent config must be a mapping at the top level.")
    return data


def _normalize_block(raw: dict[str, Any]) -> dict[str, Any]:
    """Support both flat blocks and blocks that nest agent identity under ``agent:``.

    ``{"agent": {"id": ..., "name": ...}, "model": ...}`` becomes
    ``{"id": ..., "name": ..., "model": ...}``.
    """
    if isinstance(raw.get("agent"), dict):
        identity = raw["agent"]
        relations = {k: v for k, v in raw.items() if k != "agent"}
        return {**identity, **relations}
    return raw


def parse_agent_config(data: dict[str, Any]) -> GraphDocument:
    """Convert a parsed agent-config dict into a :class:`GraphDocument`."""
    blocks_raw = data["agents"] if "agents" in data else [data]
    try:
        blocks = [_AgentBlock(**_normalize_block(block)) for block in blocks_raw]
    except ValidationError as exc:
        raise IngestionError(f"Agent config failed validation: {exc}") from exc

    builder = _GraphBuilder()
    for block in blocks:
        builder.add_agent(block)
    return builder.build()


class _GraphBuilder:
    """Accumulates de-duplicated nodes (by id) and edges across agent blocks."""

    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.agents: dict[str, Agent] = {}
        self.models: dict[str, Model] = {}
        self.tools: dict[str, Tool] = {}
        self.data_sources: dict[str, DataSource] = {}
        self.policies: dict[str, Policy] = {}
        self.edges: list[Edge] = []

    def _edge(self, sl: NodeLabel, sid: str, rel: RelType, tl: NodeLabel, tid: str) -> None:
        self.edges.append(
            Edge(
                source_id=sid,
                source_label=sl,
                rel_type=rel,
                target_id=tid,
                target_label=tl,
                properties={"declared": True},
            )
        )

    def add_agent(self, block: _AgentBlock) -> None:
        self.agents[block.id] = Agent(
            id=block.id,
            name=block.name,
            description=block.description,
            version=block.version,
            environment=block.environment,
            status=block.status,
        )

        # Owner + additional users
        for user_block in [*( [block.owner] if block.owner else [] ), *block.users]:
            self.users[user_block.id] = User(
                id=user_block.id,
                name=user_block.name,
                email=user_block.email,
                role=user_block.role,
                team=user_block.team,
            )
            rel = RelType.USES if user_block.relation.upper() == "USES" else RelType.OWNS
            self._edge(NodeLabel.USER, user_block.id, rel, NodeLabel.AGENT, block.id)

        # Model
        if block.model:
            self.models[block.model.id] = Model(
                id=block.model.id,
                name=block.model.name,
                provider=block.model.provider,
                version=block.model.version,
                modality=block.model.modality,
            )
            self._edge(NodeLabel.AGENT, block.id, RelType.USES_MODEL, NodeLabel.MODEL, block.model.id)

        # Data sources (direct access)
        for ds in block.data_sources:
            self.data_sources[ds.id] = DataSource(
                id=ds.id, name=ds.name, type=ds.type, classification=ds.classification
            )
            self._edge(NodeLabel.AGENT, block.id, RelType.ACCESSES, NodeLabel.DATA_SOURCE, ds.id)

        # Tools (+ transitive READS_FROM to data sources)
        for tool in block.tools:
            self.tools[tool.id] = Tool(
                id=tool.id,
                name=tool.name,
                type=tool.type,
                endpoint=tool.endpoint,
                scopes=tool.scopes,
            )
            self._edge(NodeLabel.AGENT, block.id, RelType.HAS_TOOL, NodeLabel.TOOL, tool.id)
            for ds_id in tool.reads_from:
                self._edge(NodeLabel.TOOL, tool.id, RelType.READS_FROM, NodeLabel.DATA_SOURCE, ds_id)

        # Policies (governance attachment)
        for policy in block.policies:
            # A stub node; the policy document (Source C) enriches it later.
            self.policies.setdefault(policy.id, Policy(id=policy.id, name=policy.name))
            self._edge(NodeLabel.AGENT, block.id, RelType.GOVERNED_BY, NodeLabel.POLICY, policy.id)

    def build(self) -> GraphDocument:
        return GraphDocument(
            users=list(self.users.values()),
            agents=list(self.agents.values()),
            models=list(self.models.values()),
            tools=list(self.tools.values()),
            data_sources=list(self.data_sources.values()),
            policies=list(self.policies.values()),
            edges=self.edges,
        )
