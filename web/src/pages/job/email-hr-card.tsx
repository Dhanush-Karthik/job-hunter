import { useEffect, useRef, useState } from 'react'
import { CircleCheck, Loader2, Mail, Paperclip, Pencil, Save, Search, TriangleAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { EmailCandidate, LeadDetail } from '@/api/client'
import { ErrorState } from '@/components/query-states'
import { fmtDateTime } from '@/components/format'
import { NativeSelect } from '@/components/native-select'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { useEmailDraft, useFindHr, useJobReachout, useSendEmail, type Attach } from './use-email-hr'

const EMAIL = /^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$/
const OTHER = '__other__'
const daysSince = (iso: string) => (Date.now() - new Date(iso).getTime()) / 86_400_000

const CONFIDENCE: Record<EmailCandidate['confidence'], string> = { high: 'Found', medium: 'On their site', low: 'Guess' }

/**
 * Email this job's HR in one click. The address is looked up for you (job post, job page, company site), the email is
 * written from your Settings template with the job ID, and the CV is attached. Nothing is sent until you press Send.
 */
export function EmailHrCard({ lead }: { lead: LeadDetail }) {
  const q = useJobReachout(lead.id)
  const find = useFindHr(lead.id)
  const send = useSendEmail(lead.id)
  const data = q.data
  const searched = useRef(false)

  const [picked, setPicked] = useState<string | null>(null)
  const [manual, setManual] = useState({ email: '', name: '' })
  const [extra, setExtra] = useState<number[]>([])
  const [attach, setAttach] = useState<Attach | null>(null)
  const [edit, setEdit] = useState<{ subject?: string; body?: string } | null>(null)
  const [editing, setEditing] = useState(false)
  const [force, setForce] = useState(false)

  // First visit to this job: look the HR address up once, without a click.
  const { mutate: findNow, isPending: finding } = find
  useEffect(() => {
    if (data && data.status.enabled && data.searched_at == null && !searched.current) {
      searched.current = true
      findNow()
    }
  }, [data, findNow])

  const candidates = data?.candidates ?? []
  const auto = candidates.find((c) => c.confidence !== 'low')?.email ?? null
  const choice = picked ?? auto
  const selected = candidates.find((c) => c.email === choice)
  const toEmail = (choice === OTHER ? manual.email : (choice ?? '')).trim()
  const toName = (choice === OTHER ? manual.name : selected?.name)?.trim() || null
  const validEmail = EMAIL.test(toEmail)

  const draft = useEmailDraft(lead.id, toName, extra, data != null)
  const auto_text = draft.data ?? data?.draft
  const subject = edit?.subject ?? auto_text?.subject ?? ''
  const body = edit?.body ?? auto_text?.body ?? ''

  if (q.isPending) return <Skeleton className="h-64" role="status" aria-busy="true" aria-label="Loading email" />
  if (q.isError) return <ErrorState title="Could not load the email card" error={q.error} onRetry={() => q.refetch()} />
  if (!data!.status.enabled) return null
  const d = data!
  const st = d.status

  const attachChoice: Attach = attach ?? d.attach_default
  const missingResume = attachChoice === 'base' && !st.resume.present
  const missingTailored = attachChoice === 'tailored' && !d.has_tailored_cv
  const emailed = selected?.last_emailed_at ?? d.history.find((h) => h.to_email.toLowerCase() === toEmail.toLowerCase() && h.state === 'sent')?.created_at ?? null
  const repeat = validEmail && emailed != null && daysSince(emailed) < st.cooldown_days
  const capped = st.sent_today >= st.daily_cap
  const sentBefore = d.history.filter((h) => h.state === 'sent')
  const ready = st.gmail_ready && validEmail && subject.trim() !== '' && body.trim() !== '' && !missingResume && !missingTailored && !draft.isFetching
  const input = (mode: 'send' | 'draft') => ({ to_email: toEmail, to_name: toName, extra_lead_ids: extra, subject: subject.trim(), body, attach: attachChoice, mode, force })
  const attachName = attachChoice === 'none' ? 'no attachment' : attachChoice === 'tailored' ? 'the tailored CV' : (st.resume.filename ?? 'resume.pdf')

  return (
    <Card role="region" aria-label="Email HR">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="size-4" aria-hidden /> Email HR about this job
        </CardTitle>
        <CardDescription>The address and the email are filled in for you. Check them and press Send.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        {sentBefore.length > 0 && (
          <p role="status" className="flex items-start gap-2 rounded-lg bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-800 dark:text-emerald-300">
            <CircleCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <span>
              You emailed {sentBefore[0].to_email} on {fmtDateTime(sentBefore[0].created_at)}
              {sentBefore.length > 1 ? ` (and ${sentBefore.length - 1} more)` : ''}.
            </span>
          </p>
        )}

        <fieldset className="grid gap-2">
          <legend className="mb-1 flex items-center gap-2 font-medium">
            Send to
            {(finding || find.isPending) && (
              <span role="status" className="flex items-center gap-1 text-xs font-normal text-muted-foreground">
                <Loader2 className="size-3 animate-spin" aria-hidden /> Looking for HR emails…
              </span>
            )}
          </legend>
          {candidates.map((c) => (
            <label key={c.email} className={cn('flex cursor-pointer items-start gap-2 rounded-lg border p-2', choice === c.email && 'border-primary bg-primary/5')}>
              <input type="radio" name={`hr-to-${lead.id}`} className="mt-1" checked={choice === c.email} onChange={() => setPicked(c.email)} />
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium break-all">{c.email}</span>
                  <Badge variant={c.confidence === 'low' ? 'outline' : 'secondary'}>{CONFIDENCE[c.confidence]}</Badge>
                </span>
                <span className="block text-xs text-muted-foreground">
                  {c.name ? `${c.name} · ` : ''}
                  {c.label}
                  {c.last_emailed_at ? ` · emailed ${fmtDateTime(c.last_emailed_at)}` : ''}
                </span>
              </span>
            </label>
          ))}
          {candidates.length === 0 && !finding && !find.isPending && (
            <p className="text-xs text-muted-foreground">No HR address found automatically. Type one below.</p>
          )}
          <label className={cn('flex cursor-pointer items-start gap-2 rounded-lg border p-2', choice === OTHER && 'border-primary bg-primary/5')}>
            <input type="radio" name={`hr-to-${lead.id}`} className="mt-1" checked={choice === OTHER} onChange={() => setPicked(OTHER)} />
            <span className="font-medium">Type an address</span>
          </label>
          {choice === OTHER && (
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-1">
                <Label htmlFor="hr-manual-email">HR email</Label>
                <Input id="hr-manual-email" type="email" placeholder="hr@company.com" value={manual.email} onChange={(e) => setManual({ ...manual, email: e.target.value })} />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="hr-manual-name">Their name (optional)</Label>
                <Input id="hr-manual-name" placeholder="Asha Rao" value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })} />
              </div>
            </div>
          )}
          {choice === OTHER && toEmail !== '' && !validEmail && <p className="text-xs text-destructive">That does not look like an email address.</p>}
          {selected?.source === 'guess' && <p className="text-xs text-amber-700 dark:text-amber-400">This is a common address, not a confirmed one. It may bounce or go unread.</p>}
          <div>
            <Button type="button" variant="ghost" size="sm" disabled={finding || find.isPending} onClick={() => find.mutate()}>
              <Search /> Search again
            </Button>
          </div>
        </fieldset>

        {d.other_jobs.length > 0 && (
          <fieldset className="grid gap-1.5">
            <legend className="mb-1 font-medium">Also mention other open roles at {d.company}</legend>
            {d.other_jobs.map((j) => (
              <span key={j.lead_id} className="flex items-center gap-2">
                <Checkbox id={`hr-extra-${j.lead_id}`} checked={extra.includes(j.lead_id)} onCheckedChange={(v) => setExtra(v === true ? [...extra, j.lead_id] : extra.filter((x) => x !== j.lead_id))} />
                <Label htmlFor={`hr-extra-${j.lead_id}`} className="font-normal">
                  {j.title}
                  {j.score != null ? ` · score ${j.score.toFixed(1)}` : ''}
                </Label>
              </span>
            ))}
          </fieldset>
        )}

        <div className="grid gap-2 rounded-lg border bg-muted/40 p-3" aria-label="Email preview">
          <div className="flex items-center justify-between gap-2">
            <p className="font-medium">The email</p>
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing((v) => !v)}>
              <Pencil /> {editing ? 'Done' : 'Edit'}
            </Button>
          </div>
          {editing ? (
            <>
              <Label htmlFor="hr-subject">Subject</Label>
              <Input id="hr-subject" value={subject} onChange={(e) => setEdit({ ...edit, subject: e.target.value })} />
              <Label htmlFor="hr-body">Message</Label>
              <Textarea id="hr-body" rows={12} className="font-mono text-[0.78rem] leading-relaxed" value={body} onChange={(e) => setEdit({ ...edit, body: e.target.value })} />
              {edit && (
                <button type="button" className="justify-self-start text-xs text-muted-foreground underline" onClick={() => setEdit(null)}>
                  Discard my edits and write it again
                </button>
              )}
            </>
          ) : (
            <>
              <p className="break-words">
                <span className="text-muted-foreground">Subject: </span>
                {subject}
              </p>
              <pre className="max-h-56 overflow-auto rounded-md bg-background p-2 text-xs leading-relaxed whitespace-pre-wrap">{body}</pre>
            </>
          )}
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor="hr-attach" className="flex items-center gap-1.5">
            <Paperclip className="size-3.5" aria-hidden /> Attachment
          </Label>
          <NativeSelect id="hr-attach" value={attachChoice} onChange={(e) => setAttach(e.target.value as Attach)}>
            {d.has_tailored_cv && <option value="tailored">Tailored CV for this job</option>}
            <option value="base">{st.resume.present ? `Resume (${st.resume.filename})` : 'Resume (upload one in Settings)'}</option>
            <option value="none">No attachment</option>
          </NativeSelect>
        </div>
        {missingResume && (
          <p className="text-xs text-destructive">
            No resume uploaded yet. Add your PDF in <Link className="underline" to="/settings?tab=account">Settings</Link>, or choose “No attachment”.
          </p>
        )}
        {!st.gmail_ready && (
          <p className="text-xs text-destructive">
            Gmail is not connected. <Link className="underline" to="/settings?tab=account">Connect it in Settings</Link> to send.
          </p>
        )}
        {repeat && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-800 dark:text-amber-300">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            <div className="grid gap-1.5">
              <span>You emailed {toEmail} less than {st.cooldown_days} days ago. A second email so soon rarely helps.</span>
              <span className="flex items-center gap-2">
                <Checkbox id="hr-force" checked={force} onCheckedChange={(v) => setForce(v === true)} />
                <Label htmlFor="hr-force" className="font-normal">
                  Send anyway
                </Label>
              </span>
            </div>
          </div>
        )}
        {capped && <p className="text-xs text-destructive">Daily limit reached ({st.daily_cap} emails). You can still save drafts.</p>}
        {send.isError && (
          <p role="alert" className="text-xs text-destructive">
            {send.error.message}
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={!ready || capped || (repeat && !force) || send.isPending} onClick={() => send.mutate(input('send'), { onSuccess: () => setForce(false) })}>
            {send.isPending ? <Loader2 className="animate-spin" /> : <Mail />} {validEmail ? `Send to ${toEmail}` : 'Send email'}
          </Button>
          <Button type="button" variant="outline" disabled={!ready || send.isPending} onClick={() => send.mutate(input('draft'))} title="Puts the email in your Gmail Drafts folder so you can read it there and press Send yourself">
            <Save /> Save as Gmail draft
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Goes out from your Gmail with {attachName} attached and cannot be unsent. {st.sent_today} of {st.daily_cap} sent today.
        </p>
      </CardContent>
    </Card>
  )
}
