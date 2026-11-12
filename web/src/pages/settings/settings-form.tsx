import { useState } from 'react'
import type { Settings, Source } from '@/api/client'
import { SOURCE_LABEL } from '@/components/lead-format'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { ChipInput } from './chip-input'
import { NumberField } from './fields'
import { FollowupsCard } from './followups-card'
import { PrefilterCard } from './prefilter-card'
import { SchedulesCard } from './schedules-card'
import { useSaveSettings } from './use-settings'
import { followupsValid, inRange, prefilterValid, schedulesValid } from './validate'

const BOARD_SITES: Source[] = ['linkedin', 'naukri', 'indeed', 'glassdoor', 'google']

/** Editable Settings (N, concurrency, targets, query matrix, prefilter, schedules, follow-ups). The rest of the object is sent back untouched. */
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
    qm.sites.length > 0 &&
    prefilterValid(s.prefilter) &&
    schedulesValid(s.schedules) &&
    followupsValid(s.followups)
  const dirty = JSON.stringify(s) !== JSON.stringify(initial)

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

      <PrefilterCard value={s.prefilter} onChange={(prefilter) => patch({ prefilter })} />
      <SchedulesCard value={s.schedules} onChange={(schedules) => patch({ schedules })} />
      <FollowupsCard value={s.followups} onChange={(followups) => patch({ followups })} />

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
