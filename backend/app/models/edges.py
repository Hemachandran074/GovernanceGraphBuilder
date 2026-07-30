"""Edge (relationship) model for the governance graph."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.nodes import NodeLabel


class RelType(str, Enum):
    """Relationship types connecting governance entities."""

    OWNS = "OWNS"  # User -> Agent
    USES = "USES"  # User -> Agent (non-owning user)
    USES_MODEL = "USES_MODEL"  # Agent -> Model
    HAS_TOOL = "HAS_TOOL"  # Agent -> Tool
    ACCESSES = "ACCESSES"  # Agent -> DataSource (direct)
    GOVERNED_BY = "GOVERNED_BY"  # Agent -> Policy
    READS_FROM = "READS_FROM"  # Tool -> DataSource (transitive data access)
    APPLIES_TO = "APPLIES_TO"  # Policy -> Tool | DataSource | Model


class Edge(BaseModel):
    """A directed, typed relationship between two nodes (matched by id)."""

    source_id: str
    source_label: NodeLabel
    rel_type: RelType
    target_id: str
    target_label: NodeLabel
    properties: dict[str, Any] = Field(default_factory=dict)
