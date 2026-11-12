import { useState } from 'react'
import { Check, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { LeadSummary } from '@/api/client'
import { useLeadActions } from '@/app/lead-actions'
import { EmptyState } from '@/components/query-states'
import { FreshBadge, InboundBadge, ScoreCell } from '@/components/lead-parts'
import { formatPlace } from '@/components/lead-format'
import { SkipDialog } from '@/components/skip-dialog'
import { Button } from '@/components/ui/button'

export function HotLeads({ leads }: { leads: LeadSummary[] }) {
  const { shortlist, skip, busy } = useLeadActions()
  const [skipping, setSkipping] = useState<LeadSummary | null>(null)

  if (!leads.length) return <EmptyState title="No fresh hot leads" hint="Run intake to look for new ones." />
  return (
    <>
      <ul className="divide-y rounded-lg border">
        {leads.map((l) => (
          <li key={l.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
            <ScoreCell lead={l} />
            <div className="min-w-0 flex-1 basis-48">
              <Link to={`/jobs/${l.id}`} className="block truncate text-sm font-medium hover:underline">
                {l.company}
              </Link>
              <div className="truncate text-xs text-muted-foreground">
                {l.title} · {formatPlace(l)}
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              {l.is_fresh && <FreshBadge />}
              {l.is_inbound && <InboundBadge />}
            </div>
            <div className="flex gap-1.5">
              <Button size="sm" disabled={busy} aria-label={`Shortlist ${l.company}`} onClick={() => shortlist.mutate(l.id)}>
                <Check /> Shortlist
              </Button>
              <Button size="sm" variant="outline" disabled={busy} aria-label={`Skip ${l.company}`} onClick={() => setSkipping(l)}>
                <X /> Skip
              </Button>
            </div>
          </li>
        ))}
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
