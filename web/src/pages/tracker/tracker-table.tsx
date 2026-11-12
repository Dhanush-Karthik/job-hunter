import { createColumnHelper, flexRender, tableFeatures, useTable } from '@tanstack/react-table'
import { Link, useNavigate } from 'react-router-dom'
import type { ApplicationOut } from '@/api/client'
import { SOURCE_LABEL } from '@/components/lead-format'
import { StatusBadge } from '@/components/status-badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const features = tableFeatures({})
const col = createColumnHelper<typeof features, ApplicationOut>()
const date = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—')

const columns = col.columns([
  col.display({ id: 'company', header: 'Company', cell: ({ row }) => <span className="font-medium">{row.original.company}</span> }),
  col.display({
    id: 'title',
    header: 'Title',
    cell: ({ row }) => (
      <Link to={`/jobs/${row.original.lead_id}`} onClick={(e) => e.stopPropagation()} className="hover:underline">
        {row.original.title}
      </Link>
    ),
  }),
  col.display({ id: 'status', header: 'Status', cell: ({ row }) => <StatusBadge status={row.original.status} /> }),
  col.display({ id: 'variant', header: 'Variant', cell: ({ row }) => row.original.resume_variant ?? '—' }),
  col.display({ id: 'applied', header: 'Applied', cell: ({ row }) => date(row.original.applied_at) }),
  col.display({ id: 'follow', header: 'Next follow-up', cell: ({ row }) => date(row.original.next_follow_up_at) }),
  col.display({ id: 'score', header: 'Score', cell: ({ row }) => row.original.eval_score?.toFixed(1) ?? '—' }),
  col.display({ id: 'source', header: 'Source', cell: ({ row }) => SOURCE_LABEL[row.original.source] }),
])

export function TrackerTable({ apps }: { apps: ApplicationOut[] }) {
  const navigate = useNavigate()
  const table = useTable({ features, columns, data: apps, getRowId: (a) => String(a.id) })
  return (
    <div className="overflow-x-auto rounded-xl border">
      <Table className="min-w-[56rem]">
        <TableHeader>
          {table.getHeaderGroups().map((g) => (
            <TableRow key={g.id}>
              {g.headers.map((h) => (
                <TableHead key={h.id}>{h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}</TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => (
            <TableRow key={row.id} className="cursor-pointer" onClick={() => navigate(`/jobs/${row.original.lead_id}`)}>
              {row.getAllCells().map((cell) => (
                <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
