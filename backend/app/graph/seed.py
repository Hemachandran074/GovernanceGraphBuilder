"""Hand-authored seed graph for development and query verification.

The seed is intentionally small but exercises every governance query:

- a **shared model** (two agents use ``gpt-4o``),
- **direct** data access (``Support Assistant`` -> ``orders-db``) and
  **transitive** access through a tool (``Analytics Agent`` -> ``sql-runner`` ->
  ``warehouse-db``),
- an **orphan agent** with no policy attached (``Sandbox Agent``),
- a tool shared by two agents (``web-search``) for the blast-radius query.
"""

from __future__ import annotations

import logging

from app.graph.client import Neo4jClient
from app.graph.loader import load_document, reset_graph
from app.graph.schema import apply_schema
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

logger = logging.getLogger(__name__)


def _edge(src_label: NodeLabel, src_id: str, rel: RelType, dst_label: NodeLabel, dst_id: str) -> Edge:
    return Edge(
        source_id=src_id,
        source_label=src_label,
        rel_type=rel,
        target_id=dst_id,
        target_label=dst_label,
    )


def build_seed_document() -> GraphDocument:
    """Return the canonical seed as a :class:`GraphDocument`."""
    users = [
        User(id="user-alice", name="Alice", email="alice@example.com", role="owner", team="support"),
        User(id="user-bob", name="Bob", email="bob@example.com", role="owner", team="analytics"),
        User(id="user-carol", name="Carol", email="carol@example.com", role="engineer", team="platform"),
    ]

    agents = [
        Agent(id="agent-support", name="Support Assistant", description="Handles customer support",
              version="1.2.0", environment="production", status="active"),
        Agent(id="agent-analytics", name="Analytics Agent", description="Runs analytics queries",
              version="0.9.0", environment="production", status="active"),
        Agent(id="agent-sandbox", name="Sandbox Agent", description="Experimental agent (no policy)",
              version="0.1.0", environment="development", status="active"),
    ]

    models = [
        Model(id="model-gpt4o", name="gpt-4o", provider="openai", version="2024-08-06", modality="text"),
        Model(id="model-claude", name="claude-3-5-sonnet", provider="anthropic", version="20241022", modality="text"),
    ]

    tools = [
        Tool(id="tool-web-search", name="web-search", type="api", endpoint="https://api.search.example.com",
             scopes=["search:read"]),
        Tool(id="tool-order-lookup", name="order-lookup", type="function", scopes=["orders:read"]),
        Tool(id="tool-sql-runner", name="sql-runner", type="function", scopes=["warehouse:read"]),
    ]

    data_sources = [
        DataSource(id="ds-orders", name="orders-db", type="db", classification="pii"),
        DataSource(id="ds-warehouse", name="warehouse-db", type="db", classification="internal"),
    ]

    policies = [
        Policy(id="policy-pii", name="PII Handling Policy", type="data",
               description="Controls access to customer PII.",
               rules=["Mask PII in logs", "Restrict orders-db to support agents"], source="seed"),
        Policy(id="policy-data", name="Data Governance Policy", type="data",
               description="Governs analytical data access.",
               rules=["Warehouse access requires audit logging"], source="seed"),
    ]

    A, U, M, T, D, P = (
        NodeLabel.AGENT, NodeLabel.USER, NodeLabel.MODEL,
        NodeLabel.TOOL, NodeLabel.DATA_SOURCE, NodeLabel.POLICY,
    )

    edges = [
        # Ownership
        _edge(U, "user-alice", RelType.OWNS, A, "agent-support"),
        _edge(U, "user-bob", RelType.OWNS, A, "agent-analytics"),
        _edge(U, "user-carol", RelType.OWNS, A, "agent-sandbox"),
        # Models (gpt-4o shared by two agents)
        _edge(A, "agent-support", RelType.USES_MODEL, M, "model-gpt4o"),
        _edge(A, "agent-analytics", RelType.USES_MODEL, M, "model-gpt4o"),
        _edge(A, "agent-sandbox", RelType.USES_MODEL, M, "model-claude"),
        # Tools (web-search shared by two agents)
        _edge(A, "agent-support", RelType.HAS_TOOL, T, "tool-web-search"),
        _edge(A, "agent-support", RelType.HAS_TOOL, T, "tool-order-lookup"),
        _edge(A, "agent-analytics", RelType.HAS_TOOL, T, "tool-sql-runner"),
        _edge(A, "agent-sandbox", RelType.HAS_TOOL, T, "tool-web-search"),
        # Direct data access
        _edge(A, "agent-support", RelType.ACCESSES, D, "ds-orders"),
        # Transitive data access (tool -> data source)
        _edge(T, "tool-order-lookup", RelType.READS_FROM, D, "ds-orders"),
        _edge(T, "tool-sql-runner", RelType.READS_FROM, D, "ds-warehouse"),
        # Policies (agent-sandbox intentionally left ungoverned -> orphan)
        _edge(A, "agent-support", RelType.GOVERNED_BY, P, "policy-pii"),
        _edge(A, "agent-analytics", RelType.GOVERNED_BY, P, "policy-data"),
        _edge(P, "policy-pii", RelType.APPLIES_TO, D, "ds-orders"),
        _edge(P, "policy-data", RelType.APPLIES_TO, D, "ds-warehouse"),
    ]

    return GraphDocument(
        users=users,
        agents=agents,
        models=models,
        tools=tools,
        data_sources=data_sources,
        policies=policies,
        edges=edges,
    )


async def seed_graph(client: Neo4jClient, reset: bool = True) -> dict[str, int]:
    """Apply schema, optionally reset, and load the seed document."""
    await apply_schema(client)
    if reset:
        await reset_graph(client)
    counts = await load_document(client, build_seed_document())
    logger.info("Seed graph loaded", extra=counts)
    return counts
