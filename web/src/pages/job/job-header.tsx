import { ArrowLeft, ExternalLink, ShieldCheck, ShieldX } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { LeadDetail } from '@/api/client'
import { fmtDateTime } from '@/components/format'
import { CHANNEL_LABEL, formatCtc, formatExp, formatPlace, SOURCE_LABEL } from '@/components/lead-format'
import { FreshBadge, InboundBadge, ScoreCell } from '@/components/lead-parts'
import { StatusBadge } from '@/components/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

function LiveBadge({ lead }: { lead: LeadDetail }) {
  const live = lead.evaluation?.is_live ?? lead.is_live
  const at = lead.evaluation?.live_verified_at
  if (live == null) return <Badge variant="outline">Live status unknown</Badge>
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

export function JobHeader({ lead }: { lead: LeadDetail }) {
  const facts = [formatPlace(lead), formatExp(lead), formatCtc(lead) ?? 'CTC unknown'].filter(Boolean).join(' · ')
  return (
    <header className="mb-6 grid gap-3">
      <Button asChild variant="ghost" size="sm" className="-ml-2 w-fit">
        <Link to="/leads">
          <ArrowLeft /> Leads
        </Link>
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
        <StatusBadge status={lead.status} />
        {lead.is_fresh && <FreshBadge />}
        {lead.is_inbound && <InboundBadge />}
        <LiveBadge lead={lead} />
        <Badge variant="outline">{CHANNEL_LABEL[lead.apply_channel]}</Badge>
        <Badge variant="outline">{SOURCE_LABEL[lead.source]}</Badge>
        {lead.duplicate_ids.length > 0 && <Badge variant="outline">{lead.duplicate_ids.length} duplicates merged</Badge>}
      </div>
      <div className="flex flex-wrap gap-2">
        {lead.canonical_url && (
          <Button asChild variant="outline" size="sm">
            <a href={lead.canonical_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink /> Open posting
            </a>
          </Button>
        )}
        {lead.apply_url && (
          <Button asChild variant="outline" size="sm">
            <a href={lead.apply_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink /> Apply link
            </a>
          </Button>
        )}
      </div>
    </header>
  )
}
