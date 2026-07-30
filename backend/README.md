# Governance Graph Builder — Backend

FastAPI service that ingests agent composition data into a Neo4j graph and
answers governance queries. See the root [plan.md](../plan.md) and
[tasks.md](../tasks.md) for the full roadmap.

## Requirements
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Docker (for a local Neo4j via docker-compose)

## Quick start (local)

Start Neo4j (from the repo root):

```bash
docker compose -f infra/docker-compose.yml up -d neo4j
```

Install dependencies and run the API:

```bash
cd backend
cp .env.example .env          # adjust if needed
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness: http://localhost:8000/ready

## Full stack via docker-compose

```bash
docker compose -f infra/docker-compose.yml up --build
```

## Configuration
All settings come from environment variables (or a local `.env`). See
[`.env.example`](./.env.example) for the full list.

## Project layout

```
app/
  main.py            FastAPI app: lifespan, middleware, error handling
  config.py          Environment-based settings
  logging_config.py  Structured JSON logging + request correlation ids
  dependencies.py    Shared FastAPI dependencies
  api/health.py      /health (liveness) and /ready (readiness)
  graph/client.py    Async Neo4j client wrapper
```
