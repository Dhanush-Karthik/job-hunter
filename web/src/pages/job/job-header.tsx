import { ArrowLeft, ExternalLink, Mail, Search, ShieldCheck, ShieldX } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { LeadDetail } from '@/api/client'
import { fmtDateTime } from '@/components/format'
import { applyTarget } from '@/components/apply-target'
import { CHANNEL_LABEL, formatCtc, formatExp, formatPlace, statusLabel } from '@/components/lead-format'
import { relativeDay } from '@/components/time'
import { AboveRangeBadge, FreshBadge, InboundBadge, ScoreCell } from '@/components/lead-parts'
import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

function LiveBadge({ lead }: { lead: LeadDetail }) {
  const live = lead.evaluation?.is_live ?? lead.is_live
  const at = lead.evaluation?.live_verified_at
  if (live == null) return null
  return (
    <Badge
      variant="secondary"
      className={live ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400' : 'bg-destructive/10 text-destructive'}
      title={at ? `Verified ${fmtDateTime(at)}` : undefined}
    >
      {live ? <ShieldCheck aria-hidden /> : <ShieldX aria-hidden />} {live ? 'Posting is live' : 'Posting closed'}
    </Badge>
  )
}

/** Where this job came from and where to go to apply, so no lead is ever a dead end. */
function WhereToApply({ lead }: { lead: LeadDetail }) {
  const t = applyTarget(lead)
  const Icon = lead.source_email_url && t.href === lead.source_email_url ? Mail : ExternalLink
  return (
    <section aria-label="Where to apply" className="grid gap-2 rounded-xl border bg-card px-4 py-3 text-sm">
      <p>
        <span className="text-muted-foreground">Source:</span> <span className="font-medium">{t.source}</span>
        <span className="text-muted-foreground"> · found {relativeDay(lead.found_at)}</span>
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {t.href && (
          <Button asChild size="sm">
            <a href={t.href} target="_blank" rel="noopener noreferrer">
              <Icon /> {t.label}
            </a>
          </Button>
        )}
        {lead.apply_url && lead.canonical_url && lead.canonical_url !== lead.apply_url && (
          <Button asChild variant="outline" size="sm">
            <a href={lead.canonical_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink /> View original posting
            </a>
          </Button>
        )}
        {!lead.apply_url && !lead.canonical_url && (
          <Button asChild variant="outline" size="sm">
            <a href={t.searchHref} target="_blank" rel="noopener noreferrer">
              <Search /> Search for it
            </a>
          </Button>
        )}
      </div>
      {t.note && <p className="text-muted-foreground">{t.note}</p>}
    </section>
  )
}

export function JobHeader({ lead }: { lead: LeadDetail }) {
  const navigate = useNavigate()
  const place = formatPlace(lead)
  const facts = [place === '—' ? null : place, formatExp(lead), formatCtc(lead) ?? 'Salary not stated', `found ${relativeDay(lead.posted_at ?? lead.found_at)}`].filter(Boolean).join(' · ')
  // Back to wherever the owner came from (Jobs, Applications, Inbox...); a direct link falls back to Jobs.
  const back = () => (window.history.state?.idx > 0 ? navigate(-1) : navigate('/leads'))
  return (
    <header className="mb-6 grid gap-3">
      <Button variant="ghost" size="sm" className="-ml-2 w-fit" onClick={back}>
        <ArrowLeft /> Back
      </Button>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground">{lead.company}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{lead.title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{facts}</p>
        </div>
        <ScoreCell lead={lead} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={lead.status} label={statusLabel(lead.status)} />
        {lead.is_fresh && <FreshBadge />}
        {lead.is_inbound && <InboundBadge />}
        {lead.exp_fit === 'above' && <AboveRangeBadge />}
        <LiveBadge lead={lead} />
        {lead.apply_channel !== 'unknown' && !lead.is_inbound && <Badge variant="outline">{CHANNEL_LABEL[lead.apply_channel]}</Badge>}
        {lead.duplicate_ids.length > 0 && (
          <Badge variant="outline" title="The same job was found on other sites and merged into this one">
            also on {lead.duplicate_ids.length} other site{lead.duplicate_ids.length === 1 ? '' : 's'}
          </Badge>
        )}
      </div>
      <WhereToApply lead={lead} />
    </header>
  )
}
