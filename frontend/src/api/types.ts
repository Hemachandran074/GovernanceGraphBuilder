// Types mirroring the backend API responses. Node/edge properties are kept
// open (Record<string, unknown>) so the UI stays dynamic across node shapes.

export type NodeProperties = Record<string, unknown> & {
  id: string
  name?: string
}

export interface GraphNode {
  id: string
  label: string
  properties: NodeProperties
}

export interface GraphEdge {
  source: string
  target: string
  type: string
}

export interface GraphSnapshot {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface QueryResponse {
  query: string
  parameters: Record<string, unknown>
  count: number
  results: Array<Record<string, unknown>>
}

export interface EntityListResponse {
  label: string
  count: number
  results: Array<Record<string, unknown>>
}

export interface GraphStats {
  nodes: Record<string, number>
  total_nodes: number
  total_edges: number
  orphan_agents: number
  drift_edges: number
  llm_provider: string
}

export interface BlastRadiusResult {
  tool: Record<string, unknown> | null
  affected_agents: Array<Record<string, unknown>>
  affected_users: Array<Record<string, unknown>>
  exposed_data_sources: Array<Record<string, unknown>>
}

export interface IngestResponse {
  status: string
  result: Record<string, unknown>
}

export interface BundleListResponse {
  bundles: string[]
}

// The six node labels used across the graph.
export const NODE_LABELS = ['User', 'Agent', 'Model', 'Tool', 'DataSource', 'Policy'] as const
export type NodeLabel = (typeof NODE_LABELS)[number]

// Color per node label (kept in sync with the Cytoscape stylesheet + legend).
export const NODE_COLORS: Record<string, string> = {
  User: '#3b82f6',
  Agent: '#a855f7',
  Model: '#22c55e',
  Tool: '#f59e0b',
  DataSource: '#ef4444',
  Policy: '#14b8a6',
}
