import { NODE_COLORS, NODE_LABELS } from '../api/types'

export function Legend() {
  return (
    <section className="panel">
      <h2>Legend</h2>
      <div className="legend">
        {NODE_LABELS.map((label) => (
          <span key={label} className="legend-item">
            <span className="dot" style={{ background: NODE_COLORS[label] }} />
            {label}
          </span>
        ))}
      </div>
      <p className="hint">Tip: click a node to highlight its immediate connections.</p>
    </section>
  )
}
