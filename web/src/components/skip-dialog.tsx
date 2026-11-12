import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  subject: string
  pending?: boolean
  onConfirm: (reason: string) => void
}

// The form lives inside DialogContent, which unmounts when closed, so the reason resets by itself.
function SkipForm({ subject, pending, onCancel, onConfirm }: Pick<Props, 'subject' | 'pending' | 'onConfirm'> & { onCancel: () => void }) {
  const [reason, setReason] = useState('')
  const valid = reason.trim().length > 0
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) onConfirm(reason.trim())
      }}
    >
      <DialogHeader>
        <DialogTitle>Skip {subject}</DialogTitle>
        <DialogDescription>Say why. It shows up in the reject audit so you can restore it later.</DialogDescription>
      </DialogHeader>
      <div className="grid gap-1.5">
        <Label htmlFor="skip-reason">Reason</Label>
        <Textarea id="skip-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. onsite only, stack mismatch" required />
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={!valid || pending}>
          Skip
        </Button>
      </DialogFooter>
    </form>
  )
}

/** Skip needs a reason (the API requires it and the reject audit uses it). */
export function SkipDialog({ open, onOpenChange, subject, pending, onConfirm }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <SkipForm subject={subject} pending={pending} onCancel={() => onOpenChange(false)} onConfirm={onConfirm} />
      </DialogContent>
    </Dialog>
  )
}
