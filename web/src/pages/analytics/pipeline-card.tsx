import type { UseQueryResult } from '@tanstack/react-query'
import type { Funnel } from '@/api/client'
import { FlowDiagram } from '@/components/flow/flow-diagram'
import type { FlowLink, FlowNode } from '@/components/flow/layout'
import { ErrorState } from '@/components/query-states'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { pct } from './calc'

/** Funnel stages as boxes left to right; what did not make it to the next stage leaves downwards as "Stopped here". */
export function pipelineFlow(stages: Funnel['stages']): { nodes: FlowNode[]; links: FlowLink[] } {
  const nodes: FlowNode[] = []
  const links: FlowLink[] = []
  stages.forEach((s, i) => {
    nodes.push({
      id: s.status,
      label: s.status,
      sub: `${s.count}${s.conversion_from_prev == null ? '' : ` · ${pct(s.conversion_from_prev)}`}`,
      value: s.count,
      col: i,
      tone: i < 3 ? 'sky' : i === 3 ? 'indigo' : 'emerald',
    })
    const next = stages[i + 1]
    if (!next) return
    links.push({ from: s.status, to: next.status, value: Math.min(next.count, s.count) })
    const lost = s.count - next.count
    if (lost > 0) {
      nodes.push({ id: `stop-${s.status}`, label: 'Stopped here', sub: String(lost), col: i + 1, tone: 'sink' })
      links.push({ from: s.status, to: `stop-${s.status}`, value: lost, tone: 'sink' })
    }
  })
  return { nodes, links }
}

export function PipelineCard({ funnel }: { funnel: UseQueryResult<Funnel> }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Pipeline</CardTitle>
        <CardDescription>
          Every shortlisted job on its way to an offer. Box and ribbon sizes follow the counts; the percentage is the share of the previous stage that got this far, and grey ribbons are the ones that stopped.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {funnel.isPending ? (
          <Skeleton className="h-72" role="status" aria-busy="true" aria-label="Loading funnel" />
        ) : funnel.isError ? (
          <ErrorState error={funnel.error} onRetry={() => funnel.refetch()} />
        ) : funnel.data.stages.every((s) => s.count === 0) ? (
          <p className="text-sm text-muted-foreground">Nothing in the pipeline for this range yet.</p>
        ) : (
          <PipelineDiagram stages={funnel.data.stages} />
        )}
      </CardContent>
    </Card>
  )
}

function PipelineDiagram({ stages }: { stages: Funnel['stages'] }) {
  const { nodes, links } = pipelineFlow(stages)
  return <FlowDiagram label="Pipeline flow" nodes={nodes} links={links} width={1000} height={360} nodeWidth={108} align="top" />
}
