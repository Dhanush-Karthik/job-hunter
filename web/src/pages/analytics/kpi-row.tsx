import type { UseQueryResult } from '@tanstack/react-query'
import type { Funnel } from '@/api/client'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { callsOf, pct } from './calc'
import { useResponseTimes } from './use-analytics'

/** Headline numbers for the range: applications, calls, call rate, and how long companies take to answer. */
export function KpiRow({ funnel }: { funnel: UseQueryResult<Funnel> }) {
  const calls = callsOf(funnel.data) ?? 0
  const applied = funnel.data?.stages.find((s) => s.status === 'Applied')?.count ?? 0
  const rt = useResponseTimes()
  const days = (d: number | null | undefined) => (d == null ? '—' : `${Math.round(d * 10) / 10} d`)
  const stats = [
    { label: 'Applied', value: String(applied), hint: 'Applications sent in this range' },
    { label: 'Interview calls', value: String(calls), aria: `${calls} interview calls`, hint: 'Applications that reached Screening' },
    { label: 'Call rate', value: applied ? pct(calls / applied) : '—', hint: 'Interview calls per application' },
    {
      label: 'Typical reply time',
      value: days(rt.data?.median_days_to_first_response),
      hint: `Median days from applying to the first reply (90% within ${days(rt.data?.p90_days_to_first_response)}, ${rt.data?.samples ?? 0} replies)`,
    },
  ]
  return (
    <Card>
      <CardContent>
        {funnel.isPending ? (
          <Skeleton className="h-16" role="status" aria-busy="true" aria-label="Loading calls" />
        ) : (
          <dl className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            {stats.map((s) => (
              <div key={s.label} title={s.hint}>
                <dt className="text-sm text-muted-foreground">{s.label}</dt>
                <dd className="text-3xl font-semibold tabular-nums" aria-label={s.aria}>
                  {s.value}
                </dd>
                <p className="mt-0.5 text-xs text-muted-foreground">{s.hint}</p>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  )
}
