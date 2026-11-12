import { ErrorState } from '@/components/query-states'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { Bar } from './bars'
import { useResponseTimes, useWeekly } from './use-analytics'

const week = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
const days = (d: number | null | undefined) => (d == null ? '—' : `${Math.round(d * 10) / 10} days`)

function Cell({ value, target }: { value: number; target: number }) {
  const hit = target > 0 && value >= target
  return (
    <TableCell className="text-right tabular-nums">
      <span className={cn(hit && 'font-medium text-emerald-700 dark:text-emerald-400')}>{value}</span>
      <span className="text-muted-foreground"> / {target}</span>
    </TableCell>
  )
}

export function WeeklyCard() {
  const weekly = useWeekly()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Weekly pace</CardTitle>
        <CardDescription>Applications and referrals against your weekly targets, newest week last.</CardDescription>
      </CardHeader>
      <CardContent>
        {weekly.isPending ? (
          <Skeleton className="h-40" role="status" aria-busy="true" aria-label="Loading weekly" />
        ) : weekly.isError ? (
          <ErrorState error={weekly.error} onRetry={() => weekly.refetch()} />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table className="min-w-[36rem]">
              <TableHeader>
                <TableRow>
                  <TableHead>Week of</TableHead>
                  <TableHead className="text-right">Applied / target</TableHead>
                  <TableHead className="w-1/4">Applied</TableHead>
                  <TableHead className="text-right">Referrals / target</TableHead>
                  <TableHead className="text-right">Calls</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {weekly.data.map((w) => (
                  <TableRow key={w.week_start}>
                    <TableCell>{week(w.week_start)}</TableCell>
                    <Cell value={w.applied} target={w.applied_target} />
                    <TableCell>
                      <Bar value={w.applied} max={Math.max(w.applied, w.applied_target)} />
                    </TableCell>
                    <Cell value={w.referrals} target={w.referrals_target} />
                    <TableCell className="text-right tabular-nums">{w.calls}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function ResponseTimeCard() {
  const rt = useResponseTimes()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Time to first response</CardTitle>
        <CardDescription>From Applied to the first reply of any kind.</CardDescription>
      </CardHeader>
      <CardContent>
        {rt.isPending ? (
          <Skeleton className="h-16" role="status" aria-busy="true" aria-label="Loading response times" />
        ) : rt.isError ? (
          <ErrorState error={rt.error} onRetry={() => rt.refetch()} />
        ) : (
          <dl className="grid grid-cols-3 gap-3 text-sm">
            <div>
              <dt className="text-muted-foreground">Median</dt>
              <dd className="text-xl font-semibold tabular-nums">{days(rt.data.median_days_to_first_response)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">90th percentile</dt>
              <dd className="text-xl font-semibold tabular-nums">{days(rt.data.p90_days_to_first_response)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Samples</dt>
              <dd className="text-xl font-semibold tabular-nums">{rt.data.samples}</dd>
            </div>
          </dl>
        )}
      </CardContent>
    </Card>
  )
}
