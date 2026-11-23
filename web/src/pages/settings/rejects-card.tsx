import { useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, unwrap, type RejectAuditRow } from '@/api/client'
import { NativeSelect } from '@/components/native-select'
import { ErrorState } from '@/components/query-states'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Bar } from '@/pages/analytics/bars'
import { RANGES, useRejects, useRestoreLead, type Range } from '@/pages/analytics/use-analytics'
import { groupReasons } from './reasons'

const TOP = 8

/** The sample jobs behind one reason, loaded only when the row is opened. */
function Samples({ ids }: { ids: number[] }) {
  const restore = useRestoreLead()
  const [restored, setRestored] = useState<Set<number>>(new Set())
  const leads = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['job', id],
      queryFn: async () => unwrap(await api.GET('/api/leads/{lead_id}', { params: { path: { lead_id: id } } })),
    })),
  })
  return (
    <ul className="grid gap-1.5 py-1 pl-6">
      {ids.map((id, i) => {
        const lead = leads[i].data
        return (
          <li key={id} className="flex flex-wrap items-center gap-2 text-sm">
            <Link to={`/jobs/${id}`} className="min-w-0 flex-1 truncate hover:underline">
              {lead ? (
                <>
                  <span className="font-medium">{lead.company}</span> <span className="text-muted-foreground">· {lead.title}{lead.location ? ` · ${lead.location}` : ''}</span>
                </>
              ) : (
                <span className="text-muted-foreground">Job #{id}</span>
              )}
            </Link>
            {restored.has(id) ? (
              <span className="text-xs text-emerald-700 dark:text-emerald-400">Restored</span>
            ) : (
              <Button
                size="xs"
                variant="outline"
                disabled={restore.isPending}
                aria-label={`Restore lead #${id}`}
                onClick={() => restore.mutate(id, { onSuccess: () => setRestored((s) => new Set(s).add(id)) })}
              >
                Restore
              </Button>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function Row({ r, max }: { r: RejectAuditRow; max: number }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="py-2">
      <button
        type="button"
        className="grid w-full grid-cols-[1rem_minmax(0,1fr)_6rem_3.5rem] items-center gap-3 text-left text-sm sm:grid-cols-[1rem_minmax(0,1fr)_10rem_3.5rem]"
        aria-expanded={open}
        disabled={r.sample_lead_ids.length === 0}
        onClick={() => setOpen((o) => !o)}
      >
        {r.sample_lead_ids.length ? open ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden /> : <span />}
        <span className="truncate font-medium">{r.reason}</span>
        <Bar value={r.count} max={max} />
        <span className="text-right tabular-nums">{r.count}</span>
      </button>
      {open && <Samples ids={r.sample_lead_ids} />}
    </li>
  )
}

/** Everything the automatic filters dropped, by reason. If a reason looks too greedy, check its examples and loosen the rule. */
export function RejectsCard() {
  const [range, setRange] = useState<Range>('30')
  const q = useRejects(range)
  const [all, setAll] = useState(false)
  const rows = groupReasons(q.data ?? [])
  const max = Math.max(1, ...rows.map((r) => r.count))
  const total = rows.reduce((n, r) => n + r.count, 0)
  return (
    <Card>
      <CardHeader>
        <CardTitle>What the filters removed</CardTitle>
        <CardDescription>
          {q.data ? `${total.toLocaleString()} jobs hidden. ` : ''}Open a reason to see examples; restore one if the rule got it wrong.
        </CardDescription>
        <CardAction>
          <NativeSelect aria-label="Filtered-out range" className="w-32" value={range} onChange={(e) => setRange(e.target.value as Range)}>
            {RANGES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </NativeSelect>
        </CardAction>
      </CardHeader>
      <CardContent>
        {q.isPending ? (
          <Skeleton className="h-40" role="status" aria-busy="true" aria-label="Loading reject audit" />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing was filtered out in this range.</p>
        ) : (
          <>
            <ul className="divide-y" aria-label="Filter reasons">
              {(all ? rows : rows.slice(0, TOP)).map((r) => (
                <Row key={r.reason} r={r} max={max} />
              ))}
            </ul>
            {rows.length > TOP && (
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => setAll((a) => !a)}>
                {all ? 'Show fewer' : `Show all ${rows.length} reasons`}
              </Button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
