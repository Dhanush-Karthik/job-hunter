import { useState } from 'react'
import { ArrowRight, CircleHelp, ExternalLink, Mail, MailCheck, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { TRANSITIONS, type ApplicationOut, type AppStatus, type ProposalOut } from '@/api/client'
import { emailBody, emailHeadline } from '@/components/email-text'
import { NativeSelect } from '@/components/native-select'
import { PageHeader } from '@/components/page-header'
import { ErrorState } from '@/components/query-states'
import { StatusBadge } from '@/components/status-badge'
import { relativeDay } from '@/components/time'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useApplications } from '@/pages/tracker/use-tracker'
import { usePendingProposals, useProposalActions } from './use-replies'

type Actions = ReturnType<typeof useProposalActions>

const GROUPS: { key: string; types: ProposalOut['type'][]; label: string; hint: string; Icon: typeof Sparkles }[] = [
  { key: 'inbound', types: ['inbound'], label: 'Recruiters reaching out', hint: 'A recruiter emailed you about a role. Add it to your jobs to apply, or ignore it.', Icon: Sparkles },
  { key: 'status', types: ['status_change', 'ghosted'], label: 'Application updates', hint: 'These look like replies to your applications. Confirm the status the app suggests, or pick another.', Icon: MailCheck },
  { key: 'unsure', types: ['needs_eyes'], label: 'Please check', hint: 'The app could not tell what these emails mean. Open one to read it, then dismiss it or set a status.', Icon: CircleHelp },
]

const str = (v: unknown) => (typeof v === 'string' && v ? v : null)
const toStatus = (p: ProposalOut): AppStatus | null => (str(p.payload.to_status) as AppStatus | null) ?? (p.type === 'ghosted' ? 'Ghosted' : null)
const receivedAt = (p: ProposalOut) => str(p.payload.received_at) ?? p.created_at

/** A rejection must say at which stage; default to where the application is now. */
function editedPayload(p: ProposalOut, to: AppStatus, app: ApplicationOut | undefined) {
  const stage = to === 'Rejected' ? (str(p.payload.rejected_at_stage) ?? app?.status ?? null) : null
  return { ...p.payload, to_status: to, rejected_at_stage: stage }
}

/** "Quest Global · Backend Developer" or, when unmatched, the email subject. */
function subjectOf(p: ProposalOut) {
  const role = p.title && p.title !== 'Recruiter opportunity' ? p.title : null
  return [p.company, role].filter(Boolean).join(' · ') || emailHeadline(p.evidence) || 'Unmatched email'
}

/** The email's subject (only when the title above does not already say it) and a short, expandable snippet. */
function EmailPreview({ p }: { p: ProposalOut }) {
  const [open, setOpen] = useState(false)
  const headline = emailHeadline(p.evidence)
  const body = emailBody(p.evidence)
  const showHeadline = headline && headline !== subjectOf(p)
  if (!showHeadline && !body) return null
  return (
    <div className="grid gap-1 rounded-lg bg-muted/50 px-3 py-2 text-sm">
      {showHeadline && <div className="font-medium">{headline}</div>}
      {body && (
        <>
          <p className={open ? 'text-muted-foreground' : 'line-clamp-2 text-muted-foreground'}>{body}</p>
          <button type="button" className="w-fit text-xs font-medium text-muted-foreground underline-offset-2 hover:underline" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? 'Show less' : 'Show more'}
          </button>
        </>
      )}
    </div>
  )
}

/** Links out of the Inbox: the full email in Gmail (the app only keeps a snippet) and, when known, where to apply. */
function Links({ p }: { p: ProposalOut }) {
  return (
    <>
      {p.email_url && (
        <Button asChild size="sm" variant="outline">
          <a href={p.email_url} target="_blank" rel="noopener noreferrer">
            <Mail /> Open email
          </a>
        </Button>
      )}
      {p.apply_url && (
        <Button asChild size="sm" variant="outline">
          <a href={p.apply_url} target="_blank" rel="noopener noreferrer">
            <ExternalLink /> Apply page
          </a>
        </Button>
      )}
    </>
  )
}

/** Confirm, then dismiss every email in a group at once. */
function DismissAll({ ids, label, actions }: { ids: number[]; label: string; actions: Actions }) {
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm" variant="ghost" disabled={actions.busy}>
          Dismiss all
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Dismiss {ids.length} emails?</AlertDialogTitle>
          <AlertDialogDescription>
            All of “{label}” leave the Inbox. Nothing changes on your jobs or applications, and the emails stay in Gmail.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => actions.dismissMany.mutate(ids)}>Dismiss {ids.length}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function Header({ p, children }: { p: ProposalOut; children?: React.ReactNode }) {
  const subject = subjectOf(p)
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      {p.lead_id != null ? (
        <Link to={`/jobs/${p.lead_id}`} className="font-medium hover:underline">
          {subject}
        </Link>
      ) : (
        <span className="font-medium">{subject}</span>
      )}
      {children}
      <span className="ml-auto text-xs text-muted-foreground">{relativeDay(receivedAt(p))}</span>
    </div>
  )
}

function InboundCard({ p, actions }: { p: ProposalOut; actions: Actions }) {
  return (
    <li className="grid gap-3 rounded-xl border bg-card p-4 text-sm" aria-label={subjectOf(p)}>
      <Header p={p}>{str(p.payload.recruiter) && <span className="text-muted-foreground">from {str(p.payload.recruiter)}</span>}</Header>
      <EmailPreview p={p} />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={actions.busy || p.lead_id == null} onClick={() => actions.convert.mutate(p.id)}>
          Add to my jobs
        </Button>
        {p.lead_id != null && (
          <Button asChild size="sm" variant="outline">
            <Link to={`/jobs/${p.lead_id}`}>View job</Link>
          </Button>
        )}
        <Links p={p} />
        <Button size="sm" variant="ghost" className="ml-auto" disabled={actions.busy} onClick={() => actions.dismiss.mutate(p.id)}>
          Ignore
        </Button>
      </div>
    </li>
  )
}

function StatusCard({ p, actions, app }: { p: ProposalOut; actions: Actions; app: ApplicationOut | undefined }) {
  const target = toStatus(p)
  const [editing, setEditing] = useState(false)
  const [edited, setEdited] = useState<AppStatus | ''>('')
  const final = edited || target
  const subject = subjectOf(p)
  return (
    <li className="grid gap-3 rounded-xl border bg-card p-4 text-sm" aria-label={subject}>
      <Header p={p}>
        {target && (
          <span className="flex items-center gap-1 text-muted-foreground">
            <ArrowRight className="size-3.5" aria-hidden /> <StatusBadge status={final ?? target} />
          </span>
        )}
        {p.confidence < 0.7 && <Badge variant="outline">Not sure</Badge>}
      </Header>
      <EmailPreview p={p} />
      {editing && (
        <div className="max-w-xs">
          <NativeSelect aria-label={`New status for ${subject}`} value={final ?? ''} onChange={(e) => setEdited(e.target.value as AppStatus)}>
            <option value="" disabled>
              Pick a status…
            </option>
            {(['Screening', 'Technical', 'Final', 'Offer', 'Rejected', 'Ghosted', 'Withdrawn'] as AppStatus[]).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </NativeSelect>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={actions.busy || !final} onClick={() => actions.accept.mutate({ id: p.id, payload: edited ? editedPayload(p, edited, app) : undefined })}>
          {final ? `Mark ${final}` : 'Confirm'}
        </Button>
        <Button size="sm" variant="outline" disabled={actions.busy} aria-pressed={editing} onClick={() => setEditing((e) => !e)}>
          Different status
        </Button>
        <Links p={p} />
        <Button size="sm" variant="ghost" className="ml-auto" disabled={actions.busy} onClick={() => actions.dismiss.mutate(p.id)}>
          Ignore
        </Button>
      </div>
    </li>
  )
}

/** needs_eyes: accepting only acknowledges on the server, so a chosen status goes straight to the application. */
function UnsureCard({ p, actions, app }: { p: ProposalOut; actions: Actions; app: ApplicationOut | undefined }) {
  const [to, setTo] = useState<AppStatus | ''>('')
  const subject = subjectOf(p)
  const targets = app ? TRANSITIONS[app.status] : []
  return (
    <li className="grid gap-3 rounded-xl border bg-card p-4 text-sm" aria-label={subject}>
      <Header p={p}>
        {app ? <StatusBadge status={app.status} /> : <Badge variant="outline">Not in your applications</Badge>}
      </Header>
      <EmailPreview p={p} />
      <div className="flex flex-wrap items-center gap-2">
        {app && targets.length > 0 && (
          <>
            <div className="w-44">
              <NativeSelect aria-label={`New status for ${subject}`} value={to} onChange={(e) => setTo(e.target.value as AppStatus)}>
                <option value="">Change status to…</option>
                {targets.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <Button size="sm" disabled={actions.busy || !to} onClick={() => to && actions.setStatus.mutate({ id: p.id, app, to })}>
              Save
            </Button>
          </>
        )}
        <Links p={p} />
        <Button size="sm" variant="outline" className="ml-auto" disabled={actions.busy} onClick={() => actions.dismiss.mutate(p.id)}>
          Dismiss
        </Button>
      </div>
    </li>
  )
}

export function RepliesPage() {
  const proposals = usePendingProposals()
  const apps = useApplications()
  const actions = useProposalActions()
  const appById = new Map((apps.data ?? []).map((a) => [a.id, a]))
  return (
    <>
      <PageHeader title="Inbox" description="Emails about your search that need a decision. The app never changes anything until you confirm." />
      {proposals.isPending ? (
        <div className="grid gap-3" role="status" aria-busy="true" aria-label="Loading replies">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : proposals.isError ? (
        <ErrorState error={proposals.error} onRetry={() => proposals.refetch()} />
      ) : proposals.data.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed p-10 text-center">
          <MailCheck className="size-6 text-muted-foreground" aria-hidden />
          <p className="font-medium">Inbox zero</p>
          <p className="text-sm text-muted-foreground">Gmail is checked every 30 minutes. Recruiter mail, replies and rejections show up here.</p>
        </div>
      ) : (
        <div className="grid gap-8">
          {GROUPS.map((g) => ({ ...g, items: proposals.data.filter((p) => g.types.includes(p.type)) }))
            .filter((g) => g.items.length)
            .map((g) => (
              <section key={g.key} aria-labelledby={`rp-${g.key}`} className="grid gap-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <h2 id={`rp-${g.key}`} className="flex items-center gap-2 font-medium">
                      <g.Icon className="size-4 text-muted-foreground" aria-hidden />
                      {g.label}
                      <Badge variant="secondary">{g.items.length}</Badge>
                    </h2>
                    <p className="mt-0.5 text-sm text-muted-foreground">{g.hint}</p>
                  </div>
                  {g.key !== 'status' && g.items.length > 1 && <DismissAll ids={g.items.map((p) => p.id)} label={g.label} actions={actions} />}
                </div>
                <ul className="grid gap-3">
                  {g.items.map((p) =>
                    p.type === 'inbound' ? (
                      <InboundCard key={p.id} p={p} actions={actions} />
                    ) : p.type === 'needs_eyes' ? (
                      <UnsureCard key={p.id} p={p} actions={actions} app={p.application_id != null ? appById.get(p.application_id) : undefined} />
                    ) : (
                      <StatusCard key={p.id} p={p} actions={actions} app={p.application_id != null ? appById.get(p.application_id) : undefined} />
                    ),
                  )}
                </ul>
              </section>
            ))}
        </div>
      )}
    </>
  )
}
