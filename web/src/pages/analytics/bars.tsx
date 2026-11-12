import { cn } from '@/lib/utils'

/** CSS bar scaled to `max`. Decorative: the number is always printed next to it. */
export function Bar({ value, max, className }: { value: number; max: number; className?: string }) {
  const pct = max > 0 ? Math.max(value > 0 ? 2 : 0, Math.min(100, (value / max) * 100)) : 0
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-muted" aria-hidden>
      <div className={cn('h-full rounded-full bg-primary', className)} style={{ width: `${pct}%` }} />
    </div>
  )
}
