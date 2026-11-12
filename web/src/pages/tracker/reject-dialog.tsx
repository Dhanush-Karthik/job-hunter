import { useState } from 'react'
import type { ApplicationOut, AppStatus } from '@/api/client'
import { NativeSelect } from '@/components/native-select'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { REJECT_STAGES } from './transitions'

function RejectForm({ app, pending, onCancel, onConfirm }: { app: ApplicationOut; pending?: boolean; onCancel: () => void; onConfirm: (stage: AppStatus) => void }) {
  const [stage, setStage] = useState<AppStatus | ''>('')
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (stage) onConfirm(stage)
      }}
    >
      <DialogHeader>
        <DialogTitle>Rejected: {app.company}</DialogTitle>
        <DialogDescription>At which stage were you rejected? It feeds the reject audit and the funnel.</DialogDescription>
      </DialogHeader>
      <div className="grid gap-1.5">
        <Label htmlFor="reject-stage">Rejected at stage</Label>
        <NativeSelect id="reject-stage" value={stage} onChange={(e) => setStage(e.target.value as AppStatus | '')} required>
          <option value="">Select a stage…</option>
          {REJECT_STAGES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </NativeSelect>
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={!stage || pending}>
          Mark rejected
        </Button>
      </DialogFooter>
    </form>
  )
}

/** Rejected needs rejected_at_stage (server rule). Closing the dialog leaves the card where it was. */
export function RejectDialog({ app, pending, onClose, onConfirm }: { app: ApplicationOut | null; pending?: boolean; onClose: () => void; onConfirm: (stage: AppStatus) => void }) {
  return (
    <Dialog open={app !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>{app && <RejectForm app={app} pending={pending} onCancel={onClose} onConfirm={onConfirm} />}</DialogContent>
    </Dialog>
  )
}
