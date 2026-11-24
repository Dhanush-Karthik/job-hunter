import { describe, expect, it } from 'vitest'
import { layoutFlow, type FlowLink, type FlowNode } from './layout'

const nodes: FlowNode[] = [
  { id: 'a', label: 'A', col: 0, tone: 'sky' },
  { id: 'b', label: 'B', col: 1, tone: 'emerald' },
  { id: 'x', label: 'Dropped', col: 1, tone: 'sink' },
]
const links: FlowLink[] = [
  { from: 'a', to: 'b', value: 30 },
  { from: 'a', to: 'x', value: 70 },
]
const opts = { width: 600, height: 300 }

describe('layoutFlow', () => {
  it('sizes nodes by what flows through them and keeps everything inside the canvas', () => {
    const l = layoutFlow(nodes, links, opts)
    const [a, b, x] = ['a', 'b', 'x'].map((id) => l.nodes.find((n) => n.id === id)!)
    expect(a.size).toBe(100)
    expect(b.size).toBe(30)
    expect(a.h).toBeGreaterThan(x.h)
    expect(x.h).toBeGreaterThan(b.h - 0.001)
    for (const n of l.nodes) {
      expect(n.y).toBeGreaterThanOrEqual(0)
      expect(n.y + n.h).toBeLessThanOrEqual(opts.height)
      expect(n.x + n.w).toBeLessThanOrEqual(opts.width + 0.001)
    }
    expect(l.nodes.filter((n) => n.col === 1).map((n) => n.id)).toEqual(['b', 'x']) // input order, top to bottom
  })

  it('draws a ribbon per link with thickness in proportion to its value', () => {
    const l = layoutFlow(nodes, links, opts)
    const [ab, ax] = l.links
    expect(ax.thickness / ab.thickness).toBeCloseTo(70 / 30, 1)
    expect(ab.path).toMatch(/^M[\d.]+,[\d.]+ C/)
  })

  it('skips empty links and fails loudly on a link to a missing node', () => {
    expect(layoutFlow(nodes, [...links, { from: 'a', to: 'b', value: 0 }], opts).links).toHaveLength(2)
    expect(() => layoutFlow(nodes, [{ from: 'a', to: 'nope', value: 1 }], opts)).toThrow(/missing node/)
  })

  it('lays out a single empty column without dividing by zero', () => {
    const l = layoutFlow([{ id: 'a', label: 'A', col: 0, tone: 'sky' }], [], opts)
    expect(Number.isFinite(l.nodes[0].y) && Number.isFinite(l.nodes[0].h)).toBe(true)
  })
})
