import { useState } from 'react'
import { Users } from 'lucide-react'
import type { ApplicationOut, EventOut, OutreachOut } from '@/api/client'
import { CopyButton } from '@/components/copy-button'
import { fmtDateTime } from '@/components/format'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { useJobMutations } from './use-job'

const KIND_LABEL: Record<OutreachOut['kind'], string> = { referral: 'Referral', follow_up: 'Follow-up', recruiter_reply: 'Recruiter reply' }

/** Contacts and drafts. Drafts are copy-only: the app never sends a message. */
export function OutreachCard({ items, searching, onFind }: { items: OutreachOut[]; searching: boolean; onFind: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Users className="size-4" aria-hidden /> Contacts and drafts
        </CardTitle>
        <CardDescription>Copy a draft and send it yourself. Nothing here sends anything.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div>
          <Button size="sm" variant="outline" disabled={searching} onClick={onFind}>
            Find contacts
          </Button>
        </div>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No contacts yet.</p>
        ) : (
          <ul className="grid gap-3" aria-label="Outreach drafts">
            {items.map((o) => (
              <li key={o.id} className="grid gap-1.5 rounded-lg border p-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{KIND_LABEL[o.kind]}</Badge>
                  {o.sent_at && <Badge variant="outline">Sent {fmtDateTime(o.sent_at)}</Badge>}
                </div>
                {o.contact && <p className="font-medium break-words">{o.contact}</p>}
                {o.draft && (
                  <>
                    <p className="rounded-md bg-muted p-2 text-xs whitespace-pre-wrap">{o.draft}</p>
                    <div>
                      <CopyButton text={o.draft} label={`Copy ${KIND_LABEL[o.kind].toLowerCase()} draft for ${o.contact ?? 'contact'}`} />
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export function Timeline({ events }: { events: EventOut[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
      </CardHeader>
      <CardContent>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground">No events yet.</p>
        ) : (
          <ol className="grid gap-2 border-l pl-4" aria-label="Application timeline">
            {[...events].sort((a, b) => (a.at < b.at ? 1 : -1)).map((e) => (
              <li key={e.id} className="relative text-sm">
                <span className="absolute top-1.5 -left-[1.31rem] size-2 rounded-full bg-primary" aria-hidden />
                <span className="font-medium">
                  {e.from_status ? `${e.from_status} → ${e.to_status}` : e.to_status}
                </span>{' '}
                <span className="text-xs text-muted-foreground">
                  {fmtDateTime(e.at)} · {e.actor}
                </span>
                {e.note && <p className="text-xs text-muted-foreground">{e.note}</p>}
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}

/** Notes save on demand. `draft` is null until the owner types, so a refetch never clobbers edits. */
export function NotesCard({ app, mutations: m }: { app: ApplicationOut | null | undefined; mutations: ReturnType<typeof useJobMutations> }) {
  const [draft, setDraft] = useState<string | null>(null)
  const value = draft ?? app?.notes ?? ''
  return (
    <Card>
      <CardHeader>
        <CardTitle>Notes</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            m.patch.mutate({ notes: value }, { onSuccess: () => setDraft(null) })
          }}
        >
          <Label htmlFor="job-notes" className="sr-only">
            Notes
          </Label>
          <Textarea id="job-notes" rows={4} value={value} disabled={!app} onChange={(e) => setDraft(e.target.value)} placeholder={app ? 'Recruiter name, referral, prep notes…' : 'Shortlist the lead to keep notes.'} />
          <div>
            <Button type="submit" size="sm" disabled={!app || draft === null || m.patch.isPending}>
              Save notes
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
