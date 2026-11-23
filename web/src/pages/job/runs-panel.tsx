import { useState } from 'react'
import { ChevronDown, ChevronRight, CircleAlert, CircleCheck, CircleSlash, Loader2 } from 'lucide-react'
import type { RunOut } from '@/api/client'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { isActive, RUN_LABEL, useRunLog } from './use-job'

const ICON = {
  queued: <Loader2 className="size-4 animate-spin text-muted-foreground" aria-hidden />,
  running: <Loader2 className="size-4 animate-spin text-sky-600" aria-hidden />,
  succeeded: <CircleCheck className="size-4 text-emerald-600" aria-hidden />,
  failed: <CircleAlert className="size-4 text-destructive" aria-hidden />,
  cancelled: <CircleSlash className="size-4 text-muted-foreground" aria-hidden />,
}

function LogTail({ run }: { run: RunOut }) {
  const log = useRunLog(run.id, isActive(run), true)
  const text = log.data?.text.trimEnd() ?? ''
  const tail = text.split('\n').slice(-40).join('\n')
  return (
    <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-muted p-2 font-mono text-xs whitespace-pre-wrap" aria-label={`Log of run ${run.id}`}>
      {log.isPending ? 'Loading log…' : log.isError ? 'Could not load the log.' : tail || '(no output yet)'}
      {log.data?.truncated && '\n(earlier output truncated)'}
    </pre>
  )
}

function RunRow({ run }: { run: RunOut }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="py-2 text-sm">
      <div className="flex items-center gap-2">
        {ICON[run.state]}
        <span className="font-medium">
          {RUN_LABEL[run.kind]}
          {typeof run.params.variant === 'string' && ` ${run.params.variant}`}
        </span>
        <span className="text-muted-foreground">#{run.id} · {run.state}</span>
      </div>
      {run.error && <p className="mt-0.5 text-xs text-destructive">{run.error}</p>}
      {run.summary && <p className="mt-0.5 text-xs text-muted-foreground">{run.summary}</p>}
      <details onToggle={(e) => setOpen(e.currentTarget.open)} className="mt-1">
        <summary className="cursor-pointer text-xs text-muted-foreground select-none">Log</summary>
        {open && <LogTail run={run} />}
      </details>
    </li>
  )
}

/** Background tasks for this job (evaluation, CV, live check...). Folded unless something is running or just failed. */
export function RunsPanel({ runs }: { runs: RunOut[] }) {
  const [open, setOpen] = useState<boolean | null>(null)
  // Once something ran while the page was open, keep the log visible so the result does not vanish when it settles.
  const [watched, setWatched] = useState(false)
  const attention = runs.some(isActive) || runs[0]?.state === 'failed'
  if (attention && !watched) setWatched(true)
  if (!runs.length) return null
  const shown = open ?? (attention || watched)
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>
          <button type="button" className="flex w-full items-center gap-2 text-left" aria-expanded={shown} onClick={() => setOpen(!shown)}>
            {shown ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
            Activity log
            <span className="text-xs font-normal text-muted-foreground">{runs.length} task{runs.length === 1 ? '' : 's'}</span>
          </button>
        </CardTitle>
      </CardHeader>
      {shown && (
        <CardContent>
          <ul className="divide-y" aria-label="Runs for this lead">
            {runs.slice(0, 5).map((r) => (
              <RunRow key={r.id} run={r} />
            ))}
          </ul>
        </CardContent>
      )}
    </Card>
  )
}
