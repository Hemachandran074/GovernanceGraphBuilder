import type { GraphStats } from '../api/types'
import { NODE_COLORS, NODE_LABELS } from '../api/types'

interface StatsBarProps {
  stats: GraphStats | null
}

export function StatsBar({ stats }: StatsBarProps) {
  if (!stats) return <div className="statsbar statsbar--empty">No graph loaded</div>

  return (
    <div className="statsbar">
      {NODE_LABELS.map((label) => (
        <span key={label} className="pill" style={{ borderColor: NODE_COLORS[label] }}>
          <span className="dot" style={{ background: NODE_COLORS[label] }} />
          {label}: <strong>{stats.nodes[label] ?? 0}</strong>
        </span>
      ))}
      <span className="pill">edges: <strong>{stats.total_edges}</strong></span>
      <span className={`pill ${stats.orphan_agents > 0 ? 'warn' : ''}`}>
        orphan agents: <strong>{stats.orphan_agents}</strong>
      </span>
      <span className={`pill ${stats.drift_edges > 0 ? 'warn' : ''}`}>
        drift: <strong>{stats.drift_edges}</strong>
      </span>
    </div>
  )
}
