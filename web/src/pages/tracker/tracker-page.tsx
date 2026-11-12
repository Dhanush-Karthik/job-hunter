import { useState } from 'react'
import { Download, Search } from 'lucide-react'
import { toast } from 'sonner'
import { useSearchParams } from 'react-router-dom'
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
import { allowedTargets } from './transitions'
import { useApplications, useFiltered, useMoveApplication } from './use-tracker'

export function TrackerPage() {
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'table' ? 'table' : 'board'
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<AppStatus | ''>('')
  const apps = useApplications()
  const move = useMoveApplication()
  const [rejecting, setRejecting] = useState<ApplicationOut | null>(null)
  const shown = useFiltered(apps.data, { q, status })

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
        title="Tracker"
        description="Drag a card, or use its Move to… menu. Rejections ask for the stage."
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
            {[...PIPELINE, ...CLOSED].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>

      {apps.isPending ? (
        <div className="grid gap-3 md:grid-cols-4" role="status" aria-busy="true" aria-label="Loading tracker">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      ) : apps.isError ? (
        <ErrorState error={apps.error} onRetry={() => apps.refetch()} />
      ) : apps.data.length === 0 ? (
        <EmptyState title="Nothing tracked yet" hint="Shortlist a lead and it lands in the first column." />
      ) : view === 'table' ? (
        shown.length ? <TrackerTable apps={shown} /> : <EmptyState title="No applications match" />
      ) : (
        <Kanban apps={shown} onMove={request} />
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
