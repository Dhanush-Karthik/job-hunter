import type { AppStatus } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

const TONE: Partial<Record<AppStatus, string>> = {
  Shortlisted: 'bg-sky-500/15 text-sky-700 dark:text-sky-400',
  Ready: 'bg-sky-500/15 text-sky-700 dark:text-sky-400',
  Applied: 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-400',
  Screening: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  Technical: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  Final: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  Offer: 'bg-emerald-500/25 text-emerald-800 dark:text-emerald-300',
  Accepted: 'bg-emerald-500/25 text-emerald-800 dark:text-emerald-300',
  Rejected: 'bg-destructive/10 text-destructive',
}

export function StatusBadge({ status, className }: { status: AppStatus; className?: string }) {
  return (
    <Badge variant="secondary" className={cn(TONE[status], className)}>
      {status}
    </Badge>
  )
}
