# Governance Graph Builder — Task Tracker

Task breakdown derived from [plan.md](./plan.md). Check items off as they land. Each phase has an **exit check** that must pass before the phase is considered done.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done

---

## Phase 0 — Foundations `[x]`
Goal: the service boots, health checks are green, and Neo4j is reachable.

- [x] 0.1 Add backend dependencies to `pyproject.toml` (fastapi, uvicorn, neo4j, pydantic-settings, gunicorn)
- [x] 0.2 `app/config.py` — env-based settings (Neo4j URI/creds, app env, log level)
- [x] 0.3 `.env.example` — documented environment variables
- [x] 0.4 `app/logging_config.py` — structured JSON logging with request IDs
- [x] 0.5 `app/graph/client.py` — Neo4j driver lifecycle + `verify_connectivity()`
- [x] 0.6 `app/api/health.py` — `/health` (liveness) and `/ready` (Neo4j readiness)
- [x] 0.7 `app/main.py` — FastAPI app, lifespan, CORS, global exception handlers, router wiring
- [x] 0.8 `backend/Dockerfile` — container image built with uv
- [x] 0.9 `infra/docker-compose.yml` — Neo4j + backend services
- [x] **Exit check:** verified locally (uv) and containerized (docker compose, gunicorn 2 workers):
  `/health`=200, `/ready`=503 when Neo4j down / 200 when up, `/docs` and `/openapi.json`=200

## Phase 1 — Graph core `[x]`
Goal: node/edge schema and all Cypher queries run against seeded data.

- [x] 1.1 `app/graph/schema.py` — uniqueness constraints + indexes for all node types
- [x] 1.2 `app/models/` — Pydantic schemas for User/Agent/Model/Tool/DataSource/Policy + edges
- [x] 1.3 `app/graph/loader.py` — idempotent `MERGE` loader (nodes + edges) + `reset_graph`
- [x] 1.4 `app/graph/queries.py` — parameterized Cypher for the 4 required queries + blast radius + full graph
- [x] 1.5 `app/graph/seed.py` — hand-authored seed (shared model, transitive access, orphan agent)
- [x] **Exit check:** all queries verified correct against seeded data — Q1 tools, Q2 shared model,
  Q3 direct + transitive data access, Q4 orphan agent, blast radius (agents/users/exposed data),
  idempotent re-load; 15 nodes / 17 edges

## Phase 2 — Ingestion + samples `[x]`
Goal: build the graph from the three sources; `simple` bundle works end to end.

- [x] 2.1 `app/ingestion/agent_config.py` — parse YAML/JSON agent config → nodes/edges (declared)
- [x] 2.2 `app/ingestion/runtime_logs.py` — parse JSONL runtime logs → observed usage + drift
- [x] 2.3 `app/ingestion/pipeline.py` + loader `load_observations` — normalize + idempotent `MERGE`
- [x] 2.4 `samples/simple/` — config + logs + policy doc (1 of each node type, no orphan)
- [x] 2.5 `samples/medium/` — 3 agents, shared model, **one policy-free agent** (Triage Bot)
- [x] 2.6 `samples/complex/` — transitive access, overlapping policies, log/config drift (shadow-export)
- [x] **Exit check:** all three bundles verified — Q1–Q4 accurate, orphan detected (medium/complex),
  direct + transitive data access, drift observed-not-declared, blast radius, idempotent re-ingest

## Phase 3 — LLM policy parsing `[x]`
Goal: policy document parsed by a real LLM into structured policies.

- [x] 3.1 `app/llm/provider.py` — provider abstraction + structured output schema + factory
- [x] 3.2 `app/llm/bedrock.py` — AWS Bedrock (Claude) implementation via Converse API
- [x] 3.3 `app/llm/` — OpenAI/Anthropic implementations (lazy, optional) + deterministic heuristic fallback
- [x] 3.4 `app/ingestion/policy_doc.py` — NL policy doc → structured policies → graph (grounded to vocabulary)
- [x] **Exit check:** verified — policy docs enrich Policy nodes (type/rules/description) and produce correct
  `APPLIES_TO` edges; isolation test proves the policy doc alone recreates `GOVERNED_BY`; orphan preserved

## Phase 4 — Full API `[x]`
Goal: all ingest/query endpoints live with OpenAPI docs and error handling.

- [x] 4.1 `app/api/ingest.py` — agent-config / runtime-logs / policy / bundle + generic `/upload` + `/bundles` discovery
- [x] 4.2 `app/api/query.py` — 4 required queries + blast radius; `app/api/graph.py` — `/graph`, reset, stats, entities, neighbors, drift
- [x] 4.3 Consistent error envelope (`IngestionError`→422, validation→422, 404s) + input validation; schema applied once at startup
- [x] **Exit check:** verified over HTTP — 24 checks incl. all queries, blast radius, stats/entities/neighbors/drift,
  error codes (404/422), reset; 19 OpenAPI paths at `/docs`

## Phase 5 — Frontend `[x]`
Goal: the graph renders and queries highlight subgraphs.

- [x] 5.1 Cytoscape (core) dependency; code-split via React.lazy into its own chunk
- [x] 5.2 `GraphView` — type-coded nodes, layout toggle (cose/breadthfirst/concentric), click-to-highlight neighborhood
- [x] 5.3 `QueryPanel` — 4 queries + blast radius + orphan + drift; API-populated dropdowns; highlights subgraph by name
- [x] 5.4 `IngestPanel` — dynamic bundle discovery + file upload (any source) + reset; `StatsBar` + `Legend`
- [x] 5.5 Typed API client (`src/api/`) + loading/error/empty states; selected-node details panel
- [x] **Exit check:** `tsc -b` + `vite build` + `eslint` all pass; app chunk 64 kB gzip, graph lib lazy-loaded
  (interactive browser render is manual)

## Phase 6 — Update & blast radius `[x]`
Goal: config changes update the graph correctly; blast radius works.

- [x] 6.1 Re-ingest reconciliation — `reconcile_declared_edges` removes stale declared edges (SC3),
  downgrades still-observed/policy-asserted edges to drift, and cleans dangling nodes
- [x] 6.2 Blast-radius endpoint (`/tools/{name}/blast-radius`) + UI query surfacing affected agents/users/data
- [x] **Exit check:** verified — changing an agent config removes stale model/tool/policy edges + dangling
  nodes (agent flips to orphan when policy dropped); an observed edge downgrades to drift; blast radius correct

## Phase 7 — Containerize + IaC `[x]`
Goal: production image parity and reproducible infra.

- [x] 7.1 Production Dockerfiles — backend (uv + gunicorn + HEALTHCHECK) + frontend (node build → nginx, SPA routing)
- [x] 7.2 `infra/terraform/` — ECR, VPC, ECS Fargate + ALB (+ autoscaling), S3/CloudFront (OAC), IAM, CloudWatch
- [x] 7.3 Secrets wiring — Neo4j creds in Secrets Manager, injected into the task; task role grants Bedrock
- [x] **Exit check:** both prod images build + run locally (nginx config valid, assets packaged);
  Terraform authored (11 files + tfvars example + deploy README). NOTE: `terraform validate/plan` pending —
  terraform not installed in this env; requires the deployer's machine + AWS creds (Phase 8)

## Phase 8 — Deploy + validate `[ ]`
Goal: live on AWS with all success criteria passing.

- [ ] 8.1 Provision infra + Neo4j Aura
- [ ] 8.2 GitHub Actions CI/CD (test → build → push ECR → deploy ECS → invalidate CloudFront)
- [ ] 8.3 Run validation suite against the deployed environment
- [ ] **Exit check:** public URL live; all success criteria pass in the cloud

## Phase 9 — Hardening (stretch) `[ ]`
- [ ] 9.1 API auth (API key / JWT)
- [ ] 9.2 Autoscaling policies
- [ ] 9.3 CloudWatch dashboards + alarms
- [ ] 9.4 Config/log drift reporting

---

## Success Criteria Traceability
- [x] SC1 — three sample configs build correctly; all queries accurate (verified Phases 2 & 4; cloud run in 8)
- [x] SC2 — orphan query flags the intentionally policy-free agent (verified Phases 2, 3, 4)
- [x] SC3 — graph updates correctly when a config changes (verified Phase 6)
- [x] Bonus — blast radius query returns affected agents + users (verified Phases 4 & 6)
