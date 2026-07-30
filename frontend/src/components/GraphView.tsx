import { useEffect, useRef } from 'react'
import cytoscape from 'cytoscape'
import type { GraphEdge, GraphNode } from '../api/types'
import { NODE_COLORS } from '../api/types'

interface GraphViewProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  highlightedIds: Set<string>
  layoutName: string
  onNodeClick: (nodeId: string) => void
}

function toElements(nodes: GraphNode[], edges: GraphEdge[]): cytoscape.ElementDefinition[] {
  const nodeEls = nodes.map((n) => ({
    data: { id: n.id, label: n.label, name: (n.properties.name as string) ?? n.id },
  }))
  const edgeEls = edges.map((e) => ({
    data: {
      id: `${e.source}|${e.type}|${e.target}`,
      source: e.source,
      target: e.target,
      type: e.type,
    },
  }))
  return [...nodeEls, ...edgeEls]
}

function runLayout(cy: cytoscape.Core, name: string): void {
  if (cy.elements().length === 0) return
  const base: Record<string, unknown> = { name, animate: true, animationDuration: 400, padding: 40, fit: true }
  let opts = base
  if (name === 'cose') {
    opts = { ...base, nodeRepulsion: 9000, idealEdgeLength: 130, nodeDimensionsIncludeLabels: true }
  } else if (name === 'breadthfirst') {
    opts = { ...base, directed: true, spacingFactor: 1.3 }
  } else if (name === 'concentric') {
    opts = { ...base, minNodeSpacing: 50 }
  }
  cy.layout(opts as unknown as cytoscape.LayoutOptions).run()
}

// Build the type-coded stylesheet. Cast at the end because @types/cytoscape's
// style typing is stricter than the literal-union values we use.
function buildStylesheet(): cytoscape.CytoscapeOptions['style'] {
  const perLabel = Object.entries(NODE_COLORS).map(([label, color]) => ({
    selector: `node[label="${label}"]`,
    style: { 'background-color': color, 'text-outline-color': color },
  }))

  return [
    {
      selector: 'node',
      style: {
        'background-color': '#94a3b8',
        label: 'data(name)',
        color: '#ffffff',
        'font-size': 11,
        'font-weight': 600,
        'text-valign': 'center',
        'text-halign': 'center',
        'text-outline-width': 2,
        'text-outline-color': '#94a3b8',
        'text-wrap': 'wrap',
        'text-max-width': '110px',
        width: 'label',
        height: 'label',
        padding: '10px',
        shape: 'round-rectangle',
        'border-width': 2,
        'border-color': 'rgba(0,0,0,0.15)',
      },
    },
    ...perLabel,
    {
      selector: 'edge',
      style: {
        width: 1.5,
        'line-color': '#cbd5e1',
        'target-arrow-color': '#cbd5e1',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        label: 'data(type)',
        'font-size': 8,
        color: '#64748b',
        'text-rotation': 'autorotate',
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.75,
        'text-background-padding': '2px',
      },
    },
    { selector: '.faded', style: { opacity: 0.1, 'text-opacity': 0.1 } },
    {
      selector: 'node.highlighted',
      style: { 'border-width': 4, 'border-color': '#0f172a', 'z-index': 10 },
    },
    {
      selector: 'edge.highlighted',
      style: { width: 3.5, 'line-color': '#0f172a', 'target-arrow-color': '#0f172a', opacity: 1, 'z-index': 10 },
    },
  ] as unknown as cytoscape.CytoscapeOptions['style']
}

export function GraphView({ nodes, edges, highlightedIds, layoutName, onNodeClick }: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)

  // Keep the latest callback / layout in refs so the one-time init effect stays stable.
  const onNodeClickRef = useRef(onNodeClick)
  const layoutNameRef = useRef(layoutName)
  useEffect(() => {
    onNodeClickRef.current = onNodeClick
  }, [onNodeClick])

  // Initialise cytoscape once.
  useEffect(() => {
    if (!containerRef.current) return
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: buildStylesheet(),
      wheelSensitivity: 0.2,
      minZoom: 0.2,
      maxZoom: 3,
    })
    cy.on('tap', 'node', (evt) => onNodeClickRef.current(evt.target.id()))
    cyRef.current = cy
    return () => {
      cy.destroy()
      cyRef.current = null
    }
  }, [])

  // Sync elements when the graph data changes.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.batch(() => {
      cy.elements().remove()
      cy.add(toElements(nodes, edges))
    })
    runLayout(cy, layoutNameRef.current)
  }, [nodes, edges])

  // Re-run layout on layout change (without rebuilding elements).
  useEffect(() => {
    layoutNameRef.current = layoutName
    const cy = cyRef.current
    if (cy) runLayout(cy, layoutName)
  }, [layoutName])

  // Apply the controlled highlight set.
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    cy.batch(() => {
      cy.elements().removeClass('faded highlighted')
      if (highlightedIds.size > 0) {
        cy.elements().addClass('faded')
        const hi = cy.nodes().filter((n) => highlightedIds.has(n.id()))
        hi.removeClass('faded').addClass('highlighted')
        hi.edgesWith(hi).removeClass('faded').addClass('highlighted')
      }
    })
  }, [highlightedIds])

  return <div ref={containerRef} className="graph-canvas" />
}
