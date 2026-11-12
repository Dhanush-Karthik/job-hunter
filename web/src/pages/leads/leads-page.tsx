import { useCallback, useMemo, useState } from 'react'
import { Check, ChevronLeft, ChevronRight, FlaskConical, RotateCcw, ShieldCheck, X } from 'lucide-react'
import type { RowSelectionState } from '@tanstack/react-table'
import { useSearchParams } from 'react-router-dom'
import type { LeadSummary } from '@/api/client'
import { useLeadActions, type BulkBody } from '@/app/lead-actions'
import { NativeSelect } from '@/components/native-select'
import { PageHeader } from '@/components/page-header'
import { EmptyState, ErrorState } from '@/components/query-states'
import { SkipDialog } from '@/components/skip-dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { LeadsFilters, type FilterPatch } from './leads-filters'
import { LeadsTable, type RowActions } from './leads-table'
import { LeadsTabs } from './leads-tabs'
import { DEFAULT_LIMIT, PAGE_SIZES, parseFilters, useLeads } from './use-leads'

type SkipTarget = { ids: number[]; subject: string; bulk: boolean }

function Bulk({ ids, busy, onRun, onSkip, onClear }: { ids: number[]; busy: boolean; onRun: (a: Exclude<BulkBody['action'], 'skip'>) => void; onSkip: () => void; onClear: () => void }) {
  return (
    <div role="toolbar" aria-label="Bulk actions" className="sticky top-14 z-20 mb-3 flex flex-wrap items-center gap-2 rounded-lg border bg-card p-2 shadow-sm md:top-2">
      <span className="px-1 text-sm font-medium">{ids.length} selected</span>
      <Button size="sm" disabled={busy} onClick={() => onRun('shortlist')}>
        <Check /> Shortlist
      </Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={onSkip}>
        <X /> Skip…
      </Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => onRun('evaluate')}>
        <FlaskConical /> Evaluate
      </Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => onRun('verify')}>
        <ShieldCheck /> Verify
      </Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => onRun('restore')}>
        <RotateCcw /> Restore
      </Button>
      <Button size="sm" variant="ghost" onClick={onClear}>
        Clear
      </Button>
    </div>
  )
}

export function LeadsPage() {
  const [params, setParams] = useSearchParams()
  const filters = useMemo(() => parseFilters(params), [params])
  const leads = useLeads(filters)
  const { shortlist, skip, evaluate, restore, bulk, busy } = useLeadActions()
  const [selection, setSelection] = useState<RowSelectionState>({})
  const [skipTarget, setSkipTarget] = useState<SkipTarget | null>(null)

  const update = useCallback(
    (patch: FilterPatch) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [k, v] of Object.entries(patch)) {
            next.delete(k)
            if (v == null || v === false || v === '' || (k === 'sort' && v === 'score') || (k === 'limit' && v === DEFAULT_LIMIT)) continue
            if (Array.isArray(v)) v.forEach((x) => next.append(k, String(x)))
            else next.set(k, String(v))
          }
          if (!('offset' in patch)) next.delete('offset')
          return next
        },
        { replace: true },
      )
      setSelection({})
    },
    [setParams],
  )

  const selectedIds = Object.keys(selection).filter((k) => selection[k]).map(Number)
  const clearSelection = () => setSelection({})
  const runBulk = (action: Exclude<BulkBody['action'], 'skip'>) => bulk.mutate({ ids: selectedIds, action }, { onSuccess: clearSelection })

  const rows = leads.data?.items ?? []
  const total = leads.data?.total ?? 0
  const from = total ? filters.offset + 1 : 0
  const to = Math.min(filters.offset + filters.limit, total)

  const rowActions = useMemo<RowActions>(
    () => ({
      busy,
      onShortlist: (l: LeadSummary) => shortlist.mutate(l.id),
      onSkip: (l: LeadSummary) => setSkipTarget({ ids: [l.id], subject: l.company, bulk: false }),
      onEvaluate: (l: LeadSummary) => evaluate.mutate(l.id),
      onRestore: (l: LeadSummary) => restore.mutate(l.id),
    }),
    [busy, shortlist, evaluate, restore],
  )

  function confirmSkip(reason: string) {
    if (!skipTarget) return
    const done = { onSuccess: () => { setSkipTarget(null); clearSelection() } }
    if (skipTarget.bulk) bulk.mutate({ ids: skipTarget.ids, action: 'skip', reason }, done)
    else skip.mutate({ id: skipTarget.ids[0], reason }, done)
  }

  return (
    <>
      <PageHeader title="Leads" description="Ranked by score, fresh first. Shortlist, skip or evaluate." />
      <LeadsTabs />
      <LeadsFilters filters={filters} onChange={update} />
      {selectedIds.length > 0 && (
        <Bulk
          ids={selectedIds}
          busy={busy}
          onRun={runBulk}
          onSkip={() => setSkipTarget({ ids: selectedIds, subject: `${selectedIds.length} lead${selectedIds.length === 1 ? '' : 's'}`, bulk: true })}
          onClear={clearSelection}
        />
      )}
      {leads.isPending ? (
        <div className="grid gap-2" aria-busy="true" aria-label="Loading leads">
          {Array.from({ length: 8 }, (_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : leads.isError ? (
        <ErrorState error={leads.error} onRetry={() => leads.refetch()} title="Could not load leads" />
      ) : rows.length === 0 ? (
        <EmptyState title="No leads match" hint="Loosen the filters or run intake from Today." />
      ) : (
        <div className={leads.isPlaceholderData ? 'opacity-70 transition-opacity' : undefined}>
          <LeadsTable leads={rows} selection={selection} onSelectionChange={setSelection} actions={rowActions} />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
            <span aria-live="polite">
              {from}–{to} of {total}
            </span>
            <div className="flex items-center gap-2">
              <NativeSelect aria-label="Rows per page" className="w-32" value={String(filters.limit)} onChange={(e) => update({ limit: Number(e.target.value) })}>
                {PAGE_SIZES.map((n) => (
                  <option key={n} value={n}>
                    {n} / page
                  </option>
                ))}
              </NativeSelect>
              <Button variant="outline" size="sm" disabled={filters.offset === 0} onClick={() => update({ offset: Math.max(0, filters.offset - filters.limit) })}>
                <ChevronLeft /> Prev
              </Button>
              <Button variant="outline" size="sm" disabled={to >= total} onClick={() => update({ offset: filters.offset + filters.limit })}>
                Next <ChevronRight />
              </Button>
            </div>
          </div>
        </div>
      )}
      <SkipDialog
        open={skipTarget != null}
        onOpenChange={(o) => !o && setSkipTarget(null)}
        subject={skipTarget?.subject ?? ''}
        pending={skip.isPending || bulk.isPending}
        onConfirm={confirmSkip}
      />
    </>
  )
}
