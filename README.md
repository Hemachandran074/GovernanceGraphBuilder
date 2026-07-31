# Governance Graph Builder

A governance graph that models **agents, models, tools, users, data sources, and policies** as connected nodes — making the full composition of any AI agent queryable, auditable, and visualizable in one place.

Modern AI agents are compositions: an LLM, an orchestration layer, a set of tools, a memory store, and the data sources they can reach. Those pieces usually live in separate systems — the model in a registry, the tools undocumented, the data in a catalogue. When something goes wrong, no one can reconstruct what was connected to what. This project unifies those facts into a single graph and answers governance questions over it.

---

## Table of Contents

- [Highlights](#highlights)
- [Architecture](#architecture)
- [Graph Data Model](#graph-data-model)
- [Tech Stack](#tech-stack)
- [Repository Layout](#repository-layout)
- [Getting Started](#getting-started)
- [Sample Data](#sample-data)
- [Governance Queries](#governance-queries)
- [Natural-Language Queries](#natural-language-queries)
- [API Reference](#api-reference)
- [Ingestion Model](#ingestion-model)
- [LLM Integration](#llm-integration)
- [Configuration](#configuration)
- [Production Readiness](#production-readiness)
- [Deployment (AWS)](#deployment-aws)
- [Success Criteria](#success-criteria)

---

## Highlights

- **Unified graph** of six governance entity types with typed relationships, backed by Neo4j.
- **Three-source ingestion** — declarative agent configs (YAML/JSON), runtime logs (JSONL), and natural-language policy documents parsed by a real LLM.
- **Governance queries** answering "what can this agent reach?", "who uses this model?", "which agents touch this data source (directly *or* transitively)?", and "which agents have no policy?".
- **Blast-radius analysis** — given a compromised tool, find every affected agent, user, and exposed data source.
- **Config/runtime drift detection** — relationships observed at runtime but never declared in config are surfaced automatically.
- **Correct updates** — re-ingesting a changed agent config reconciles the graph, removing stale edges (and downgrading still-observed ones to drift rather than deleting them).
- **Interactive visualization** — a React + Cytoscape UI that renders the graph, highlights query results, and drives ingestion.
- **Natural-language queries** — ask a question in plain English; an LLM generates a *read-only* Cypher statement (statically validated and executed inside a read transaction) and the matching subgraph is rendered.
- **Production-ready** — async API with structured logging, health/readiness probes, global error handling, autoscaling-ready containers, and full Terraform for AWS.

---

## Architecture

```mermaid
flowchart LR
    A1[Agent Config] --> ING[Ingestion Pipeline]
    A2[Runtime Logs] --> ING
    A3[Policy Document] --> LLM[LLM Provider]
    LLM --> ING
    ING --> NEO[(Neo4j Graph)]
    API[FastAPI: query + graph API] --> NEO
    UI[React + Cytoscape UI] -->|REST| API
```

The React UI calls the FastAPI service over REST. The API runs parameterized Cypher against Neo4j. Ingestion normalizes each of the three sources into the same node/edge model; the natural-language policy document is parsed by an LLM into structured policies before it reaches the graph. The same LLM provider also powers natural-language queries, translating a question into a validated read-only Cypher statement (see [Natural-Language Queries](#natural-language-queries)).

---

## Graph Data Model

**Node types:** `User`, `Agent`, `Model`, `Tool`, `DataSource`, `Policy`.

```mermaid
graph LR
    U[User] -->|OWNS / USES| A[Agent]
    A -->|USES_MODEL| M[Model]
    A -->|HAS_TOOL| T[Tool]
    A -->|ACCESSES| D[DataSource]
    A -->|GOVERNED_BY| P[Policy]
    T -->|READS_FROM| D
    P -->|APPLIES_TO| T
```

Two properties on relationships make governance analysis possible:

- **`declared`** — the edge came from an agent config (the intended composition).
- **`observed`** — the edge was seen in runtime logs (what actually happened).

An edge that is `observed` but not `declared` is **drift**. Data-source access is evaluated both **directly** (`Agent-[:ACCESSES]->DataSource`) and **transitively** (`Agent-[:HAS_TOOL]->Tool-[:READS_FROM]->DataSource`).

`id` is the stable merge key for every node; `name` is the human-facing identifier the queries look entities up by. Uniqueness constraints and name indexes are applied automatically at startup.

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Graph database | Neo4j (Neo4j 5.x locally via Docker; Neo4j Aura in the cloud) |
| Backend | Python 3.12, FastAPI, async Neo4j driver, managed with `uv` |
| App server | Gunicorn + Uvicorn workers (concurrent) |
| LLM | Generic OpenAI-compatible provider (natural-language → Cypher + policy parsing); AWS Bedrock / OpenAI / Anthropic optional; deterministic heuristic fallback |
| Frontend | React 19 + TypeScript + Vite, Cytoscape for graph rendering |
| Containers | Docker — unified image (React SPA built and served by FastAPI) |
| Infrastructure | Terraform — ECR, VPC, ECS Fargate + ALB, Secrets Manager, IAM, CloudWatch |

---

## Repository Layout

```
Governance Graph Builder/
├── backend/                  FastAPI service (Python, uv)
│   ├── app/
│   │   ├── main.py           App factory: lifespan, middleware, error handling
│   │   ├── config.py         Environment-based settings
│   │   ├── logging_config.py Structured JSON logging + request ids
│   │   ├── api/              health, ingest, query, graph routers + schemas
│   │   ├── graph/            Neo4j client, schema, loader (+ reconciliation), queries, seed
│   │   ├── ingestion/        agent_config, runtime_logs, policy_doc, pipeline
│   │   ├── llm/              provider abstraction, generic OpenAI-compatible `llm` provider, bedrock/openai/anthropic, heuristic, and NL→Cypher (schema + read-only safety)
│   │   └── models/           Pydantic node/edge/graph models
│   ├── samples/{simple,medium,complex}/   agent_config.yaml + runtime_logs.jsonl + policy.md
│   └── Dockerfile
├── frontend/                 React + Vite + TypeScript UI
│   └── src/{api,components}/  typed client + GraphView / QueryPanel / NlQueryPanel / IngestPanel / StatsBar
├── infra/
│   ├── docker-compose.yml    local Neo4j + backend
│   └── terraform/            AWS infrastructure as code (+ its own README)
├── test-files/               ready-to-upload sample files (json / yaml / md / txt)
├── plan.md                   engineering plan
├── tasks.md                  phased task tracker
└── problem_statement.md
```

---

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python 3.12)
- Node.js 20.19+ or 22.12+
- Docker (for Neo4j locally)

### 1. Start Neo4j and the backend

From the repository root:

```bash
# Start Neo4j
docker compose -f infra/docker-compose.yml up -d neo4j

# Run the API
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

A `.env` is optional locally — defaults match the Docker Neo4j. Interactive API docs are at **http://localhost:8000/docs**; liveness at `/health`, readiness at `/ready`.

Alternatively, run the whole stack (Neo4j + backend) in containers:

```bash
docker compose -f infra/docker-compose.yml up --build
```

### 2. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open the printed URL (default **http://localhost:5173**). The backend already allows this origin via CORS.

### 3. Load data and explore

Ingest a sample bundle from the UI's **Ingest** panel, or via the API:

```bash
curl -X POST http://localhost:8000/ingest/bundle \
  -H "Content-Type: application/json" \
  -d '{"bundle":"complex","reset":true}'
```

Then run the governance queries from the **Query** panel and watch the matching subgraph highlight.

---

## Sample Data

Three bundles of increasing complexity live in `backend/samples/`. Each contains an agent config, a runtime log, and a policy document.

| Bundle | What it exercises |
|--------|-------------------|
| `simple` | One of each node type; all queries; no orphan |
| `medium` | Multiple agents, a shared model, one policy governing two agents, and **one intentionally policy-free (orphan) agent** |
| `complex` | Transitive data access, overlapping policies (an agent with two policies), a non-owning user, an orphan agent, and **config/runtime drift** (a tool invoked at runtime but never declared) |

### Upload fixtures

`test-files/` holds four ready-to-upload files — one per format — that form one coherent scenario for exercising the **Ingest** panel (or the `/ingest/upload` API):

| File | Upload as `kind` | Format |
|------|------------------|--------|
| `agent-config.json` | `agent-config` | JSON |
| `agent-config.yaml` | `agent-config` | YAML (single-agent form) |
| `runtime-logs.txt` | `runtime-logs` | JSONL |
| `policy.md` | `policy` | Markdown |

Upload the JSON with **reset** on, then the others, to build a graph with a shared model, transitive data access, an orphan agent, and runtime drift.

---

## Governance Queries

The four required queries (from the problem statement), plus the bonus and extras, are all exposed over HTTP and in the UI:

| Question | Endpoint |
|----------|----------|
| What tools does Agent X have access to? | `GET /agents/{name}/tools` |
| Which agents are using Model Y? | `GET /models/{name}/agents` |
| Which agents can access DataSource Z? (direct + transitive) | `GET /datasources/{name}/agents` |
| Is there any agent with no policy attached? | `GET /agents/orphans` |
| **Blast radius:** which agents/users/data are affected by a compromised tool? | `GET /tools/{name}/blast-radius` |
| Where does runtime usage diverge from declared config? | `GET /graph/drift` |
| **Ask in natural language** (LLM → read-only Cypher → subgraph) | `POST /graph/nl-query` |

---

## Natural-Language Queries

Beyond the fixed governance queries, the UI includes an **Ask AI** box: type a question in plain English and the matching subgraph is rendered. The pipeline is deliberately safety-first:

1. **Generate** — the configured LLM turns the question into a single Cypher statement, grounded by the fixed graph schema and instructed to return whole nodes and relationships.
2. **Validate** — `ensure_read_only` rejects anything that is not a single read statement (no `CREATE` / `MERGE` / `DELETE` / `SET` / `REMOVE` / `DROP`, no `LOAD CSV`, no `db.` / `dbms.` / `apoc.` procedure calls, no stacked statements) and appends a `LIMIT`.
3. **Execute** — the statement runs inside a **read transaction**, so any write that slips past validation is refused by the database itself (defense in depth). Relationships among the returned nodes are backfilled so the subgraph renders connected.
4. **Return** — the response carries the executed Cypher (for transparency), a short explanation, the provider used, and the subgraph.

This requires a generative provider (`LLM_PROVIDER=llm` with an API key); the offline heuristic cannot author Cypher, so the endpoint responds `503` in that case.

```bash
curl -X POST http://localhost:8000/graph/nl-query \
  -H "Content-Type: application/json" \
  -d '{"question":"Which agents can access the ledger database?"}'
```

---

## API Reference

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness probe |
| GET | `/ready` | Readiness probe (checks Neo4j) |
| POST | `/ingest/agent-config` | Ingest an agent config (raw text or object) |
| POST | `/ingest/runtime-logs` | Ingest runtime logs (JSONL or records) |
| POST | `/ingest/policy` | Ingest a policy document (LLM-parsed) |
| POST | `/ingest/bundle` | Ingest a full sample bundle |
| POST | `/ingest/upload` | Ingest any source from an uploaded file |
| GET | `/ingest/bundles` | List available sample bundles |
| GET | `/graph` | Full node/edge snapshot for visualization |
| DELETE | `/graph` | Reset the graph |
| GET | `/graph/stats` | Node/edge counts, orphan/drift counts, active LLM provider |
| GET | `/graph/entities/{label}` | List entities of a type (search + limit) |
| GET | `/graph/neighbors/{name}` | Subgraph around a node |
| GET | `/graph/drift` | Observed-but-undeclared relationships |
| POST | `/graph/nl-query` | Natural-language question → LLM-generated read-only Cypher → matching subgraph |

Full interactive documentation (OpenAPI/Swagger) is served at `/docs`.

---

## Ingestion Model

The graph is built from three heterogeneous sources, each normalized into the same node/edge model:

1. **Agent config (YAML/JSON)** — the authoritative *structural* source. Declares each agent with its owner/users, model, tools, direct data-source access, tool→data-source reads, and governing policies. Supports a single agent or a fleet via a top-level `agents:` list. Edges are tagged `declared`.

2. **Runtime logs (JSONL)** — observed usage from a sample agent run (`model_invoke`, `tool_call`, `data_read`). Adds `observed` metadata (occurrence counts, `last_seen`) and surfaces **drift** when logs reference entities the config never declared.

3. **Policy document (Markdown/text)** — a manually authored, natural-language document. An **LLM** extracts structured policies (type, rules, which agents they govern, which entities they apply to), which are grounded against the existing graph and written as enriched `Policy` nodes plus `GOVERNED_BY` and `APPLIES_TO` edges.

Loading is idempotent (`MERGE`), so re-ingestion updates in place. Re-ingesting a **changed** agent config reconciles its declared edges to match the new config: stale edges are removed, and an edge that is still observed at runtime (or asserted by a policy document) is downgraded to drift rather than deleted.

---

## LLM Integration

Two capabilities use an LLM — **policy-document parsing** (natural language → structured policies) and **natural-language queries** (question → read-only Cypher). Both go through a single provider abstraction with graceful fallback:

- **Generic (`llm`)** — an OpenAI-compatible chat provider configured with `LLM_API_KEY` and `LLM_MODEL`. It powers natural-language → Cypher and policy extraction, and is the provider used in the deployed stack.
- **AWS Bedrock** (Claude via the Converse API) — credentials resolve from the standard AWS chain (environment, shared config, or the ECS task role in production), so no secrets live in code.
- **OpenAI / Anthropic** — optional direct providers (lazy-loaded SDKs).
- **Heuristic** — a deterministic, offline extractor that parses policy documents structurally and grounds references against the known graph vocabulary. Always available, so ingestion runs fully locally with no credentials. It cannot author Cypher, so natural-language queries require a generative provider.

The active provider is selected by `LLM_PROVIDER` (default `auto`: the first available real provider, otherwise the heuristic). Policy ingestion never hard-fails on an LLM error — it falls back to the heuristic and reports the fallback reason in the response. The current provider is reported at `GET /graph/stats`.

---

## Configuration

Backend settings come from environment variables (or a local `.env`; see `backend/.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Deployment environment |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `true` | Logging level and JSON output |
| `CORS_ORIGINS` | localhost dev origins | Comma-separated allowed origins |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URI |
| `NEO4J_USER` / `NEO4J_PASSWORD` | `neo4j` / `localdevpassword` | Neo4j credentials |
| `NEO4J_DATABASE` | `neo4j` | Neo4j database name |
| `LLM_PROVIDER` | `auto` | `auto` \| `llm` \| `bedrock` \| `openai` \| `anthropic` \| `heuristic` |
| `LLM_API_KEY` | unset | API key for the generic OpenAI-compatible provider (`llm`) |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Model id for the generic provider |
| `AWS_REGION` | `us-east-1` | Region for Bedrock |
| `BEDROCK_MODEL_ID` | Claude 3.5 Sonnet | Bedrock model / inference profile |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | unset | Optional direct-provider keys |

The frontend reads `VITE_API_BASE_URL` (default `http://localhost:8000`); see `frontend/.env.example`.

---

## Production Readiness

- **Concurrency** — async FastAPI served by Gunicorn with multiple Uvicorn workers; the Neo4j driver maintains a connection pool.
- **Persistence** — Neo4j (managed Aura in the cloud); no in-memory-only state.
- **Observability** — structured JSON logs with per-request correlation ids, ready for CloudWatch Logs Insights.
- **Health** — `/health` (liveness) and `/ready` (dependency readiness) wired to container and load-balancer checks.
- **Error handling** — global handlers return a consistent `{ "error": { "type", "message" } }` envelope with the correlation id.
- **Config & secrets** — 12-factor configuration; Neo4j credentials injected from AWS Secrets Manager in production.
- **Security** — least-privilege IAM task roles, private-subnet tasks behind an ALB, CORS lockdown, and injection-safe parameterized Cypher.

---

## Deployment (AWS)

The `infra/terraform/` directory provisions a production-shaped stack. The default
deployment is a **unified container**: one ECS service runs FastAPI, which also
serves the built React SPA — so the UI and API share a single origin and URL
(no CORS, no separate frontend host).

- **ECR** for the unified image
- **VPC** (public + private subnets, NAT)
- **ECS Fargate + ALB** serving both the UI and API, with CPU-based autoscaling
- **Secrets Manager** for Neo4j credentials **and the LLM API key**, **IAM** roles (execution + Bedrock task role), and **CloudWatch Logs**

The unified image is built from the repo root (`docker build -f backend/Dockerfile .`);
the frontend is compiled in a Node stage and served by FastAPI at `/`.

```mermaid
flowchart TB
    Dev[git push] --> IMG[Docker image] --> ECR[(ECR)]
    ECR --> ECS[ECS Fargate]
    ALB[Application Load Balancer] --> ECS
    ECS --> AURA[(Neo4j Aura)]
    ECS --> BR[AWS Bedrock]
    ECS --> SM[[Secrets Manager]]
```

The graph database is managed **Neo4j Aura**, provisioned separately and passed in as variables. Step-by-step deployment instructions (init, apply, image push, frontend sync) are in [`infra/terraform/README.md`](infra/terraform/README.md).

---

## Success Criteria

All requirements from the problem statement are implemented and verified against the three sample bundles:

- **Correct graph build + accurate queries** across the `simple`, `medium`, and `complex` configs.
- **Orphan-agent query** correctly flags the intentionally policy-free agent (and only it).
- **Correct updates** when an agent config changes — stale edges are reconciled away.
- **Bonus:** the **blast-radius query** returns the affected agents, users, and exposed data sources for a compromised tool.