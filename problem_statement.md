### The Governance Graph Builder

## Context
An agent is a composition: an LLM, an orchestration layer, a set of tools, a memory store, and data sources it can access. Today these components are tracked in separate systems — the LLM in a model registry, the tools undocumented, the data sources in a data catalogue. When something goes wrong, no one can reconstruct what was connected to what.

## The Challenge
Build a governance graph that represents agents, models, tools, users, and policies as connected nodes — making the full composition of any agent queryable in one place.

## What to Build
* **A graph data model** with node types: `User`, `Agent`, `Model`, `Tool`, `DataSource`, `Policy` (use Neo4j, NetworkX, or any graph library).
* **An ingestion layer** that builds the graph from three sources: an agent config file, runtime logs from a sample agent run, and a manually authored policy document.
* **Queries** that answer:
  * What tools does Agent X have access to?
  * Which agents are using Model Y?
  * Which agents can access DataSource Z?
  * Is there any agent with no policy attached?
* **A visual graph render** of the result.

## Success Criteria
* Given three sample agent configs of increasing complexity, the graph is correctly built and all queries return accurate results.
* The orphan agent query (agents with no policy) returns correct results when one agent is intentionally left policy-free.
* Graph updates correctly when an agent config changes.

## Bonus
* Add a **blast radius query**: given a compromised tool, which agents and users are potentially affected?