"""Policy document ingestion (Source C) — LLM-powered.

Runs the configured LLM provider over a natural-language policy document to
extract structured policies, then grounds the extracted references against the
existing graph vocabulary to produce:

- enriched ``Policy`` nodes (type, description, rules) that upsert onto the
  stubs created from the agent config, and
- ``GOVERNED_BY`` (Agent -> Policy) and ``APPLIES_TO`` (Policy -> Tool/DataSource/Model)
  edges.

References are routed by the *resolved node label*, so a policy can never, for
example, ``APPLIES_TO`` an agent — keeping the graph schema correct regardless
of how the provider classified a name.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.graph.client import Neo4jClient
from app.graph.loader import load_document
from app.llm.provider import LLMProvider, PolicyExtraction, get_llm_provider
from app.models.edges import Edge, RelType
from app.models.graph import GraphDocument
from app.models.nodes import NodeLabel, Policy

logger = logging.getLogger(__name__)

_ENTITY_LABELS = {NodeLabel.TOOL.value, NodeLabel.DATA_SOURCE.value, NodeLabel.MODEL.value}


def _slugify(name: str) -> str:
    return "policy-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def _load_vocabulary(
    client: Neo4jClient,
) -> tuple[dict[str, tuple[str, str]], list[str], list[str]]:
    """Return (name -> (id, label)), agent names, and entity names in the graph."""
    rows = await client.run_query(
        "MATCH (n) WHERE n.name IS NOT NULL "
        "RETURN n.name AS name, n.id AS id, labels(n)[0] AS label"
    )
    name_to_node: dict[str, tuple[str, str]] = {}
    agents: list[str] = []
    entities: list[str] = []
    for row in rows:
        name_to_node[row["name"]] = (row["id"], row["label"])
        if row["label"] == NodeLabel.AGENT.value:
            agents.append(row["name"])
        elif row["label"] in _ENTITY_LABELS:
            entities.append(row["name"])
    return name_to_node, agents, entities


def _extraction_to_document(
    extraction: PolicyExtraction,
    name_to_node: dict[str, tuple[str, str]],
) -> GraphDocument:
    policies: list[Policy] = []
    edges: list[Edge] = []

    for extracted in extraction.policies:
        policy_id = extracted.id or _slugify(extracted.name)
        policies.append(
            Policy(
                id=policy_id,
                name=extracted.name,
                type=extracted.type,
                description=extracted.description,
                rules=extracted.rules,
                source="policy-document",
            )
        )

        # GOVERNED_BY: only when the referenced name resolves to an Agent.
        for agent_name in extracted.governs:
            node = name_to_node.get(agent_name)
            if node and node[1] == NodeLabel.AGENT.value:
                edges.append(
                    Edge(
                        source_id=node[0],
                        source_label=NodeLabel.AGENT,
                        rel_type=RelType.GOVERNED_BY,
                        target_id=policy_id,
                        target_label=NodeLabel.POLICY,
                        properties={"source": "policy-document"},
                    )
                )
            else:
                logger.warning("Policy governs unknown agent; skipping", extra={"name": agent_name})

        # APPLIES_TO: only when the referenced name resolves to Tool/DataSource/Model.
        for entity_name in extracted.applies_to:
            node = name_to_node.get(entity_name)
            if node and node[1] in _ENTITY_LABELS:
                edges.append(
                    Edge(
                        source_id=policy_id,
                        source_label=NodeLabel.POLICY,
                        rel_type=RelType.APPLIES_TO,
                        target_id=node[0],
                        target_label=NodeLabel(node[1]),
                        properties={"source": "policy-document"},
                    )
                )
            else:
                logger.warning("Policy applies to unknown entity; skipping", extra={"name": entity_name})

    return GraphDocument(policies=policies, edges=edges)


async def ingest_policy_document(
    client: Neo4jClient,
    document_text: str,
    provider: LLMProvider | None = None,
) -> dict[str, Any]:
    """Parse a policy document with the LLM provider and load it into the graph."""
    provider = provider or get_llm_provider()
    name_to_node, agents, entities = await _load_vocabulary(client)

    extraction = provider.extract_policies(
        document_text, known_agents=agents, known_entities=entities
    )
    document = _extraction_to_document(extraction, name_to_node)
    counts = await load_document(client, document)

    logger.info(
        "Ingested policy document",
        extra={"provider": provider.name, "policies": len(extraction.policies)},
    )
    return {"provider": provider.name, "policies_extracted": len(extraction.policies), **counts}
