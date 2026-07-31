"""Natural-language -> Cypher support: schema grounding, prompt, and safety.

The graph ontology is fixed, so we hand the model a curated schema (more
reliable than runtime introspection) and force it to return whole
nodes/relationships so the result is a renderable subgraph.

SECURITY: an LLM (or a prompt-injected question) can emit destructive or admin
Cypher. ``ensure_read_only`` is the gate that every generated statement must
pass before it touches the database. It is defense-in-depth alongside running
the statement inside a READ transaction (see ``Neo4jClient.run_read_graph``).
"""

from __future__ import annotations

import re

# Curated schema handed to the model for grounding.
GRAPH_SCHEMA = """
Node labels (every node has properties: id, name):
  User, Agent, Model, Tool, DataSource, Policy

Relationships (direction is significant):
  (User)-[:OWNS]->(Agent)
  (User)-[:USES]->(Agent)
  (Agent)-[:HAS_TOOL]->(Tool)
  (Agent)-[:USES_MODEL]->(Model)
  (Agent)-[:ACCESSES]->(DataSource)
  (Tool)-[:READS_FROM]->(DataSource)
  (Agent)-[:GOVERNED_BY]->(Policy)
  (Policy)-[:APPLIES_TO]->(Tool)   // also to DataSource or Model

Notes:
  - Match nodes by their `name` property (case-sensitive).
  - Runtime-observed (drift) edges carry properties observed=true, declared=null.
  - An "orphan" agent has no outgoing GOVERNED_BY relationship.
""".strip()

CYPHER_SYSTEM_PROMPT = (
    "You translate a user's question into ONE read-only Cypher query for the "
    "governance graph described below. Rules:\n"
    "1. Return ONLY a JSON object: {\"cypher\": string, \"explanation\": string}.\n"
    "2. The query MUST be read-only: never use CREATE, MERGE, SET, DELETE, "
    "REMOVE, DROP, LOAD CSV, FOREACH, or CALL to db./dbms./apoc procedures.\n"
    "3. RETURN whole nodes and relationships (e.g. `RETURN a, r, t`) so the "
    "result forms a subgraph, not scalar columns.\n"
    "4. Use only the labels, properties, and relationship types in the schema.\n"
    "5. Add a sensible LIMIT (<= 200).\n\n"
    "Schema:\n" + GRAPH_SCHEMA
)


def build_cypher_messages(question: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for Cypher generation."""
    return CYPHER_SYSTEM_PROMPT, f"Question: {question.strip()}"


# --- Safety gate -------------------------------------------------------------

# Write / admin constructs that must never reach the database.
_FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH|"
    r"CREATE\s+CONSTRAINT|CREATE\s+INDEX)\b|CALL\s+(db|dbms|apoc)\.",
    re.IGNORECASE,
)
# A read query must begin with one of these clauses.
_READ_START = re.compile(r"^\s*(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|RETURN|CALL\s*\{)", re.IGNORECASE)
_FENCE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")


class UnsafeCypherError(ValueError):
    """Raised when a generated statement fails the read-only safety check."""


def ensure_read_only(cypher: str) -> str:
    """Validate and normalize a generated statement; raise if it is not safe.

    Returns the cleaned statement (fences stripped, trailing ``;`` removed, a
    ``LIMIT`` appended when absent). Raises :class:`UnsafeCypherError` otherwise.
    """
    stmt = _FENCE.sub("", (cypher or "").strip()).strip().rstrip(";").strip()

    if not stmt:
        raise UnsafeCypherError("Empty query.")
    if ";" in stmt:
        raise UnsafeCypherError("Only a single statement is allowed.")
    if _FORBIDDEN.search(stmt):
        raise UnsafeCypherError("Only read-only queries are allowed (no writes or admin calls).")
    if not _READ_START.match(stmt):
        raise UnsafeCypherError("Query must start with MATCH / OPTIONAL MATCH / WITH / UNWIND / RETURN.")
    if not re.search(r"\bLIMIT\b", stmt, re.IGNORECASE):
        stmt += "\nLIMIT 200"
    return stmt
