import { useState } from 'react'
import { Check, CheckCheck, ExternalLink, FlaskConical, RotateCcw, ShieldCheck, X } from 'lucide-react'
import { TRANSITIONS, type LeadDetail, type RunOut } from '@/api/client'
import { useLeadActions } from '@/app/lead-actions'
import { isRejected } from '@/components/lead-format'
import { SkipDialog } from '@/components/skip-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { isActive, type useJobMutations } from './use-job'

type Props = { lead: LeadDetail; runs: RunOut[]; mutations: ReturnType<typeof useJobMutations> }

/**
 * Lead-level actions. There is deliberately no button that submits an application or sends a message:
 * Assist apply pre-fills a form for review and the owner presses Submit; "Mark applied" only records what they did.
 */
export function ActionsCard({ lead, runs, mutations: m }: Props) {
  const actions = useLeadActions()
  const [skipOpen, setSkipOpen] = useState(false)
  const app = lead.application
  const can = (to: (typeof TRANSITIONS)[typeof lead.status][number]) => TRANSITIONS[lead.status].includes(to)
  const running = (kind: RunOut['kind']) => runs.some((r) => r.kind === kind && isActive(r))
  const canMarkApplied = !!app && (lead.status === 'Shortlisted' || lead.status === 'Ready')
  const assistReady = !!app?.cv_approved && lead.status !== 'Applied'

  return (
    <Card>
      <CardHeader>
        <CardTitle>Actions</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="flex flex-wrap gap-2">
          {isRejected(lead) && (
            <Button size="sm" variant="outline" disabled={actions.busy} onClick={() => actions.restore.mutate(lead.id)}>
              <RotateCcw /> Restore
            </Button>
          )}
          {can('Shortlisted') && (
            <Button size="sm" disabled={actions.busy} onClick={() => actions.shortlist.mutate(lead.id)}>
              <Check /> Shortlist
            </Button>
          )}
          {can('Skipped') && (
            <Button size="sm" variant="outline" disabled={actions.busy} onClick={() => setSkipOpen(true)}>
              <X /> Skip
            </Button>
          )}
          <Button size="sm" variant="outline" disabled={actions.busy || running('evaluate')} onClick={() => actions.evaluate.mutate(lead.id)}>
            <FlaskConical /> {lead.evaluation ? 'Re-evaluate' : 'Evaluate'}
          </Button>
          <Button size="sm" variant="outline" disabled={m.verify.isPending || running('verify')} onClick={() => m.verify.mutate()}>
            <ShieldCheck /> Verify
          </Button>
        </div>

        <div className="grid gap-1.5">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" disabled={!assistReady || m.assist.isPending || running('assist_apply')} onClick={() => m.assist.mutate()}>
              <ExternalLink /> Assist apply
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Opens a pre-filled form in a browser window; you review and press Submit yourself.
            {!assistReady && ' Approve a CV first.'}
          </p>
        </div>

        <div className="grid gap-1.5">
          <div>
            <Button size="sm" disabled={!canMarkApplied || actions.busy} onClick={() => app && actions.markApplied.mutate(app.id)}>
              <CheckCheck /> Mark applied
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">Press this after you have submitted the application yourself. It only records it.</p>
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
