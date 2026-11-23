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

/** Colour of a 0-100 match score: strong, fair, weak. */
const matchTone = (pct: number) =>
  pct >= 75 ? 'text-emerald-700 dark:text-emerald-400' : pct >= 60 ? 'text-foreground' : 'text-muted-foreground'

/** Score 0-5 from the AI evaluation; null grade falls back to the score alone. */
function evalTone(score: number | null | undefined, grade: string | null | undefined) {
  if (grade) return GRADE_TONE[grade] ?? GRADE_BAD
  if (score == null) return ''
  return score >= 4 ? GRADE_TONE.A : score >= 3.5 ? GRADE_TONE.B : score >= 3 ? GRADE_TONE.C : GRADE_BAD
}

export function EvalBadge({ lead, className }: { lead: Pick<LeadSummary, 'eval_score' | 'eval_grade'>; className?: string }) {
  if (lead.eval_score == null && !lead.eval_grade) return null
  const text = [lead.eval_grade, lead.eval_score != null ? `${lead.eval_score.toFixed(1)}/5` : null].filter(Boolean).join(' ')
  return (
    <Badge variant="secondary" className={cn('tabular-nums', evalTone(lead.eval_score, lead.eval_grade), className)} title="AI evaluation: how well your CV fits this job (out of 5)">
      {text}
    </Badge>
  )
}

/** Match score (keyword fit, freshness, source; 0-100) and, when evaluated, the AI fit score. */
export function ScoreCell({ lead }: { lead: Pick<LeadSummary, 'quick_score' | 'eval_score' | 'eval_grade'> }) {
  const pct = quickScorePct(lead)
  return (
    <div className="flex items-center gap-1.5">
      <span
        className={cn('min-w-7 font-semibold tabular-nums', matchTone(pct))}
        aria-label={`Match score ${pct}`}
        title="Match score (0-100): keyword fit with your CV, freshness and source"
      >
        {pct}
      </span>
      <EvalBadge lead={lead} />
    </div>
  )
}

export function FreshBadge() {
  return (
    <Badge className="bg-sky-500/15 text-sky-700 dark:text-sky-400" variant="secondary" title="Posted in the last 48 hours: early applicants get more views">
      <Sparkles aria-hidden /> Fresh
    </Badge>
  )
}

export function InboundBadge() {
  return (
    <Badge className="bg-violet-500/15 text-violet-700 dark:text-violet-400" variant="secondary" title="A recruiter contacted you about this">
      <Mail aria-hidden /> Recruiter
    </Badge>
  )
}
