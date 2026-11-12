import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ActionItem } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/query-states'

type Kind = ActionItem['kind']

const GROUPS: { kind: Kind; label: string }[] = [
  { kind: 'inbound', label: 'Inbound recruiters' },
  { kind: 'proposal', label: 'Replies to confirm' },
  { kind: 'follow_up', label: 'Follow-ups due' },
  { kind: 'quick_apply', label: 'Quick-applies waiting' },
  { kind: 'profile_refresh', label: 'Profile refresh' },
  { kind: 'cv_review', label: 'CVs to approve' },
  { kind: 'referral', label: 'Referrals' },
]

/** Where each kind of item is handled. */
function actionHref(a: ActionItem): string {
  switch (a.kind) {
    case 'inbound':
    case 'proposal':
      return '/replies'
    case 'follow_up':
    case 'referral':
      return '/outreach'
    case 'quick_apply':
      return '/leads/quick-apply'
    case 'profile_refresh':
      return '/settings'
    case 'cv_review':
      return a.lead_id != null ? `/jobs/${a.lead_id}` : '/tracker'
  }
}

export function ActionQueue({ actions }: { actions: ActionItem[] }) {
  const groups = GROUPS.map((g) => ({ ...g, items: actions.filter((a) => a.kind === g.kind) })).filter((g) => g.items.length)
  if (!groups.length) return <EmptyState title="Nothing waiting" hint="Inbox zero. Check Leads for anything new." />
  return (
    <div className="grid gap-4">
      {groups.map((g) => (
        <section key={g.kind} aria-labelledby={`aq-${g.kind}`}>
          <h3 id={`aq-${g.kind}`} className="mb-1.5 flex items-center gap-2 text-sm font-medium">
            {g.label}
            <Badge variant="secondary">{g.items.length}</Badge>
          </h3>
          <ul className="divide-y rounded-lg border">
            {g.items.map((a, i) => (
              <li key={`${a.kind}-${a.proposal_id ?? a.outreach_id ?? a.lead_id ?? i}-${i}`}>
                <Link to={actionHref(a)} className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{a.title}</span>
                    {a.subtitle && <span className="block truncate text-xs text-muted-foreground">{a.subtitle}</span>}
                  </span>
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  )
}
