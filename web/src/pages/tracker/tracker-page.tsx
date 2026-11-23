import { useState } from 'react'
import { Download, Search } from 'lucide-react'
import { toast } from 'sonner'
import { Link, useSearchParams } from 'react-router-dom'
import { CLOSED, PIPELINE, type ApplicationOut, type AppStatus } from '@/api/client'
import { NativeSelect } from '@/components/native-select'
import { PageHeader } from '@/components/page-header'
import { EmptyState, ErrorState } from '@/components/query-states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Kanban } from './kanban'
import { RejectDialog } from './reject-dialog'
import { TrackerTable } from './tracker-table'
import { allowedTargets, BOARD } from './transitions'
import { useApplications, useFiltered, useMoveApplication } from './use-tracker'

const PRE_APPLY: AppStatus[] = ['Shortlisted', 'Ready']
const INTERVIEWING: AppStatus[] = ['Screening', 'Technical', 'Final']

function Summary({ apps }: { apps: ApplicationOut[] }) {
  const count = (pred: (a: ApplicationOut) => boolean) => apps.filter(pred).length
  const stats = [
    { label: 'Waiting for a reply', value: count((a) => a.status === 'Applied'), hint: 'Applied, no response yet' },
    { label: 'Interviewing', value: count((a) => INTERVIEWING.includes(a.status)), hint: 'Screening, technical or final round' },
    { label: 'Offers', value: count((a) => a.status === 'Offer' || a.status === 'Accepted'), hint: 'Offers received' },
    { label: 'Closed', value: count((a) => CLOSED.includes(a.status) && a.applied_at != null), hint: 'Rejected, ghosted or withdrawn after applying' },
  ]
  return (
    <dl className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
      {stats.map((s) => (
        <div key={s.label} className="rounded-xl border p-3" title={s.hint}>
          <dt className="text-xs text-muted-foreground">{s.label}</dt>
          <dd className="text-2xl font-semibold tabular-nums">{s.value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function TrackerPage() {
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'table' ? 'table' : 'board'
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<AppStatus | ''>('')
  const apps = useApplications()
  const move = useMoveApplication()
  const [rejecting, setRejecting] = useState<ApplicationOut | null>(null)
  const shown = useFiltered(apps.data, { q, status })
  const waiting = shown.filter((a) => PRE_APPLY.includes(a.status)).length

  const request = (app: ApplicationOut, to: AppStatus) => {
    if (to === app.status) return
    if (!allowedTargets(app.status).includes(to)) {
      toast.error(`${app.company} can't move from ${app.status} to ${to}`)
      return
    }
    if (to === 'Rejected') setRejecting(app)
    else move.mutate({ app, to })
  }

  return (
    <>
      <PageHeader
        title="Applications"
        description="Every job you applied to, by stage. Drag a card or use Move to… when something changes."
        actions={
          <Button asChild variant="outline" size="sm">
            <a href="/api/applications/export.csv" download="applications.csv">
              <Download /> Export CSV
            </a>
          </Button>
        }
      />
      <div className="mb-4 flex flex-wrap items-end gap-3" role="search" aria-label="Filter applications">
        <Tabs value={view} onValueChange={(v) => setParams(v === 'table' ? { view: 'table' } : {}, { replace: true })}>
          <TabsList>
            <TabsTrigger value="board">Board</TabsTrigger>
            <TabsTrigger value="table">Table</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="relative min-w-48 flex-1 sm:max-w-72">
          <Search className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input type="search" aria-label="Search company or title" placeholder="Search company or title" className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="w-44">
          <NativeSelect aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value as AppStatus | '')}>
            <option value="">All statuses</option>
            {(view === 'table' ? [...PIPELINE, ...CLOSED] : [...BOARD, ...CLOSED]).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>

      {apps.data && apps.data.length > 0 && <Summary apps={apps.data} />}
      {apps.isPending ? (
        <div className="grid gap-3 md:grid-cols-4" role="status" aria-busy="true" aria-label="Loading tracker">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      ) : apps.isError ? (
        <ErrorState error={apps.error} onRetry={() => apps.refetch()} />
      ) : apps.data.length === 0 ? (
        <EmptyState title="No applications yet" hint="Shortlist a job, apply on the site and mark it applied: it shows up here." />
      ) : view === 'table' ? (
        shown.length ? <TrackerTable apps={shown} /> : <EmptyState title="No applications match" />
      ) : (
        <>
          {waiting > 0 && (
            <p className="mb-3 text-sm text-muted-foreground">
              {waiting} shortlisted job{waiting === 1 ? ' is' : 's are'} not applied to yet.{' '}
              <Link to="/leads?tab=apply" className="font-medium text-foreground underline underline-offset-2">
                Go to To apply
              </Link>
            </p>
          )}
          <Kanban apps={shown.filter((a) => !PRE_APPLY.includes(a.status))} onMove={request} />
        </>
      )}

      <RejectDialog
        app={rejecting}
        pending={move.isPending}
        onClose={() => setRejecting(null)}
        onConfirm={(stage) => {
          if (rejecting) move.mutate({ app: rejecting, to: 'Rejected', rejected_at_stage: stage }, { onSettled: () => setRejecting(null) })
        }}
      />
    </>
  )
}
