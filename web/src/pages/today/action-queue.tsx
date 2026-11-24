import { CheckCircle2, ChevronRight, ExternalLink, FileCheck2, Inbox, MailQuestion, RefreshCw, Sparkles, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ActionItem } from '@/api/client'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { usePatchProfile } from '@/pages/settings/use-settings'

type Kind = ActionItem['kind']

type Task = {
  key: string
  Icon: LucideIcon
  title: string
  detail?: string
  urgent?: boolean
  href?: string
  cta?: string
  extra?: React.ReactNode
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
/** "Infosys, HCLTech and 3 more" */
function names(items: ActionItem[]): string {
  const uniq = [...new Set(items.map((a) => a.title.replace(/^(Follow up: |Referral draft: |Approve CV for )/, '').split(' — ')[0]))]
  if (uniq.length <= 2) return uniq.join(' and ')
  return `${uniq.slice(0, 2).join(', ')} and ${uniq.length - 2} more`
}
const platformName = (p: string | null | undefined) => (p ? p.charAt(0).toUpperCase() + p.slice(1) : 'profile')

function ProfileButtons({ item }: { item: ActionItem }) {
  const patch = usePatchProfile()
  const url = item.subtitle?.startsWith('http') ? item.subtitle : null
  return (
    <div className="flex flex-wrap gap-1.5">
      {url && (
        <Button asChild size="sm" variant="outline">
          <a href={url} target="_blank" rel="noopener noreferrer">
            <ExternalLink /> Open {platformName(item.platform)}
          </a>
        </Button>
      )}
      {item.platform && (
        <Button size="sm" variant="ghost" disabled={patch.isPending} onClick={() => patch.mutate({ platform: item.platform!, refreshed_now: true })}>
          Mark done
        </Button>
      )}
    </div>
  )
}

/** One row per kind of work, in the order it should be done. The raw items stay on the page that handles them. */
function buildTasks(actions: ActionItem[], toApply: number): Task[] {
  const of = (k: Kind) => actions.filter((a) => a.kind === k)
  const tasks: Task[] = []

  const inbound = of('inbound')
  if (inbound.length)
    tasks.push({ key: 'inbound', Icon: Sparkles, urgent: true, title: `${plural(inbound.length, 'recruiter')} reached out`, detail: names(inbound), href: '/replies', cta: 'Review' })

  const proposals = of('proposal')
  if (proposals.length)
    tasks.push({
      key: 'proposal',
      Icon: MailQuestion,
      title: `${plural(proposals.length, 'email update')} to confirm`,
      detail: 'Rejections, replies and mail the app could not place on its own',
      href: '/replies',
      cta: 'Confirm',
    })

  const cvs = of('cv_review')
  if (cvs.length) {
    const one = cvs.length === 1 && cvs[0].lead_id != null
    tasks.push({ key: 'cv', Icon: FileCheck2, title: `${plural(cvs.length, 'CV')} to approve`, detail: names(cvs), href: one ? `/jobs/${cvs[0].lead_id}` : '/leads?tab=apply', cta: 'Approve' })
  }

  if (toApply > 0)
    tasks.push({
      key: 'apply',
      Icon: CheckCircle2,
      title: `${plural(toApply, 'shortlisted job')} to apply to`,
      detail: 'Tailor the CV, apply on the site, then mark it applied',
      href: '/leads?tab=apply',
      cta: 'Apply',
    })

  for (const p of of('profile_refresh'))
    tasks.push({
      key: `profile-${p.platform}`,
      Icon: RefreshCw,
      title: `Refresh your ${platformName(p.platform)} profile`,
      detail: 'Recruiters see recently updated profiles first. About 2 minutes.',
      extra: <ProfileButtons item={p} />,
    })

  return tasks
}

/** `toApply` counts Shortlisted + Ready jobs on every channel (the server's quick_apply item only counts platform 1-click ones). */
export function ActionQueue({ actions, toApply = 0 }: { actions: ActionItem[]; toApply?: number }) {
  const tasks = buildTasks(actions, toApply)
  if (!tasks.length)
    return (
      <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed p-8 text-center">
        <Inbox className="size-6 text-muted-foreground" aria-hidden />
        <p className="font-medium">All caught up</p>
        <p className="text-sm text-muted-foreground">Nothing needs you right now. Review new matches when you have time.</p>
      </div>
    )
  return (
    <ul className="divide-y rounded-xl border" aria-label="To do">
      {tasks.map((t) => (
        <li key={t.key} className="flex flex-wrap items-center gap-3 px-3 py-3">
          <span className={cn('grid size-8 shrink-0 place-items-center rounded-lg', t.urgent ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground')}>
            <t.Icon className="size-4" aria-hidden />
          </span>
          <div className="min-w-0 flex-1 basis-40">
            <div className="text-sm font-medium">{t.title}</div>
            {t.detail && <div className="line-clamp-2 text-xs text-muted-foreground">{t.detail}</div>}
          </div>
          {t.extra}
          {t.href && (
            <Button asChild size="sm" variant={t.urgent ? 'default' : 'outline'}>
              <Link to={t.href} aria-label={`${t.cta}: ${t.title}`}>
                {t.cta} <ChevronRight />
              </Link>
            </Button>
          )}
        </li>
      ))}
    </ul>
  )
}
