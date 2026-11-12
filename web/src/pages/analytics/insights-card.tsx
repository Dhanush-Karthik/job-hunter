import { CircleAlert, CircleCheck, Info, type LucideIcon } from 'lucide-react'
import type { Insight } from '@/api/client'
import { ErrorState } from '@/components/query-states'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useInsights, type Range } from './use-analytics'

const STYLE: Record<Insight['severity'], { Icon: LucideIcon; tone: string; label: string }> = {
  good: { Icon: CircleCheck, tone: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-300', label: 'Good' },
  warn: { Icon: CircleAlert, tone: 'border-amber-500/40 bg-amber-500/10 text-amber-800 dark:text-amber-300', label: 'Warning' },
  info: { Icon: Info, tone: 'border-border bg-muted/40 text-foreground', label: 'Info' },
}

export function InsightsCard({ range }: { range: Range }) {
  const q = useInsights(range)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Insights</CardTitle>
        <CardDescription>Rule-based reading of your own numbers: what to do more or less of.</CardDescription>
      </CardHeader>
      <CardContent>
        {q.isPending ? (
          <Skeleton className="h-24" role="status" aria-busy="true" aria-label="Loading insights" />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : q.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">Not enough data yet. Insights appear after a few applications.</p>
        ) : (
          <ul className="grid gap-2" aria-label="Insights">
            {q.data.map((i) => {
              const { Icon, tone, label } = STYLE[i.severity]
              return (
                <li key={`${i.kind}-${i.text}`} data-severity={i.severity} className={cn('flex items-start gap-2 rounded-lg border p-3 text-sm', tone)}>
                  <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
                  <span className="sr-only">{label}: </span>
                  <span>{i.text}</span>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
