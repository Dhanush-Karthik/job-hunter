import { useState } from 'react'
import type { RunOut } from '@/api/client'
import { EmptyState, ErrorState } from '@/components/query-states'
import { fmtDateTime } from '@/components/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { useCancelRun, useRunLog, useRuns } from './use-settings'

const TONE: Record<RunOut['state'], string> = {
  queued: '',
  running: 'bg-sky-500/15 text-sky-700 dark:text-sky-400',
  succeeded: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  failed: 'bg-destructive/10 text-destructive',
  cancelled: '',
}
const kind = (k: string) => k.replaceAll('_', ' ')

function LogView({ id }: { id: number }) {
  const log = useRunLog(id)
  if (log.isPending) return <Skeleton className="h-24" role="status" aria-busy="true" aria-label="Loading log" />
  if (log.isError) return <ErrorState error={log.error} onRetry={() => log.refetch()} />
  return (
    <div>
      <pre aria-label={`Log of run ${id}`} className="max-h-64 overflow-auto rounded-lg bg-muted p-3 text-xs whitespace-pre-wrap">
        {log.data.text || '(empty log)'}
      </pre>
      {log.data.truncated && <p className="mt-1 text-xs text-muted-foreground">Showing the end of the log only.</p>}
    </div>
  )
}

export function RunLogsPanel() {
  const runs = useRuns()
  const cancel = useCancelRun()
  const [open, setOpen] = useState<number | null>(null)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Run logs</CardTitle>
        <CardDescription>Intake, evaluation, CV and follow-up runs. Open one to read its log.</CardDescription>
      </CardHeader>
      <CardContent>
        {runs.isPending ? (
          <Skeleton className="h-32" role="status" aria-busy="true" aria-label="Loading runs" />
        ) : runs.isError ? (
          <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
        ) : runs.data.length === 0 ? (
          <EmptyState title="No runs yet" />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table className="min-w-[44rem]">
              <TableHeader>
                <TableRow>
                  <TableHead>Run</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.data.slice(0, 30).map((r) => {
                  const active = r.state === 'queued' || r.state === 'running'
                  return (
                    <TableRow key={r.id}>
                      <TableCell className="font-medium capitalize">
                        {kind(r.kind)} <span className="font-normal text-muted-foreground">#{r.id}</span>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className={cn(TONE[r.state])}>
                          {r.state}
                        </Badge>
                      </TableCell>
                      <TableCell>{fmtDateTime(r.started_at ?? r.created_at)}</TableCell>
                      <TableCell className="max-w-64 text-xs">{r.error ? <span className="text-destructive">{r.error}</span> : (r.summary ?? '—')}</TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button size="xs" variant="outline" aria-expanded={open === r.id} aria-label={`${open === r.id ? 'Hide' : 'Show'} log of run ${r.id}`} onClick={() => setOpen(open === r.id ? null : r.id)}>
                            {open === r.id ? 'Hide log' : 'Log'}
                          </Button>
                          {active && (
                            <Button size="xs" variant="ghost" disabled={cancel.isPending} aria-label={`Cancel run ${r.id}`} onClick={() => cancel.mutate(r.id)}>
                              Cancel
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
        {open != null && (
          <div className="mt-3">
            <LogView id={open} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
