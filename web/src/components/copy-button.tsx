import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'

/** Copies text to the clipboard. Drafts are copy-only: nothing in the app sends a message. */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false)
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      aria-label={label}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setDone(true)
          setTimeout(() => setDone(false), 1500)
          toast.success('Copied to clipboard')
        } catch {
          toast.error('Could not copy; select the text and copy it by hand')
        }
      }}
    >
      {done ? <Check /> : <Copy />} {done ? 'Copied' : 'Copy'}
    </Button>
  )
}
