import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CLOSED, PIPELINE, type AppStatus, type ProposalOut } from '@/api/client'
import { NativeSelect } from '@/components/native-select'
import { PageHeader } from '@/components/page-header'
import { EmptyState, ErrorState } from '@/components/query-states'
import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { usePendingProposals, useProposalActions } from './use-replies'

const GROUPS: { type: ProposalOut['type']; label: string }[] = [
  { type: 'inbound', label: 'Inbound recruiters' },
  { type: 'status_change', label: 'Status changes' },
  { type: 'ghosted', label: 'Ghosted' },
  { type: 'needs_eyes', label: 'Needs eyes' },
]
const STATUS_CHOICES: AppStatus[] = [...PIPELINE, ...CLOSED]
const toStatus = (p: ProposalOut) => (typeof p.payload.to_status === 'string' ? (p.payload.to_status as AppStatus) : null)

function ProposalCard({ p, actions }: { p: ProposalOut; actions: ReturnType<typeof useProposalActions> }) {
  const [editing, setEditing] = useState(false)
  const [edited, setEdited] = useState<AppStatus | ''>('')
  const subject = [p.company, p.title].filter(Boolean).join(' · ') || `Proposal #${p.id}`
  const target = edited || toStatus(p)
  const inbound = p.type === 'inbound'
  const recruiter = typeof p.payload.recruiter === 'string' ? p.payload.recruiter : null
  return (
    <li className="grid gap-2 rounded-xl border p-3 text-sm" aria-label={subject}>
      <div className="flex flex-wrap items-center gap-2">
        {p.lead_id != null ? (
          <Link to={`/jobs/${p.lead_id}`} className="font-medium hover:underline">
            {subject}
          </Link>
        ) : (
          <span className="font-medium">{subject}</span>
        )}
        <Badge variant="outline" title="How sure the classifier is">
          {Math.round(p.confidence * 100)}% confident
        </Badge>
        {!inbound && target && (
          <span className="flex items-center gap-1 text-muted-foreground">
            → <StatusBadge status={target} />
          </span>
        )}
        {recruiter && <span className="text-muted-foreground">from {recruiter}</span>}
      </div>
      {p.evidence && <blockquote className="border-l-2 pl-3 text-muted-foreground">{p.evidence}</blockquote>}
      {editing && !inbound && (
        <div className="flex max-w-xs items-center gap-2">
          <NativeSelect aria-label={`New status for ${subject}`} value={edited || toStatus(p) || ''} onChange={(e) => setEdited(e.target.value as AppStatus)}>
            <option value="" disabled>
              Pick a status…
            </option>
            {STATUS_CHOICES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </NativeSelect>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {inbound ? (
          <Button size="sm" disabled={actions.busy} onClick={() => actions.convert.mutate(p.id)}>
            Convert to application
          </Button>
        ) : (
          <>
            <Button
              size="sm"
              disabled={actions.busy || !target}
              onClick={() => actions.accept.mutate({ id: p.id, payload: edited ? { ...p.payload, to_status: edited } : undefined })}
            >
              Accept{edited ? ` as ${edited}` : ''}
            </Button>
            <Button size="sm" variant="outline" disabled={actions.busy} aria-pressed={editing} onClick={() => setEditing((e) => !e)}>
              Edit
            </Button>
          </>
        )}
        <Button size="sm" variant="ghost" disabled={actions.busy} onClick={() => actions.dismiss.mutate(p.id)}>
          Dismiss
        </Button>
      </div>
    </li>
  )
}

export function RepliesPage() {
  const proposals = usePendingProposals()
  const actions = useProposalActions()
  return (
    <>
      <PageHeader title="Replies & Inbound" description="Proposed status changes and recruiters who reached out. Nothing changes until you accept." />
      {proposals.isPending ? (
        <div className="grid gap-3" role="status" aria-busy="true" aria-label="Loading replies">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : proposals.isError ? (
        <ErrorState error={proposals.error} onRetry={() => proposals.refetch()} />
      ) : proposals.data.length === 0 ? (
        <EmptyState
          title="Nothing to confirm"
          hint="Gmail capture arrives in Wave 3: replies, rejections and recruiter mail will show up here as proposals for you to confirm."
        />
      ) : (
        <div className="grid gap-6">
          {GROUPS.map((g) => ({ ...g, items: proposals.data.filter((p) => p.type === g.type) }))
            .filter((g) => g.items.length)
            .map((g) => (
              <section key={g.type} aria-labelledby={`rp-${g.type}`}>
                <h2 id={`rp-${g.type}`} className="mb-2 flex items-center gap-2 text-sm font-medium">
                  {g.label}
                  <Badge variant="secondary">{g.items.length}</Badge>
                </h2>
                <ul className="grid gap-3">
                  {g.items.map((p) => (
                    <ProposalCard key={p.id} p={p} actions={actions} />
                  ))}
                </ul>
              </section>
            ))}
        </div>
      )}
    </>
  )
}
