import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ErrorState } from '@/components/query-states'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Bar } from './bars'
import { useRejects, useRestoreLead, type Range } from './use-analytics'

/** Everything the prefilter dropped, by reason. If a reason looks too greedy, restore a sample lead and loosen the rule. */
export function RejectsCard({ range }: { range: Range }) {
  const q = useRejects(range)
  const restore = useRestoreLead()
  const [restored, setRestored] = useState<Set<number>>(new Set())
  const rows = q.data ? [...q.data].sort((a, b) => b.count - a.count) : []
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Reject audit</CardTitle>
        <CardDescription>Why leads were dropped before you saw them. Restore a sample to check the rule is not too strict.</CardDescription>
      </CardHeader>
      <CardContent>
        {q.isPending ? (
          <Skeleton className="h-40" role="status" aria-busy="true" aria-label="Loading reject audit" />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing was dropped in this range.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table className="min-w-[36rem]">
              <TableHeader>
                <TableRow>
                  <TableHead>Reason</TableHead>
                  <TableHead className="text-right">Dropped</TableHead>
                  <TableHead className="w-1/4">Share</TableHead>
                  <TableHead>Sample leads</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.reason}>
                    <TableCell className="font-medium capitalize">{r.reason}</TableCell>
                    <TableCell className="text-right tabular-nums">{r.count}</TableCell>
                    <TableCell>
                      <Bar value={r.count} max={max} />
                    </TableCell>
                    <TableCell>
                      {r.sample_lead_ids.length === 0 ? (
                        <span className="text-muted-foreground">—</span>
                      ) : (
                        <ul className="flex flex-wrap gap-x-4 gap-y-1">
                          {r.sample_lead_ids.map((id) => (
                            <li key={id} className="flex items-center gap-1.5">
                              <Link to={`/jobs/${id}`} className="hover:underline">
                                Lead #{id}
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
                          ))}
                        </ul>
                      )}
                    </TableCell>
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
