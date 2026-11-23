import { useCallback, useMemo, useState } from 'react'
import { Check, ChevronLeft, ChevronRight, FlaskConical, Loader2, Play, RotateCcw, ShieldCheck, X } from 'lucide-react'
import type { RowSelectionState } from '@tanstack/react-table'
import { useSearchParams } from 'react-router-dom'
import type { LeadSummary } from '@/api/client'
import { useLeadActions, useRunIntake, type BulkBody } from '@/app/lead-actions'
import { NativeSelect } from '@/components/native-select'
import { PageHeader } from '@/components/page-header'
import { EmptyState, ErrorState } from '@/components/query-states'
import { SkipDialog } from '@/components/skip-dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { LeadsFilters, type FilterPatch } from './leads-filters'
import { LeadsTable, type RowActions } from './leads-table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ApplyQueue } from './apply-queue'
import { DEFAULT_LIMIT, PAGE_SIZES, parseFilters, useLeads, useTabCount, type LeadsTab } from './use-leads'

type SkipTarget = { ids: number[]; subject: string; bulk: boolean }

const TABS: { value: LeadsTab; label: string; hint: string }[] = [
  { value: 'review', label: 'To review', hint: 'New matches, best first. Shortlist the ones worth applying to, skip the rest.' },
  { value: 'apply', label: 'To apply', hint: 'Shortlisted jobs. Prepare a tailored CV, apply on the site, then mark it applied.' },
  { value: 'all', label: 'All jobs', hint: 'Everything found, in any status.' },
]

const EMPTY: Record<LeadsTab, { title: string; hint: string }> = {
  review: { title: 'Nothing new to review', hint: 'New searches run every few hours, or press Find new jobs.' },
  apply: { title: 'Nothing shortlisted', hint: 'Shortlist jobs from To review and they line up here.' },
  all: { title: 'No jobs match', hint: 'Loosen the filters.' },
}

function TabCount({ tab }: { tab: LeadsTab }) {
  const n = useTabCount(tab).data
  return n == null ? null : <span className="ml-1 text-xs text-muted-foreground tabular-nums">{n}</span>
}

function Bulk({ ids, busy, onRun, onSkip, onClear, showRestore }: { ids: number[]; busy: boolean; showRestore: boolean; onRun: (a: Exclude<BulkBody['action'], 'skip'>) => void; onSkip: () => void; onClear: () => void }) {
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
      {showRestore && (
        <Button size="sm" variant="outline" disabled={busy} onClick={() => onRun('restore')}>
          <RotateCcw /> Restore
        </Button>
      )}
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
  const intake = useRunIntake()

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

  // A new tab starts clean: the status/rejected filters only mean something on All.
  const setTab = (tab: LeadsTab) => {
    setParams(tab === 'review' ? {} : { tab }, { replace: true })
    setSelection({})
  }

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
      <PageHeader
        title="Jobs"
        description={TABS.find((t) => t.value === filters.tab)!.hint}
        actions={
          <Button variant="outline" onClick={() => intake.mutate()} disabled={intake.isPending} title="Search every job board and inbox now instead of waiting for the schedule">
            {intake.isPending ? <Loader2 className="animate-spin" /> : <Play />} Find new jobs
          </Button>
        }
      />
      <Tabs value={filters.tab} onValueChange={(v) => setTab(v as LeadsTab)} className="mb-4">
        <TabsList aria-label="Jobs views">
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
              {t.value !== 'all' && <TabCount tab={t.value} />}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {filters.tab !== 'apply' && <LeadsFilters key={filters.tab} filters={filters} onChange={update} />}
      {selectedIds.length > 0 && filters.tab !== 'apply' && (
        <Bulk
          ids={selectedIds}
          busy={busy}
          onRun={runBulk}
          onSkip={() => setSkipTarget({ ids: selectedIds, subject: `${selectedIds.length} lead${selectedIds.length === 1 ? '' : 's'}`, bulk: true })}
          onClear={clearSelection}
          showRestore={filters.include_rejected}
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
        <EmptyState {...EMPTY[filters.tab]} />
      ) : filters.tab === 'apply' ? (
        <ApplyQueue leads={rows} />
      ) : (
        <div className={leads.isPlaceholderData ? 'opacity-70 transition-opacity' : undefined}>
          <LeadsTable mode={filters.tab === 'review' ? 'review' : 'all'} leads={rows} selection={selection} onSelectionChange={setSelection} actions={rowActions} />
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
