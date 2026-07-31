import { useState } from 'react'
import { api, ApiError } from '../api/client'
import type { GraphSnapshot, NlQueryResponse } from '../api/types'

interface NlQueryPanelProps {
  // Render the returned subgraph in the main graph view.
  onGraph: (snapshot: GraphSnapshot) => void
}

const EXAMPLES = [
  'Show all agents and the models they use',
  'Which agents have no policy attached?',
  'Which agents can access crm-db?',
  'Show the tools each agent has',
]

export function NlQueryPanel({ onGraph }: NlQueryPanelProps) {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<NlQueryResponse | null>(null)

  async function ask(q?: string) {
    const text = (q ?? question).trim()
    if (text.length < 3) return
    setLoading(true)
    setError(null)
    try {
      const r = await api.nlQuery(text)
      setResult(r)
      onGraph(r.snapshot)
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.message : String(e))
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel">
      <h2>Ask AI</h2>
      <label className="field">
        <span>Ask about the graph in plain English</span>
        <textarea
          className="nl-input"
          rows={2}
          placeholder="e.g. Which agents can access crm-db?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void ask()
          }}
        />
      </label>

      <div className="nl-examples">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            className="chip"
            onClick={() => {
              setQuestion(ex)
              void ask(ex)
            }}
            disabled={loading}
          >
            {ex}
          </button>
        ))}
      </div>

      <div className="row">
        <button
          className="btn primary"
          onClick={() => void ask()}
          disabled={loading || question.trim().length < 3}
        >
          {loading ? 'Asking…' : 'Ask'}
        </button>
        <button
          className="btn"
          onClick={() => {
            setQuestion('')
            setResult(null)
            setError(null)
          }}
          disabled={loading}
        >
          Clear
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="nl-result">
          <p className="summary">
            {result.node_count} node(s) · {result.edge_count} edge(s)
            <span className="tag nl-provider">{result.provider}</span>
          </p>
          {result.explanation && <p className="hint">{result.explanation}</p>}
          <details className="cypher-details">
            <summary>Generated Cypher</summary>
            <pre className="cypher-box">
              <code>{result.cypher}</code>
            </pre>
          </details>
          <p className="hint">Showing the query result — click Refresh to restore the full graph.</p>
        </div>
      )}
    </section>
  )
}
