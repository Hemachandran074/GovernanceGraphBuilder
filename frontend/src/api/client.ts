// Typed client for the Governance Graph Builder API.
//
// The base URL comes from VITE_API_BASE_URL (falls back to localhost:8000).
// Errors are normalized from the backend's { error: { type, message } } envelope.

import type {
  BlastRadiusResult,
  BundleListResponse,
  EntityListResponse,
  GraphSnapshot,
  GraphStats,
  IngestResponse,
  NlQueryResponse,
  QueryResponse,
} from './types'

const configured = import.meta.env.VITE_API_BASE_URL as string | undefined
const BASE_URL =
  configured === undefined
    ? 'http://localhost:8000'
    : configured.trim().replace(/\/+$/, '')

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      message = body?.error?.message ?? body?.detail ?? message
    } catch {
      // non-JSON error body; keep the default message
    }
    throw new ApiError(message, response.status)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const encode = (value: string) => encodeURIComponent(value)

export const api = {
  // --- Graph ---
  getGraph: () => request<GraphSnapshot>('/graph'),
  getStats: () => request<GraphStats>('/graph/stats'),
  resetGraph: () => request<{ status: string; message: string }>('/graph', { method: 'DELETE' }),
  getDrift: () => request<QueryResponse>('/graph/drift'),
  listEntities: (label: string) => request<EntityListResponse>(`/graph/entities/${encode(label)}`),

  // --- Ingestion ---
  getBundles: () => request<BundleListResponse>('/ingest/bundles'),
  ingestBundle: (bundle: string, reset: boolean) =>
    request<IngestResponse>('/ingest/bundle', {
      method: 'POST',
      body: JSON.stringify({ bundle, reset }),
    }),
  uploadFile: (kind: string, file: File, reset: boolean) => {
    const form = new FormData()
    form.append('file', file)
    // FormData sets its own multipart Content-Type boundary.
    return request<IngestResponse>(
      `/ingest/upload?kind=${encode(kind)}&reset=${reset}`,
      { method: 'POST', body: form, headers: {} },
    )
  },

  // --- Natural-language query (LLM -> read-only Cypher -> subgraph) ---
  nlQuery: (question: string) =>
    request<NlQueryResponse>('/graph/nl-query', {
      method: 'POST',
      body: JSON.stringify({ question }),
    }),

  // --- Governance queries ---
  toolsForAgent: (name: string) => request<QueryResponse>(`/agents/${encode(name)}/tools`),
  agentsUsingModel: (name: string) => request<QueryResponse>(`/models/${encode(name)}/agents`),
  agentsAccessingDataSource: (name: string) => request<QueryResponse>(`/datasources/${encode(name)}/agents`),
  orphanAgents: () => request<QueryResponse>('/agents/orphans'),
  blastRadius: (name: string) => request<BlastRadiusResult>(`/tools/${encode(name)}/blast-radius`),
}
