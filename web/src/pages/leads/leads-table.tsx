import { createColumnHelper, flexRender, rowSelectionFeature, tableFeatures, useTable, type RowSelectionState } from '@tanstack/react-table'
import { Link, useNavigate } from 'react-router-dom'
import type { LeadSummary } from '@/api/client'
import { SOURCE_LABEL, formatCtc, formatExp, formatPlace, isRejected, statusLabel } from '@/components/lead-format'
import { ExpText, FreshBadge, InboundBadge, ScoreCell } from '@/components/lead-parts'
import { StatusBadge } from '@/components/status-badge'
import { relativeDay } from '@/components/time'
import { Checkbox } from '@/components/ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useMediaQuery } from '@/components/use-media-query'
import { cn } from '@/lib/utils'
import { LeadCards } from './lead-cards'
import { RowActionButtons, type RowActions } from './row-actions'

export type { RowActions }

const features = tableFeatures({ rowSelectionFeature })
const col = createColumnHelper<typeof features, LeadSummary>()

/**
 * Fixed layout: every column but the job has a set width so the row (actions included) fits from 1024 px;
 * company and title truncate (full text in the tooltip). Below md the cards in lead-cards.tsx replace the table.
 */
const WIDTH: Record<string, string> = {
  select: 'w-10',
  score: 'w-28',
  exp: 'w-24',
  ctc: 'w-28',
  found: 'w-28',
  status: 'w-28',
  actions: 'w-28',
}
const HIDE: Record<string, string> = { found: 'hidden xl:table-cell', ctc: 'hidden lg:table-cell' }
const colClass = (id: string) => cn(WIDTH[id], HIDE[id])

const stop = (e: React.SyntheticEvent) => e.stopPropagation()

export type TableMode = 'review' | 'all'

function buildColumns(a: RowActions, mode: TableMode) {
  const cols = [
    col.display({
      id: 'select',
      header: ({ table }) => (
        <Checkbox
          aria-label="Select all leads on this page"
          checked={table.getIsAllRowsSelected() ? true : table.getIsSomeRowsSelected() ? 'indeterminate' : false}
          onCheckedChange={(v) => table.toggleAllRowsSelected(v === true)}
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          aria-label={`Select ${row.original.company} ${row.original.title}`}
          checked={row.getIsSelected()}
          onCheckedChange={(v) => row.toggleSelected(v === true)}
        />
      ),
    }),
    col.display({
      id: 'score',
      header: () => <span title="Match score 0-100, plus the AI fit score out of 5 once evaluated">Match</span>,
      cell: ({ row }) => <ScoreCell lead={row.original} />,
    }),
    col.display({
      id: 'job',
      header: 'Job',
      cell: ({ row }) => {
        const l = row.original
        const place = formatPlace(l)
        return (
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="truncate font-medium" title={l.company}>
                {l.company}
              </span>
              {l.is_inbound && <InboundBadge />}
              {l.is_fresh && <FreshBadge />}
            </div>
            <div className="flex items-baseline gap-1.5">
              <Link to={`/jobs/${l.id}`} onClick={stop} className="truncate text-sm hover:underline" title={l.title}>
                {l.title}
              </Link>
            </div>
            <div className="truncate text-xs text-muted-foreground" title={place}>
              {[place === '—' ? null : place, SOURCE_LABEL[l.source], l.duplicates > 0 ? `also on ${l.duplicates} other site${l.duplicates === 1 ? '' : 's'}` : null].filter(Boolean).join(' · ')}
            </div>
            {isRejected(l) && l.prefilter_reasons.length > 0 && (
              <div className="truncate text-xs text-destructive/80" title={l.prefilter_reasons.join('; ')}>
                Auto-filtered: {l.prefilter_reasons.join('; ')}
              </div>
            )}
          </div>
        )
      },
    }),
    col.display({
      id: 'exp',
      header: 'Experience',
      cell: ({ row }) => <ExpText lead={row.original} text={formatExp(row.original)} />,
    }),
    col.display({
      id: 'ctc',
      header: 'Salary',
      cell: ({ row }) => {
        const ctc = formatCtc(row.original)
        return ctc ? <span className="whitespace-nowrap">{ctc}</span> : <span className="text-muted-foreground" title="The post does not say">Not stated</span>
      },
    }),
    col.display({
      id: 'found',
      header: 'Posted',
      cell: ({ row }) => {
        const l = row.original
        const iso = l.posted_at ?? l.found_at
        return (
          <span className="whitespace-nowrap text-muted-foreground" title={l.posted_at ? 'Posted' : 'Found by the app (posting date unknown)'}>
            {relativeDay(iso)}
          </span>
        )
      },
    }),
  ]
  if (mode === 'all')
    cols.push(
      col.display({
        id: 'status',
        header: 'Status',
        cell: ({ row }) => <StatusBadge status={row.original.status} label={statusLabel(row.original.status)} />,
      }),
    )
  cols.push(
    col.display({
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => <RowActionButtons lead={row.original} actions={a} />,
    }),
  )
  return col.columns(cols)
}

export function LeadsTable({
  leads,
  selection,
  onSelectionChange,
  actions,
  mode = 'all',
}: {
  mode?: TableMode
  leads: LeadSummary[]
  selection: RowSelectionState
  onSelectionChange: (s: RowSelectionState) => void
  actions: RowActions
}) {
  const navigate = useNavigate()
  const wide = useMediaQuery('(min-width: 768px)')
  const table = useTable({
    features,
    columns: buildColumns(actions, mode),
    data: leads,
    getRowId: (l) => String(l.id),
    state: { rowSelection: selection },
    onRowSelectionChange: (u) => onSelectionChange(typeof u === 'function' ? u(selection) : u),
  })

  if (!wide) {
    const rows = table.getRowModel().rows
    return (
      <LeadCards
        items={rows.map((r) => ({ lead: r.original, selected: r.getIsSelected(), onSelect: (v) => r.toggleSelected(v) }))}
        allSelected={table.getIsAllRowsSelected() ? true : table.getIsSomeRowsSelected() ? 'indeterminate' : false}
        onToggleAll={(v) => table.toggleAllRowsSelected(v)}
        actions={actions}
        showStatus={mode === 'all'}
      />
    )
  }

  return (
    <Table className="min-w-[48rem] table-fixed">
      <TableHeader>
        {table.getHeaderGroups().map((g) => (
          <TableRow key={g.id}>
            {g.headers.map((h) => (
              <TableHead key={h.id} className={colClass(h.column.id)}>
                {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow
            key={row.id}
            data-state={row.getIsSelected() ? 'selected' : undefined}
            data-rejected={isRejected(row.original) || undefined}
            className={cn('cursor-pointer', isRejected(row.original) && 'opacity-60')}
            onClick={() => navigate(`/jobs/${row.original.id}`)}
          >
            {row.getAllCells().map((cell) => (
              <TableCell
                key={cell.id}
                className={colClass(cell.column.id)}
                onClick={cell.column.id === 'select' || cell.column.id === 'actions' ? stop : undefined}
              >
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
