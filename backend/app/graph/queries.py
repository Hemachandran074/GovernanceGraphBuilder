"""Governance queries over the graph.

Each method is a thin wrapper around a parameterized Cypher statement. Entity
lookups are by ``name`` (the human-facing identifier from the problem
statement). All statements use query parameters — never string interpolation of
user input — to stay injection-safe.
"""

from __future__ import annotations

from typing import Any

from app.graph.client import Neo4jClient
from app.models.graph import (
    BlastRadiusResult,
    GraphEdgeView,
    GraphNodeView,
    GraphSnapshot,
)
from app.models.nodes import NodeLabel


class GraphQueries:
    def __init__(self, client: Neo4jClient) -> None:
        self._client = client

    async def tools_for_agent(self, agent_name: str) -> list[dict[str, Any]]:
        """Q1: What tools does Agent X have access to?"""
        cypher = (
            "MATCH (:Agent {name: $name})-[:HAS_TOOL]->(t:Tool) "
            "RETURN t{.*} AS tool ORDER BY t.name"
        )
        rows = await self._client.run_query(cypher, {"name": agent_name})
        return [row["tool"] for row in rows]

    async def agents_using_model(self, model_name: str) -> list[dict[str, Any]]:
        """Q2: Which agents are using Model Y?"""
        cypher = (
            "MATCH (a:Agent)-[:USES_MODEL]->(:Model {name: $name}) "
            "RETURN a{.*} AS agent ORDER BY a.name"
        )
        rows = await self._client.run_query(cypher, {"name": model_name})
        return [row["agent"] for row in rows]

    async def agents_accessing_datasource(self, datasource_name: str) -> list[dict[str, Any]]:
        """Q3: Which agents can access DataSource Z?

        Considers both direct access (``Agent-[:ACCESSES]->DataSource``) and
        transitive access through a tool (``Agent-[:HAS_TOOL]->Tool-[:READS_FROM]->DataSource``).
        Each result is annotated with how the access is granted.
        """
        cypher = (
            "MATCH (a:Agent) "
            "WHERE EXISTS { (a)-[:ACCESSES]->(:DataSource {name: $name}) } "
            "   OR EXISTS { (a)-[:HAS_TOOL]->(:Tool)-[:READS_FROM]->(:DataSource {name: $name}) } "
            "RETURN a{.*} AS agent, "
            "       EXISTS { (a)-[:ACCESSES]->(:DataSource {name: $name}) } AS direct, "
            "       EXISTS { (a)-[:HAS_TOOL]->(:Tool)-[:READS_FROM]->(:DataSource {name: $name}) } AS via_tool "
            "ORDER BY a.name"
        )
        rows = await self._client.run_query(cypher, {"name": datasource_name})
        return [
            {**row["agent"], "access": {"direct": row["direct"], "via_tool": row["via_tool"]}}
            for row in rows
        ]

    async def orphan_agents(self) -> list[dict[str, Any]]:
        """Q4: Is there any agent with no policy attached?"""
        cypher = (
            "MATCH (a:Agent) "
            "WHERE NOT EXISTS { (a)-[:GOVERNED_BY]->(:Policy) } "
            "RETURN a{.*} AS agent ORDER BY a.name"
        )
        rows = await self._client.run_query(cypher)
        return [row["agent"] for row in rows]

    async def blast_radius(self, tool_name: str) -> BlastRadiusResult:
        """Bonus: given a compromised tool, which agents and users are affected
        (and which data sources are exposed through it)?"""
        cypher = (
            "MATCH (t:Tool {name: $name}) "
            "OPTIONAL MATCH (t)<-[:HAS_TOOL]-(a:Agent) "
            "OPTIONAL MATCH (a)<-[:OWNS|USES]-(u:User) "
            "OPTIONAL MATCH (t)-[:READS_FROM]->(d:DataSource) "
            "RETURN t{.*} AS tool, "
            "       [x IN collect(DISTINCT a{.*}) WHERE x IS NOT NULL] AS agents, "
            "       [x IN collect(DISTINCT u{.*}) WHERE x IS NOT NULL] AS users, "
            "       [x IN collect(DISTINCT d{.*}) WHERE x IS NOT NULL] AS data_sources"
        )
        rows = await self._client.run_query(cypher, {"name": tool_name})
        if not rows:
            return BlastRadiusResult(tool=None)
        row = rows[0]
        return BlastRadiusResult(
            tool=row["tool"],
            affected_agents=row["agents"],
            affected_users=row["users"],
            exposed_data_sources=row["data_sources"],
        )

    async def full_graph(self) -> GraphSnapshot:
        """Return the full node/edge set for visualization."""
        node_rows = await self._client.run_query(
            "MATCH (n) RETURN labels(n)[0] AS label, n{.*} AS props ORDER BY label, props.name"
        )
        edge_rows = await self._client.run_query(
            "MATCH (s)-[r]->(t) RETURN s.id AS source, t.id AS target, type(r) AS type"
        )
        nodes = [
            GraphNodeView(id=row["props"]["id"], label=row["label"], properties=row["props"])
            for row in node_rows
        ]
        edges = [
            GraphEdgeView(source=row["source"], target=row["target"], type=row["type"])
            for row in edge_rows
        ]
        return GraphSnapshot(nodes=nodes, edges=edges)

    # --- Dynamic / dashboard queries ---------------------------------------

    async def stats(self) -> dict[str, Any]:
        """Aggregate counts for a dashboard: nodes per label, edges, orphans, drift."""
        label_rows = await self._client.run_query(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY label"
        )
        nodes = {row["label"]: row["count"] for row in label_rows}
        edge_rows = await self._client.run_query("MATCH ()-[r]->() RETURN count(r) AS c")
        orphan_rows = await self._client.run_query(
            "MATCH (a:Agent) WHERE NOT EXISTS { (a)-[:GOVERNED_BY]->(:Policy) } RETURN count(a) AS c"
        )
        drift_rows = await self._client.run_query(
            "MATCH ()-[r]->() WHERE r.observed = true AND r.declared IS NULL RETURN count(r) AS c"
        )
        return {
            "nodes": nodes,
            "total_nodes": sum(nodes.values()),
            "total_edges": edge_rows[0]["c"] if edge_rows else 0,
            "orphan_agents": orphan_rows[0]["c"] if orphan_rows else 0,
            "drift_edges": drift_rows[0]["c"] if drift_rows else 0,
        }

    async def list_entities(
        self,
        label: NodeLabel,
        search: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List nodes of a given label, optionally filtered by a name substring.

        The label comes from the ``NodeLabel`` enum (never raw user input), so
        interpolating it into the statement is injection-safe.
        """
        cypher = (
            f"MATCH (n:`{label.value}`) "
            "WHERE $search IS NULL OR toLower(n.name) CONTAINS toLower($search) "
            "RETURN n{.*} AS n ORDER BY n.name LIMIT $limit"
        )
        rows = await self._client.run_query(cypher, {"search": search, "limit": limit})
        return [row["n"] for row in rows]

    async def neighbors(self, name: str, depth: int = 1) -> GraphSnapshot:
        """Return the subgraph within ``depth`` hops of a named node.

        Powers interactive "expand node" exploration in the UI. ``depth`` is a
        validated integer interpolated into the variable-length pattern.
        """
        depth = max(1, min(depth, 4))
        cypher = (
            "MATCH (start {name: $name}) "
            f"MATCH (start)-[*0..{depth}]-(n) "
            "WITH collect(DISTINCT n) AS ns "
            "CALL { WITH ns UNWIND ns AS a MATCH (a)-[r]->(b) WHERE b IN ns "
            "RETURN collect(DISTINCT {source: a.id, target: b.id, type: type(r)}) AS edges } "
            "RETURN [x IN ns | {id: x.id, label: head(labels(x)), props: x{.*}}] AS nodes, edges"
        )
        rows = await self._client.run_query(cypher, {"name": name})
        if not rows:
            return GraphSnapshot()
        row = rows[0]
        nodes = [
            GraphNodeView(id=n["id"], label=n["label"], properties=n["props"]) for n in row["nodes"]
        ]
        edges = [
            GraphEdgeView(source=e["source"], target=e["target"], type=e["type"]) for e in row["edges"]
        ]
        return GraphSnapshot(nodes=nodes, edges=edges)

    async def drift(self) -> list[dict[str, Any]]:
        """Governance drift: relationships observed at runtime but never declared."""
        cypher = (
            "MATCH (a:Agent)-[r]->(t) WHERE r.observed = true AND r.declared IS NULL "
            "RETURN a.name AS agent, type(r) AS relationship, labels(t)[0] AS target_label, "
            "       t.name AS target, r.observed_count AS observed_count, r.last_seen AS last_seen "
            "ORDER BY agent, target"
        )
        return await self._client.run_query(cypher)
