import { useState } from 'react'
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { ChevronDown, ChevronRight, GripVertical } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CLOSED, type ApplicationOut, type AppStatus } from '@/api/client'
import { SOURCE_LABEL } from '@/components/lead-format'
import { NativeSelect } from '@/components/native-select'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { relativeDay } from '@/components/time'
import { allowedTargets, BOARD, CLOSED_COLUMN } from './transitions'

type Props = { apps: ApplicationOut[]; onMove: (app: ApplicationOut, to: AppStatus) => void }

function CardBody({ app }: { app: ApplicationOut }) {
  return (
    <>
      <div className="truncate font-medium" title={app.company}>
        {app.company}
      </div>
      <div className="truncate text-xs text-muted-foreground" title={app.title}>
        {app.title}
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        {app.applied_at && <span>Applied {relativeDay(app.applied_at)}</span>}
        <span>{SOURCE_LABEL[app.source]}</span>
        {app.resume_variant && <span>CV {app.resume_variant}</span>}
      </div>
    </>
  )
}

function KanbanCard({ app, onMove }: { app: ApplicationOut; onMove: Props['onMove'] }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({ id: app.id })
  const targets = allowedTargets(app.status)
  return (
    <li ref={setNodeRef} className={cn('relative min-w-0 rounded-lg border bg-card p-2.5 text-sm shadow-xs', isDragging && 'opacity-40')}>
      <div className="flex items-start gap-1">
        <button
          type="button"
          aria-label={`Drag ${app.company}`}
          className="relative z-10 -ml-1 shrink-0 cursor-grab touch-none rounded p-0.5 text-muted-foreground hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          {...attributes}
          {...listeners}
        >
          <GripVertical className="size-4" aria-hidden />
        </button>
        <div className="min-w-0 flex-1">
          <Link to={`/jobs/${app.lead_id}`} aria-label={`${app.company}: ${app.title}`} className="after:absolute after:inset-0">
            <CardBody app={app} />
          </Link>
        </div>
      </div>
      {targets.length > 0 && (
        <div className="relative z-10 mt-2">
          <NativeSelect
            aria-label={`Move ${app.company} to`}
            value=""
            className="h-7 text-xs"
            onChange={(e) => {
              if (e.target.value) onMove(app, e.target.value as AppStatus)
            }}
          >
            <option value="">Move to…</option>
            {targets.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </NativeSelect>
        </div>
      )}
    </li>
  )
}

function Zone({ status, apps, active, onMove, heading = 'h2' }: { status: AppStatus; apps: ApplicationOut[]; active: ApplicationOut | null; onMove: Props['onMove']; heading?: 'h2' | 'h3' }) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  const valid = active ? allowedTargets(active.status).includes(status) : false
  const H = heading
  return (
    <section
      ref={setNodeRef}
      aria-label={`${status} column`}
      className={cn('rounded-xl border bg-muted/30 p-2 transition-colors', active && valid && 'border-primary/50 bg-primary/5', active && !valid && active.status !== status && 'opacity-50', isOver && valid && 'ring-2 ring-primary')}
    >
      <H className="mb-2 flex items-center gap-2 px-1 text-sm font-medium">
        {status}
        <Badge variant="secondary">{apps.length}</Badge>
      </H>
      {apps.length === 0 && <p className="px-1 pb-1 text-xs text-muted-foreground">None</p>}
      <ul className="grid grid-cols-[minmax(0,1fr)] gap-2" aria-label={`${status} applications`}>
        {apps.map((a) => (
          <KanbanCard key={a.id} app={a} onMove={onMove} />
        ))}
      </ul>
    </section>
  )
}

/** Board. Drag by the grip (pointer or keyboard: Space, arrows, Space); the "Move to…" select is the plain fallback. */
export function Kanban({ apps, onMove }: Props) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor))
  const [active, setActive] = useState<ApplicationOut | null>(null)
  const [closedOpen, setClosedOpen] = useState(false)
  const by = (s: AppStatus) => apps.filter((a) => a.status === s)
  const closedCount = apps.filter((a) => CLOSED.includes(a.status)).length

  const end = (e: DragEndEvent) => {
    const app = apps.find((a) => a.id === e.active.id)
    setActive(null)
    if (app && e.over) onMove(app, e.over.id as AppStatus)
  }
  const start = (e: DragStartEvent) => setActive(apps.find((a) => a.id === e.active.id) ?? null)
  // The collapsed Closed column opens while dragging so Rejected / Withdrawn / ... can be dropped on.
  const showClosed = closedOpen || active !== null

  return (
    <DndContext sensors={sensors} onDragStart={start} onDragEnd={end} onDragCancel={() => setActive(null)}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:overflow-x-auto md:pb-2">
        {BOARD.map((s) => (
          <div key={s} className="min-w-0 md:min-w-40 md:flex-1">
            <Zone status={s} apps={by(s)} active={active} onMove={onMove} />
          </div>
        ))}
        <div className="min-w-0 md:min-w-40 md:flex-1">
          <button
            type="button"
            aria-expanded={showClosed}
            onClick={() => setClosedOpen((o) => !o)}
            className="mb-2 flex w-full items-center gap-2 rounded-xl border bg-muted/30 px-3 py-2 text-sm font-medium"
          >
            {showClosed ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
            Closed
            <Badge variant="secondary">{closedCount}</Badge>
          </button>
          {showClosed && (
            <div className="grid gap-2">
              {CLOSED_COLUMN.map((s) => (
                <Zone key={s} status={s} apps={by(s)} active={active} onMove={onMove} heading="h3" />
              ))}
            </div>
          )}
        </div>
      </div>
      <DragOverlay>
        {active && (
          <div className="rounded-lg border bg-card p-2.5 text-sm shadow-lg">
            <CardBody app={active} />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  )
}
