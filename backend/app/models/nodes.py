"""Node models for the governance graph.

Each model maps to a Neo4j node label. ``id`` is the stable merge key used by
the loader; ``name`` is the human-facing identifier the governance queries look
up by. Optional fields default to ``None`` and are simply omitted from the node
when not provided.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NodeLabel(str, Enum):
    """Neo4j node labels for the six governance entity types."""

    USER = "User"
    AGENT = "Agent"
    MODEL = "Model"
    TOOL = "Tool"
    DATA_SOURCE = "DataSource"
    POLICY = "Policy"


class GraphNodeBase(BaseModel):
    """Common fields shared by every node."""

    id: str = Field(..., description="Stable unique identifier (merge key).")
    name: str = Field(..., description="Human-facing name used by governance queries.")


class User(GraphNodeBase):
    email: str | None = None
    role: str | None = None
    team: str | None = None


class Agent(GraphNodeBase):
    description: str | None = None
    version: str | None = None
    environment: str | None = None  # development | staging | production
    status: str | None = None


class Model(GraphNodeBase):
    provider: str | None = None  # openai | anthropic | bedrock | ...
    version: str | None = None
    modality: str | None = None


class Tool(GraphNodeBase):
    type: str | None = None  # api | function | retriever | ...
    endpoint: str | None = None
    scopes: list[str] = Field(default_factory=list)


class DataSource(GraphNodeBase):
    type: str | None = None  # s3 | db | vector | api | ...
    classification: str | None = None  # public | internal | pii | secret


class Policy(GraphNodeBase):
    type: str | None = None  # access | data | usage | ...
    description: str | None = None
    rules: list[str] = Field(default_factory=list)
    source: str | None = None  # provenance, e.g. the policy document name
