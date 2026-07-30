"""Runtime log ingestion (Source B).

Parses JSONL runtime events from a sample agent run into *observed* usage.
Each recognized event contributes an edge tagged ``observed=True`` with an
occurrence count and a ``last_seen`` timestamp.

Reconciliation with the declared config happens naturally in the graph: when an
observed edge matches a declared one, the relationship carries both
``declared`` and ``observed`` markers. When a log references an entity that was
never declared (e.g. a tool used at runtime but absent from the config), the
observed-only edge surfaces **drift**.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.models.edges import Edge, RelType
from app.models.graph import GraphDocument
from app.models.nodes import (
    Agent,
    DataSource,
    Model,
    NodeLabel,
    Tool,
)

logger = logging.getLogger(__name__)

# event name -> (target label, relationship, id field, name field)
_EVENT_MAP: dict[str, tuple[NodeLabel, RelType, str, str]] = {
    "model_invoke": (NodeLabel.MODEL, RelType.USES_MODEL, "model", "model_name"),
    "tool_call": (NodeLabel.TOOL, RelType.HAS_TOOL, "tool", "tool_name"),
    "data_read": (NodeLabel.DATA_SOURCE, RelType.ACCESSES, "data_source", "data_source_name"),
    "data_write": (NodeLabel.DATA_SOURCE, RelType.ACCESSES, "data_source", "data_source_name"),
}


@dataclass
class _EdgeAgg:
    rel: RelType
    target_label: NodeLabel
    target_id: str
    agent_id: str
    count: int = 0
    last_seen: str | None = None


@dataclass
class _Accumulator:
    agents: dict[str, str] = field(default_factory=dict)  # id -> name
    targets: dict[tuple[str, str], str] = field(default_factory=dict)  # (label, id) -> name
    edges: dict[tuple[str, str, str], _EdgeAgg] = field(default_factory=dict)


def _iter_records(lines: Iterable[str | dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for raw in lines:
        if isinstance(raw, dict):
            yield raw
            continue
        line = raw.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed log line", extra={"error": str(exc)})


def parse_runtime_logs(lines: Iterable[str | dict[str, Any]]) -> GraphDocument:
    """Aggregate runtime events into an observed :class:`GraphDocument`."""
    acc = _Accumulator()

    for record in _iter_records(lines):
        agent_id = record.get("agent_id")
        event = record.get("event")
        if not agent_id or event not in _EVENT_MAP:
            continue

        acc.agents.setdefault(agent_id, record.get("agent_name", agent_id))

        label, rel, id_field, name_field = _EVENT_MAP[event]
        target_id = record.get(id_field)
        if not target_id:
            continue
        acc.targets.setdefault((label.value, target_id), record.get(name_field, target_id))

        key = (agent_id, rel.value, target_id)
        agg = acc.edges.get(key)
        if agg is None:
            agg = _EdgeAgg(rel=rel, target_label=label, target_id=target_id, agent_id=agent_id)
            acc.edges[key] = agg
        agg.count += 1
        ts = record.get("timestamp")
        if ts and (agg.last_seen is None or ts > agg.last_seen):
            agg.last_seen = ts

    return _build_document(acc)


def _build_document(acc: _Accumulator) -> GraphDocument:
    agents = [Agent(id=aid, name=name) for aid, name in acc.agents.items()]

    models: list[Model] = []
    tools: list[Tool] = []
    data_sources: list[DataSource] = []
    for (label, node_id), name in acc.targets.items():
        if label == NodeLabel.MODEL.value:
            models.append(Model(id=node_id, name=name))
        elif label == NodeLabel.TOOL.value:
            tools.append(Tool(id=node_id, name=name))
        elif label == NodeLabel.DATA_SOURCE.value:
            data_sources.append(DataSource(id=node_id, name=name))

    edges: list[Edge] = []
    for agg in acc.edges.values():
        edges.append(
            Edge(
                source_id=agg.agent_id,
                source_label=NodeLabel.AGENT,
                rel_type=agg.rel,
                target_id=agg.target_id,
                target_label=agg.target_label,
                properties={
                    "observed": True,
                    "observed_count": agg.count,
                    "last_seen": agg.last_seen,
                },
            )
        )

    return GraphDocument(
        agents=agents,
        models=models,
        tools=tools,
        data_sources=data_sources,
        edges=edges,
    )
