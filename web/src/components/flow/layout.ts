/** Sankey-style layout for small flow diagrams. Pure: no DOM, so it is unit-tested directly. */

export type Tone = 'sky' | 'indigo' | 'emerald' | 'amber' | 'sink'

export type FlowNode = {
  id: string
  label: string
  /** Second line, e.g. "26 applied · 11.5%". */
  sub?: string
  /** Size when no link carries it (a node with links is sized by the larger of what flows in or out). */
  value?: number
  col: number
  tone: Tone
}
export type FlowLink = { from: string; to: string; value: number; tone?: Tone }

export type PlacedNode = FlowNode & { x: number; y: number; w: number; h: number; size: number }
export type PlacedLink = FlowLink & { id: string; path: string; thickness: number; tone: Tone }
export type Layout = { width: number; height: number; nodes: PlacedNode[]; links: PlacedLink[] }

export type LayoutOptions = {
  width: number
  height: number
  nodeWidth?: number
  gap?: number
  minNodeHeight?: number
  paddingY?: number
  /** 'top' lines every column up at the top (funnels, sinks hang below); 'center' centres each column. */
  align?: 'top' | 'center'
}

/**
 * Columns are evenly spaced; nodes in a column are stacked top to bottom (input order) and the whole stack is
 * centred. Node height is proportional to its size, with a floor so labels stay readable. Links attach to a node
 * face in the order the links were given, so keep `links` ordered the way you want ribbons to stack.
 */
export function layoutFlow(nodes: FlowNode[], links: FlowLink[], opts: LayoutOptions): Layout {
  const { width, height, nodeWidth = 150, gap = 14, minNodeHeight = 34, paddingY = 8, align = 'center' } = opts
  const live = links.filter((l) => l.value > 0)
  const ids = new Set(nodes.map((n) => n.id))
  for (const l of live) if (!ids.has(l.from) || !ids.has(l.to)) throw new Error(`link ${l.from} -> ${l.to} references a missing node`)

  const sizeOf = (n: FlowNode) => {
    const inflow = live.filter((l) => l.to === n.id).reduce((s, l) => s + l.value, 0)
    const outflow = live.filter((l) => l.from === n.id).reduce((s, l) => s + l.value, 0)
    return Math.max(inflow, outflow, n.value ?? 0)
  }
  const cols = [...new Set(nodes.map((n) => n.col))].sort((a, b) => a - b)
  // 'sink' nodes (where things stop) hang below the main path in their column.
  const byCol = new Map(cols.map((c) => [c, [...nodes.filter((n) => n.col === c && n.tone !== 'sink'), ...nodes.filter((n) => n.col === c && n.tone === 'sink')]]))

  // One scale for the whole diagram: the tallest column (including gaps and minimum heights) must fit.
  const avail = height - paddingY * 2
  const need = (scale: number) =>
    Math.max(...cols.map((c) => byCol.get(c)!.reduce((s, n) => s + Math.max(sizeOf(n) * scale, minNodeHeight), 0) + gap * (byCol.get(c)!.length - 1)))
  const peak = Math.max(1, ...nodes.map(sizeOf))
  let scale = avail / peak
  for (let i = 0; i < 40 && need(scale) > avail; i++) scale *= 0.9
  scale = Math.max(scale, 0)

  const step = cols.length > 1 ? (width - nodeWidth) / (cols.length - 1) : 0
  const placed = new Map<string, PlacedNode>()
  for (const [ci, c] of cols.entries()) {
    const list = byCol.get(c)!
    const heights = list.map((n) => Math.max(sizeOf(n) * scale, minNodeHeight))
    let y = paddingY + (align === 'top' ? 0 : (avail - (heights.reduce((s, h) => s + h, 0) + gap * (list.length - 1))) / 2)
    list.forEach((n, i) => {
      placed.set(n.id, { ...n, x: ci * step, y, w: nodeWidth, h: heights[i], size: sizeOf(n) })
      y += heights[i] + gap
    })
  }

  const outUsed = new Map<string, number>()
  const inUsed = new Map<string, number>()
  const out: PlacedLink[] = live.map((l, i) => {
    const a = placed.get(l.from)!
    const b = placed.get(l.to)!
    const t = Math.max(l.value * scale, 1.5)
    const outTotal = live.filter((x) => x.from === a.id).reduce((s, x) => s + Math.max(x.value * scale, 1.5), 0)
    const inTotal = live.filter((x) => x.to === b.id).reduce((s, x) => s + Math.max(x.value * scale, 1.5), 0)
    const lead = (h: number, total: number) => (align === 'top' ? 0 : (h - total) / 2)
    const y0 = a.y + lead(a.h, outTotal) + (outUsed.get(a.id) ?? 0) + t / 2
    const y1 = b.y + lead(b.h, inTotal) + (inUsed.get(b.id) ?? 0) + t / 2
    outUsed.set(a.id, (outUsed.get(a.id) ?? 0) + t)
    inUsed.set(b.id, (inUsed.get(b.id) ?? 0) + t)
    const x0 = a.x + a.w
    const x1 = b.x
    const mid = (x0 + x1) / 2
    return { ...l, id: `${l.from}>${l.to}#${i}`, thickness: t, tone: l.tone ?? b.tone, path: `M${x0},${y0} C${mid},${y0} ${mid},${y1} ${x1},${y1}` }
  })
  return { width, height, nodes: [...placed.values()], links: out }
}
