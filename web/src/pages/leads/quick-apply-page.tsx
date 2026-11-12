import { useMemo } from 'react'
import { CheckCheck, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { LeadSummary, Source } from '@/api/client'
import { useLeadActions } from '@/app/lead-actions'
import { SOURCE_LABEL, formatPlace } from '@/components/lead-format'
import { ScoreCell } from '@/components/lead-parts'
import { PageHeader } from '@/components/page-header'
import { EmptyState, ErrorState } from '@/components/query-states'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { LeadsTabs } from './leads-tabs'
import { useQuickApply } from './use-leads'

function groupBySource(leads: LeadSummary[]): [Source, LeadSummary[]][] {
  const m = new Map<Source, LeadSummary[]>()
  for (const l of leads) m.set(l.source, [...(m.get(l.source) ?? []), l])
  return [...m.entries()].sort((a, b) => b[1].length - a[1].length || SOURCE_LABEL[a[0]].localeCompare(SOURCE_LABEL[b[0]]))
}

function markHint(l: LeadSummary): string | null {
  if (l.status === 'Ready' && l.application_id != null) return null
  if (l.status === 'Shortlisted') return 'Approve a CV first (status must be Ready).'
  return 'Not ready to mark applied.'
}

function Item({ lead, busy, onMark }: { lead: LeadSummary; busy: boolean; onMark: () => void }) {
  const hint = markHint(lead)
  const hintId = `qa-hint-${lead.id}`
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5">
      <ScoreCell lead={lead} />
      <div className="min-w-0 flex-1 basis-48">
        <Link to={`/jobs/${lead.id}`} className="block truncate text-sm font-medium hover:underline">
          {lead.company}
        </Link>
        <div className="truncate text-xs text-muted-foreground">
          {lead.title} · {formatPlace(lead)}
        </div>
        {hint && (
          <div id={hintId} className="text-xs text-muted-foreground">
            {hint}
          </div>
        )}
      </div>
      <Badge variant="secondary">{lead.status}</Badge>
      <div className="flex gap-1.5">
        {lead.apply_url ? (
          <Button asChild size="sm" variant="outline">
            <a href={lead.apply_url} target="_blank" rel="noopener noreferrer" aria-label={`Open apply link for ${lead.company}`}>
              <ExternalLink /> Open apply link
            </a>
          </Button>
        ) : (
          <Button size="sm" variant="outline" disabled>
            No apply link
          </Button>
        )}
        <Button size="sm" disabled={hint != null || busy} aria-describedby={hint ? hintId : undefined} aria-label={`Mark applied for ${lead.company}`} onClick={onMark}>
          <CheckCheck /> Mark applied
        </Button>
      </div>
    </li>
  )
}

export function QuickApplyPage() {
  const q = useQuickApply()
  const { markApplied, busy } = useLeadActions()
  const groups = useMemo(() => groupBySource(q.data ?? []), [q.data])

  return (
    <>
      <PageHeader title="Quick apply" description="Platform 1-click jobs, grouped by source. Open, apply on the platform, then mark applied." />
      <LeadsTabs />
      {q.isPending ? (
        <div className="grid gap-3" aria-busy="true" aria-label="Loading quick apply">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} title="Could not load quick-apply leads" />
      ) : groups.length === 0 ? (
        <EmptyState title="No quick-applies waiting" hint="Shortlist leads on Naukri, LinkedIn or other platforms to batch them here." />
      ) : (
        <div className="grid gap-4">
          {groups.map(([source, items]) => (
            <Card key={source} role="region" aria-label={`${SOURCE_LABEL[source]} quick-applies`}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {SOURCE_LABEL[source]}
                  <Badge variant="secondary">{items.length}</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="divide-y rounded-lg border">
                  {items.map((l) => (
                    <Item key={l.id} lead={l} busy={busy} onMark={() => l.application_id != null && markApplied.mutate(l.application_id)} />
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  )
}
