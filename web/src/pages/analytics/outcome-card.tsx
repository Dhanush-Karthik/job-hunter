import { useState } from 'react'
import type { Breakdown } from '@/api/client'
import { FlowDiagram } from '@/components/flow/flow-diagram'
import type { FlowLink, FlowNode } from '@/components/flow/layout'
import { SOURCE_LABEL } from '@/components/lead-format'
import { EmptyState, ErrorState } from '@/components/query-states'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { pct } from './calc'
import { useBreakdown, type Range } from './use-analytics'

type By = 'source' | 'channel' | 'title' | 'variant'
const TABS: { by: By; label: string }[] = [
  { by: 'source', label: 'Source' },
  { by: 'channel', label: 'Channel' },
  { by: 'title', label: 'Title' },
  { by: 'variant', label: 'CV variant' },
]
const CHANNEL: Record<string, string> = { platform_quick: 'Platform quick apply', company_ats: 'Company ATS', email: 'Email' }
const MAX_ROWS = 8

function label(by: By, key: string) {
  if (by === 'source') return SOURCE_LABEL[key as keyof typeof SOURCE_LABEL] ?? key
  if (by === 'channel') return CHANNEL[key] ?? key
  if (by === 'variant') return `Variant ${key}`
  return key
}

/** Each way of applying on the left, flowing into "Interview call" or "No call yet" on the right. */
export function outcomeFlow(by: By, rows: Breakdown['rows']): { nodes: FlowNode[]; links: FlowLink[] } {
  const sorted = [...rows].sort((a, b) => b.calls - a.calls || b.applied - a.applied)
  const top = sorted.slice(0, MAX_ROWS)
  const rest = sorted.slice(MAX_ROWS)
  if (rest.length) {
    const applied = rest.reduce((s, r) => s + r.applied, 0)
    const calls = rest.reduce((s, r) => s + r.calls, 0)
    top.push({ key: `${rest.length} others`, applied, calls, rate: applied ? calls / applied : null })
  }
  const nodes: FlowNode[] = top.map((r, i) => ({
    id: `row-${i}`,
    label: rest.length && i === top.length - 1 ? r.key : label(by, r.key),
    sub: `${r.applied} applied · ${pct(r.rate)}`,
    value: r.applied,
    col: 0,
    tone: 'indigo',
  }))
  const calls = top.reduce((s, r) => s + r.calls, 0)
  nodes.push({ id: 'call', label: 'Interview call', sub: String(calls), col: 1, tone: 'emerald' })
  nodes.push({ id: 'none', label: 'No call yet', sub: String(top.reduce((s, r) => s + Math.max(r.applied - r.calls, 0), 0)), col: 1, tone: 'sink' })
  const links: FlowLink[] = []
  top.forEach((r, i) => {
    links.push({ from: `row-${i}`, to: 'call', value: Math.min(r.calls, r.applied) })
    links.push({ from: `row-${i}`, to: 'none', value: Math.max(r.applied - r.calls, 0), tone: 'sink' })
  })
  return { nodes, links }
}

function Outcomes({ by, range }: { by: By; range: Range }) {
  const q = useBreakdown(by, range)
  if (q.isPending) return <Skeleton className="h-64" role="status" aria-busy="true" aria-label="Loading breakdown" />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (q.data.rows.length === 0) return <EmptyState title="No applications in this range" />
  const { nodes, links } = outcomeFlow(by, q.data.rows)
  const rows = nodes.filter((n) => n.col === 0).length
  return <FlowDiagram label={`Calls by ${by}`} nodes={nodes} links={links} width={760} height={Math.max(240, rows * 58)} nodeWidth={210} />
}

export function OutcomeCard({ range }: { range: Range }) {
  const [by, setBy] = useState<By>('source')
  return (
    <Card>
      <CardHeader>
        <CardTitle>Interview calls by…</CardTitle>
        <CardDescription>Where each application came from and whether it turned into an interview call. Wide green ribbons are what to do more of.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <Tabs value={by} onValueChange={(v) => setBy(v as By)}>
          <TabsList className="max-w-full overflow-x-auto">
            {TABS.map((t) => (
              <TabsTrigger key={t.by} value={t.by}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Outcomes by={by} range={range} />
      </CardContent>
    </Card>
  )
}
