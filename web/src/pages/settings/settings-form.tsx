import { useState } from 'react'
import type { Settings, Source } from '@/api/client'
import { SOURCE_LABEL } from '@/components/lead-format'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ChipInput } from './chip-input'
import { useSaveSettings } from './use-settings'

const BOARD_SITES: Source[] = ['linkedin', 'naukri', 'indeed', 'glassdoor', 'google']

function NumberField({ label, value, min, max, step, onChange }: { label: string; value: number; min: number; max: number; step?: number; onChange: (n: number) => void }) {
  const id = `num-${label.toLowerCase().replace(/\W+/g, '-')}`
  const bad = !Number.isFinite(value) || value < min || value > max
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="number" min={min} max={max} step={step} value={Number.isFinite(value) ? value : ''} aria-invalid={bad} onChange={(e) => onChange(e.target.value === '' ? NaN : Number(e.target.value))} />
      {bad && <p className="text-xs text-destructive">Between {min} and {max}.</p>}
    </div>
  )
}

const inRange = (n: number, min: number, max: number) => Number.isFinite(n) && n >= min && n <= max

/** Editable subset of Settings (N, concurrency, targets, query matrix). The rest of the object is sent back untouched. */
export function SettingsForm({ initial }: { initial: Settings }) {
  const [s, setS] = useState(initial)
  const save = useSaveSettings()
  const patch = (p: Partial<Settings>) => setS((prev) => ({ ...prev, ...p }))
  const qm = s.query_matrix
  const setQm = (p: Partial<Settings['query_matrix']>) => patch({ query_matrix: { ...qm, ...p } })
  const valid =
    inRange(s.auto_evaluate_top_n, 0, 50) &&
    inRange(s.claude_concurrency, 1, 4) &&
    inRange(s.targets.applied_per_week, 0, 1000) &&
    inRange(s.targets.referrals_per_week, 0, 1000) &&
    inRange(s.targets.min_eval_score, 0, 5) &&
    qm.titles.length > 0 &&
    qm.locations.length > 0 &&
    qm.sites.length > 0
  const dirty = JSON.stringify(s) !== JSON.stringify(initial)
  const sch = s.schedules

  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) save.mutate(s)
      }}
    >
      <Card>
        <CardHeader>
          <CardTitle>Evaluation</CardTitle>
          <CardDescription>Each evaluation uses Claude quota (about 3.5 min and a fair bit of tokens), so keep N modest.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <NumberField label="Auto-evaluate top N per day" value={s.auto_evaluate_top_n} min={0} max={50} onChange={(n) => patch({ auto_evaluate_top_n: n })} />
          <NumberField label="Claude concurrency" value={s.claude_concurrency} min={1} max={4} onChange={(n) => patch({ claude_concurrency: n })} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Targets</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <NumberField label="Applications per week" value={s.targets.applied_per_week} min={0} max={1000} onChange={(n) => patch({ targets: { ...s.targets, applied_per_week: n } })} />
          <NumberField label="Referrals per week" value={s.targets.referrals_per_week} min={0} max={1000} onChange={(n) => patch({ targets: { ...s.targets, referrals_per_week: n } })} />
          <NumberField label="Minimum eval score" value={s.targets.min_eval_score} min={0} max={5} step={0.1} onChange={(n) => patch({ targets: { ...s.targets, min_eval_score: n } })} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Query matrix</CardTitle>
          <CardDescription>Board intake searches every title in every location on the ticked sites, rotating through them each run.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <ChipInput label="Titles" values={qm.titles} onChange={(titles) => setQm({ titles })} placeholder="e.g. Java Developer" />
          <ChipInput label="Locations" values={qm.locations} onChange={(locations) => setQm({ locations })} placeholder="e.g. Chennai" />
          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-medium">Sites</legend>
            <div className="flex flex-wrap gap-x-5 gap-y-2">
              {BOARD_SITES.map((site) => (
                <div key={site} className="flex items-center gap-2">
                  <Checkbox
                    id={`site-${site}`}
                    checked={qm.sites.includes(site)}
                    onCheckedChange={(v) => setQm({ sites: v === true ? [...qm.sites, site] : qm.sites.filter((x) => x !== site) })}
                  />
                  <Label htmlFor={`site-${site}`} className="font-normal">
                    {SOURCE_LABEL[site]}
                  </Label>
                </div>
              ))}
            </div>
            {site_note(qm.sites)}
          </fieldset>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Schedules</CardTitle>
          <CardDescription>Read-only for now; editing arrives in Wave 3.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-muted-foreground">Boards</dt>
            <dd>every {sch.boards_every_hours} h, between {sch.boards_window[0]}:00 and {sch.boards_window[1]}:00</dd>
            <dt className="text-muted-foreground">Career-page scan</dt>
            <dd>{sch.careerops_scan_times.join(', ')}</dd>
            <dt className="text-muted-foreground">Remote boards</dt>
            <dd>{sch.remote_boards_times.join(', ')}</dd>
            <dt className="text-muted-foreground">Gmail</dt>
            <dd>every {sch.gmail_every_minutes} min</dd>
          </dl>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!valid || !dirty || save.isPending}>
          Save settings
        </Button>
        {!valid && <span className="text-sm text-destructive">Fix the highlighted fields first.</span>}
      </div>
    </form>
  )
}

function site_note(sites: Source[]) {
  return sites.includes('google') ? (
    <p className="text-xs text-muted-foreground">Google Jobs currently returns nothing through JobSpy; it is kept here in case that gets fixed.</p>
  ) : null
}
