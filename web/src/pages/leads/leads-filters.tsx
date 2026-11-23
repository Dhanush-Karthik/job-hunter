import { useEffect, useState } from 'react'
import { Search, SlidersHorizontal } from 'lucide-react'
import { CHANNEL_LABEL, SOURCE_LABEL, statusLabel } from '@/components/lead-format'
import { NativeSelect } from '@/components/native-select'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CHANNELS, MIN_SCORES, SORTS, SOURCES, STATUSES, type Filters, type Sort } from './use-leads'

export type FilterPatch = Partial<{ [K in keyof Filters]: Filters[K] | null }>

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid min-w-36 flex-1 gap-1 sm:flex-none">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  )
}

function Toggle({ id, label, checked, onChange }: { id: string; label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center gap-2">
      <Checkbox id={id} checked={checked} onCheckedChange={(v) => onChange(v === true)} />
      <Label htmlFor={id} className="text-sm font-normal">
        {label}
      </Label>
    </div>
  )
}

/** Filters beyond search and sort, counted for the button badge. */
function activeCount(f: Filters) {
  return [f.tab === 'all' && f.status.length, f.source.length, f.channel.length, f.min_score != null, f.fresh_only, f.inbound_only, f.tab === 'all' && f.include_rejected].filter(Boolean).length
}

export function LeadsFilters({ filters, onChange }: { filters: Filters; onChange: (patch: FilterPatch) => void }) {
  // Text search is debounced into the URL; the URL stays the source of truth (back/forward resets the box).
  const [q, setQ] = useState(filters.q)
  const [urlQ, setUrlQ] = useState(filters.q)
  if (filters.q !== urlQ) {
    setUrlQ(filters.q)
    setQ(filters.q)
  }
  useEffect(() => {
    if (q === filters.q) return
    const t = setTimeout(() => onChange({ q }), 300)
    return () => clearTimeout(t)
  }, [q, filters.q, onChange])

  const active = activeCount(filters)
  const [open, setOpen] = useState(active > 0)
  const single = <T extends string>(values: T[]) => (values.length === 1 ? values[0] : '')
  const all = filters.tab === 'all'

  return (
    <div className="mb-4 grid gap-3" role="search" aria-label="Filter leads">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-52 flex-1">
          <Label htmlFor="lead-q" className="sr-only">
            Search company or title
          </Label>
          <Search className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input id="lead-q" type="search" className="pl-8" placeholder="Search company or title" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="w-40">
          <NativeSelect aria-label="Sort by" value={filters.sort} onChange={(e) => onChange({ sort: e.target.value as Sort })}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                Sort: {s.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <Button type="button" variant={open ? 'secondary' : 'outline'} aria-expanded={open} aria-controls="lead-more-filters" onClick={() => setOpen((o) => !o)}>
          <SlidersHorizontal /> Filters
          {active > 0 && <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground tabular-nums">{active}</span>}
        </Button>
      </div>
      {open && (
        <div id="lead-more-filters" className="grid gap-3 rounded-xl border bg-muted/30 p-3">
          <div className="flex flex-wrap items-end gap-3">
            {all && (
              <Field label="Status">
                <NativeSelect aria-label="Status" value={single(filters.status)} onChange={(e) => onChange({ status: e.target.value ? [e.target.value as Filters['status'][number]] : null })}>
                  <option value="">Any status</option>
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {statusLabel(s)}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
            )}
            <Field label="Found on">
              <NativeSelect aria-label="Source" value={single(filters.source)} onChange={(e) => onChange({ source: e.target.value ? [e.target.value as Filters['source'][number]] : null })}>
                <option value="">Anywhere</option>
                {SOURCES.map((s) => (
                  <option key={s} value={s}>
                    {SOURCE_LABEL[s]}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="How to apply">
              <NativeSelect aria-label="Channel" value={single(filters.channel)} onChange={(e) => onChange({ channel: e.target.value ? [e.target.value as Filters['channel'][number]] : null })}>
                <option value="">Any way</option>
                {CHANNELS.map((c) => (
                  <option key={c} value={c}>
                    {CHANNEL_LABEL[c]}
                  </option>
                ))}
              </NativeSelect>
            </Field>
            <Field label="Match score">
              <NativeSelect aria-label="Min score" value={filters.min_score == null ? '' : String(filters.min_score)} onChange={(e) => onChange({ min_score: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Any score</option>
                {MIN_SCORES.map((m) => (
                  <option key={m} value={m}>
                    {Math.round(m * 100)} or more
                  </option>
                ))}
              </NativeSelect>
            </Field>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <Toggle id="f-fresh" label="Fresh only (last 48 h)" checked={filters.fresh_only} onChange={(v) => onChange({ fresh_only: v })} />
            <Toggle id="f-inbound" label="From recruiters only" checked={filters.inbound_only} onChange={(v) => onChange({ inbound_only: v })} />
            {all && <Toggle id="f-rejected" label="Show auto-filtered jobs" checked={filters.include_rejected} onChange={(v) => onChange({ include_rejected: v })} />}
            {active > 0 && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="ml-auto"
                onClick={() => onChange({ status: null, source: null, channel: null, min_score: null, fresh_only: null, inbound_only: null, include_rejected: null })}
              >
                Clear filters
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
