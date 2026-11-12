import type { FollowupRules } from '@/api/client'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ChipInput } from './chip-input'
import { NumberField } from './fields'
import { validDate } from './validate'

/** When follow-ups come due, when silence turns into a "ghosted" proposal, and when notifications stay quiet. */
export function FollowupsCard({ value: f, onChange }: { value: FollowupRules; onChange: (f: FollowupRules) => void }) {
  const set = (patch: Partial<FollowupRules>) => onChange({ ...f, ...patch })
  const bad = f.extra_holidays.filter((d) => !validDate(d))
  return (
    <Card>
      <CardHeader>
        <CardTitle>Follow-up rules</CardTitle>
        <CardDescription>Business days skip weekends and Indian holidays. The app drafts follow-ups; you send them.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <NumberField label="First follow-up after (business days)" value={f.follow_up_business_days} min={1} max={20} integer onChange={(n) => set({ follow_up_business_days: n })} />
          <NumberField label="Second follow-up after (business days)" value={f.second_follow_up_business_days} min={1} max={30} integer onChange={(n) => set({ second_follow_up_business_days: n })} />
          <NumberField label="Propose ghosted after (days)" value={f.ghosted_after_days} min={7} max={90} integer onChange={(n) => set({ ghosted_after_days: n })} />
          <NumberField label="Quiet hours start" value={f.quiet_hours[0]} min={0} max={23} integer onChange={(n) => set({ quiet_hours: [n, f.quiet_hours[1]] })} />
          <NumberField label="Quiet hours end" value={f.quiet_hours[1]} min={0} max={23} integer onChange={(n) => set({ quiet_hours: [f.quiet_hours[0], n] })} />
          <NumberField label="First Gmail run reads back (days)" value={f.gmail_lookback_days} min={1} max={90} integer onChange={(n) => set({ gmail_lookback_days: n })} />
        </div>
        <div className="grid gap-1">
          <ChipInput label="Extra holidays" values={f.extra_holidays} onChange={(extra_holidays) => set({ extra_holidays })} placeholder="YYYY-MM-DD" />
          {bad.length > 0 && <p className="text-xs text-destructive">Use YYYY-MM-DD: {bad.join(', ')} is not valid.</p>}
        </div>
      </CardContent>
    </Card>
  )
}
