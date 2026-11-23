import { CheckCheck, ChevronRight, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { LeadSummary } from '@/api/client'
import { useLeadActions } from '@/app/lead-actions'
import { CHANNEL_LABEL, SOURCE_LABEL, leadFacts } from '@/components/lead-format'
import { ScoreCell } from '@/components/lead-parts'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

/** What the owner does next for a shortlisted job. */
function nextStep(l: LeadSummary): { label: string; tone: string } {
  if (l.status === 'Ready') return { label: 'CV approved: apply now', tone: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400' }
  return { label: 'Needs a tailored CV', tone: 'bg-amber-500/15 text-amber-700 dark:text-amber-400' }
}

/**
 * Shortlisted and CV-approved jobs, best first. Each row says the next step; the job page holds the CV tools.
 * "Mark applied" only records what the owner did on the site: nothing here submits an application.
 */
export function ApplyQueue({ leads }: { leads: LeadSummary[] }) {
  const { markApplied, busy } = useLeadActions()
  return (
    <ul className="divide-y rounded-xl border" aria-label="Jobs to apply to">
      {leads.map((l) => {
        const step = nextStep(l)
        const link = l.apply_url ?? l.canonical_url
        const facts = leadFacts(l)
        return (
          <li key={l.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-3">
            <ScoreCell lead={l} />
            <div className="min-w-0 flex-1 basis-56">
              <Link to={`/jobs/${l.id}`} className="block truncate text-sm font-medium hover:underline">
                {l.company} <span className="font-normal text-muted-foreground">· {l.title}</span>
              </Link>
              <div className="truncate text-xs text-muted-foreground">
                {[facts, SOURCE_LABEL[l.source], l.apply_channel !== 'unknown' ? CHANNEL_LABEL[l.apply_channel] : null].filter(Boolean).join(' · ')}
              </div>
            </div>
            <Badge variant="secondary" className={step.tone}>
              {step.label}
            </Badge>
            <div className="flex flex-wrap gap-1.5">
              {l.status === 'Shortlisted' ? (
                <Button asChild size="sm">
                  <Link to={`/jobs/${l.id}`} aria-label={`Prepare CV for ${l.company}`}>
                    Prepare CV <ChevronRight />
                  </Link>
                </Button>
              ) : (
                link && (
                  <Button asChild size="sm">
                    <a href={link} target="_blank" rel="noopener noreferrer" aria-label={`Open apply link for ${l.company}`}>
                      <ExternalLink /> Apply on site
                    </a>
                  </Button>
                )
              )}
              <Button
                size="sm"
                variant="outline"
                disabled={busy || l.application_id == null}
                aria-label={`Mark applied for ${l.company}`}
                title="Press after you have submitted the application yourself"
                onClick={() => l.application_id != null && markApplied.mutate(l.application_id)}
              >
                <CheckCheck /> Mark applied
              </Button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
