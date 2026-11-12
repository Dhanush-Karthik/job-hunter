import { useState } from 'react'
import type { Breakdown } from '@/api/client'
import { ErrorState, EmptyState } from '@/components/query-states'
import { SOURCE_LABEL } from '@/components/lead-format'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Bar } from './bars'
import { pct } from './calc'
import { useBreakdown, type Range } from './use-analytics'

type By = 'source' | 'channel' | 'title' | 'variant'
const TABS: { by: By; label: string }[] = [
  { by: 'source', label: 'Source' },
  { by: 'channel', label: 'Channel' },
  { by: 'title', label: 'Title' },
  { by: 'variant', label: 'CV variant' },
]
const CHANNEL: Record<string, string> = { platform_quick: 'Platform quick apply', company_ats: 'Company ATS', email: 'Email' }

function label(by: By, key: string) {
  if (by === 'source') return SOURCE_LABEL[key as keyof typeof SOURCE_LABEL] ?? key
  if (by === 'channel') return CHANNEL[key] ?? key
  if (by === 'variant') return `Variant ${key}`
  return key
}

function BreakdownTable({ by, range }: { by: By; range: Range }) {
  const q = useBreakdown(by, range)
  if (q.isPending) return <Skeleton className="h-40" role="status" aria-busy="true" aria-label="Loading breakdown" />
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  const rows: Breakdown['rows'] = [...q.data.rows].sort((a, b) => b.calls - a.calls || b.applied - a.applied)
  if (rows.length === 0) return <EmptyState title="No applications in this range" />
  const max = Math.max(1, ...rows.map((r) => r.calls))
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table className="min-w-[32rem]">
        <TableHeader>
          <TableRow>
            <TableHead>{TABS.find((t) => t.by === by)?.label}</TableHead>
            <TableHead className="text-right">Applied</TableHead>
            <TableHead className="text-right">Calls</TableHead>
            <TableHead className="w-1/3">Calls</TableHead>
            <TableHead className="text-right">Call rate</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.key}>
              <TableCell className="font-medium">{label(by, r.key)}</TableCell>
              <TableCell className="text-right tabular-nums">{r.applied}</TableCell>
              <TableCell className="text-right tabular-nums">{r.calls}</TableCell>
              <TableCell>
                <Bar value={r.calls} max={max} />
              </TableCell>
              <TableCell className="text-right tabular-nums">{pct(r.rate)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

export function BreakdownCard({ range }: { range: Range }) {
  const [by, setBy] = useState<By>('source')
  return (
    <Card>
      <CardHeader>
        <CardTitle>Interview calls by…</CardTitle>
        <CardDescription>Which source, channel, title and CV variant turn applications into calls.</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={by} onValueChange={(v) => setBy(v as By)}>
          <TabsList className="max-w-full overflow-x-auto">
            {TABS.map((t) => (
              <TabsTrigger key={t.by} value={t.by}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value={by}>
            <BreakdownTable by={by} range={range} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}
