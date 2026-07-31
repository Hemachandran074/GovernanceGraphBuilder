import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from './api/client'
import type { GraphNode, GraphSnapshot, GraphStats } from './api/types'
import { IngestPanel } from './components/IngestPanel'
import { Legend } from './components/Legend'
import { NlQueryPanel } from './components/NlQueryPanel'
import { QueryPanel } from './components/QueryPanel'
import { StatsBar } from './components/StatsBar'
import './App.css'

// Code-split the graph view (and its Cytoscape dependency) into its own chunk.
const GraphView = lazy(() => import('./components/GraphView').then((m) => ({ default: m.GraphView })))
const LAYOUTS = ['cose', 'breadthfirst', 'concentric'] as const
const EMPTY_GRAPH: GraphSnapshot = { nodes: [], edges: [] }

function App() {
  const [graph, setGraph] = useState<GraphSnapshot>(EMPTY_GRAPH)
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [highlighted, setHighlighted] = useState<Set<string>>(new Set())
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [layout, setLayout] = useState<string>('cose')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [g, s] = await Promise.all([api.getGraph(), api.getStats()])
      setGraph(g)
      setStats(s)
      setHighlighted(new Set())
      setSelected(null)
      setRefreshKey((k) => k + 1)
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // Initial data load on mount. refresh() also backs the manual Refresh
    // button; a single fetch here is intentional.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh()
  }, [refresh])

  const nameToId = useMemo(() => {
    const map = new Map<string, string>()
    for (const node of graph.nodes) {
      const name = (node.properties.name as string) ?? node.id
      map.set(name, node.id)
    }
    return map
  }, [graph])

  const handleHighlight = useCallback(
    (names: string[]) => {
      const ids = new Set<string>()
      for (const name of names) {
        const id = nameToId.get(name)
        if (id) ids.add(id)
      }
      setHighlighted(ids)
    },
    [nameToId],
  )

  const handleNodeClick = useCallback(
    (nodeId: string) => {
      setSelected(graph.nodes.find((n) => n.id === nodeId) ?? null)
      const ids = new Set<string>([nodeId])
      for (const edge of graph.edges) {
        if (edge.source === nodeId) ids.add(edge.target)
        if (edge.target === nodeId) ids.add(edge.source)
      }
      setHighlighted(ids)
    },
    [graph],
  )

  // Replace the view with the subgraph returned by a natural-language query.
  // The Refresh button restores the full graph.
  const handleNlGraph = useCallback((snapshot: GraphSnapshot) => {
    setGraph(snapshot)
    setHighlighted(new Set())
    setSelected(null)
  }, [])

  const isEmpty = graph.nodes.length === 0

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <h1>Governance Graph Builder</h1>
          <p>Agents, models, tools, users, data sources & policies — one queryable graph.</p>
        </div>
        <StatsBar stats={stats} />
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <IngestPanel onIngested={refresh} />
          <NlQueryPanel onGraph={handleNlGraph} />
          <QueryPanel onHighlight={handleHighlight} refreshKey={refreshKey} />
          <Legend />
          {selected && (
            <section className="panel">
              <h2>Selected</h2>
              <p className="node-title">
                <span className="tag">{selected.label}</span> {(selected.properties.name as string) ?? selected.id}
              </p>
              <ul className="props">
                {Object.entries(selected.properties)
                  .filter(([k]) => k !== 'name')
                  .map(([k, v]) => (
                    <li key={k}>
                      <span className="k">{k}</span>
                      <span className="v">{Array.isArray(v) ? v.join(', ') : String(v)}</span>
                    </li>
                  ))}
              </ul>
            </section>
          )}
        </aside>

        <main className="graph-area">
          <div className="graph-toolbar">
            <label className="field inline">
              <span>Layout</span>
              <select value={layout} onChange={(e) => setLayout(e.target.value)}>
                {LAYOUTS.map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <button className="btn" onClick={() => void refresh()} disabled={loading}>
              {loading ? 'Loading…' : 'Refresh'}
            </button>
            {highlighted.size > 0 && (
              <button className="btn" onClick={() => setHighlighted(new Set())}>
                Clear highlight
              </button>
            )}
            <span className="spacer" />
            <span className="count">
              {graph.nodes.length} nodes · {graph.edges.length} edges
            </span>
          </div>

          <div className="graph-wrap">
            <Suspense fallback={<div className="overlay">Loading graph…</div>}>
              <GraphView
                nodes={graph.nodes}
                edges={graph.edges}
                highlightedIds={highlighted}
                layoutName={layout}
                onNodeClick={handleNodeClick}
              />
            </Suspense>
            {error && <div className="overlay error-overlay">{error}</div>}
            {!error && isEmpty && !loading && (
              <div className="overlay">Graph is empty — ingest a bundle from the sidebar to begin.</div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

export default App
