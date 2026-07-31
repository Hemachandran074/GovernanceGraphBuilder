# syntax=docker/dockerfile:1

# Unified image (Strategy 1): builds the React SPA and serves it from FastAPI.
# Build from the REPOSITORY ROOT so both backend/ and frontend/ are in context:
#   docker build -f backend/Dockerfile -t ggb-backend .

# --- Frontend build stage ---
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin API in the unified container -> relative request paths.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# --- Backend runtime stage ---
FROM python:3.12-slim AS runtime

# Bring in the uv binary from the official image (pinned for reproducibility).
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first for better layer caching (needs backend/uv.lock).
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Application source + sample bundles (used by /ingest/bundle).
COPY backend/app ./app
COPY backend/samples ./samples

# Built SPA served by FastAPI (Strategy 1) at /app/static.
COPY --from=frontend /fe/dist ./static

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Container-level liveness check (curl isn't in the slim image, so use Python).
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

# Gunicorn manages multiple Uvicorn workers for concurrent request handling.
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", \
     "-w", "2", \
     "--error-logfile", "-"]
