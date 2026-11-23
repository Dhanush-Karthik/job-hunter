import { useState } from 'react'
import { Check, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { LeadSummary } from '@/api/client'
import { useLeadActions } from '@/app/lead-actions'
import { FreshBadge, InboundBadge, ScoreCell } from '@/components/lead-parts'
import { leadFacts } from '@/components/lead-format'
import { SkipDialog } from '@/components/skip-dialog'
import { Button } from '@/components/ui/button'

export function HotLeads({ leads }: { leads: LeadSummary[] }) {
  const { shortlist, skip, busy } = useLeadActions()
  const [skipping, setSkipping] = useState<LeadSummary | null>(null)

  if (!leads.length)
    return (
      <div className="rounded-xl border border-dashed p-8 text-center">
        <p className="font-medium">No fresh matches right now</p>
        <p className="mt-1 text-sm text-muted-foreground">New searches run every few hours. Older matches are on the Jobs page.</p>
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
