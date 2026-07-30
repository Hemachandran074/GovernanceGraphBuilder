"""Async Neo4j client wrapper.

Owns the driver lifecycle (one driver per process, with an internal connection
pool that is safe for concurrent requests) and exposes a lightweight
connectivity check used by the readiness probe.
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase, NotificationDisabledClassification

from app.config import Settings

logger = logging.getLogger(__name__)


class Neo4jClient:
    """Thin wrapper around the Neo4j async driver."""

    def __init__(self, settings: Settings) -> None:
        self._uri = settings.neo4j_uri
        self._auth = (settings.neo4j_user, settings.neo4j_password)
        self._database = settings.neo4j_database
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
