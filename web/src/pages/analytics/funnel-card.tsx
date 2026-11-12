import { ErrorState } from '@/components/query-states'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/status-badge'
import type { Funnel } from '@/api/client'
import { Bar } from './bars'
import { callsOf, pct } from './calc'
import type { UseQueryResult } from '@tanstack/react-query'

export function CallsHeadline({ funnel }: { funnel: UseQueryResult<Funnel> }) {
  const calls = callsOf(funnel.data)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Interview calls</CardTitle>
        <CardDescription>Applications that reached Screening in this range.</CardDescription>
      </CardHeader>
      <CardContent>
        {funnel.isPending ? (
          <Skeleton className="h-12 w-24" role="status" aria-busy="true" aria-label="Loading calls" />
        ) : (
          <div className="text-5xl font-semibold tabular-nums" aria-label={`${calls ?? 0} interview calls`}>
            {calls ?? 0}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function FunnelCard({ funnel }: { funnel: UseQueryResult<Funnel> }) {
  const max = Math.max(0, ...(funnel.data?.stages.map((s) => s.count) ?? []))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Funnel</CardTitle>
        <CardDescription>How many applications reached each stage, and the share that moved on from the stage before.</CardDescription>
      </CardHeader>
      <CardContent>
        {funnel.isPending ? (
          <Skeleton className="h-40" role="status" aria-busy="true" aria-label="Loading funnel" />
        ) : funnel.isError ? (
          <ErrorState error={funnel.error} onRetry={() => funnel.refetch()} />
        ) : (
          <ol className="grid gap-3" aria-label="Funnel stages">
            {funnel.data.stages.map((s) => (
              <li key={s.status} className="grid grid-cols-[6.5rem_1fr_auto] items-center gap-3 text-sm" aria-label={s.status}>
                <StatusBadge status={s.status} className="justify-self-start" />
                <Bar value={s.count} max={max} />
                <span className="tabular-nums">
                  <span className="font-medium">{s.count}</span>
                  <span className="ml-2 inline-block w-14 text-right text-xs text-muted-foreground">{s.conversion_from_prev == null ? '' : `${pct(s.conversion_from_prev)} of prev`}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
