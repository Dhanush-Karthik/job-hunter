import { Check, FlaskConical, RotateCcw, X } from 'lucide-react'
import { TRANSITIONS, type LeadSummary } from '@/api/client'
import { isRejected } from '@/components/lead-format'
import { Button } from '@/components/ui/button'

export type RowActions = {
  busy: boolean
  onShortlist: (l: LeadSummary) => void
  onSkip: (l: LeadSummary) => void
  onEvaluate: (l: LeadSummary) => void
  onRestore: (l: LeadSummary) => void
}

/** Per-row Shortlist / Skip / Evaluate, or Restore for prefilter drops. Shared by the table and the mobile cards. */
export function RowActionButtons({ lead: l, actions: a }: { lead: LeadSummary; actions: RowActions }) {
  if (isRejected(l)) {
    return (
      <Button size="xs" variant="outline" disabled={a.busy} aria-label={`Restore ${l.company}`} onClick={() => a.onRestore(l)}>
        <RotateCcw /> Restore
      </Button>
    )
  }
  return (
    <div className="flex gap-1">
      {TRANSITIONS[l.status].includes('Shortlisted') && (
        <Button size="icon-sm" variant="ghost" disabled={a.busy} aria-label={`Shortlist ${l.company}`} title="Shortlist" onClick={() => a.onShortlist(l)}>
          <Check />
        </Button>
      )}
      {TRANSITIONS[l.status].includes('Skipped') && (
        <Button size="icon-sm" variant="ghost" disabled={a.busy} aria-label={`Skip ${l.company}`} title="Skip" onClick={() => a.onSkip(l)}>
          <X />
        </Button>
      )}
      {l.eval_score == null && (
        <Button size="icon-sm" variant="ghost" disabled={a.busy} aria-label={`Evaluate ${l.company}`} title="Evaluate" onClick={() => a.onEvaluate(l)}>
          <FlaskConical />
        </Button>
      )}
    </div>
  )
}
