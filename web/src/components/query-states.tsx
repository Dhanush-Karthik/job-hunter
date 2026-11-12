import { TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function ErrorState({ error, onRetry, title = 'Could not load' }: { error: unknown; onRetry?: () => void; title?: string }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">
      <div className="flex items-center gap-2 font-medium text-destructive">
        <TriangleAlert className="size-4" aria-hidden />
        {title}
      </div>
      <p className="text-muted-foreground">{error instanceof Error ? error.message : 'Unknown error'}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-dashed p-8 text-center">
      <p className="font-medium">{title}</p>
      {hint && <p className="mt-1 text-sm text-muted-foreground">{hint}</p>}
    </div>
  )
}
