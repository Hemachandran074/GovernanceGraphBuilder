"""Deterministic, offline policy extractor.

Parses Markdown policy documents structurally (headers, ``Policy ID:``/``Type:``
metadata, and bullet rules) and grounds ``governs`` / ``applies_to`` references
by matching known agent and entity names that appear in each policy section.

This provider is always available and requires no credentials, so the system
degrades gracefully when no real LLM is configured. It is also fully
deterministic, which makes it ideal for tests and reproducible demos.
"""

from __future__ import annotations

import re

from app.llm.provider import ExtractedPolicy, LLMProvider, PolicyExtraction

_HEADER_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_ID_RE = re.compile(r"Policy\s*ID\s*[:*]*\s*`?([A-Za-z0-9_\-]+)`?", re.IGNORECASE)
_TYPE_RE = re.compile(r"\bType\s*[:*]*\s*`?([A-Za-z0-9_\-]+)`?", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")


class HeuristicPolicyExtractor(LLMProvider):
    name = "heuristic"

    def is_available(self) -> bool:
        return True

    def extract_policies(
        self,
        document_text: str,
        *,
        known_agents: list[str] | None = None,
        known_entities: list[str] | None = None,
    ) -> PolicyExtraction:
        known_agents = known_agents or []
        known_entities = known_entities or []

        policies: list[ExtractedPolicy] = []
        for header, body in _split_sections(document_text):
            id_match = _ID_RE.search(body)
            if not id_match:
                # A section without a policy id is treated as a title/preamble.
                continue

            type_match = _TYPE_RE.search(body)
            rules = [m.group(1).strip() for line in body.splitlines() if (m := _BULLET_RE.match(line))]

            policies.append(
                ExtractedPolicy(
                    id=id_match.group(1),
                    name=header,
                    type=type_match.group(1).lower() if type_match else None,
                    description=_first_prose_line(body),
                    rules=rules,
                    governs=_mentions(body, known_agents),
                    applies_to=_mentions(body, known_entities),
                )
            )

        return PolicyExtraction(policies=policies)


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Group document lines under their most recent Markdown header."""
    sections: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        header = _HEADER_RE.match(line)
        if header:
            sections.append((header.group(2).strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return [(name, "\n".join(lines)) for name, lines in sections]


def _mentions(body: str, names: list[str]) -> list[str]:
    """Return names that appear as whole words/phrases in the section body."""
    found = []
    for candidate in names:
        if re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", body):
            found.append(candidate)
    return found


def _first_prose_line(body: str) -> str | None:
    """First non-metadata, non-bullet, non-blank line, used as a description."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith((">", "-", "*", "#")):
            continue
        if _ID_RE.search(stripped) or re.match(r"^\**\s*Type\b", stripped, re.IGNORECASE):
            continue
        return re.sub(r"\*\*|`", "", stripped)
    return None
