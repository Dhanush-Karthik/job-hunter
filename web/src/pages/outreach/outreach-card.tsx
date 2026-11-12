import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { OutreachOut } from '@/api/client'
import { CopyButton } from '@/components/copy-button'
import { fmtDateTime } from '@/components/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { subjectOf } from './subject'
import type { useOutreachActions } from './use-outreach'

const SNOOZE_DAYS = [1, 3, 7]
const KIND_LABEL: Record<OutreachOut['kind'], string> = { referral: 'Referral', follow_up: 'Follow-up', recruiter_reply: 'Recruiter reply' }

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
        <Input id={`contact-${o.id}`} value={contact} onChange={(e) => setContact(e.target.value)} />
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

export function OutreachCard({ o, actions, due = false }: { o: OutreachOut; actions: ReturnType<typeof useOutreachActions>; due?: boolean }) {
  const [editing, setEditing] = useState(false)
  const subject = subjectOf(o)
  const sent = o.sent_at != null
  return (
    <li className="grid gap-2 rounded-xl border p-3 text-sm" aria-label={subject}>
      <div className="flex flex-wrap items-center gap-2">
        {o.lead_id != null ? (
          <Link to={`/jobs/${o.lead_id}`} className="font-medium hover:underline">
            {subject}
          </Link>
        ) : (
          <span className="font-medium">{subject}</span>
        )}
        <Badge variant="outline">{KIND_LABEL[o.kind]}</Badge>
        {due && !sent && <Badge variant="destructive">Due</Badge>}
        {sent && <Badge variant="secondary">Sent {fmtDateTime(o.sent_at!)}</Badge>}
      </div>
      <dl className="grid gap-x-4 gap-y-0.5 text-muted-foreground sm:grid-cols-[auto_1fr]">
        <dt>Contact</dt>
        <dd className="break-words text-foreground">{o.contact ?? 'No contact yet'}</dd>
        {o.due_at && !sent && (
          <>
            <dt>Due date</dt>
            <dd className="text-foreground">{fmtDateTime(o.due_at)}</dd>
          </>
        )}
        {o.snoozed_until && !sent && (
          <>
            <dt>Snoozed until</dt>
            <dd className="text-foreground">{fmtDateTime(o.snoozed_until)}</dd>
          </>
        )}
      </dl>
      {editing ? (
        <EditForm o={o} actions={actions} onDone={() => setEditing(false)} />
      ) : (
        <>
          {o.draft ? (
            <blockquote className="rounded-lg bg-muted/50 p-3 whitespace-pre-wrap">{o.draft}</blockquote>
          ) : (
            <p className="text-muted-foreground">No draft yet.</p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            {o.draft && <CopyButton text={o.draft} label={`Copy draft for ${subject}`} />}
            {!sent && (
              <>
                <Button size="sm" variant="outline" disabled={actions.busy} aria-label={`Edit draft for ${subject}`} onClick={() => setEditing(true)}>
                  Edit draft
                </Button>
                <Button size="sm" disabled={actions.busy} aria-label={`Mark sent: ${subject}`} onClick={() => actions.markSent.mutate(o.id)}>
                  Mark sent
                </Button>
                <span className="flex items-center gap-1" role="group" aria-label={`Snooze ${subject}`}>
                  <span className="text-xs text-muted-foreground">Snooze</span>
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
              </>
            )}
          </div>
        </>
      )}
    </li>
  )
}
