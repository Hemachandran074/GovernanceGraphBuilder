# Governance Graph Builder — Video Walkthrough Script

**Estimated runtime:** ~11–12 minutes (each scene is timed; trim the deep-dive scenes for a shorter cut).
**Tone:** calm, confident, explanatory. Short sentences. Let the visuals carry detail.
**Structure:** Part 1 is **high-level** (the problem, the big picture, a live demo). Part 2 is a **low-level** technical deep dive (data model, ingestion, queries, natural-language safety, deployment).

> Pronouns: written in a neutral "let's / here's" voice. Swap to "I built…" if you're presenting your own work.

### Before you record — setup checklist
- Open the live app: `http://ggb-prod-alb-287388877.us-east-1.elb.amazonaws.com` and seed the **complex** bundle so the graph is populated.
- Have these files open in the editor for cutaways: `backend/app/graph/queries.py`, `backend/app/ingestion/pipeline.py`, `backend/app/llm/cypher.py`, `test-files/`, `infra/terraform/ecs.tf`.
- Have the README architecture diagrams ready to screen-share.
- Optional: a terminal with `uv run python scripts/validate.py` ready to run against the deployed URL.

---

## PART 1 — HIGH LEVEL

### Scene 1 — Hook  (0:00–0:30)  ·  *High-level*

**On screen:** The live app with a populated graph slowly rotating/settling. Title card: "Governance Graph Builder."

**Narration:**
> "Modern AI agents aren't one thing — they're a composition. A model, a set of tools, the data they can reach, the people who own them, and the policies that are supposed to govern them. The problem is: all of that lives in different systems. So when something goes wrong, nobody can answer a simple question — what was actually connected to what? This project answers that question. It turns an agent's entire composition into a single graph you can query, visualize, and audit."

---

### Scene 2 — The problem, concretely  (0:30–1:30)  ·  *High-level*

**On screen:** Simple motion graphic or slide: scattered boxes labeled "Model Registry," "Tool docs," "Data Catalogue," "Policy doc (Word file)" — disconnected. Then they collapse into one connected graph.

**Narration:**
> "Picture an incident. A tool your agents use just got compromised. Which agents had access to it? Which users are affected? What sensitive data could it reach? Today, answering that means chasing facts across a model registry, some undocumented tooling, a data catalogue, and a policy doc someone wrote months ago. There's no single source of truth. The Governance Graph Builder fixes that by unifying those facts into one graph — and because it's a graph, questions like 'blast radius of a compromised tool' become a single traversal."

---

### Scene 3 — The big picture  (1:30–2:45)  ·  *High-level*

**On screen:** The README graph-data-model diagram (six node types with typed edges). Then cut to the live UI, hovering over nodes of different colors.

**Narration:**
> "Here's the core idea. Six types of nodes: Users, Agents, Models, Tools, Data Sources, and Policies. And the edges between them capture the real relationships — an agent uses a model, has tools, accesses data, and is governed by a policy; a tool reads from a data source; a user owns or uses an agent. Once those facts are in a graph, governance becomes queryable. Which agents use this model? Which can reach this database — directly or through a tool? Is there an agent with no policy at all? Every one of those is just a path through the graph."

**Callout (lower third):** `User · Agent · Model · Tool · DataSource · Policy`

---

### Scene 4 — Live demo: from raw files to a graph  (2:45–4:30)  ·  *High-level*

**On screen:** The UI's Ingest panel. Upload `test-files/agent-config.json` (reset on), then `runtime-logs.txt`, then `policy.md`. The graph grows after each step. Then click a node to highlight its neighborhood.

**Narration:**
> "Let's build one live. I'll start with an agent configuration — this is the declared structure: which agents exist, their models, tools, and data. The graph appears. Next, runtime logs — what the agents actually did when they ran. Watch the graph light up with observed activity. And finally, a policy document written in plain English. Notice I didn't write any code to parse that — an LLM reads the document and extracts structured policies, which attach to the right agents and resources automatically. In under a minute, three completely different inputs became one connected, governed graph."

**Callout:** "Three sources → one graph: config (declared) + logs (observed) + policy (LLM-parsed)."

---

## PART 2 — LOW LEVEL (technical deep dive)

### Scene 5 — The data model and the one idea that makes it work  (4:30–6:00)  ·  *Low-level*

**On screen:** Editor showing a node/edge model file, then a Neo4j-style Cypher snippet. Highlight the `declared` and `observed` properties on a relationship.

**Narration:**
> "Now the technical core. Everything is stored in Neo4j. Each node has a stable `id` as its merge key and a human-friendly `name` that queries look up. The interesting design decision is on the *edges*. Every relationship carries two flags: `declared` — meaning it came from a config, the intended design — and `observed` — meaning it was actually seen in the runtime logs. That single distinction is powerful. An edge that's observed but never declared is *drift* — the agent did something it was never configured to do. And data access is evaluated two ways: directly, when an agent accesses a data source, and transitively, when it reaches data *through* a tool. So 'who can touch this database' catches the indirect paths too."

**On-screen Cypher to show:**
```cypher
// transitive data access
MATCH (a:Agent)-[:HAS_TOOL]->(:Tool)-[:READS_FROM]->(d:DataSource {name: $name})
RETURN a
```

---

### Scene 6 — Ingestion internals  (6:00–7:45)  ·  *Low-level*

**On screen:** Split view of the three input files (`agent-config.json`, `runtime-logs.txt`, `policy.md`) next to `pipeline.py`. Then show the LLM provider abstraction file briefly.

**Narration:**
> "Ingestion normalizes three very different formats into that same node-and-edge model. The agent config — YAML or JSON — is the authoritative structural source; its edges are tagged `declared`. The runtime logs are JSON lines — model invocations, tool calls, data reads — and they add `observed` metadata like occurrence counts. The policy document is the interesting one: it's unstructured English, so it goes through an LLM that extracts structured policies — the type, the rules, which agents they govern, and which resources they apply to — and those are grounded against the entities already in the graph. Loading is idempotent — everything uses `MERGE` — so re-ingesting the same data updates in place instead of duplicating."

**Narration (continued — the update criterion):**
> "And when a config *changes*, the graph reconciles. Stale edges are removed — but if an edge is still being observed at runtime, it's downgraded to drift rather than silently deleted. So you never lose the signal that reality and intent disagree."

**Callout:** "MERGE = idempotent · changed config → reconcile, don't duplicate."

---

### Scene 7 — The governance queries  (7:45–9:15)  ·  *Low-level*

**On screen:** `queries.py` with the actual Cypher. Then the UI Query panel: run "tools for an agent," "agents using a model," "orphan agents," and finally "blast radius" — each highlighting its subgraph.

**Narration:**
> "The queries are where the graph earns its keep. The four required ones — the tools an agent can reach, the agents using a given model, the agents that can access a data source, and the agents with no policy attached — are each a short, parameterized Cypher statement. Parameterized matters: it's injection-safe by construction. The orphan query is a simple negative pattern — agents with no outgoing `GOVERNED_BY` edge. And the bonus, blast radius, is the incident-response query: give it a compromised tool, and it walks outward to every agent that has it, every user of those agents, and every data source they can reach — the full set of potentially affected entities, in one traversal."

**On-screen Cypher to show:**
```cypher
// orphan agents — no governing policy
MATCH (a:Agent)
WHERE NOT (a)-[:GOVERNED_BY]->(:Policy)
RETURN a
```

---

### Scene 8 — Natural-language querying, safely  (9:15–10:45)  ·  *Low-level*

**On screen:** The UI's "Ask AI" box. Type: *"Which agents can access the ledger database?"* Show the returned subgraph, the generated Cypher, and the explanation. Then cut to `cypher.py` and highlight the `ensure_read_only` validator.

**Narration:**
> "Here's a feature I'm proud of. You can ask a question in plain English, and the app answers with a subgraph. Under the hood, the LLM translates your question into a Cypher query — but letting a model write queries against your database is genuinely dangerous, so the pipeline is safety-first. Step one: generate the Cypher, grounded by the fixed graph schema. Step two: validate it — a read-only gate rejects anything that isn't a single read statement. No CREATE, MERGE, DELETE, SET, no admin procedures, no stacked statements. Step three: even after that, it runs inside a read-only transaction — so if a write somehow slipped through, the database itself refuses it. That's defense in depth. And the response always shows you the exact Cypher that ran, so nothing is a black box. Try to prompt-inject a 'delete everything' and it's simply rejected."

**Callout:** "Generate → validate (read-only) → read transaction → subgraph. The query is always shown."

---

### Scene 9 — Production and deployment  (10:45–12:15)  ·  *Low-level*

**On screen:** The README deployment diagram. Then the live URL in the browser (working). Then `infra/terraform/ecs.tf` scrolling. Optionally the AWS console showing the ECS service running.

**Narration:**
> "This isn't running on my laptop — it's deployed on AWS, and the whole stack is Terraform. The backend is async FastAPI, served by Gunicorn with multiple Uvicorn workers, running on ECS Fargate behind a load balancer. A single container serves both the API and the compiled React UI, so they share one origin — no CORS, one thing to operate. The graph lives in managed Neo4j Aura, so state survives restarts and scaling. Secrets — the database credentials and the LLM key — come from AWS Secrets Manager through a least-privilege role, never from the code or the image. There are liveness and readiness health checks wired to the load balancer, structured JSON logs with a request id on every line for CloudWatch, and CPU-based autoscaling. And the LLM is pluggable — a generic OpenAI-compatible provider in the deployment, with Bedrock, OpenAI, and Anthropic supported, and a deterministic offline fallback so the system is never hard-blocked on an external dependency."

**Callout:** "ECS Fargate + ALB · Neo4j Aura · Secrets Manager · CloudWatch · Terraform · autoscaling."

---

### Scene 10 — Proof it works  (12:15–13:00)  ·  *Low-level*

**On screen:** Terminal running `uv run python scripts/validate.py` against the deployed URL; the checks scroll and end with all passing.

**Narration:**
> "Finally — does it actually meet the requirements? There's an automated validation suite that ingests three bundles of increasing complexity and asserts every query result — including that the orphan query flags exactly the one policy-free agent, and that the graph reconciles correctly when a config changes. I run it against the live deployment, and all the checks pass. That's the success criteria, verified end to end against the real system."

---

### Scene 11 — Outro  (13:00–13:30)  ·  *High-level*

**On screen:** Back to the full graph in the live app. Title card with the URL and repo.

**Narration:**
> "So that's the Governance Graph Builder: three messy sources unified into one graph, the governance questions answered as traversals, a natural-language layer that's safe by construction, and a real production deployment on AWS. It takes the question 'what is this agent actually connected to?' and makes it something you can just ask. Thanks for watching."

**Callout:** `Live: http://ggb-prod-alb-287388877.us-east-1.elb.amazonaws.com`

---

## Appendix A — 3-minute short cut

For a quick version, use only: **Scene 1** (hook) → **Scene 3** (big picture) → **Scene 4** (live ingest demo) → **Scene 8** (Ask AI) → **Scene 9** (deployed on AWS, briefly) → **Scene 11** (outro).

## Appendix B — Suggested on-screen lower-thirds / captions

- Scene 3: `6 node types · typed relationships`
- Scene 5: `declared vs observed → drift`
- Scene 6: `config + logs + policy → one graph`
- Scene 7: `parameterized Cypher · injection-safe`
- Scene 8: `read-only by construction`
- Scene 9: `deployed on AWS · Terraform`
- Scene 10: `success criteria: verified`

## Appendix C — One-sentence elevator pitch (for the video description)

> The Governance Graph Builder unifies an AI agent's full composition — model, tools, data, users, and policies — into a single Neo4j graph you can query, visualize, and ask in plain English, deployed production-ready on AWS.
