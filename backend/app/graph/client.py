"""Async Neo4j client wrapper.

Owns the driver lifecycle (one driver per process, with an internal connection
pool that is safe for concurrent requests) and exposes a lightweight
connectivity check used by the readiness probe.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, NotificationDisabledClassification
from neo4j.graph import Node, Path, Relationship

from app.config import Settings
from app.models.graph import GraphEdgeView, GraphNodeView, GraphSnapshot

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Thin wrapper around the Neo4j async driver."""

    def __init__(self, settings: Settings) -> None:
        self._uri = settings.neo4j_uri
        self._auth = (settings.neo4j_user, settings.neo4j_password)
        # An empty/blank database name means "use the server's home database".
        # This must be passed to the driver as None (not ""): on a routed
        # connection (neo4j+s:// / Aura) an empty string, or a name that does
        # not exist on the instance, fails routing with SessionExpired /
        # DatabaseNotFound even though verify_connectivity() still succeeds.
        # None lets the driver resolve the home database, which works on both
        # Aura and a local single-instance Neo4j.
        self._database = (settings.neo4j_database or "").strip() or None
        self._timeout = settings.neo4j_connection_timeout
        self._driver: AsyncDriver | None = None

    def connect(self) -> None:
        """Create the driver.

        Driver creation is lazy: it does not open a socket until first use, so
        the app boots even when the database is temporarily unreachable. Actual
        connectivity is validated by :meth:`verify_connectivity` (readiness).
        """
        if self._driver is not None:
            return
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=self._auth,
            connection_acquisition_timeout=self._timeout,
            # Our model intentionally uses relationship types (e.g. OWNS|USES)
            # and optional patterns that may have no instances in a given
            # dataset; suppress the benign "unrecognized type" notifications.
            notifications_disabled_classifications=[
                NotificationDisabledClassification.UNRECOGNIZED
            ],
        )
        logger.info("Neo4j driver created", extra={"neo4j_uri": self._uri, "database": self._database})

    async def close(self) -> None:
        """Close the driver and release pooled connections."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j driver closed")

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4j driver is not initialized; call connect() first.")
        return self._driver

    async def verify_connectivity(self) -> bool:
        """Return True when the database is reachable, False otherwise."""
        if self._driver is None:
            return False
        try:
            await self._driver.verify_connectivity()
            return True
        except Exception as exc:  # noqa: BLE001 - readiness must never raise
            logger.warning("Neo4j connectivity check failed", extra={"error": str(exc)})
            return False

    async def run_query(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher statement and return rows as dictionaries."""
        records, _summary, _keys = await self.driver.execute_query(
            cypher,
            parameters_=parameters or {},
            database_=self._database,
        )
        return [record.data() for record in records]

    async def run_read_graph(
        self,
        cypher: str,
        parameters: dict[str, Any] | None = None,
    ) -> GraphSnapshot:
        """Run a statement in a READ transaction and return it as a subgraph.

        Executing via :meth:`AsyncSession.execute_read` forces read access mode,
        so any write slipping past static validation is rejected by the server
        (defense in depth). Node/Relationship/Path values in the result are
        converted into the same :class:`GraphSnapshot` shape the UI already
        renders; scalar-only results yield an empty snapshot.
        """

        async def _work(tx):
            result = await tx.run(cypher, parameters or {})
            return [record async for record in result]

        async def _edges_among(tx, ids: list[str]):
            result = await tx.run(
                "MATCH (s)-[r]->(t) WHERE s.id IN $ids AND t.id IN $ids "
                "RETURN s.id AS source, t.id AS target, type(r) AS type",
                {"ids": ids},
            )
            return [record async for record in result]

        async with self.driver.session(database=self._database) as session:
            records = await session.execute_read(_work)
            snapshot = _records_to_snapshot(records)
            # Generated queries often RETURN only node variables (e.g. `RETURN a, m`),
            # which yields nodes but no edges. Backfill the relationships that exist
            # among the returned nodes so the subgraph renders connected.
            node_ids = [n.id for n in snapshot.nodes]
            if node_ids and not snapshot.edges:
                edge_rows = await session.execute_read(_edges_among, node_ids)
                snapshot.edges = [
                    GraphEdgeView(source=row["source"], target=row["target"], type=row["type"])
                    for row in edge_rows
                ]
        return snapshot


def _records_to_snapshot(records: list) -> GraphSnapshot:
    """Convert Neo4j result records into a GraphSnapshot.

    Walks every value in every record, collecting Nodes and Relationships
    (including those nested in lists, maps, or paths). Relationship endpoints
    are added as nodes too, so the returned subgraph is always self-contained.
    Nodes are keyed by their business ``id`` property when present, falling back
    to the driver's ``element_id``.
    """
    nodes: dict[str, GraphNodeView] = {}
    edges: list[GraphEdgeView] = []
    seen_edges: set[str] = set()

    def business_id(node: Node) -> str:
        return str(node.get("id") or node.element_id)

    def add_node(node: Node) -> None:
        bid = business_id(node)
        if bid in nodes:
            return
        props = dict(node)
        props.setdefault("id", bid)
        label = next(iter(node.labels), "Node")
        nodes[bid] = GraphNodeView(id=bid, label=label, properties=props)

    def add_rel(rel: Relationship) -> None:
        start, end = rel.start_node, rel.end_node
        if start is None or end is None:
            return
        add_node(start)
        add_node(end)
        src, tgt = business_id(start), business_id(end)
        key = f"{src}|{rel.type}|{tgt}|{rel.element_id}"
        if key in seen_edges:
            return
        seen_edges.add(key)
        edges.append(GraphEdgeView(source=src, target=tgt, type=rel.type))

    def walk(value: Any) -> None:
        if isinstance(value, Node):
            add_node(value)
        elif isinstance(value, Relationship):
            add_rel(value)
        elif isinstance(value, Path):
            for node in value.nodes:
                add_node(node)
            for rel in value.relationships:
                add_rel(rel)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    for record in records:
        for value in record.values():
            walk(value)

    return GraphSnapshot(nodes=list(nodes.values()), edges=edges)
