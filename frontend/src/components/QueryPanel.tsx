import { useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { NodeLabel } from '../api/types'

type QueryKind =
  | 'tools_for_agent'
  | 'agents_using_model'
  | 'agents_accessing_datasource'
  | 'blast_radius'
  | 'orphan_agents'
  | 'drift'

interface QueryDef {
  kind: QueryKind
  label: string
  entityLabel: NodeLabel | null // which entity type to populate the parameter dropdown
}

const QUERIES: QueryDef[] = [
  { kind: 'tools_for_agent', label: 'Tools an agent can access', entityLabel: 'Agent' },
  { kind: 'agents_using_model', label: 'Agents using a model', entityLabel: 'Model' },
  { kind: 'agents_accessing_datasource', label: 'Agents accessing a data source', entityLabel: 'DataSource' },
  { kind: 'blast_radius', label: 'Blast radius of a compromised tool', entityLabel: 'Tool' },
  { kind: 'orphan_agents', label: 'Orphan agents (no policy)', entityLabel: null },
  { kind: 'drift', label: 'Config / runtime drift', entityLabel: null },
]

interface QueryPanelProps {
  onHighlight: (names: string[]) => void
  refreshKey: number // bump to re-fetch entity options after ingestion
}

const asStr = (v: unknown): string => (v == null ? '' : String(v))

export function QueryPanel({ onHighlight, refreshKey }: QueryPanelProps) {
  const [kind, setKind] = useState<QueryKind>('tools_for_agent')
  const [options, setOptions] = useState<string[]>([])
  const [param, setParam] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [items, setItems] = useState<string[]>([])

  const current = QUERIES.find((q) => q.kind === kind) ?? QUERIES[0]

  // Switching the question clears prior results and, for parameterless queries,
  // the parameter options (done in the handler to avoid setState-in-effect).
  function changeKind(next: QueryKind) {
    setKind(next)
    setSummary(null)
    setItems([])
    setError(null)
    if (!QUERIES.find((q) => q.kind === next)?.entityLabel) {
      setOptions([])
      setParam('')
    }
  }

  // Populate the parameter dropdown dynamically from the live graph. Only the
  // async fetch runs here; state is set inside the promise callbacks.
  useEffect(() => {
    if (!current.entityLabel) return
    let active = true
    api
      .listEntities(current.entityLabel)
      .then((r) => {
        if (!active) return
        const names = r.results.map((x) => asStr(x.name)).filter(Boolean).sort()
        setOptions(names)
        setParam((prev) => (names.includes(prev) ? prev : names[0] ?? ''))
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)))
    return () => {
      active = false
    }
  }, [kind, refreshKey, current.entityLabel])

  async function run() {
    setLoading(true)
    setError(null)
    try {
      const highlight: string[] = []
      const display: string[] = []
      let text = ''

      if (kind === 'orphan_agents') {
        const r = await api.orphanAgents()
        r.results.forEach((x) => {
          highlight.push(asStr(x.name))
          display.push(asStr(x.name))
        })
        text = `${r.count} orphan agent(s)`
      } else if (kind === 'drift') {
        const r = await api.getDrift()
        r.results.forEach((x) => {
          const agent = asStr(x.agent)
          const target = asStr(x.target)
          highlight.push(agent, target)
          display.push(`${agent} → ${target}  (${asStr(x.relationship)}, x${asStr(x.observed_count)})`)
        })
        text = `${r.count} undeclared (observed-only) relationship(s)`
      } else if (kind === 'blast_radius') {
        const r = await api.blastRadius(param)
        highlight.push(param)
        for (const x of r.affected_agents) {
          highlight.push(asStr(x.name))
          display.push(`agent: ${asStr(x.name)}`)
        }
        for (const x of r.affected_users) {
          highlight.push(asStr(x.name))
          display.push(`user: ${asStr(x.name)}`)
        }
        for (const x of r.exposed_data_sources) {
          highlight.push(asStr(x.name))
          display.push(`data: ${asStr(x.name)}`)
        }
        text = `${r.affected_agents.length} agent(s), ${r.affected_users.length} user(s), ${r.exposed_data_sources.length} data source(s) affected`
      } else {
        const r =
          kind === 'tools_for_agent'
            ? await api.toolsForAgent(param)
            : kind === 'agents_using_model'
              ? await api.agentsUsingModel(param)
              : await api.agentsAccessingDataSource(param)
        highlight.push(param)
        r.results.forEach((x) => {
          highlight.push(asStr(x.name))
          display.push(asStr(x.name))
        })
        text = `${r.count} result(s)`
      }

      setSummary(text)
      setItems(display)
      onHighlight(highlight)
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const needsParam = current.entityLabel != null

  return (
    <section className="panel">
      <h2>Query</h2>
      <label className="field">
        <span>Question</span>
        <select value={kind} onChange={(e) => changeKind(e.target.value as QueryKind)}>
          {QUERIES.map((q) => (
            <option key={q.kind} value={q.kind}>
              {q.label}
            </option>
          ))}
        </select>
      </label>

      {needsParam && (
        <label className="field">
          <span>{current.entityLabel}</span>
          <select value={param} onChange={(e) => setParam(e.target.value)} disabled={options.length === 0}>
            {options.length === 0 && <option value="">(none in graph)</option>}
            {options.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="row">
        <button className="btn primary" onClick={run} disabled={loading || (needsParam && !param)}>
          {loading ? 'Running…' : 'Run query'}
        </button>
        <button className="btn" onClick={() => onHighlight([])} disabled={loading}>
          Clear
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {summary && <p className="summary">{summary}</p>}
      {items.length > 0 && (
        <ul className="results">
          {items.map((it, i) => (
            <li key={`${it}-${i}`}>{it}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
