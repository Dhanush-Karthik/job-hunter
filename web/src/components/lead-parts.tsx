import { Mail, Sparkles } from 'lucide-react'
import type { LeadSummary } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { quickScorePct } from './lead-format'

const GRADE_TONE: Record<string, string> = {
  A: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  B: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  C: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
}
const GRADE_BAD = 'bg-destructive/10 text-destructive'

export function ScoreCell({ lead }: { lead: Pick<LeadSummary, 'quick_score' | 'eval_score' | 'eval_grade'> }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="min-w-8 font-semibold tabular-nums" aria-label={`Quick score ${quickScorePct(lead)}`}>
        {quickScorePct(lead)}
      </span>
      {lead.eval_grade && (
        <Badge variant="secondary" className={cn('tabular-nums', GRADE_TONE[lead.eval_grade] ?? GRADE_BAD)} title="Evaluation grade and score">
          {lead.eval_score != null ? `${lead.eval_grade} ${lead.eval_score.toFixed(1)}` : lead.eval_grade}
        </Badge>
      )}
    </div>
  )
}

export function FreshBadge() {
  return (
    <Badge className="bg-sky-500/15 text-sky-700 dark:text-sky-400" variant="secondary">
      <Sparkles aria-hidden /> Fresh
    </Badge>
  )
}

export function InboundBadge() {
  return (
    <Badge className="bg-violet-500/15 text-violet-700 dark:text-violet-400" variant="secondary">
      <Mail aria-hidden /> Inbound
    </Badge>
  )
}
