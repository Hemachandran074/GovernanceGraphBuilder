"""Loader that writes a :class:`GraphDocument` into Neo4j.

Uses ``UNWIND ... MERGE`` batched per label / relationship type so loading is
idempotent: re-ingesting the same document updates existing nodes in place
rather than creating duplicates. Node/relationship labels are interpolated from
enums (never user input), so the dynamic Cypher is injection-safe.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from app.graph.client import Neo4jClient
from app.models.edges import Edge, RelType
from app.models.graph import GraphDocument
from app.models.nodes import NodeLabel

logger = logging.getLogger(__name__)

# Relationship types the agent config is authoritative for. On re-ingest, the
# declared edges of these types for an agent must exactly match the new config.
_AGENT_OUTGOING_RECONCILE = (
    RelType.USES_MODEL,
    RelType.HAS_TOOL,
    RelType.ACCESSES,
    RelType.GOVERNED_BY,
)
_AGENT_INCOMING_RECONCILE = (RelType.OWNS, RelType.USES)


async def _merge_nodes(
    client: Neo4jClient,
    label: NodeLabel,
    rows: list[dict],
    *,
    overwrite: bool = True,
) -> None:
    if not rows:
        return
    # When overwrite is False, only set properties on first create so that
    # observation stubs (id + name) never clobber richer config-authored nodes.
    set_clause = "SET n += row" if overwrite else "ON CREATE SET n += row"
    cypher = (
        "UNWIND $rows AS row "
        f"MERGE (n:`{label.value}` {{id: row.id}}) "
        f"{set_clause}"
    )
    await client.run_query(cypher, {"rows": rows})


async def _merge_edges(client: Neo4jClient, edges: list[Edge]) -> None:
    # Group edges by (source label, rel type, target label) so each group can
    # be written with a single UNWIND batch.
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for edge in edges:
        key = (edge.source_label.value, edge.rel_type.value, edge.target_label.value)
        groups[key].append(
            {
                "source_id": edge.source_id,
                "target_id": edge.target_id,
                "props": edge.properties,
            }
        )

    for (source_label, rel_type, target_label), rows in groups.items():
        cypher = (
            "UNWIND $rows AS row "
            f"MATCH (s:`{source_label}` {{id: row.source_id}}) "
            f"MATCH (t:`{target_label}` {{id: row.target_id}}) "
            f"MERGE (s)-[r:`{rel_type}`]->(t) "
            "SET r += row.props"
        )
        await client.run_query(cypher, {"rows": rows})


async def load_document(client: Neo4jClient, document: GraphDocument) -> dict[str, int]:
    """Merge every node and edge of ``document`` into the graph.

    Returns the counts of entities written.
    """
    for label, nodes in document.node_groups():
        rows = [node.model_dump() for node in nodes]
        await _merge_nodes(client, label, rows)

    await _merge_edges(client, document.edges)

    counts = document.counts()
    logger.info("Loaded graph document", extra=counts)
    return counts


async def load_observations(client: Neo4jClient, document: GraphDocument) -> dict[str, int]:
    """Merge observed (runtime) nodes and edges into the graph.

    Unlike :func:`load_document`, node properties are only written on create, so
    observation stubs never overwrite config-authored node details. Edges
    accumulate observed metadata (``observed``, ``observed_count``,
    ``last_seen``) on top of any existing declared relationship.
    """
    for label, nodes in document.node_groups():
        rows = [node.model_dump() for node in nodes]
        await _merge_nodes(client, label, rows, overwrite=False)

    await _merge_edges(client, document.edges)

    counts = document.counts()
    logger.info("Loaded observations", extra=counts)
    return counts


async def _run_count(client: Neo4jClient, cypher: str, params: dict) -> int:
    rows = await client.run_query(cypher, params)
    return int(rows[0]["n"]) if rows else 0


async def _reconcile_relationship(
    client: Neo4jClient,
    agent_id: str,
    rel: RelType,
    desired_ids: list[str],
    *,
    incoming: bool,
) -> tuple[int, int]:
    """Reconcile one relationship type for one agent.

    Declared edges whose "other" endpoint is no longer in ``desired_ids`` are
    either downgraded (``declared`` removed) when the edge still has another
    provenance — observed at runtime or asserted by a policy document — or
    deleted outright when the config was its only source. Returns
    ``(downgraded, deleted)``.
    """
    pattern = (
        f"(other)-[r:`{rel.value}`]->(a:Agent {{id: $aid}})"
        if incoming
        else f"(a:Agent {{id: $aid}})-[r:`{rel.value}`]->(other)"
    )
    base_where = "coalesce(r.declared, false) = true AND NOT other.id IN $ids"
    has_other_provenance = "(coalesce(r.observed, false) = true OR r.source IS NOT NULL)"
    params = {"aid": agent_id, "ids": desired_ids}

    downgraded = await _run_count(
        client,
        f"MATCH {pattern} WHERE {base_where} AND {has_other_provenance} "
        "WITH collect(r) AS rs FOREACH (x IN rs | SET x.declared = null) RETURN size(rs) AS n",
        params,
    )
    deleted = await _run_count(
        client,
        f"MATCH {pattern} WHERE {base_where} AND NOT {has_other_provenance} "
        "WITH collect(r) AS rs FOREACH (x IN rs | DELETE x) RETURN size(rs) AS n",
        params,
    )
    return downgraded, deleted


async def _cleanup_dangling_nodes(client: Neo4jClient) -> int:
    """Delete non-agent entities left with no relationships after reconciliation."""
    return await _run_count(
        client,
        "MATCH (n) WHERE (n:User OR n:Model OR n:Tool OR n:DataSource OR n:Policy) "
        "AND NOT (n)--() "
        "WITH collect(n) AS ns FOREACH (x IN ns | DELETE x) RETURN size(ns) AS n",
        {},
    )


async def reconcile_declared_edges(client: Neo4jClient, document: GraphDocument) -> dict[str, int]:
    """Make each agent's declared edges match the just-loaded config document.

    Call this after :func:`load_document` so the new declared edges already
    exist; this step removes the stale ones. Only agents present in the document
    are touched. Observed (runtime) edges are never deleted — a config removal
    that was still observed becomes drift instead.
    """
    downgraded_total = 0
    deleted_total = 0

    for agent in document.agents:
        for rel in _AGENT_OUTGOING_RECONCILE:
            desired = [e.target_id for e in document.edges if e.source_id == agent.id and e.rel_type == rel]
            downgraded, deleted = await _reconcile_relationship(client, agent.id, rel, desired, incoming=False)
            downgraded_total += downgraded
            deleted_total += deleted
        for rel in _AGENT_INCOMING_RECONCILE:
            desired = [e.source_id for e in document.edges if e.target_id == agent.id and e.rel_type == rel]
            downgraded, deleted = await _reconcile_relationship(client, agent.id, rel, desired, incoming=True)
            downgraded_total += downgraded
            deleted_total += deleted

    cleaned = await _cleanup_dangling_nodes(client) if document.agents else 0

    result = {
        "declared_edges_removed": deleted_total,
        "declared_edges_downgraded": downgraded_total,
        "dangling_nodes_removed": cleaned,
    }
    if deleted_total or downgraded_total or cleaned:
        logger.info("Reconciled declared edges", extra=result)
    return result


async def reset_graph(client: Neo4jClient) -> None:
    """Delete all nodes and relationships (constraints/indexes are kept)."""
    await client.run_query("MATCH (n) DETACH DELETE n")
    logger.info("Graph reset: all nodes and relationships deleted")
