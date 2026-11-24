import { cn } from '@/lib/utils'
import { layoutFlow, type FlowLink, type FlowNode, type Tone } from './layout'

const NODE: Record<Tone, string> = {
  sky: 'fill-sky-500/15 stroke-sky-500/60',
  indigo: 'fill-indigo-500/15 stroke-indigo-500/60',
  emerald: 'fill-emerald-500/20 stroke-emerald-500/70',
  amber: 'fill-amber-500/15 stroke-amber-500/60',
  sink: 'fill-muted stroke-border',
}
const LINK: Record<Tone, string> = {
  sky: 'stroke-sky-500/25',
  indigo: 'stroke-indigo-500/25',
  emerald: 'stroke-emerald-500/30',
  amber: 'stroke-amber-500/25',
  sink: 'stroke-muted-foreground/10',
}

/**
 * A Sankey-style flow diagram in plain SVG. Boxes are sized by count, ribbons by how many moved between them.
 * Every number is also in the visually hidden list, so the picture is never the only source of the data.
 */
export function FlowDiagram({
  label,
  nodes,
  links,
  height = 320,
  width = 960,
  nodeWidth = 150,
  align,
  className,
}: {
  label: string
  nodes: FlowNode[]
  links: FlowLink[]
  height?: number
  width?: number
  nodeWidth?: number
  align?: 'top' | 'center'
  className?: string
}) {
  const layout = layoutFlow(nodes, links, { width, height, nodeWidth, align })
  return (
    <div className={cn('overflow-x-auto', className)}>
      <svg role="group" aria-label={label} viewBox={`0 0 ${width} ${height}`} className="h-auto w-full min-w-[640px]" style={{ maxHeight: height * 1.15 }}>
        <g fill="none">
          {layout.links.map((l) => (
            <path key={l.id} d={l.path} strokeWidth={l.thickness} className={LINK[l.tone]}>
              <title>{`${nodes.find((n) => n.id === l.from)?.label} → ${nodes.find((n) => n.id === l.to)?.label}: ${l.value}`}</title>
            </path>
          ))}
        </g>
        {layout.nodes.map((n) => (
          <g key={n.id} data-node={n.id}>
            <rect x={n.x} y={n.y} width={n.w} height={n.h} rx={8} strokeWidth={1} className={NODE[n.tone]} />
            <text x={n.x + 10} y={n.y + n.h / 2 - (n.sub ? 3 : -4)} className="fill-foreground text-[12px] font-medium">
              {n.label}
            </text>
            {n.sub && (
              <text x={n.x + 10} y={n.y + n.h / 2 + 12} className="fill-muted-foreground text-[11px]">
                {n.sub}
              </text>
            )}
          </g>
        ))}
      </svg>
      <ul className="sr-only" aria-label={`${label}: numbers`}>
        {layout.nodes.map((n) => (
          <li key={n.id}>
            {n.label}: {n.size}
            {n.sub ? `, ${n.sub}` : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}
