import { useState } from 'react'
import { Check, CheckCheck, Circle, CircleCheck, ExternalLink, FlaskConical, Loader2, RotateCcw, ShieldCheck, Wand2, X } from 'lucide-react'
import { CLOSED, TRANSITIONS, type AppStatus, type LeadDetail, type RunOut } from '@/api/client'
import { useLeadActions } from '@/app/lead-actions'
import { applyTarget } from '@/components/apply-target'
import { isRejected } from '@/components/lead-format'
import { NativeSelect } from '@/components/native-select'
import { SkipDialog } from '@/components/skip-dialog'
import { relativeDay } from '@/components/time'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { useMoveApplication } from '@/pages/tracker/use-tracker'
import { RUN_LABEL, isActive, type useJobMutations } from './use-job'

type Props = { lead: LeadDetail; runs: RunOut[]; mutations: ReturnType<typeof useJobMutations> }

function Step({ n, done, title, children }: { n: number; done: boolean; title: string; children?: React.ReactNode }) {
  return (
    <li className="grid grid-cols-[1.25rem_1fr] gap-x-2 gap-y-1.5">
      {done ? <CircleCheck className="mt-0.5 size-5 text-emerald-600" aria-hidden /> : <Circle className="mt-0.5 size-5 text-muted-foreground" aria-hidden />}
      <div className={cn('text-sm font-medium', done && 'text-muted-foreground line-through decoration-muted-foreground/40')}>
        <span className="sr-only">Step {n}{done ? ' (done)' : ''}: </span>
        {title}
      </div>
      {children && <div className="col-start-2 grid gap-1.5">{children}</div>}
    </li>
  )
}

/**
 * The one card that says what to do next with this job, based on where it stands.
 * There is deliberately no button that submits an application or sends a message:
 * Assist apply pre-fills a form for review and the owner presses Submit; "Mark applied" only records what they did.
 */
export function ActionsCard({ lead, runs, mutations: m }: Props) {
  const actions = useLeadActions()
  const move = useMoveApplication()
  const [skipOpen, setSkipOpen] = useState(false)
  const [to, setTo] = useState<AppStatus | ''>('')
  const app = lead.application
  const status = lead.status
  const can = (s: AppStatus) => TRANSITIONS[status].includes(s)
  const running = (kind: RunOut['kind']) => runs.some((r) => r.kind === kind && isActive(r))
  const active = runs.filter(isActive)
  const target = applyTarget(lead)
  const preApply = status === 'Shortlisted' || status === 'Ready'
  const afterApply = !preApply && status !== 'New' && !CLOSED.includes(status)

  let title = 'Next step'
  let hint: string | null = null
  if (isRejected(lead)) {
    title = 'Filtered out automatically'
    hint = `Hidden by your search rules: ${lead.prefilter_reasons.join('; ')}. Restore it if the rule got it wrong.`
  } else if (status === 'New') {
    title = 'Worth applying?'
    hint = 'Shortlist it to prepare a CV and apply, or skip it.'
  } else if (preApply) {
    title = 'Apply in 4 steps'
  } else if (afterApply) {
    title = 'Waiting on the company'
    hint = app?.applied_at ? `Applied ${relativeDay(app.applied_at)}. Update the status when you hear back.` : 'Update the status when you hear back.'
  } else {
    title = `Closed: ${status}`
    hint = app?.rejected_at_stage ? `Rejected at the ${app.rejected_at_stage} stage.` : null
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {hint && <CardDescription>{hint}</CardDescription>}
      </CardHeader>
      <CardContent className="grid gap-4">
        {active.length > 0 && (
          <p role="status" className="flex items-center gap-2 rounded-lg bg-sky-500/10 px-2.5 py-1.5 text-xs text-sky-700 dark:text-sky-400">
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
            {active.map((r) => RUN_LABEL[r.kind]).join(', ')} running…
          </p>
        )}

        {isRejected(lead) && (
          <div>
            <Button size="sm" disabled={actions.busy} onClick={() => actions.restore.mutate(lead.id)}>
              <RotateCcw /> Restore
            </Button>
          </div>
        )}

        {!isRejected(lead) && status === 'New' && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={actions.busy} onClick={() => actions.shortlist.mutate(lead.id)}>
              <Check /> Shortlist
            </Button>
            <Button size="sm" variant="outline" disabled={actions.busy} onClick={() => setSkipOpen(true)}>
              <X /> Skip
            </Button>
          </div>
        )}

        {preApply && (
          <ol className="grid gap-3" aria-label="Steps to apply">
            <Step n={1} done={!!app?.has_cv_pdf} title="Generate a tailored CV">
              <p className="text-xs text-muted-foreground">Use the Tailored CV card below (about a minute).</p>
            </Step>
            <Step n={2} done={!!app?.cv_approved} title="Check and approve the CV" />
            <Step n={3} done={false} title={`Apply via ${target.source}`}>
              <div className="flex flex-wrap gap-2">
                <Button asChild size="sm" variant="outline">
                  <a href={target.href ?? target.searchHref} target="_blank" rel="noopener noreferrer">
                    <ExternalLink /> {target.label}
                  </a>
                </Button>
                <Button size="sm" variant="secondary" disabled={!app?.cv_approved || m.assist.isPending || running('assist_apply')} onClick={() => m.assist.mutate()}>
                  <Wand2 /> Assist apply
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Assist apply opens a pre-filled form in a browser window; you review and press Submit yourself.
                {!app?.cv_approved && ' Approve a CV first.'}
              </p>
            </Step>
            <Step n={4} done={false} title="Record it">
              <div>
                <Button size="sm" disabled={!app || actions.busy} onClick={() => app && actions.markApplied.mutate(app.id)}>
                  <CheckCheck /> Mark applied
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">Press after you have submitted. It only records it and schedules a follow-up.</p>
            </Step>
          </ol>
        )}

        {afterApply && app && (
          <div className="flex flex-wrap items-center gap-2">
            <div className="w-48">
              <NativeSelect aria-label="New status" value={to} onChange={(e) => setTo(e.target.value as AppStatus)}>
                <option value="">Change status to…</option>
                {TRANSITIONS[status].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <Button
              size="sm"
              disabled={!to || move.isPending}
              onClick={() => to && move.mutate({ app, to, rejected_at_stage: to === 'Rejected' ? status : undefined }, { onSuccess: () => setTo('') })}
            >
              Save
            </Button>
          </div>
        )}

        <div className="flex flex-wrap gap-2 border-t pt-3">
          <Button size="sm" variant="ghost" disabled={actions.busy || running('evaluate')} onClick={() => actions.evaluate.mutate(lead.id)} title="AI reads the job against your CV and writes the report (about 3 minutes)">
            <FlaskConical /> {lead.evaluation ? 'Re-evaluate' : 'Evaluate with AI'}
          </Button>
          <Button size="sm" variant="ghost" disabled={m.verify.isPending || running('verify')} onClick={() => m.verify.mutate()} title="Opens the posting to check it is still accepting applications">
            <ShieldCheck /> Verify still open
          </Button>
          {can('Skipped') && status !== 'New' && (
            <Button size="sm" variant="ghost" disabled={actions.busy} onClick={() => setSkipOpen(true)}>
              <X /> Skip
            </Button>
          )}
        </div>
      </CardContent>
      <SkipDialog
        open={skipOpen}
        onOpenChange={setSkipOpen}
        subject={`${lead.company} · ${lead.title}`}
        pending={actions.skip.isPending}
        onConfirm={(reason) => actions.skip.mutate({ id: lead.id, reason }, { onSuccess: () => setSkipOpen(false) })}
      />
    </Card>
  )
}
