import type { Settings } from '@/api/client'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { ChipInput } from './chip-input'
import { NumberField } from './fields'

type P = Settings['prefilter']

/** Rules that drop leads before you see them. Dropped leads stay in the reject audit on Analytics. */
export function PrefilterCard({ value: p, onChange }: { value: P; onChange: (p: P) => void }) {
  const set = (patch: Partial<P>) => onChange({ ...p, ...patch })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Automatic filters</CardTitle>
        <CardDescription>Jobs that fail these rules are hidden from Jobs. Check “What the filters removed” below before tightening them.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <ChipInput label="Accepted cities" values={p.cities} onChange={(cities) => set({ cities })} placeholder="e.g. Chennai" />
        <div className="flex items-center gap-2">
          <Checkbox id="prefilter-remote" checked={p.remote_ok} onCheckedChange={(v) => set({ remote_ok: v === true })} />
          <Label htmlFor="prefilter-remote" className="font-normal">
            Accept remote roles
          </Label>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <NumberField label="Experience from (years)" value={p.exp_years[0]} min={0} max={40} step={0.5} onChange={(n) => set({ exp_years: [n, p.exp_years[1]] })} />
          <NumberField label="Experience to (years)" value={p.exp_years[1]} min={0} max={40} step={0.5} onChange={(n) => set({ exp_years: [p.exp_years[0], n] })} />
          <NumberField label="Drop if minimum experience is at least" value={p.exp_drop_min_at_least} min={0} max={40} step={0.5} onChange={(n) => set({ exp_drop_min_at_least: n })} />
          <NumberField label="Minimum CTC (LPA)" value={p.ctc_min_lpa} min={0} max={500} onChange={(n) => set({ ctc_min_lpa: n })} />
          <NumberField label="USD to INR" value={p.usd_inr} min={1} max={500} onChange={(n) => set({ usd_inr: n })} />
          <span />
          <NumberField label="Pass if posted within (days)" value={p.max_age_days_pass} min={1} max={365} integer onChange={(n) => set({ max_age_days_pass: n })} />
          <NumberField label="Drop if older than (days)" value={p.max_age_days_drop} min={1} max={365} integer onChange={(n) => set({ max_age_days_drop: n })} />
        </div>
        {p.exp_years[0] > p.exp_years[1] && <p className="text-xs text-destructive">Experience "from" must not exceed "to".</p>}
        {p.max_age_days_pass > p.max_age_days_drop && <p className="text-xs text-destructive">The pass age must not exceed the drop age.</p>}
        <ChipInput label="Stack keywords that help" values={p.stack_positive} onChange={(stack_positive) => set({ stack_positive })} placeholder="e.g. spring boot" />
        <ChipInput label="Stack keywords that hurt" values={p.stack_negative} onChange={(stack_negative) => set({ stack_negative })} placeholder="e.g. php" />
      </CardContent>
    </Card>
  )
}
