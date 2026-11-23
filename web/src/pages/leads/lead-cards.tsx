import { Link, useNavigate } from 'react-router-dom'
import type { LeadSummary } from '@/api/client'
import { CHANNEL_LABEL, SOURCE_LABEL, formatCtc, formatExp, formatPlace, isRejected, statusLabel } from '@/components/lead-format'
import { StatusBadge } from '@/components/status-badge'
import { FreshBadge, InboundBadge, ScoreCell } from '@/components/lead-parts'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { RowActionButtons, type RowActions } from './row-actions'

export type CardItem = { lead: LeadSummary; selected: boolean; onSelect: (v: boolean) => void }

const stop = (e: React.SyntheticEvent) => e.stopPropagation()

/** Phone layout (< md): one card per lead instead of a wide table. */
export function LeadCards({
  items,
  allSelected,
  onToggleAll,
  actions,
  showStatus = true,
}: {
  showStatus?: boolean
  items: CardItem[]
  allSelected: boolean | 'indeterminate'
  onToggleAll: (v: boolean) => void
  actions: RowActions
}) {
  const navigate = useNavigate()
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <Checkbox id="select-all-cards" aria-label="Select all leads on this page" checked={allSelected} onCheckedChange={(v) => onToggleAll(v === true)} />
        <Label htmlFor="select-all-cards" className="text-sm font-normal text-muted-foreground">
          Select all on this page
        </Label>
      </div>
      <ul className="grid gap-2">
        {items.map(({ lead: l, selected, onSelect }) => (
          <li
            key={l.id}
            data-state={selected ? 'selected' : undefined}
            data-rejected={isRejected(l) || undefined}
            className={cn('cursor-pointer rounded-lg border p-3', selected && 'bg-muted/60', isRejected(l) && 'opacity-60')}
            onClick={() => navigate(`/jobs/${l.id}`)}
          >
            <div className="flex items-start gap-3">
              <span onClick={stop} className="pt-0.5">
                <Checkbox aria-label={`Select ${l.company} ${l.title}`} checked={selected} onCheckedChange={(v) => onSelect(v === true)} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <ScoreCell lead={l} />
                  {l.is_fresh && <FreshBadge />}
                  {l.is_inbound && <InboundBadge />}
                </div>
                <div className="mt-1 font-medium">{l.company}</div>
                <Link to={`/jobs/${l.id}`} onClick={stop} className="block text-sm hover:underline">
                  {l.title}
                </Link>
                <div className="mt-1 text-xs text-muted-foreground">
                  {[formatPlace(l), formatExp(l)].filter((x) => x && x !== '—').join(' · ')}
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1">
                  {formatCtc(l) && <Badge variant="outline">{formatCtc(l)}</Badge>}
                  <Badge variant="outline">{SOURCE_LABEL[l.source]}</Badge>
                  {l.apply_channel !== 'unknown' && <Badge variant="outline">{CHANNEL_LABEL[l.apply_channel]}</Badge>}
                  {showStatus && <StatusBadge status={l.status} label={statusLabel(l.status)} />}
                  {l.restored && <Badge variant="secondary">Restored</Badge>}
                </div>
                {isRejected(l) && l.prefilter_reasons.length > 0 && (
                  <div className="mt-1 text-xs text-destructive/80">Auto-filtered: {l.prefilter_reasons.join('; ')}</div>
                )}
              </div>
              <div onClick={stop}>
                <RowActionButtons lead={l} actions={actions} />
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
