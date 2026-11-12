import { createColumnHelper, flexRender, rowSelectionFeature, tableFeatures, useTable, type RowSelectionState } from '@tanstack/react-table'
import { Link, useNavigate } from 'react-router-dom'
import type { LeadSummary } from '@/api/client'
import { CHANNEL_LABEL, SOURCE_LABEL, formatCtc, formatExp, formatPlace, isRejected } from '@/components/lead-format'
import { FreshBadge, InboundBadge, ScoreCell } from '@/components/lead-parts'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useMediaQuery } from '@/components/use-media-query'
import { cn } from '@/lib/utils'
import { LeadCards } from './lead-cards'
import { RowActionButtons, type RowActions } from './row-actions'

export type { RowActions }

const features = tableFeatures({ rowSelectionFeature })
const col = createColumnHelper<typeof features, LeadSummary>()

/** Responsive visibility per column id. Below md the cards in lead-cards.tsx replace the table. */
const HIDE: Record<string, string> = {
  channel: 'hidden xl:table-cell',
  exp: 'hidden lg:table-cell',
  ctc: 'hidden lg:table-cell',
  source: 'hidden lg:table-cell',
  tags: 'hidden xl:table-cell',
}

const stop = (e: React.SyntheticEvent) => e.stopPropagation()

function buildColumns(a: RowActions) {
  return col.columns([
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
      header: 'Score',
      cell: ({ row }) => <ScoreCell lead={row.original} />,
    }),
    col.display({
      id: 'badges',
      header: 'Flags',
      cell: ({ row }) => (
        <div className="flex flex-col items-start gap-1">
          {row.original.is_fresh && <FreshBadge />}
          {row.original.is_inbound && <InboundBadge />}
        </div>
      ),
    }),
    col.display({
      id: 'channel',
      header: 'Channel',
      cell: ({ row }) => <Badge variant="outline">{CHANNEL_LABEL[row.original.apply_channel]}</Badge>,
    }),
    col.display({
      id: 'company',
      header: 'Company',
      cell: ({ row }) => <span className="font-medium">{row.original.company}</span>,
    }),
    col.display({
      id: 'title',
      header: 'Title',
      cell: ({ row }) => {
        const l = row.original
        return (
          <div className="min-w-40 max-w-80">
            <Link to={`/jobs/${l.id}`} onClick={stop} className="font-medium hover:underline">
              {l.title}
            </Link>
            {l.duplicates > 0 && <span className="ml-1.5 text-xs text-muted-foreground">+{l.duplicates} dup</span>}
            {isRejected(l) && l.prefilter_reasons.length > 0 && (
              <div className="mt-0.5 text-xs text-destructive/80 xl:hidden">{l.prefilter_reasons.join('; ')}</div>
            )}
          </div>
        )
      },
    }),
    col.display({
      id: 'place',
      header: 'City / mode',
      cell: ({ row }) => <span className="whitespace-nowrap">{formatPlace(row.original)}</span>,
    }),
    col.display({
      id: 'exp',
      header: 'Exp',
      cell: ({ row }) => <span className="whitespace-nowrap">{formatExp(row.original) ?? '—'}</span>,
    }),
    col.display({
      id: 'ctc',
      header: 'CTC',
      cell: ({ row }) => {
        const ctc = formatCtc(row.original)
        return ctc ? <span className="whitespace-nowrap">{ctc}</span> : <Badge variant="outline">CTC unknown</Badge>
      },
    }),
    col.display({
      id: 'source',
      header: 'Source',
      cell: ({ row }) => <span className="whitespace-nowrap">{SOURCE_LABEL[row.original.source]}</span>,
    }),
    col.display({
      id: 'tags',
      header: 'Prefilter',
      cell: ({ row }) => {
        const l = row.original
        const reasons = isRejected(l) ? l.prefilter_reasons : []
        return (
          <div className="flex max-w-56 flex-wrap gap-1">
            {l.prefilter_tags.filter((t) => t !== 'CTC unknown').map((t) => (
              <Badge key={t} variant="secondary">
                {t}
              </Badge>
            ))}
            {reasons.map((r) => (
              <Badge key={r} variant="destructive">
                {r}
              </Badge>
            ))}
            {l.restored && <Badge variant="secondary">Restored</Badge>}
          </div>
        )
      },
    }),
    col.display({
      id: 'status',
      header: 'Status',
      cell: ({ row }) => <Badge variant="secondary">{row.original.status}</Badge>,
    }),
    col.display({
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => <RowActionButtons lead={row.original} actions={a} />,
    }),
  ])
}

export function LeadsTable({
  leads,
  selection,
  onSelectionChange,
  actions,
}: {
  leads: LeadSummary[]
  selection: RowSelectionState
  onSelectionChange: (s: RowSelectionState) => void
  actions: RowActions
}) {
  const navigate = useNavigate()
  const wide = useMediaQuery('(min-width: 768px)')
  const table = useTable({
    features,
    columns: buildColumns(actions),
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
      />
    )
  }

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((g) => (
          <TableRow key={g.id}>
            {g.headers.map((h) => (
              <TableHead key={h.id} className={cn(HIDE[h.column.id], h.column.id === 'select' && 'w-8')}>
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
                className={cn(HIDE[cell.column.id])}
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
