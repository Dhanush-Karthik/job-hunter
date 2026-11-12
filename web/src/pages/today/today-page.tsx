import { Loader2, Minus, Play, TrendingDown, TrendingUp } from 'lucide-react'
import type { TodaySummary } from '@/api/client'
import { useRunIntake } from '@/app/lead-actions'
import { PageHeader } from '@/components/page-header'
import { ErrorState } from '@/components/query-states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { ActionQueue } from './action-queue'
import { HotLeads } from './hot-leads'
import { useToday } from './use-today'

function CallsKpi({ data }: { data: TodaySummary }) {
  const diff = data.interview_calls_week - data.interview_calls_prev_week
  const Trend = diff > 0 ? TrendingUp : diff < 0 ? TrendingDown : Minus
  return (
    <Card>
      <CardHeader>
        <CardTitle>Interview calls this week</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-5xl font-semibold tabular-nums" aria-label={`${data.interview_calls_week} interview calls this week`}>
          {data.interview_calls_week}
        </div>
        <p
          className={cn(
            'mt-2 flex items-center gap-1 text-sm',
            diff > 0 ? 'text-emerald-600 dark:text-emerald-400' : diff < 0 ? 'text-destructive' : 'text-muted-foreground',
          )}
        >
          <Trend className="size-4" aria-hidden />
          {diff > 0 ? '+' : ''}
          {diff} vs previous week ({data.interview_calls_prev_week})
        </p>
      </CardContent>
    </Card>
  )
}

function Meter({ label, value, target }: { label: string; value: number; target: number }) {
  const pct = target > 0 ? Math.min(100, Math.round((value / target) * 100)) : 0
  return (
    <div className="grid gap-1.5">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground tabular-nums">
          {value} / {target}
        </span>
      </div>
      <Progress value={pct} aria-label={`${label}: ${value} of ${target}`} className="h-2" />
    </div>
  )
}

function Health({ health }: { health: TodaySummary['health'] }) {
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Service health">
      {health.map((h) => (
        <li
          key={h.name}
          title={h.detail ?? (h.ok ? 'ok' : 'down')}
          className={cn(
            'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
            h.ok ? 'text-foreground' : 'border-destructive/40 bg-destructive/5 text-destructive',
          )}
        >
          <span className={cn('size-2 rounded-full', h.ok ? 'bg-emerald-500' : 'bg-destructive')} aria-hidden />
          {h.name}
          <span className="sr-only">{h.ok ? 'ok' : 'problem'}</span>
          {!h.ok && h.detail && <span className="font-normal text-muted-foreground">· {h.detail}</span>}
        </li>
      ))}
    </ul>
  )
}

function TodaySkeleton() {
  return (
    <div className="grid gap-4" aria-busy="true" aria-label="Loading today">
      <div className="grid gap-4 md:grid-cols-3">
        <Skeleton className="h-36" />
        <Skeleton className="h-36 md:col-span-2" />
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <Skeleton className="h-72 lg:col-span-3" />
        <Skeleton className="h-72 lg:col-span-2" />
      </div>
    </div>
  )
}

function TodayBody({ data }: { data: TodaySummary }) {
  return (
    <div className="grid gap-4">
      <div className="grid gap-4 md:grid-cols-3">
        <CallsKpi data={data} />
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>This week vs target</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <Meter label="Applied" value={data.applied_week} target={data.applied_target} />
            <Meter label="Referrals" value={data.referrals_week} target={data.referrals_target} />
          </CardContent>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Fresh hot leads</CardTitle>
          </CardHeader>
          <CardContent>
            <HotLeads leads={data.fresh_hot_leads} />
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Action queue</CardTitle>
          </CardHeader>
          <CardContent>
            <ActionQueue actions={data.actions} />
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Service health</CardTitle>
        </CardHeader>
        <CardContent>
          <Health health={data.health} />
        </CardContent>
      </Card>
    </div>
  )
}

export function TodayPage() {
  const today = useToday()
  const intake = useRunIntake()

  return (
    <>
      <PageHeader
        title="Today"
        description="What moves interview calls today."
        actions={
          <Button onClick={() => intake.mutate()} disabled={intake.isPending}>
            {intake.isPending ? <Loader2 className="animate-spin" /> : <Play />} Run intake now
          </Button>
        }
      />
      {today.isPending ? (
        <TodaySkeleton />
      ) : today.isError ? (
        <ErrorState error={today.error} onRetry={() => today.refetch()} title="Could not load Today" />
      ) : (
        <TodayBody data={today.data} />
      )}
    </>
  )
}
