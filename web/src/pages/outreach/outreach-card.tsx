import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { OutreachOut } from '@/api/client'
import { CopyButton } from '@/components/copy-button'
import { dueLabel, relativeDay } from '@/components/time'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { subjectOf } from './subject'
import type { useOutreachActions } from './use-outreach'

const SNOOZE_DAYS = [1, 3, 7]
const KIND_LABEL: Record<OutreachOut['kind'], string> = { referral: 'Referral request', follow_up: 'Follow-up', recruiter_reply: 'Reply to recruiter' }

function EditForm({ o, actions, onDone }: { o: OutreachOut; actions: ReturnType<typeof useOutreachActions>; onDone: () => void }) {
  const [draft, setDraft] = useState(o.draft ?? '')
  const [contact, setContact] = useState(o.contact ?? '')
  const subject = subjectOf(o)
  return (
    <form
      className="grid gap-2"
      onSubmit={(e) => {
        e.preventDefault()
        actions.edit.mutate({ id: o.id, draft, contact }, { onSuccess: onDone })
      }}
    >
      <div className="grid gap-1.5">
        <Label htmlFor={`contact-${o.id}`}>Contact for {subject}</Label>
        <Input id={`contact-${o.id}`} value={contact} placeholder="Recruiter name, email or LinkedIn URL" onChange={(e) => setContact(e.target.value)} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`draft-${o.id}`}>Draft for {subject}</Label>
        <Textarea id={`draft-${o.id}`} rows={6} value={draft} onChange={(e) => setDraft(e.target.value)} />
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={actions.busy || !draft.trim()}>
          Save draft
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

/** One message to send. The draft stays folded until asked for, so a long queue fits on one screen. */
export function OutreachCard({ o, actions, due = false }: { o: OutreachOut; actions: ReturnType<typeof useOutreachActions>; due?: boolean }) {
  const [editing, setEditing] = useState(false)
  const [open, setOpen] = useState(false)
  const subject = subjectOf(o)
  const sent = o.sent_at != null
  const when = !sent && o.due_at ? dueLabel(o.due_at) : null
  return (
    <li className="grid gap-2 px-3 py-3 text-sm" aria-label={subject}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <button type="button" className="-ml-1 rounded p-0.5 text-muted-foreground hover:bg-muted" aria-expanded={open} aria-label={`${open ? 'Hide' : 'Show'} message for ${subject}`} onClick={() => setOpen((v) => !v)}>
          {open ? <ChevronDown className="size-4" aria-hidden /> : <ChevronRight className="size-4" aria-hidden />}
        </button>
        <div className="min-w-0 flex-1 basis-56">
          {o.lead_id != null ? (
            <Link to={`/jobs/${o.lead_id}`} className="font-medium hover:underline">
              {o.company ?? subject}
            </Link>
          ) : (
            <span className="font-medium">{o.company ?? subject}</span>
          )}
          {o.title && <span className="text-muted-foreground"> · {o.title}</span>}
          <div className="text-xs text-muted-foreground">
            {KIND_LABEL[o.kind]} · {o.contact ? `to ${o.contact}` : 'no contact yet'}
          </div>
        </div>
        {when && (
          <Badge variant={when.overdue ? 'destructive' : 'secondary'} className={cn(!when.overdue && due && 'bg-amber-500/15 text-amber-700 dark:text-amber-400')}>
            {when.text}
          </Badge>
        )}
        {o.snoozed_until && !sent && <Badge variant="outline">Snoozed until {relativeDay(o.snoozed_until)}</Badge>}
        {sent && <Badge variant="secondary">Sent {relativeDay(o.sent_at!)}</Badge>}
        <div className="flex flex-wrap items-center gap-1.5">
          {o.draft && !editing && <CopyButton text={o.draft} label={`Copy draft for ${subject}`} caption="Copy message" />}
          {!sent && !editing && (
            <Button size="sm" disabled={actions.busy} aria-label={`Mark sent: ${subject}`} onClick={() => actions.markSent.mutate(o.id)}>
              Mark sent
            </Button>
          )}
        </div>
      </div>
      {(open || editing) && (
        <div className="grid gap-2 pl-6">
          {editing ? (
            <EditForm o={o} actions={actions} onDone={() => setEditing(false)} />
          ) : (
            <>
              {o.draft ? <blockquote className="rounded-lg bg-muted/50 p-3 whitespace-pre-wrap">{o.draft}</blockquote> : <p className="text-muted-foreground">No draft yet.</p>}
              {!sent && (
                <div className="flex flex-wrap items-center gap-2">
                  <Button size="sm" variant="outline" disabled={actions.busy} aria-label={`Edit draft for ${subject}`} onClick={() => setEditing(true)}>
                    Edit
                  </Button>
                  <span className="flex items-center gap-1" role="group" aria-label={`Snooze ${subject}`}>
                    <span className="text-xs text-muted-foreground">Remind me in</span>
                    {SNOOZE_DAYS.map((days) => (
                      <Button
                        key={days}
                        size="xs"
                        variant="ghost"
                        disabled={actions.busy}
                        aria-label={`Snooze ${subject} ${days} day${days === 1 ? '' : 's'}`}
                        onClick={() => actions.snooze.mutate({ id: o.id, days })}
                      >
                        {days}d
                      </Button>
                    ))}
                  </span>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </li>
  )
}
