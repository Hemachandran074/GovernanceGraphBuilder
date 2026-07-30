"""Ingestion pipeline: orchestrates parsing + loading for each source.

Provides small, composable entry points used by the API layer (Phase 4) and a
convenience ``ingest_bundle`` that loads a full sample bundle (agent config +
runtime logs) from disk. Policy-document parsing is added in Phase 3.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from app.graph.client import Neo4jClient
from app.graph.loader import load_document, load_observations, reconcile_declared_edges, reset_graph
from app.graph.schema import apply_schema
from app.ingestion.agent_config import (
    IngestionError,
    load_config_text,
    parse_agent_config,
)
from app.ingestion.policy_doc import ingest_policy_document
from app.ingestion.runtime_logs import parse_runtime_logs

logger = logging.getLogger(__name__)

# backend/app/ingestion/pipeline.py -> backend/
_BACKEND_DIR = Path(__file__).resolve().parents[2]
SAMPLES_DIR = _BACKEND_DIR / "samples"

_CONFIG_FILENAMES = ("agent_config.yaml", "agent_config.yml", "agent_config.json")
_LOGS_FILENAME = "runtime_logs.jsonl"
_POLICY_FILENAME = "policy.md"


async def ingest_agent_config(client: Neo4jClient, data: dict[str, Any]) -> dict[str, Any]:
    """Ingest an already-parsed agent-config dict.

    After loading, reconciles each agent's declared edges to the new config so a
    changed config (e.g. a removed tool or policy) drops its now-stale edges.
    """
    document = parse_agent_config(data)
    counts = await load_document(client, document)
    reconciliation = await reconcile_declared_edges(client, document)
    return {**counts, "reconciliation": reconciliation}


async def ingest_agent_config_text(client: Neo4jClient, text: str) -> dict[str, int]:
    """Ingest raw agent-config text (YAML or JSON)."""
    return await ingest_agent_config(client, load_config_text(text))


async def ingest_runtime_logs(client: Neo4jClient, lines: Iterable[str | dict[str, Any]]) -> dict[str, int]:
    """Ingest runtime log records (JSONL lines or dicts)."""
    document = parse_runtime_logs(lines)
    return await load_observations(client, document)


async def ingest_runtime_logs_text(client: Neo4jClient, text: str) -> dict[str, int]:
    """Ingest raw JSONL runtime-log text."""
    return await ingest_runtime_logs(client, text.splitlines())


def resolve_bundle_dir(bundle: str) -> Path:
    """Map a bundle name (or path) to its directory."""
    candidate = Path(bundle)
    if candidate.is_dir():
        return candidate
    resolved = SAMPLES_DIR / bundle
    if not resolved.is_dir():
        raise IngestionError(f"Sample bundle not found: {bundle}")
    return resolved


async def ingest_bundle(
    client: Neo4jClient,
    bundle: str,
    *,
    reset: bool = False,
    ensure_schema: bool = True,
) -> dict[str, Any]:
    """Ingest a full bundle directory (agent config + runtime logs).

    ``reset`` clears the graph first (useful when switching bundles). Policy
    document parsing is layered on in Phase 3.
    """
    bundle_dir = resolve_bundle_dir(bundle)

    if ensure_schema:
        await apply_schema(client)
    if reset:
        await reset_graph(client)

    result: dict[str, Any] = {"bundle": bundle_dir.name}

    config_path = next((bundle_dir / name for name in _CONFIG_FILENAMES if (bundle_dir / name).is_file()), None)
    if config_path is None:
        raise IngestionError(f"No agent config found in bundle: {bundle_dir}")
    result["agent_config"] = await ingest_agent_config_text(client, config_path.read_text(encoding="utf-8"))

    logs_path = bundle_dir / _LOGS_FILENAME
    if logs_path.is_file():
        result["runtime_logs"] = await ingest_runtime_logs_text(client, logs_path.read_text(encoding="utf-8"))

    # Policy document is ingested last so agents/entities exist for grounding.
    policy_path = bundle_dir / _POLICY_FILENAME
    if policy_path.is_file():
        result["policy_document"] = await ingest_policy_document(client, policy_path.read_text(encoding="utf-8"))

    logger.info("Ingested bundle", extra={"bundle": bundle_dir.name})
    return result
