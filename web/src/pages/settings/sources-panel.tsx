import { Play } from 'lucide-react'
import { useRunIntake } from '@/app/lead-actions'
import { ErrorState } from '@/components/query-states'
import { fmtDateTime } from '@/components/format'
import { SOURCE_LABEL } from '@/components/lead-format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { usePatchSource, useSources } from './use-settings'
import type { Source } from '@/api/client'

const label = (s: string) => SOURCE_LABEL[s as Source] ?? s

export function SourcesPanel() {
  const sources = useSources()
  const patch = usePatchSource()
  const intake = useRunIntake()
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sources</CardTitle>
        <CardDescription>A source that keeps failing pauses itself. Unpause it once the cause is fixed.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div>
          <Button size="sm" disabled={intake.isPending} onClick={() => intake.mutate()}>
            <Play /> Run intake now
          </Button>
        </div>
        {sources.isPending ? (
          <Skeleton className="h-48" role="status" aria-busy="true" aria-label="Loading sources" />
        ) : sources.isError ? (
          <ErrorState error={sources.error} onRetry={() => sources.refetch()} />
        ) : (
          <div className="overflow-x-auto rounded-lg border">
            <Table className="min-w-[44rem]">
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Enabled</TableHead>
                  <TableHead>Last run</TableHead>
                  <TableHead>Last ok</TableHead>
                  <TableHead className="text-right">Count</TableHead>
                  <TableHead>Health</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.data.map((s) => {
                  const paused = s.paused_until != null || s.consecutive_failures > 0
                  return (
                    <TableRow key={s.source}>
                      <TableCell className="font-medium">{label(s.source)}</TableCell>
                      <TableCell>
                        <Switch
                          size="sm"
                          aria-label={`Enable ${label(s.source)}`}
                          checked={s.enabled}
                          disabled={patch.isPending}
                          onCheckedChange={(enabled) => patch.mutate({ source: s.source, enabled })}
                        />
                      </TableCell>
                      <TableCell>{s.last_run_at ? fmtDateTime(s.last_run_at) : '—'}</TableCell>
                      <TableCell>{s.last_ok_at ? fmtDateTime(s.last_ok_at) : '—'}</TableCell>
                      <TableCell className="text-right tabular-nums">{s.last_count}</TableCell>
                      <TableCell>
                        {paused ? (
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="destructive">{s.paused_until ? `Paused until ${fmtDateTime(s.paused_until)}` : `${s.consecutive_failures} failures`}</Badge>
                            <Button size="xs" variant="outline" disabled={patch.isPending} aria-label={`Unpause ${label(s.source)}`} onClick={() => patch.mutate({ source: s.source, unpause: true })}>
                              Unpause
                            </Button>
                          </div>
                        ) : (
                          <Badge variant="secondary" className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
                            OK
                          </Badge>
                        )}
                        {s.last_error && <p className="mt-1 max-w-64 text-xs text-destructive">{s.last_error}</p>}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
