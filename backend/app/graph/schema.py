"""Graph schema management: uniqueness constraints and lookup indexes.

Constraints guarantee one node per ``id`` per label (making the loader's
``MERGE`` idempotent). Indexes on ``name`` keep the governance queries fast,
since they look entities up by their human-facing name.

All statements are idempotent (``IF NOT EXISTS``) so applying the schema on
every startup is safe.
"""

from __future__ import annotations

import logging

from app.graph.client import Neo4jClient
from app.models.nodes import NodeLabel

logger = logging.getLogger(__name__)


def _constraint_statements() -> list[str]:
    # Label values come from the NodeLabel enum (never user input), so
    # interpolating them into the statement is safe from injection.
    return [
        f"CREATE CONSTRAINT {label.name.lower()}_id_unique IF NOT EXISTS "
        f"FOR (n:`{label.value}`) REQUIRE n.id IS UNIQUE"
        for label in NodeLabel
    ]


def _index_statements() -> list[str]:
    return [
        f"CREATE INDEX {label.name.lower()}_name IF NOT EXISTS "
        f"FOR (n:`{label.value}`) ON (n.name)"
        for label in NodeLabel
    ]


async def apply_schema(client: Neo4jClient) -> None:
    """Create all constraints and indexes if they do not already exist."""
    statements = _constraint_statements() + _index_statements()
    for statement in statements:
        await client.run_query(statement)
    logger.info("Graph schema applied", extra={"statements": len(statements)})
