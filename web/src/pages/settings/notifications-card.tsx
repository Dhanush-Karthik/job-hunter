import type { FollowupRules } from '@/api/client'
import { ChipInput } from './chip-input'
import { NumberField } from './fields'
import { SettingsSection } from './settings-section'
import { validDate } from './validate'

/** Quiet hours for desktop notifications, how far back Gmail is read, when silence becomes "ghosted", and holidays. */
export function NotificationsCard({ value: f, onChange }: { value: FollowupRules; onChange: (f: FollowupRules) => void }) {
  const set = (patch: Partial<FollowupRules>) => onChange({ ...f, ...patch })
  const bad = f.extra_holidays.filter((d) => !validDate(d))
  return (
    <SettingsSection title="Notifications & mail" description="When the app stays quiet, how much old mail it reads on the first run, and when a silent application is suggested as ghosted.">
      <div className="grid gap-4 sm:grid-cols-2">
        <NumberField label="No notifications from (hour)" value={f.quiet_hours[0]} min={0} max={23} integer onChange={(n) => set({ quiet_hours: [n, f.quiet_hours[1]] })} />
        <NumberField label="No notifications until (hour)" value={f.quiet_hours[1]} min={0} max={23} integer onChange={(n) => set({ quiet_hours: [f.quiet_hours[0], n] })} />
        <NumberField label="First Gmail run reads back (days)" value={f.gmail_lookback_days} min={1} max={90} integer onChange={(n) => set({ gmail_lookback_days: n })} />
        <NumberField label="Suggest ghosted after (days of silence)" value={f.ghosted_after_days} min={7} max={90} integer onChange={(n) => set({ ghosted_after_days: n })} />
      </div>
      <div className="grid gap-1">
        <ChipInput label="Extra holidays" values={f.extra_holidays} onChange={(extra_holidays) => set({ extra_holidays })} placeholder="YYYY-MM-DD" />
        {bad.length > 0 && <p className="text-xs text-destructive">Use YYYY-MM-DD: {bad.join(', ')} is not valid.</p>}
      </div>
    </SettingsSection>
  )
}
