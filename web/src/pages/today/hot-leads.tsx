import { useState } from 'react'
import { Check, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { LeadSummary } from '@/api/client'
import { useLeadActions } from '@/app/lead-actions'
import { FreshBadge, InboundBadge, ScoreCell } from '@/components/lead-parts'
import { leadFacts } from '@/components/lead-format'
import { SkipDialog } from '@/components/skip-dialog'
import { Button } from '@/components/ui/button'

const CHANCE_STYLE = {
  high: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
  medium: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  low: 'bg-muted text-muted-foreground',
} as const

function CallChance({ chance }: { chance: keyof typeof CHANCE_STYLE }) {
  return (
    <span className={`mr-1.5 inline-block rounded px-1.5 py-px text-[11px] font-medium ${CHANCE_STYLE[chance]}`}>
      {chance === 'high' ? 'High' : chance === 'medium' ? 'Medium' : 'Low'} call chance
    </span>
  )
}

export function HotLeads({ leads }: { leads: LeadSummary[] }) {
  const { shortlist, skip, busy } = useLeadActions()
  const [skipping, setSkipping] = useState<LeadSummary | null>(null)

  if (!leads.length)
    return (
      <div className="rounded-xl border border-dashed p-8 text-center">
        <p className="font-medium">No picks yet</p>
        <p className="mt-1 text-sm text-muted-foreground">The nightly run evaluates the best new jobs at midnight. Every job found so far is on the Jobs page.</p>
      </div>
    )
  return (
    <>
      <ul className="divide-y rounded-xl border">
        {leads.map((l) => {
          const facts = leadFacts(l, { ctc: false })
          return (
            <li key={l.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
              <ScoreCell lead={l} />
              <div className="min-w-0 flex-1 basis-48">
                <div className="flex items-center gap-1.5">
                  <Link to={`/jobs/${l.id}`} className="truncate text-sm font-medium hover:underline">
                    {l.company}
                  </Link>
                  {l.is_inbound && <InboundBadge />}
                  {l.is_fresh && !l.is_inbound && <FreshBadge />}
                </div>
                <div className="truncate text-xs text-muted-foreground" title={l.title}>
                  {[l.title, facts].filter(Boolean).join(' · ')}
                </div>
                {l.pick_reason && (
                  <div className="mt-0.5 line-clamp-2 text-xs" title={l.pick_reason}>
                    {l.call_chance && <CallChance chance={l.call_chance} />}
                    {l.pick_reason}
                  </div>
                )}
              </div>
              <div className="flex gap-1.5">
                <Button size="sm" variant="outline" disabled={busy} aria-label={`Shortlist ${l.company}`} onClick={() => shortlist.mutate(l.id)}>
                  <Check /> Shortlist
                </Button>
                <Button size="icon-sm" variant="ghost" disabled={busy} aria-label={`Skip ${l.company}`} title="Skip" onClick={() => setSkipping(l)}>
                  <X />
                </Button>
              </div>
            </li>
          )
        })}
      </ul>
      <SkipDialog
        open={skipping != null}
        onOpenChange={(o) => !o && setSkipping(null)}
        subject={skipping ? `${skipping.company}` : ''}
        pending={skip.isPending}
        onConfirm={(reason) => skipping && skip.mutate({ id: skipping.id, reason }, { onSuccess: () => setSkipping(null) })}
      />
    </>
  )
}
