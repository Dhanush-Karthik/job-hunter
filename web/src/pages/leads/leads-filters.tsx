import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { CHANNEL_LABEL, SOURCE_LABEL } from '@/components/lead-format'
import { NativeSelect } from '@/components/native-select'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CHANNELS, MIN_SCORES, SORTS, SOURCES, STATUSES, type Filters, type Sort } from './use-leads'

export type FilterPatch = Partial<{ [K in keyof Filters]: Filters[K] | null }>

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid min-w-32 flex-1 gap-1 sm:flex-none">
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

  const single = <T extends string>(values: T[]) => (values.length === 1 ? values[0] : '')

  return (
    <div className="mb-4 grid gap-3" role="search" aria-label="Filter leads">
      <div className="flex flex-wrap items-end gap-3">
        <div className="relative min-w-52 flex-1">
          <Label htmlFor="lead-q" className="sr-only">
            Search company or title
          </Label>
          <Search className="pointer-events-none absolute top-2 left-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input id="lead-q" type="search" className="pl-8" placeholder="Search company or title" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Field label="Status">
          <NativeSelect aria-label="Status" value={single(filters.status)} onChange={(e) => onChange({ status: e.target.value ? [e.target.value as Filters['status'][number]] : null })}>
            <option value="">Any status</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Source">
          <NativeSelect aria-label="Source" value={single(filters.source)} onChange={(e) => onChange({ source: e.target.value ? [e.target.value as Filters['source'][number]] : null })}>
            <option value="">Any source</option>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {SOURCE_LABEL[s]}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Channel">
          <NativeSelect aria-label="Channel" value={single(filters.channel)} onChange={(e) => onChange({ channel: e.target.value ? [e.target.value as Filters['channel'][number]] : null })}>
            <option value="">Any channel</option>
            {CHANNELS.map((c) => (
              <option key={c} value={c}>
                {CHANNEL_LABEL[c]}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Min score">
          <NativeSelect aria-label="Min score" value={filters.min_score == null ? '' : String(filters.min_score)} onChange={(e) => onChange({ min_score: e.target.value ? Number(e.target.value) : null })}>
            <option value="">Any score</option>
            {MIN_SCORES.map((m) => (
              <option key={m} value={m}>
                ≥ {Math.round(m * 100)}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Sort by">
          <NativeSelect aria-label="Sort by" value={filters.sort} onChange={(e) => onChange({ sort: e.target.value as Sort })}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-2">
        <Toggle id="f-fresh" label="Fresh only" checked={filters.fresh_only} onChange={(v) => onChange({ fresh_only: v })} />
        <Toggle id="f-inbound" label="Inbound only" checked={filters.inbound_only} onChange={(v) => onChange({ inbound_only: v })} />
        <Toggle id="f-rejected" label="Include rejected" checked={filters.include_rejected} onChange={(v) => onChange({ include_rejected: v })} />
      </div>
    </div>
  )
}
