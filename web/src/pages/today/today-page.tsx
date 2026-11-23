import { ArrowRight, Minus, TrendingDown, TrendingUp, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { TodaySummary } from '@/api/client'
import { useNavCounts } from '@/app/nav-counts'
import { PageHeader } from '@/components/page-header'
import { ErrorState } from '@/components/query-states'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { ActionQueue } from './action-queue'
import { HotLeads } from './hot-leads'
import { useToday } from './use-today'

function greeting(now = new Date()) {
  const h = now.getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

function Calls({ data }: { data: TodaySummary }) {
  const diff = data.interview_calls_week - data.interview_calls_prev_week
  const Trend = diff > 0 ? TrendingUp : diff < 0 ? TrendingDown : Minus
  return (
    <div className="grid content-start gap-1">
      <div className="text-sm text-muted-foreground">Interview calls this week</div>
      <div className="text-4xl font-semibold tabular-nums" aria-label={`${data.interview_calls_week} interview calls this week`}>
        {data.interview_calls_week}
      </div>
      <p
        className={cn(
          'flex items-center gap-1 text-xs',
          diff > 0 ? 'text-emerald-600 dark:text-emerald-400' : diff < 0 ? 'text-destructive' : 'text-muted-foreground',
        )}
      >
        <Trend className="size-3.5" aria-hidden />
        {diff === 0 ? 'Same as' : `${diff > 0 ? '+' : ''}${diff} vs`} last week ({data.interview_calls_prev_week})
      </p>
    </div>
  )
}

function Meter({ label, value, target, unit }: { label: string; value: number; target: number; unit: string }) {
  const pct = target > 0 ? Math.min(100, Math.round((value / target) * 100)) : 0
  const left = Math.max(0, target - value)
  return (
    <div className="grid content-start gap-1.5">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-4xl font-semibold tabular-nums">{value}</span>
        <span className="text-sm text-muted-foreground tabular-nums">/ {target}</span>
      </div>
      <Progress value={pct} aria-label={`${label}: ${value} of ${target}`} className="h-1.5" />
      <p className="text-xs text-muted-foreground">{left > 0 ? `${left} more ${unit} to hit the weekly goal` : 'Weekly goal reached'}</p>
    </div>
  )
}

function ProblemsBanner({ health }: { health: TodaySummary['health'] }) {
  const down = health.filter((h) => !h.ok)
  if (!down.length) return null
  return (
    <div role="alert" className="flex flex-wrap items-center gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
      <TriangleAlert className="size-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="font-medium">Something needs attention: </span>
        {down.map((h) => `${h.name}${h.detail ? ` (${h.detail})` : ''}`).join(', ')}
      </span>
      <Link to="/settings?tab=system" className="font-medium underline underline-offset-2">
        Open System
      </Link>
    </div>
  )
}

function TodaySkeleton() {
  return (
    <div className="grid gap-4" aria-busy="true" aria-label="Loading today">
      <Skeleton className="h-32" />
      <div className="grid gap-4 lg:grid-cols-5">
        <Skeleton className="h-72 lg:col-span-2" />
        <Skeleton className="h-72 lg:col-span-3" />
      </div>
    </div>
  )
}

function TodayBody({ data }: { data: TodaySummary }) {
  const { toApply } = useNavCounts()
  return (
    <div className="grid gap-4">
      <ProblemsBanner health={data.health} />
      <Card>
        <CardContent className="grid gap-6 sm:grid-cols-3">
          <Meter label="Applied this week" value={data.applied_week} target={data.applied_target} unit="applications" />
          <Meter label="Referrals asked" value={data.referrals_week} target={data.referrals_target} unit="referral requests" />
          <Calls data={data} />
        </CardContent>
      </Card>
      <div className="grid items-start gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>To do</CardTitle>
            <CardDescription>Most important first.</CardDescription>
          </CardHeader>
          <CardContent>
            <ActionQueue actions={data.actions} toApply={toApply} />
          </CardContent>
        </Card>
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Fresh matches</CardTitle>
            <CardDescription>Best new jobs from the last 48 hours. Shortlist the ones worth applying to.</CardDescription>
            <CardAction>
              <Link to="/leads" className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
                All jobs <ArrowRight className="size-3.5" aria-hidden />
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent>
            <HotLeads leads={data.fresh_hot_leads} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export function TodayPage() {
  const today = useToday()
  return (
    <>
      <PageHeader title="Home" description={`${greeting()}. Here is what needs you today.`} />
      {today.isPending ? (
        <TodaySkeleton />
      ) : today.isError ? (
        <ErrorState error={today.error} onRetry={() => today.refetch()} title="Could not load Home" />
      ) : (
        <TodayBody data={today.data} />
      )}
    </>
  )
}
