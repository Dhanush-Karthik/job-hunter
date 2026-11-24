import { ErrorState } from '@/components/query-states'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useWeekly } from './use-analytics'

const week = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
const CHART_H = 140

/** One column per week: bar = applications, tick = the weekly target, green number = interview calls. */
export function WeeklyCard() {
  const weekly = useWeekly()
  const rows = weekly.data ?? []
  const max = Math.max(1, ...rows.map((w) => Math.max(w.applied, w.applied_target)))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Weekly pace</CardTitle>
        <CardDescription>Applications against the weekly target, newest week on the right. Green is a week that hit the target.</CardDescription>
      </CardHeader>
      <CardContent>
        {weekly.isPending ? (
          <Skeleton className="h-40" role="status" aria-busy="true" aria-label="Loading weekly" />
        ) : weekly.isError ? (
          <ErrorState error={weekly.error} onRetry={() => weekly.refetch()} />
        ) : (
          <ol className="flex items-end gap-2 overflow-x-auto pb-1" aria-label="Weekly pace">
            {rows.map((w) => {
              const hit = w.applied_target > 0 && w.applied >= w.applied_target
              return (
                <li
                  key={w.week_start}
                  className="flex min-w-14 flex-1 flex-col items-center gap-1.5 text-xs"
                  aria-label={`Week of ${week(w.week_start)}: ${w.applied} of ${w.applied_target} applications, ${w.referrals} of ${w.referrals_target} referrals, ${w.calls} calls`}
                >
                  <span className={cn('font-medium tabular-nums', w.calls > 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-muted-foreground')} title="Interview calls">
                    {w.calls} {w.calls === 1 ? 'call' : 'calls'}
                  </span>
                  <div className="relative w-full max-w-14" style={{ height: CHART_H }} aria-hidden>
                    <div className="absolute inset-x-0 bottom-0 rounded-t-md bg-muted" style={{ height: `${(w.applied_target / max) * 100}%` }} />
                    <div className={cn('absolute inset-x-1 bottom-0 rounded-t-md', hit ? 'bg-emerald-500' : 'bg-primary')} style={{ height: `${Math.max(w.applied > 0 ? 2 : 0, (w.applied / max) * 100)}%` }} />
                  </div>
                  <span className="font-medium tabular-nums">
                    {w.applied}
                    <span className="text-muted-foreground"> / {w.applied_target}</span>
                  </span>
                  <span className="text-muted-foreground">{week(w.week_start)}</span>
                </li>
              )
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
