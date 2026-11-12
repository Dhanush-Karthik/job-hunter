import type { Settings } from '@/api/client'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ChipInput } from './chip-input'
import { NumberField } from './fields'
import { validTime } from './validate'

type S = Settings['schedules']

function Times({ label, values, onChange }: { label: string; values: string[]; onChange: (v: string[]) => void }) {
  const bad = values.filter((v) => !validTime(v))
  return (
    <div className="grid gap-1">
      <ChipInput label={label} values={values} onChange={onChange} placeholder="HH:MM, e.g. 08:00" />
      {bad.length > 0 && <p className="text-xs text-destructive">Use 24-hour HH:MM: {bad.join(', ')} is not valid.</p>}
    </div>
  )
}

/** When the scheduler runs. Times are local. */
export function SchedulesCard({ value: s, onChange }: { value: S; onChange: (s: S) => void }) {
  const set = (patch: Partial<S>) => onChange({ ...s, ...patch })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Schedules</CardTitle>
        <CardDescription>Local time. The scheduler picks the changes up after you save.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-4">
          <NumberField label="Boards every (hours)" value={s.boards_every_hours} min={1} max={24} integer onChange={(n) => set({ boards_every_hours: n })} />
          <NumberField label="Boards window start (hour)" value={s.boards_window[0]} min={0} max={23} integer onChange={(n) => set({ boards_window: [n, s.boards_window[1]] })} />
          <NumberField label="Boards window end (hour)" value={s.boards_window[1]} min={1} max={24} integer onChange={(n) => set({ boards_window: [s.boards_window[0], n] })} />
          <NumberField label="Gmail every (minutes)" value={s.gmail_every_minutes} min={5} max={240} integer onChange={(n) => set({ gmail_every_minutes: n })} />
        </div>
        {s.boards_window[0] >= s.boards_window[1] && <p className="text-xs text-destructive">The window must start before it ends.</p>}
        <Times label="Career-page scan times" values={s.careerops_scan_times} onChange={(careerops_scan_times) => set({ careerops_scan_times })} />
        <Times label="Remote boards times" values={s.remote_boards_times} onChange={(remote_boards_times) => set({ remote_boards_times })} />
      </CardContent>
    </Card>
  )
}
